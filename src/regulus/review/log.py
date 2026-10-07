import hashlib
import json
from collections.abc import Sequence

from regulus.domain import Obligation, ObligationContent, ObligationStatus, ReviewDecision

from .models import ReviewRecord

GENESIS = "GENESIS"


class ReplayError(ValueError):
    pass


def canonical(record: ReviewRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json", exclude={"hash"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def record_hash(prev_hash: str, record: ReviewRecord) -> str:
    return hashlib.sha256((prev_hash + canonical(record)).encode()).hexdigest()


def seal(record: ReviewRecord) -> ReviewRecord:
    return record.model_copy(update={"hash": record_hash(record.prev_hash, record)})


def tip(records: Sequence[ReviewRecord]) -> str:
    return records[-1].hash if records else GENESIS


def verify_chain(records: Sequence[ReviewRecord]) -> bool:
    prev = GENESIS
    for r in records:
        if r.prev_hash != prev or r.hash != record_hash(prev, r):
            return False
        prev = r.hash
    return True


def obligation_version(obligation: Obligation, n_records: int) -> str:
    payload = json.dumps(obligation.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{n_records}".encode()).hexdigest()


def step(obligation: Obligation, d: ReviewDecision) -> Obligation:
    if d.obligation_id != obligation.id or d.from_status != obligation.status:
        raise ReplayError("record does not follow the obligation's state")
    current = obligation.current
    if d.to_status is ObligationStatus.EDITED:
        data = current.model_dump()
        for c in d.changes:
            if data[c.field] != c.before:
                raise ReplayError(f"stale edit on {c.field}")
            data[c.field] = c.after
        current = ObligationContent.model_validate(data)
    return obligation.model_copy(update={"status": d.to_status, "current": current})


def replay(initial: Obligation, records: Sequence[ReviewRecord]) -> Obligation:
    if not verify_chain(records):
        raise ReplayError("hash chain broken")
    ob = initial
    for r in records:
        ob = step(ob, r.decision)
    return ob
