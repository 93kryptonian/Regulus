import hashlib
from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from regulus.domain import (
    FieldChange,
    Obligation,
    ReviewDecision,
    TransitionError,
    apply_decision,
)
from regulus.domain import (
    ObligationStatus as S,
)
from regulus.generation.verify import tokens

from .authorize import ReviewConfig
from .gates import label_of, refusals, verified_evidence
from .log import ReplayError, obligation_version, seal, tip
from .models import (
    Action,
    ActionRequest,
    RejectCode,
    ReviewOutcome,
    ReviewRecord,
    ReviewTask,
    Status,
    TaskStatus,
)
from .store import ReviewStore, StaleCommit, StoreError


def _out(status: Status, *reasons: str, task: ReviewTask | None = None) -> ReviewOutcome:
    return ReviewOutcome(status=status, reasons=tuple(reasons), task=task)


def _did(oid: str, n: int) -> str:
    return "dec-" + hashlib.sha256(f"{oid}|{n}".encode()).hexdigest()[:16]


def _rid(oid: str, n: int, prev: str) -> str:
    return "rrec-" + hashlib.sha256(f"{oid}|{n}|{prev}".encode()).hexdigest()[:16]


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
    found = refusals(task, req, ob, log, version, cfg, owner_texts)
    if found:
        f = found[0]
        return _out(f.status, *f.reasons, task=task if f.with_task else None)
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
    evidence = verified_evidence(task.snapshot, ob, owner_texts)
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
    if rr.code is RejectCode.DUPLICATE_OF and label_of(task.snapshot, rr.match_id or "") is None:
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
    d = _decision(ob, len(log), req, S.APPROVED, S.PUBLISHED, req.reason)
    try:
        after = apply_decision(ob, d, [])
    except TransitionError as e:
        return _out(Status.INVALID_TRANSITION, str(e), task=task)
    rec = _record(ob, log, d, task, version, req, {})
    return _commit(store, ob, after, [rec], version, task)
