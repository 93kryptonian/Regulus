from copy import deepcopy
from datetime import datetime
from typing import Any, Protocol

from regulus.review import InMemoryReviewStore, ReviewTask, StoreError

from .ledger import make_record, submission_state, tamper_free, tip
from .models import Kind, Phase, PreparedSubmission, Principal, SubmissionState, WorkflowRecord

STEPS = ("intent", "task", "obligation", "record")


class Crash(BaseException):
    pass


class ClockRegression(StoreError):
    pass


def obligation_stream(obligation_id: str) -> str:
    return f"obligation:{obligation_id}"


class WorkflowStore(Protocol):
    review: InMemoryReviewStore

    def ledger(self, stream: str) -> tuple[WorkflowRecord, ...]: ...

    def submission(self, obligation_id: str) -> SubmissionState: ...

    def registered(self, obligation_id: str) -> bool: ...

    def task(self, task_id: str) -> ReviewTask | None: ...

    def append(
        self,
        stream: str,
        kind: Kind,
        principal: Principal,
        at: datetime,
        key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> WorkflowRecord: ...

    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None: ...

    def complete_submission(
        self, obligation_id: str, principal: Principal, at: datetime
    ) -> None: ...


class _Base:
    def __init__(self) -> None:
        self.review = InMemoryReviewStore()
        self.streams: dict[str, tuple[WorkflowRecord, ...]] = {}
        self.tasks: dict[str, ReviewTask] = {}
        self.fail_after: str | None = None
        self.fail_store = 0

    def ledger(self, stream: str) -> tuple[WorkflowRecord, ...]:
        return self.streams.get(stream, ())

    def submission(self, obligation_id: str) -> SubmissionState:
        return submission_state(self.ledger(obligation_stream(obligation_id)))

    def registered(self, obligation_id: str) -> bool:
        try:
            self.review.get(obligation_id)
        except KeyError:
            return False
        return True

    def task(self, task_id: str) -> ReviewTask | None:
        return self.tasks.get(task_id)

    def _guard(self) -> None:
        if self.fail_store:
            self.fail_store -= 1
            raise StoreError("injected store failure")

    def _crash(self, step: str) -> None:
        if self.fail_after == step:
            self.fail_after = None
            raise Crash(step)

    def _check_clock(self, stream: str, kind: Kind, principal: Principal, at: datetime) -> None:
        recs = self.ledger(stream)
        if recs and at < recs[-1].at:
            self.streams[stream] = (
                *recs,
                make_record(
                    stream,
                    recs,
                    Kind.CLOCK_REGRESSION,
                    principal.id,
                    recs[-1].at,
                    details={"attempted": at.isoformat(), "kind": kind.value},
                ),
            )
            raise ClockRegression(stream)

    def _append(
        self,
        stream: str,
        kind: Kind,
        principal: Principal,
        at: datetime,
        key: str | None,
        details: dict[str, Any] | None,
    ) -> WorkflowRecord:
        self._check_clock(stream, kind, principal, at)
        recs = self.ledger(stream)
        rec = make_record(stream, recs, kind, principal.id, at, key, details)
        self.streams[stream] = (*recs, rec)
        return rec

    def append(
        self,
        stream: str,
        kind: Kind,
        principal: Principal,
        at: datetime,
        key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> WorkflowRecord:
        self._guard()
        return self._append(stream, kind, principal, at, key, details)

    def verify(self) -> bool:
        return tamper_free(self.streams)

    def violations(self) -> list[str]:
        out = []
        for oid in sorted(self.review._initial):
            if not any(t.obligation_id == oid for t in self.tasks.values()):
                out.append(f"{oid}: registered without a task")
        for stream in sorted(self.streams):
            if not stream.startswith("obligation:"):
                continue
            oid = stream.split(":", 1)[1]
            st = self.submission(oid)
            if st.phase is Phase.COMPLETE and (
                not self.registered(oid) or st.task_id not in self.tasks
            ):
                out.append(f"{oid}: complete submission without obligation or task")
        return out

    def _effects(self, p: PreparedSubmission) -> None:
        self.tasks.setdefault(p.task.id, p.task)
        self._crash("task")
        if not self.registered(p.obligation.id):
            self.review.register(p.obligation)
        self._crash("obligation")

    def _finish(self, p: PreparedSubmission, principal: Principal, at: datetime) -> None:
        stream = obligation_stream(p.obligation.id)
        recs = self.ledger(stream)
        if not any(r.kind is Kind.SUBMITTED and r.key == p.key for r in recs):
            self._append(
                stream,
                Kind.SUBMITTED,
                principal,
                max(at, recs[-1].at),
                p.key,
                {"task_id": p.task.id, "content_hash": p.content_hash},
            )
        self._crash("record")


class InMemoryWorkflowStore(_Base):
    def _state(self) -> Any:
        r = self.review
        return deepcopy((r._initial, r._state, r._log, self.tasks, self.streams))

    def _restore(self, saved: Any) -> None:
        r = self.review
        r._initial, r._state, r._log, self.tasks, self.streams = saved

    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None:
        self._guard()
        self._check_clock(
            obligation_stream(prepared.obligation.id), Kind.SUBMISSION_INTENT, principal, at
        )
        saved = self._state()
        try:
            self._append(
                obligation_stream(prepared.obligation.id),
                Kind.SUBMISSION_INTENT,
                principal,
                at,
                prepared.key,
                {"prepared": prepared.model_dump(mode="json")},
            )
            self._crash("intent")
            self._effects(prepared)
            self._finish(prepared, principal, at)
        except BaseException:
            self._restore(saved)
            raise

    def complete_submission(self, obligation_id: str, principal: Principal, at: datetime) -> None:
        return None


class IntentWorkflowStore(_Base):
    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None:
        self._guard()
        stream = obligation_stream(prepared.obligation.id)
        self._check_clock(stream, Kind.SUBMISSION_INTENT, principal, at)
        if self.submission(prepared.obligation.id).phase is Phase.NONE:
            self._append(
                stream,
                Kind.SUBMISSION_INTENT,
                principal,
                at,
                prepared.key,
                {"prepared": prepared.model_dump(mode="json")},
            )
        self._crash("intent")
        self._effects(prepared)
        self._finish(prepared, principal, at)

    def complete_submission(self, obligation_id: str, principal: Principal, at: datetime) -> None:
        st = self.submission(obligation_id)
        if st.phase is Phase.INTENT and st.prepared is not None:
            self._effects(st.prepared)
            self._finish(st.prepared, principal, at)


__all__ = [
    "STEPS",
    "ClockRegression",
    "Crash",
    "InMemoryWorkflowStore",
    "IntentWorkflowStore",
    "WorkflowStore",
    "obligation_stream",
    "tip",
]
