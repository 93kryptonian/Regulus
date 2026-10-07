from collections.abc import Mapping, Sequence
from datetime import datetime

from regulus.domain import Obligation, ObligationEvidence
from regulus.domain import ObligationStatus as S
from regulus.domain.base import Model
from regulus.similarity import Label

from .authorize import ReviewConfig, authorize
from .models import (
    SOURCE_CHANGED,
    SOURCE_INCOMPLETE,
    SOURCE_WITHDRAWN,
    Action,
    ActionRequest,
    ReviewRecord,
    ReviewSnapshot,
    ReviewTask,
    Status,
    TaskStatus,
)

DANGEROUS = {Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY}
EXPECTED_FROM = {
    Action.APPROVE: S.PENDING_REVIEW,
    Action.REJECT: S.PENDING_REVIEW,
    Action.EDIT: S.PENDING_REVIEW,
    Action.PUBLISH: S.APPROVED,
}


class Gate(Model):
    id: str
    ok: bool
    detail: str | None = None


class Refusal(Model):
    status: Status
    reasons: tuple[str, ...]
    with_task: bool = False


def label_of(snap: ReviewSnapshot, match_id: str) -> Label | None:
    if snap.similarity is None:
        return None
    return next(
        (m.verdict.label for m in snap.similarity.matches if m.obligation_id == match_id), None
    )


def resolved_questions(
    task: ReviewTask, log: Sequence[ReviewRecord], req: ActionRequest
) -> set[str]:
    questions = {q for s in task.snapshots for q in (*s.open_questions, *s.carried_questions)}
    done = {r.question for rec in log for r in rec.open_question_resolutions}
    done |= {r.question for r in req.resolutions}
    edited = {c.field for rec in log for c in rec.decision.changes if c.after}
    done |= {q for q in questions if q.split(":")[0] in edited}
    return done & questions


def approval_items(task: ReviewTask, log: Sequence[ReviewRecord], req: ActionRequest) -> list[Gate]:
    snap = task.snapshot
    items: list[Gate] = []
    questions = {q for s in task.snapshots for q in (*s.open_questions, *s.carried_questions)}
    done = resolved_questions(task, log, req)
    for q in sorted(questions):
        items.append(Gate(id=f"OPEN_QUESTION:{q}", ok=q in done))
    given = {d.match_id for d in req.dispositions}
    by_hash = {s.hash: s for s in task.snapshots}
    for rec in log:
        old = by_hash.get(rec.snapshot_hash)
        for d in rec.match_dispositions:
            if old is not None and label_of(old, d.match_id) == label_of(snap, d.match_id):
                given.add(d.match_id)
    if snap.similarity is not None:
        for m in snap.similarity.matches:
            if m.verdict.label in DANGEROUS:
                items.append(Gate(id=f"DISPOSITION:{m.obligation_id}", ok=m.obligation_id in given))
    acked = set(req.acknowledged_flags) | {f for rec in log for f in rec.acknowledged_flags}
    for flag in snap.source_flags:
        if flag == SOURCE_WITHDRAWN:
            items.append(Gate(id=SOURCE_WITHDRAWN, ok=False))
        elif flag in (SOURCE_INCOMPLETE, SOURCE_CHANGED):
            items.append(Gate(id=f"ACKNOWLEDGE:{flag}", ok=flag in acked))
    return items


def approval_gaps(task: ReviewTask, log: Sequence[ReviewRecord], req: ActionRequest) -> list[str]:
    return [g.id for g in approval_items(task, log, req) if not g.ok]


def verified_evidence(
    snap: ReviewSnapshot, ob: Obligation, owner_texts: Mapping[str, str]
) -> list[ObligationEvidence]:
    out = []
    for e in snap.evidence:
        text = owner_texts.get(e.owner_id)
        if (
            e.obligation_id == ob.id
            and e.owner_id == ob.source_owner_id
            and text is not None
            and e.matches(e.owner_id, text)
        ):
            out.append(e)
    return out


def claim_held(task: ReviewTask, actor_id: str, at: datetime) -> bool:
    return (
        task.status is TaskStatus.CLAIMED
        and task.claimed_by == actor_id
        and task.claim_expires_at is not None
        and at < task.claim_expires_at
    )


def refusals(
    task: ReviewTask,
    req: ActionRequest,
    ob: Obligation,
    log: Sequence[ReviewRecord],
    version: str,
    cfg: ReviewConfig,
    owner_texts: Mapping[str, str],
) -> list[Refusal]:
    out: list[Refusal] = []
    if req.task_id != task.id:
        out.append(Refusal(status=Status.DENIED, reasons=("TASK_MISMATCH",)))
    auth = authorize(req.actor, req.action, log, cfg)
    if not auth.allowed:
        out.append(Refusal(status=Status.DENIED, reasons=(auth.reason or "DENIED",)))
    if req.action is not Action.PUBLISH and not claim_held(task, req.actor.id, req.at):
        out.append(Refusal(status=Status.DENIED, reasons=("NO_CLAIM",)))
    if req.base_version != version:
        out.append(Refusal(status=Status.STALE, reasons=(), with_task=True))
    if ob.status is not EXPECTED_FROM[req.action]:
        out.append(
            Refusal(status=Status.INVALID_TRANSITION, reasons=(f"{req.action} from {ob.status}",))
        )
    if req.action is Action.APPROVE:
        if not verified_evidence(task.snapshot, ob, owner_texts):
            out.append(
                Refusal(
                    status=Status.EVIDENCE_INVALID,
                    reasons=("no verified evidence",),
                    with_task=True,
                )
            )
        gaps = approval_gaps(task, log, req)
        if gaps:
            out.append(
                Refusal(status=Status.INCOMPLETE_REVIEW, reasons=tuple(gaps), with_task=True)
            )
    if req.action is Action.PUBLISH and SOURCE_WITHDRAWN in task.snapshot.source_flags:
        out.append(
            Refusal(status=Status.INCOMPLETE_REVIEW, reasons=(SOURCE_WITHDRAWN,), with_task=True)
        )
    return out
