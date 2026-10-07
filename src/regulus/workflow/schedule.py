from datetime import UTC, datetime, timedelta
from enum import StrEnum

from regulus.domain.base import Model
from regulus.review import ReviewTask
from regulus.similarity import Label

from .assign import Directory, assign, current_assignment, is_open, task_stream
from .models import Kind, Principal, WorkflowRecord, WorkflowRole
from .store import WorkflowStore

DANGEROUS = {Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY}


class RiskClass(StrEnum):
    HIGH = "HIGH"
    ELEVATED = "ELEVATED"
    NORMAL = "NORMAL"


class ScheduleConfig(Model):
    sla_seconds: dict[RiskClass, int] = {
        RiskClass.HIGH: 4 * 3600,
        RiskClass.ELEVATED: 24 * 3600,
        RiskClass.NORMAL: 72 * 3600,
    }
    due_soon_seconds: int = 3600
    backoff_base_seconds: int = 30
    backoff_cap_seconds: int = 3600
    max_attempts: int = 5


class TickKind(StrEnum):
    TASK_DUE_SOON = "TASK_DUE_SOON"
    TASK_OVERDUE = "TASK_OVERDUE"


class TickAction(Model):
    kind: TickKind
    task_id: str
    key: str


def risk_class(task: ReviewTask) -> RiskClass:
    s = task.snapshot
    labels = {m.verdict.label for m in s.similarity.matches} if s.similarity else set()
    if labels & DANGEROUS or s.source_flags:
        return RiskClass.HIGH
    if s.open_questions or s.carried_questions:
        return RiskClass.ELEVATED
    return RiskClass.NORMAL


def sla_due(task: ReviewTask, cfg: ScheduleConfig) -> datetime:
    return task.created_at + timedelta(seconds=cfg.sla_seconds[risk_class(task)])


def overdue(due_at: datetime, now: datetime) -> bool:
    return now >= due_at


def backoff(attempt: int, cfg: ScheduleConfig) -> timedelta:
    return timedelta(seconds=min(cfg.backoff_base_seconds * 2**attempt, cfg.backoff_cap_seconds))


def next_attempt_at(now: datetime, attempt: int, cfg: ScheduleConfig) -> datetime | None:
    return None if attempt + 1 >= cfg.max_attempts else now + backoff(attempt, cfg)


def due_at(records: list[WorkflowRecord] | tuple[WorkflowRecord, ...]) -> datetime | None:
    out: datetime | None = None
    for r in records:
        if r.kind in (Kind.DUE_SET, Kind.RESCHEDULED):
            out = datetime.fromisoformat(r.details["due_at"])
    return out


def current_due(store: WorkflowStore, task_id: str) -> datetime | None:
    return due_at(store.ledger(task_stream(task_id)))


def reschedule(
    store: WorkflowStore,
    task_id: str,
    new_due: datetime,
    reason: str,
    principal: Principal,
    now: datetime,
) -> bool:
    if WorkflowRole.COORDINATOR not in principal.roles:
        return False
    if not reason or current_due(store, task_id) == new_due:
        return False
    store.append(
        task_stream(task_id), Kind.RESCHEDULED, principal, now,
        details={"due_at": new_due.isoformat(), "reason": reason},
    )  # fmt: skip
    return True


def tick(
    store: WorkflowStore,
    now: datetime,
    directory: Directory,
    principal: Principal,
    cfg: ScheduleConfig | None = None,
) -> list[TickAction]:
    if not {WorkflowRole.SYSTEM, WorkflowRole.OPERATOR} & set(principal.roles):
        return []
    cfg = cfg or ScheduleConfig()
    out: list[TickAction] = []
    for tid in sorted(store.tasks):
        if not is_open(store, tid):
            continue
        stream = task_stream(tid)
        if current_due(store, tid) is None:
            store.append(
                stream, Kind.DUE_SET, principal, now,
                details={"due_at": sla_due(store.tasks[tid], cfg).isoformat()},
            )  # fmt: skip
        if current_assignment(store, tid).assignee is None:
            assign(store, tid, principal, now, directory)
        due = current_due(store, tid)
        assert due is not None
        done = {r.key for r in store.ledger(stream) if r.kind is Kind.TICK_ACTION}
        wanted: list[TickAction] = []
        if overdue(due, now):
            wanted.append(
                TickAction(
                    kind=TickKind.TASK_OVERDUE, task_id=tid,
                    key=f"overdue:{tid}:{now.astimezone(UTC).date().isoformat()}",
                )
            )  # fmt: skip
        elif now >= due - timedelta(seconds=cfg.due_soon_seconds):
            wanted.append(
                TickAction(
                    kind=TickKind.TASK_DUE_SOON,
                    task_id=tid,
                    key=f"due-soon:{tid}:{due.isoformat()}",
                )
            )
        for a in wanted:
            if a.key not in done:
                store.append(
                    stream, Kind.TICK_ACTION, principal, now, a.key, {"kind": a.kind.value}
                )
                out.append(a)
    return out
