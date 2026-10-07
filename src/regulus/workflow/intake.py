import hashlib
import json
from collections.abc import Mapping
from datetime import datetime

from regulus.domain import ObligationStatus as S
from regulus.domain import submit
from regulus.domain.base import Model
from regulus.generation import GenerationResult
from regulus.generation import Status as GenStatus
from regulus.obligations import ObligationCandidate, ObligationImpact
from regulus.review import StoreError, build_snapshot, new_task
from regulus.review.gates import verified_evidence
from regulus.similarity import SimilarityResult

from .ledger import make_record  # noqa: F401
from .models import (
    Kind,
    Phase,
    PreparedSubmission,
    Principal,
    SubmissionOutcome,
    SubmitStatus,
    WorkflowRole,
)
from .store import ClockRegression, WorkflowStore, obligation_stream

ALLOWED = {WorkflowRole.SYSTEM, WorkflowRole.OPERATOR}


class SnapshotInputs(Model):
    source_complete: bool = True
    similarity: SimilarityResult | None = None
    impacts: tuple[ObligationImpact, ...] = ()
    permitted_source: str = ""
    candidate: ObligationCandidate | None = None


def content_hash(result: GenerationResult) -> str:
    assert result.obligation is not None
    payload = json.dumps(
        result.obligation.generated.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def submission_key(obligation_id: str, chash: str) -> str:
    return "sub-" + hashlib.sha256(f"{obligation_id}|{chash}".encode()).hexdigest()[:24]


def _note(
    store: WorkflowStore,
    kind: Kind,
    principal: Principal,
    at: datetime,
    oid: str,
    key: str | None,
    reasons: tuple[str, ...],
) -> None:
    try:
        store.append(obligation_stream(oid), kind, principal, at, key, {"reasons": list(reasons)})
    except (StoreError, ClockRegression):
        pass


def submit_for_review(
    store: WorkflowStore,
    result: GenerationResult,
    inputs: SnapshotInputs,
    principal: Principal,
    now: datetime,
    owner_texts: Mapping[str, str],
) -> SubmissionOutcome:
    if not ALLOWED & set(principal.roles):
        return SubmissionOutcome(status=SubmitStatus.DENIED, reasons=("ROLE",))
    ob = result.obligation
    if result.status is not GenStatus.GENERATED or ob is None:
        return SubmissionOutcome(status=SubmitStatus.NOT_GENERATED, reasons=(result.status.value,))
    chash = content_hash(result)
    key = submission_key(ob.id, chash)
    state = store.submission(ob.id)
    if state.phase is not Phase.NONE:
        if state.key != key:
            _note(store, Kind.SUBMIT_REFUSED, principal, now, ob.id, key, ("CONFLICT",))
            return SubmissionOutcome(status=SubmitStatus.CONFLICT, reasons=("CONTENT_DIFFERS",))
        if state.phase is Phase.COMPLETE:
            return SubmissionOutcome(
                status=SubmitStatus.ALREADY_SUBMITTED,
                task=store.task(state.task_id or ""),
            )
        try:
            store.complete_submission(ob.id, principal, now)
        except StoreError:
            return SubmissionOutcome(status=SubmitStatus.FAILED, reasons=("STORE",))
        return SubmissionOutcome(
            status=SubmitStatus.SUBMITTED, task=store.task(state.task_id or "")
        )
    if store.registered(ob.id):
        _note(store, Kind.SUBMIT_REFUSED, principal, now, ob.id, key, ("REGISTERED_ELSEWHERE",))
        return SubmissionOutcome(status=SubmitStatus.CONFLICT, reasons=("REGISTERED_ELSEWHERE",))
    if ob.status is not S.GENERATED:
        return SubmissionOutcome(status=SubmitStatus.NOT_SUBMITTABLE, reasons=(ob.status.value,))
    probe = build_snapshot(
        ob, result.evidence, result.open_questions, inputs.source_complete, inputs.similarity,
        inputs.impacts, inputs.permitted_source, candidate=inputs.candidate,
    )  # fmt: skip
    ok = verified_evidence(probe, ob, owner_texts)
    if result.trace is None or not result.evidence or len(ok) != len(result.evidence):
        _note(store, Kind.SUBMIT_REFUSED, principal, now, ob.id, key, ("EVIDENCE_INVALID",))
        return SubmissionOutcome(status=SubmitStatus.EVIDENCE_INVALID, reasons=("EVIDENCE",))
    pending = submit(ob)
    snap = build_snapshot(
        pending, result.evidence, result.open_questions, inputs.source_complete, inputs.similarity,
        inputs.impacts, inputs.permitted_source, candidate=inputs.candidate,
    )  # fmt: skip
    task = new_task(snap, now)
    prepared = PreparedSubmission(key=key, content_hash=chash, obligation=pending, task=task)
    try:
        store.commit_submission(prepared, principal, now)
    except StoreError as e:
        _note(store, Kind.SUBMIT_FAILED, principal, now, ob.id, key, (type(e).__name__,))
        return SubmissionOutcome(status=SubmitStatus.FAILED, reasons=(type(e).__name__,))
    return SubmissionOutcome(status=SubmitStatus.SUBMITTED, task=task)
