import hashlib
from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from regulus.domain import (
    FieldChange,
    Obligation,
    ObligationEvidence,
    ReviewDecision,
    TransitionError,
    apply_decision,
)
from regulus.domain import (
    ObligationStatus as S,
)
from regulus.generation.verify import tokens
from regulus.similarity import Label

from .authorize import ReviewConfig, authorize
from .log import ReplayError, obligation_version, seal, tip
from .models import (
    SOURCE_CHANGED,
    SOURCE_INCOMPLETE,
    SOURCE_WITHDRAWN,
    Action,
    ActionRequest,
    RejectCode,
    ReviewOutcome,
    ReviewRecord,
    ReviewSnapshot,
    ReviewTask,
    Status,
    TaskStatus,
)
from .store import ReviewStore, StaleCommit, StoreError

DANGEROUS = {Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY}
EXPECTED_FROM = {
    Action.APPROVE: S.PENDING_REVIEW,
    Action.REJECT: S.PENDING_REVIEW,
    Action.EDIT: S.PENDING_REVIEW,
    Action.PUBLISH: S.APPROVED,
}


def _out(status: Status, *reasons: str, task: ReviewTask | None = None) -> ReviewOutcome:
    return ReviewOutcome(status=status, reasons=tuple(reasons), task=task)


def _did(oid: str, n: int) -> str:
    return "dec-" + hashlib.sha256(f"{oid}|{n}".encode()).hexdigest()[:16]


def _rid(oid: str, n: int, prev: str) -> str:
    return "rrec-" + hashlib.sha256(f"{oid}|{n}|{prev}".encode()).hexdigest()[:16]


def _label(snap: ReviewSnapshot, match_id: str) -> Label | None:
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


def approval_gaps(task: ReviewTask, log: Sequence[ReviewRecord], req: ActionRequest) -> list[str]:
    snap = task.snapshot
    gaps: list[str] = []
    for q in sorted(
        {q for s in task.snapshots for q in (*s.open_questions, *s.carried_questions)}
        - resolved_questions(task, log, req)
    ):
        gaps.append(f"OPEN_QUESTION:{q}")
    given = {d.match_id for d in req.dispositions}
    by_hash = {s.hash: s for s in task.snapshots}
    for rec in log:
        old = by_hash.get(rec.snapshot_hash)
        for d in rec.match_dispositions:
            if old is not None and _label(old, d.match_id) == _label(snap, d.match_id):
                given.add(d.match_id)
    if snap.similarity is not None:
        for m in snap.similarity.matches:
            if m.verdict.label in DANGEROUS and m.obligation_id not in given:
                gaps.append(f"DISPOSITION:{m.obligation_id}")
    acked = set(req.acknowledged_flags) | {f for rec in log for f in rec.acknowledged_flags}
    for flag in snap.source_flags:
        if flag == SOURCE_WITHDRAWN:
            gaps.append(SOURCE_WITHDRAWN)
        elif flag in (SOURCE_INCOMPLETE, SOURCE_CHANGED) and flag not in acked:
            gaps.append(f"ACKNOWLEDGE:{flag}")
    return gaps


