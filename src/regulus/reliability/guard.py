from collections.abc import Sequence
from datetime import datetime
from typing import Any

from regulus.review import ReplayError, ReviewRecord, StoreError, replay, verify_chain
from regulus.review.store import InMemoryReviewStore
from regulus.workflow import PreparedSubmission, Principal, WorkflowRecord
from regulus.workflow import verify_chain as verify_workflow_chain
from regulus.workflow.store import obligation_stream


class IntegrityError(StoreError):
    obs_attr = ("store", "INTEGRITY")


class GuardedStore:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._tips: dict[str, tuple[int, str]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _check(self, stream: str) -> None:
        recs: tuple[WorkflowRecord, ...] = self._inner.ledger(stream)
        if not verify_workflow_chain(recs):
            raise IntegrityError(f"{stream}: chain verification failed")
        tip = self._tips.get(stream)
        if tip is not None and (len(recs) <= tip[0] or recs[tip[0]].hash != tip[1]):
            raise IntegrityError(f"{stream}: truncated or rewritten since the last guarded write")

    def _remember(self, stream: str) -> None:
        recs: tuple[WorkflowRecord, ...] = self._inner.ledger(stream)
        if recs:
            self._tips[stream] = (len(recs) - 1, recs[-1].hash)

    def append(self, stream: str, *args: Any, **kw: Any) -> WorkflowRecord:
        self._check(stream)
        out: WorkflowRecord = self._inner.append(stream, *args, **kw)
        self._remember(stream)
        return out

    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None:
        stream = obligation_stream(prepared.obligation.id)
        self._check(stream)
        self._inner.commit_submission(prepared, principal, at)
        self._remember(stream)

    def complete_submission(self, obligation_id: str, principal: Principal, at: datetime) -> None:
        stream = obligation_stream(obligation_id)
        self._check(stream)
        self._inner.complete_submission(obligation_id, principal, at)
        self._remember(stream)


class GuardedReviewStore:
    def __init__(self, inner: InMemoryReviewStore) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def commit(
        self, oid: str, after: Any, records: Sequence[ReviewRecord], expected_version: str
    ) -> None:
        state, log = self._inner.get(oid)
        if not verify_chain(log):
            raise IntegrityError(f"{oid}: review log chain verification failed")
        try:
            if replay(self._inner._initial[oid], log) != state:
                raise IntegrityError(f"{oid}: review log and stored state disagree")
        except ReplayError as e:
            raise IntegrityError(f"{oid}: review log does not replay") from e
        self._inner.commit(oid, after, records, expected_version)
