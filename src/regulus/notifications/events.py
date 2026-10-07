from collections.abc import Sequence

from regulus.domain import ObligationStatus as S
from regulus.review.models import SOURCE_CHANGED, SOURCE_WITHDRAWN
from regulus.workflow import TickAction, TickKind, WorkflowStore, current_assignment, current_due

from .models import NotificationEvent, NotificationKind


def tick_events(store: WorkflowStore, actions: Sequence[TickAction]) -> list[NotificationEvent]:
    out = []
    for a in actions:
        due = current_due(store, a.task_id)
        kind = (
            NotificationKind.TASK_OVERDUE
            if a.kind is TickKind.TASK_OVERDUE
            else NotificationKind.TASK_DUE_SOON
        )
        out.append(
            NotificationEvent(
                kind=kind, subject=a.task_id, version=a.key,
                payload={"task_id": a.task_id, "due_at": due.isoformat() if due else ""},
            )
        )  # fmt: skip
    return out


def assigned_events(store: WorkflowStore) -> list[NotificationEvent]:
    out = []
    for tid in sorted(store.tasks):
        a = current_assignment(store, tid)
        if a.assignee is not None:
            out.append(
                NotificationEvent(
                    kind=NotificationKind.TASK_ASSIGNED, subject=tid, version=f"{a.assignee}:{a.history}",
                    payload={"task_id": tid, "assignee": a.assignee},
                )
            )  # fmt: skip
    return out


def source_events(store: WorkflowStore) -> list[NotificationEvent]:
    out = []
    for tid in sorted(store.tasks):
        task = store.tasks[tid]
        if store.review.get(task.obligation_id)[0].status is not S.PENDING_REVIEW:
            continue
        for flag, kind in (
            (SOURCE_CHANGED, NotificationKind.SOURCE_CHANGED),
            (SOURCE_WITHDRAWN, NotificationKind.SOURCE_WITHDRAWN),
        ):
            if flag in task.snapshot.source_flags:
                out.append(
                    NotificationEvent(
                        kind=kind, subject=tid, version=task.snapshot.hash,
                        payload={"task_id": tid, "obligation_id": task.obligation_id},
                    )
                )  # fmt: skip
    return out


def review_decided_events(store: WorkflowStore) -> list[NotificationEvent]:
    out = []
    for tid in sorted(store.tasks):
        oid = store.tasks[tid].obligation_id
        ob, log = store.review.get(oid)
        for r in log:
            out.append(
                NotificationEvent(
                    kind=NotificationKind.REVIEW_DECIDED, subject=oid, version=r.hash,
                    payload={"obligation_id": oid, "status": r.decision.to_status.value, "record_hash": r.hash[:16]},
                )
            )  # fmt: skip
    return out
