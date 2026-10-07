import json
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from regulus.domain import ObligationStatus as S
from regulus.domain.base import Model
from regulus.workflow import Principal, WorkflowRole, WorkflowStore

from .chain import ChainLog, LogUnavailable

TERMINAL = {S.PUBLISHED, S.REJECTED}


class Policy(Model):
    illustrative: bool = True
    days: dict[str, int | None]


def load_policy(path: Path) -> Policy:
    return Policy.model_validate(json.loads(path.read_text(encoding="utf-8")))


def retention_class(stream: str) -> str | None:
    if stream.startswith(("notification:", "run:", "task:", "obligation:")):
        return "WORKFLOW"
    if stream.startswith("review:"):
        return "REVIEW_RECORD"
    return None


class PurgeStatus(StrEnum):
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"
    REFUSED = "REFUSED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class Retention:
    def __init__(
        self, store: WorkflowStore, policy: Policy, purge_log: ChainLog, audit: ChainLog
    ) -> None:
        self.store, self.policy, self.log, self.audit = store, policy, purge_log, audit
        self.holds: dict[str, str] = {}
        self.fail_after: str | None = None

    def streams(self) -> list[str]:
        ws = [
            s
            for p in ("notification:", "run:", "task:", "obligation:")
            for s in self.store.streams_with(p)
        ]
        rs = [f"review:{oid}" for oid in sorted(self.store.review._initial)]
        return ws + rs

    def last_time(self, stream: str) -> datetime | None:
        if stream.startswith("review:"):
            log = self.store.review.get(stream[7:])[1]
            return log[-1].decision.at if log else None
        recs = self.store.ledger(stream)
        return recs[-1].at if recs else None

    def terminal(self, stream: str) -> bool:
        if stream.startswith("review:"):
            return self.store.review.get(stream[7:])[0].status in TERMINAL
        if stream.startswith("obligation:"):
            oid = stream.split(":", 1)[1]
            return (not self.store.registered(oid)) or self.store.review.get(oid)[
                0
            ].status in TERMINAL
        return True

    def expired(self, stream: str, now: datetime) -> bool:
        cls = retention_class(stream)
        days = self.policy.days.get(cls or "")
        last = self.last_time(stream)
        return (
            cls is not None
            and days is not None
            and last is not None
            and now >= last + timedelta(days=days)
        )

    def eligible(self, stream: str, now: datetime) -> str | None:
        if stream not in self.streams():
            return "MISSING"
        if (
            retention_class(stream) is None
            or self.policy.days.get(retention_class(stream) or "") is None
        ):
            return "NO_POLICY"
        if stream in self.holds:
            return "HELD"
        if not self.terminal(stream):
            return "NON_TERMINAL"
        if not self.expired(stream, now):
            return "UNEXPIRED"
        return None

    def hold(self, operator: Principal, stream: str, reason: str, now: datetime) -> bool:
        if WorkflowRole.OPERATOR not in operator.roles:
            return False
        self.audit.append(
            "HOLD",
            now,
            operation="HOLD",
            actor=operator.id,
            resource=stream.replace(":", "_"),
            reason=reason,
        )
        self.holds[stream] = reason
        return True

    def release(self, operator: Principal, stream: str, reason: str, now: datetime) -> bool:
        if WorkflowRole.OPERATOR not in operator.roles or stream not in self.holds:
            return False
        self.audit.append(
            "RELEASE_HOLD",
            now,
            operation="RELEASE_HOLD",
            actor=operator.id,
            resource=stream.replace(":", "_"),
            reason=reason,
        )
        del self.holds[stream]
        return True

    def _tip(self, stream: str) -> str:
        if stream.startswith("review:"):
            log = self.store.review.get(stream[7:])[1]
            return log[-1].hash if log else "EMPTY"
        recs = self.store.ledger(stream)
        return recs[-1].hash if recs else "EMPTY"

    def _count(self, stream: str) -> int:
        return (
            len(self.store.review.get(stream[7:])[1])
            if stream.startswith("review:")
            else len(self.store.ledger(stream))
        )

    def _delete(self, stream: str) -> None:
        if stream.startswith("review:"):
            oid = stream[7:]
            r = self.store.review
            r._initial.pop(oid, None)
            r._state.pop(oid, None)
            r._log.pop(oid, None)
            for tid in [t for t, task in self.store.tasks.items() if task.obligation_id == oid]:
                del self.store.tasks[tid]
        else:
            self.store.streams.pop(stream, None)  # type: ignore[attr-defined]

    def purge(self, operator: Principal, stream: str, reason: str, now: datetime) -> PurgeStatus:
        if WorkflowRole.OPERATOR not in operator.roles:
            return PurgeStatus.DENIED
        why = self.eligible(stream, now)
        if why is not None:
            self.audit.append(
                "ACCESS_DENIED",
                now,
                operation="PURGE",
                actor=operator.id,
                resource=stream.replace(":", "_"),
                outcome=why,
            )
            return PurgeStatus.REFUSED
        key = stream.replace(":", "_")
        try:
            intent = self.log.append("PURGE_INTENT", now, stream=key, cls=retention_class(stream) or "NONE", records=self._count(stream),
                                     tip=self._tip(stream), actor=operator.id, reason=reason)  # fmt: skip
        except LogUnavailable:
            return PurgeStatus.FAILED
        if self.fail_after == "intent":
            self.fail_after = None
            raise RuntimeError("crash after intent")
        again = self.eligible(stream, now)
        if again is not None:
            self.log.append("PURGE_CANCELLED", now, intent=intent.id, stream=key, outcome=again)
            return PurgeStatus.CANCELLED
        self._delete(stream)
        if self.fail_after == "delete":
            self.fail_after = None
            raise RuntimeError("crash after delete")
        self.log.append("PURGE_APPLIED", now, intent=intent.id, stream=key)
        return PurgeStatus.APPLIED

    def recover(self, now: datetime) -> int:
        done = 0
        recs = list(self.log.records)
        closed = {
            r.fields.get("intent") for r in recs if r.kind in ("PURGE_APPLIED", "PURGE_CANCELLED")
        }
        for r in recs:
            if r.kind != "PURGE_INTENT" or r.id in closed:
                continue
            key = str(r.fields["stream"])
            stream = key.replace("_", ":", 1)
            if stream not in self.streams():
                self.log.append("PURGE_APPLIED", now, intent=r.id, stream=key, recovered=True)
            elif self.eligible(stream, now) is None:
                self._delete(stream)
                self.log.append("PURGE_APPLIED", now, intent=r.id, stream=key, recovered=True)
            else:
                self.log.append(
                    "PURGE_CANCELLED",
                    now,
                    intent=r.id,
                    stream=key,
                    outcome=self.eligible(stream, now) or "UNKNOWN",
                )
            done += 1
        return done