def _verified_evidence(
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


def _record(
    ob: Obligation,
    log: Sequence[ReviewRecord],
    decision: ReviewDecision,
    task: ReviewTask,
    version: str,
    req: ActionRequest,
    extra: Mapping[str, object],
) -> ReviewRecord:
    prev = tip(log)
    rec = ReviewRecord(
        id=_rid(ob.id, len(log), prev),
        decision=decision,
        task_id=task.id,
        base_version=version,
        snapshot_hash=task.snapshot.hash,
        actor_id=req.actor.id,
        actor_roles=req.actor.roles,
        prev_hash=prev,
        **extra,
    )
    return seal(rec)


def _decision(
    ob: Obligation,
    n: int,
    req: ActionRequest,
    frm: S,
    to: S,
    reason: str | None,
    changes: tuple[FieldChange, ...] = (),
) -> ReviewDecision:
    return ReviewDecision(
        id=_did(ob.id, n),
        obligation_id=ob.id,
        reviewer=req.actor.id,
        at=req.at,
        from_status=frm,
        to_status=to,
        reason=reason,
        changes=changes,
    )


def apply(
    store: ReviewStore,
    task: ReviewTask,
    req: ActionRequest,
    cfg: ReviewConfig | None = None,
    owner_texts: Mapping[str, str] | None = None,
) -> ReviewOutcome:
    cfg = cfg or ReviewConfig()
    owner_texts = owner_texts or {}
    ob, log = store.get(task.obligation_id)
    version = obligation_version(ob, len(log))
    if req.task_id != task.id:
        return _out(Status.DENIED, "TASK_MISMATCH")
    auth = authorize(req.actor, req.action, log, cfg)
    if not auth.allowed:
        return _out(Status.DENIED, auth.reason or "DENIED")
    if req.action is not Action.PUBLISH and not (
        task.status is TaskStatus.CLAIMED
        and task.claimed_by == req.actor.id
        and task.claim_expires_at is not None
        and req.at < task.claim_expires_at
    ):
        return _out(Status.DENIED, "NO_CLAIM")
    if req.base_version != version:
        return _out(Status.STALE, task=task)
    if ob.status is not EXPECTED_FROM[req.action]:
        return _out(Status.INVALID_TRANSITION, f"{req.action} from {ob.status}")
    if req.action is Action.APPROVE:
        return _approve(store, task, req, ob, log, version, owner_texts)
    if req.action is Action.REJECT:
        return _reject(store, task, req, ob, log, version)
    if req.action is Action.EDIT:
        return _edit(store, task, req, ob, log, version)
    return _publish(store, task, req, ob, log, version)


def _commit(
    store: ReviewStore,
    ob: Obligation,
    after: Obligation,
    records: list[ReviewRecord],
    version: str,
    task: ReviewTask,
) -> ReviewOutcome:
    try:
        store.commit(ob.id, after, records, version)
    except StaleCommit:
        return _out(Status.STALE, task=task)
    except (StoreError, ReplayError) as e:
        return _out(Status.NOT_RECORDED, str(e), task=task)
    return ReviewOutcome(status=Status.APPLIED, obligation=after, records=tuple(records), task=task)


def _approve(
    store: ReviewStore,
    task: ReviewTask,
    req: ActionRequest,
    ob: Obligation,
    log: Sequence[ReviewRecord],
    version: str,
    owner_texts: Mapping[str, str],
) -> ReviewOutcome:
    evidence = _verified_evidence(task.snapshot, ob, owner_texts)
    if not evidence:
        return _out(Status.EVIDENCE_INVALID, "no verified evidence", task=task)
    gaps = approval_gaps(task, log, req)
    if gaps:
        return _out(Status.INCOMPLETE_REVIEW, *gaps, task=task)
    d = _decision(ob, len(log), req, S.PENDING_REVIEW, S.APPROVED, req.reason)
    try:
        after = apply_decision(ob, d, evidence)
    except TransitionError as e:
        return _out(Status.INVALID_TRANSITION, str(e), task=task)
    extra = {
        "open_question_resolutions": req.resolutions,
        "match_dispositions": req.dispositions,
        "acknowledged_flags": req.acknowledged_flags,
    }
    rec = _record(ob, log, d, task, version, req, extra)
    done = task.model_copy(
        update={"status": TaskStatus.DONE, "claimed_by": None, "claim_expires_at": None}
    )
    return _commit(store, ob, after, [rec], version, done)


def _reject(
    store: ReviewStore,
    task: ReviewTask,
    req: ActionRequest,
    ob: Obligation,
    log: Sequence[ReviewRecord],
    version: str,
) -> ReviewOutcome:
    rr = req.reject_reason
    if rr is None:
        return _out(Status.INCOMPLETE_REVIEW, "REJECT_REASON", task=task)
    if rr.code is RejectCode.DUPLICATE_OF and _label(task.snapshot, rr.match_id or "") is None:
        return _out(Status.INCOMPLETE_REVIEW, "DUPLICATE_OF_NOT_IN_SNAPSHOT", task=task)
    d = _decision(ob, len(log), req, S.PENDING_REVIEW, S.REJECTED, rr.code.value)
    try:
        after = apply_decision(ob, d, [])
    except TransitionError as e:
        return _out(Status.INVALID_TRANSITION, str(e), task=task)
    rec = _record(
        ob,
        log,
        d,
        task,
        version,
        req,
        {"reject_reason": rr, "acknowledged_flags": req.acknowledged_flags},
    )
    done = task.model_copy(
        update={"status": TaskStatus.DONE, "claimed_by": None, "claim_expires_at": None}
    )
    return _commit(store, ob, after, [rec], version, done)


def _edit(
    store: ReviewStore,
    task: ReviewTask,
    req: ActionRequest,
    ob: Obligation,
    log: Sequence[ReviewRecord],
    version: str,
) -> ReviewOutcome:
    if not req.changes or not req.reason:
        return _out(Status.INCOMPLETE_REVIEW, "EDIT_CHANGES_AND_REASON", task=task)
    d1 = _decision(ob, len(log), req, S.PENDING_REVIEW, S.EDITED, req.reason, req.changes)
    try:
        mid = apply_decision(ob, d1, [])
        d2 = _decision(ob, len(log) + 1, req, S.EDITED, S.PENDING_REVIEW, "RESUBMIT")
        after = apply_decision(mid, d2, [])
    except (TransitionError, ValidationError, ValueError) as e:
        return _out(Status.INVALID_TRANSITION, str(e)[:120], task=task)
    divergence: tuple[str, ...] = ()
    if any(c.field == "text" for c in req.changes):
        allowed = set(tokens(task.snapshot.permitted_source))
        divergence = tuple(dict.fromkeys(t for t in tokens(after.current.text) if t not in allowed))
    r1 = _record(ob, log, d1, task, version, req, {"divergence": divergence})
    r2 = _record(ob, [*log, r1], d2, task, version, req, {})
    open_task = task.model_copy(
        update={"status": TaskStatus.OPEN, "claimed_by": None, "claim_expires_at": None}
    )
    return _commit(store, ob, after, [r1, r2], version, open_task)


def _publish(
    store: ReviewStore,
    task: ReviewTask,
    req: ActionRequest,
    ob: Obligation,
    log: Sequence[ReviewRecord],
    version: str,
) -> ReviewOutcome:
    if SOURCE_WITHDRAWN in task.snapshot.source_flags:
        return _out(Status.INCOMPLETE_REVIEW, SOURCE_WITHDRAWN, task=task)
    d = _decision(ob, len(log), req, S.APPROVED, S.PUBLISHED, req.reason)
    try:
        after = apply_decision(ob, d, [])
    except TransitionError as e:
        return _out(Status.INVALID_TRANSITION, str(e), task=task)
    rec = _record(ob, log, d, task, version, req, {})
    return _commit(store, ob, after, [rec], version, task)
