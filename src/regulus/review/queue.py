import hashlib
from collections.abc import Sequence
from datetime import datetime, timedelta

from regulus.domain import ObligationStatus
from regulus.similarity import Label

from .models import ReviewSnapshot, ReviewTask, TaskStatus


class ClaimError(Exception):
    pass


def new_task(snapshot: ReviewSnapshot, created_at: datetime) -> ReviewTask:
    if snapshot.obligation.status is not ObligationStatus.PENDING_REVIEW:
        raise ValueError("a review task needs a PENDING_REVIEW obligation")
    tid = (
        "task-"
        + hashlib.sha256(f"{snapshot.obligation.id}|{snapshot.hash}".encode()).hexdigest()[:12]
    )
    return ReviewTask(
        id=tid, obligation_id=snapshot.obligation.id, snapshots=(snapshot,), created_at=created_at
    )


def release_if_expired(task: ReviewTask, now: datetime) -> ReviewTask:
    if (
        task.status is TaskStatus.CLAIMED
        and task.claim_expires_at is not None
        and now >= task.claim_expires_at
    ):
        return task.model_copy(
            update={"status": TaskStatus.OPEN, "claimed_by": None, "claim_expires_at": None}
        )
    return task


def claim(task: ReviewTask, actor_id: str, now: datetime, ttl_seconds: int) -> ReviewTask:
    task = release_if_expired(task, now)
    if task.status is TaskStatus.DONE or task.status is TaskStatus.SUPERSEDED:
        raise ClaimError("task is closed")
    if task.status is TaskStatus.CLAIMED:
        raise ClaimError("task already claimed")
    return task.model_copy(
        update={
            "status": TaskStatus.CLAIMED,
            "claimed_by": actor_id,
            "claim_expires_at": now + timedelta(seconds=ttl_seconds),
        }
    )


def refresh(task: ReviewTask, snapshot: ReviewSnapshot) -> ReviewTask:
    return task.model_copy(
        update={
            "snapshots": (*task.snapshots, snapshot),
            "status": TaskStatus.OPEN,
            "claimed_by": None,
            "claim_expires_at": None,
        }
    )


def priority_key(task: ReviewTask) -> tuple[int, int, int, int, str, str]:
    s = task.snapshot
    labels = {m.verdict.label for m in s.similarity.matches} if s.similarity else set()
    questions = len(s.open_questions) + len(s.carried_questions)
    degraded = bool(s.source_flags)
    return (
        0 if Label.CONTRADICTORY_MODALITY in labels else 1,
        0 if Label.POSSIBLE_DUPLICATE in labels else 1,
        0 if degraded else 1,
        -questions,
        task.created_at.isoformat(),
        task.id,
    )


def ordered(tasks: Sequence[ReviewTask]) -> list[ReviewTask]:
    return sorted(
        (t for t in tasks if t.status in (TaskStatus.OPEN, TaskStatus.CLAIMED)), key=priority_key
    )
