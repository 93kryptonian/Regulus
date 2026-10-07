from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from regulus.domain import ObligationStatus as S
from regulus.domain.base import Model

from .ledger import tip  # noqa: F401
from .models import Kind, Principal, WorkflowRecord, WorkflowRole
from .store import WorkflowStore

NO_REVIEWER = "NO_REVIEWER_AVAILABLE"


class ReviewerInfo(Model):
    id: str
    available: bool = True


class Directory(Protocol):
    def reviewers(self, now: datetime) -> Sequence[ReviewerInfo]: ...


class AssignStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"
    UNCHANGED = "UNCHANGED"
    DENIED = "DENIED"
    REFUSED = "REFUSED"


class AssignOutcome(Model):
    status: AssignStatus
    assignee: str | None = None
    reasons: tuple[str, ...] = ()


class Assignment(Model):
    assignee: str | None = None
    unassigned_reason: str | None = None
    history: int = 0


def task_stream(task_id: str) -> str:
    return f"task:{task_id}"


def assignment(records: Sequence[WorkflowRecord]) -> Assignment:
    state = Assignment()
    for r in records:
        if r.kind in (Kind.ASSIGNED, Kind.REASSIGNED):
            state = Assignment(assignee=r.details["to"], history=state.history + 1)
        elif r.kind is Kind.UNASSIGNED:
            state = Assignment(unassigned_reason=r.details["reason"], history=state.history + 1)
    return state


def current_assignment(store: WorkflowStore, task_id: str) -> Assignment:
    return assignment(store.ledger(task_stream(task_id)))


def is_open(store: WorkflowStore, task_id: str) -> bool:
    task = store.tasks.get(task_id)
    return task is not None and store.review.get(task.obligation_id)[0].status is S.PENDING_REVIEW


def open_load(store: WorkflowStore) -> dict[str, int]:
    load: dict[str, int] = {}
    for tid in sorted(store.tasks):
        who = current_assignment(store, tid).assignee
        if who is not None and is_open(store, tid):
            load[who] = load.get(who, 0) + 1
    return load


def pick(directory: Directory, now: datetime, load: dict[str, int]) -> str | None:
    ok = sorted(
        (r.id for r in directory.reviewers(now) if r.available), key=lambda i: (load.get(i, 0), i)
    )
    return ok[0] if ok else None


def assign(
    store: WorkflowStore,
    task_id: str,
    principal: Principal,
    now: datetime,
    directory: Directory,
    to: str | None = None,
    reason: str | None = None,
) -> AssignOutcome:
    roles = set(principal.roles)
    if to is None and not roles & {WorkflowRole.SYSTEM, WorkflowRole.COORDINATOR}:
        return AssignOutcome(status=AssignStatus.DENIED, reasons=("ROLE",))
    if to is not None and WorkflowRole.COORDINATOR not in roles:
        return AssignOutcome(status=AssignStatus.DENIED, reasons=("ROLE",))
    if task_id not in store.tasks:
        return AssignOutcome(status=AssignStatus.REFUSED, reasons=("UNKNOWN_TASK",))
    if not is_open(store, task_id):
        return AssignOutcome(status=AssignStatus.REFUSED, reasons=("TASK_CLOSED",))
    stream, current = task_stream(task_id), current_assignment(store, task_id)
    if to is None:
        who = pick(directory, now, open_load(store))
        if who is None:
            if current.unassigned_reason == NO_REVIEWER and current.assignee is None:
                return AssignOutcome(status=AssignStatus.UNCHANGED, reasons=(NO_REVIEWER,))
            store.append(stream, Kind.UNASSIGNED, principal, now, details={"reason": NO_REVIEWER})
            return AssignOutcome(status=AssignStatus.UNASSIGNED, reasons=(NO_REVIEWER,))
        if current.assignee is not None:
            return AssignOutcome(status=AssignStatus.UNCHANGED, assignee=current.assignee)
        store.append(stream, Kind.ASSIGNED, principal, now, details={"to": who, "by": principal.id})
        return AssignOutcome(status=AssignStatus.ASSIGNED, assignee=who)
    if not reason:
        return AssignOutcome(status=AssignStatus.REFUSED, reasons=("REASON_REQUIRED",))
    if not any(r.id == to and r.available for r in directory.reviewers(now)):
        return AssignOutcome(status=AssignStatus.REFUSED, reasons=("NOT_AN_AVAILABLE_REVIEWER",))
    if current.assignee == to:
        return AssignOutcome(status=AssignStatus.UNCHANGED, assignee=to)
    kind = Kind.REASSIGNED if current.assignee is not None else Kind.ASSIGNED
    store.append(
        stream, kind, principal, now,
        details={"to": to, "from": current.assignee, "by": principal.id, "reason": reason},
    )  # fmt: skip
    return AssignOutcome(status=AssignStatus.ASSIGNED, assignee=to)
