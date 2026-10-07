import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from .models import (
    Kind,
    Phase,
    PreparedSubmission,
    SubmissionState,
    WorkflowRecord,
)

GENESIS = "GENESIS"


def canonical(r: WorkflowRecord) -> str:
    return json.dumps(
        r.model_dump(mode="json", exclude={"hash"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def record_hash(prev_hash: str, r: WorkflowRecord) -> str:
    return hashlib.sha256((prev_hash + canonical(r)).encode()).hexdigest()


def seal(r: WorkflowRecord) -> WorkflowRecord:
    return r.model_copy(update={"hash": record_hash(r.prev_hash, r)})


def tip(records: Sequence[WorkflowRecord]) -> str:
    return records[-1].hash if records else GENESIS


def verify_chain(records: Sequence[WorkflowRecord]) -> bool:
    prev = GENESIS
    for i, r in enumerate(records):
        if r.prev_hash != prev or r.seq != i or r.hash != record_hash(prev, r):
            return False
        prev = r.hash
    return True


def make_record(
    stream: str,
    existing: Sequence[WorkflowRecord],
    kind: Kind,
    principal_id: str,
    at: datetime,
    key: str | None = None,
    details: dict[str, Any] | None = None,
) -> WorkflowRecord:
    seq, prev = len(existing), tip(existing)
    rid = "wrec-" + hashlib.sha256(f"{stream}|{seq}|{prev}".encode()).hexdigest()[:16]
    return seal(
        WorkflowRecord(
            id=rid,
            stream=stream,
            seq=seq,
            kind=kind,
            key=key,
            principal_id=principal_id,
            at=at,
            details=details or {},
            prev_hash=prev,
        )
    )


def submission_state(records: Sequence[WorkflowRecord]) -> SubmissionState:
    state = SubmissionState()
    for r in records:
        if r.kind is Kind.SUBMISSION_INTENT:
            prepared = PreparedSubmission.model_validate(r.details["prepared"])
            state = SubmissionState(
                phase=Phase.INTENT,
                key=prepared.key,
                content_hash=prepared.content_hash,
                task_id=prepared.task.id,
                prepared=prepared,
            )
        elif r.kind is Kind.SUBMITTED:
            state = state.model_copy(update={"phase": Phase.COMPLETE, "prepared": None})
    return state


def tamper_free(streams: dict[str, tuple[WorkflowRecord, ...]]) -> bool:
    return all(verify_chain(rs) and all(r.stream == s for r in rs) for s, rs in streams.items())
