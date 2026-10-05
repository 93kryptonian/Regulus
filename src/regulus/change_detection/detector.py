from collections import defaultdict
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from datetime import date

from regulus.domain import (
    EventType,
    Regulation,
    RegulatoryEvent,
    regulation_id,
)
from regulus.domain import (
    ReviewReason as R,
)

from .identity import conflict_discriminator, event_id, target_discriminator
from .matcher import MatchClass, RegulationIndex, classify, norm_number, norm_text
from .models import (
    ACTION_EVENT,
    Action,
    Conflict,
    DeclaredRelation,
    DetectionResult,
    Outcome,
    SourceRecord,
)

REASON = {
    MatchClass.UNRESOLVED: R.UNRESOLVED_TARGET,
    MatchClass.AMBIGUOUS: R.AMBIGUOUS_TARGET,
    MatchClass.MALFORMED: R.MALFORMED_TARGET,
}
CONTRADICTORY = (
    {Action.MENGUBAH, Action.MENCABUT},
    {Action.MENCABUT, Action.MENCABUT_SEBAGIAN},
)


def _errors(r: SourceRecord) -> list[str]:
    e = []
    if r.kind is None:
        e.append("missing kind")
    if not r.number or not r.number.strip():
        e.append("missing number")
    if r.year is None or not 1945 <= r.year <= 2100:
        e.append("missing or invalid year")
    if not r.title or not r.title.strip():
        e.append("missing title")
    if r.promulgated_on is None:
        e.append("missing promulgated_on")
    return e


def _conflicts(r: SourceRecord, old: Regulation) -> list[Conflict]:
    pairs = [
        ("title", old.title, r.title, norm_text),
        ("promulgated_on", old.promulgated_on, r.promulgated_on, str),
        ("enacted_on", old.enacted_on, r.enacted_on, str),
    ]
    return [
        Conflict(field=f, indexed=str(a), incoming=str(b))
        for f, a, b, n in pairs
        if a is not None and b is not None and n(a) != n(b)  # type: ignore[operator]
    ]


def detect(
    record: SourceRecord, index: RegulationIndex, seen: AbstractSet[str], detected_on: date
) -> DetectionResult:
    sid = record.source_id
    if errs := _errors(record):
        return DetectionResult(source_id=sid, outcome=Outcome.FAILED, errors=tuple(errs))
    assert record.kind and record.number and record.year and record.promulgated_on
    rid = regulation_id(record.kind, record.number, record.year)
    events: dict[str, RegulatoryEvent] = {}
    dup = 0

    def emit(
        type: EventType, basis: str, target: str | None = None, disc: str = "", **kw: object
    ) -> None:
        nonlocal dup
        eid = event_id(type, rid, target, disc)
        if eid in seen or eid in events:
            dup += 1
            return
        events[eid] = RegulatoryEvent(
            id=eid,
            type=type,
            regulation_id=rid,
            target_id=target,
            occurred_on=record.promulgated_on,
            detected_on=detected_on,
            basis=basis,
            **kw,
        )

    def result(conflicts: tuple[Conflict, ...] = ()) -> DetectionResult:
        out = tuple(events[k] for k in sorted(events))
        return DetectionResult(
            source_id=sid,
            outcome=Outcome.PROCESSED_OK if out else Outcome.PROCESSED_EMPTY,
            events=out,
            duplicates=dup,
            conflicts=conflicts,
        )

    old = index.get(record.kind, record.number, record.year)
    if old and (conflicts := _conflicts(record, old)):
        disc = conflict_discriminator(
            R.METADATA_CONFLICT, [f"{c.field}={c.indexed}>{c.incoming}" for c in conflicts]
        )
        emit(EventType.NEEDS_REVIEW, f"src={sid}|metadata", None, disc, reason=R.METADATA_CONFLICT)
        return result(tuple(conflicts))

    emit(EventType.NEW, f"src={sid}")

    own = (record.kind, norm_number(record.number), record.year)
    resolved: dict[str, list[DeclaredRelation]] = defaultdict(list)
    for rel in record.relations:
        t = rel.target
        basis = f"src={sid}|rel={rel.action}|ref={t.raw}"
        is_self = (
            t.kind
            and t.number
            and t.year is not None
            and (t.kind, norm_number(t.number), t.year) == own
        )
        cls, hit = classify(t, index)
        if is_self or (hit and hit.id == rid):
            disc = target_discriminator(R.SELF_REFERENCE, rel.action, t.raw)
            emit(
                EventType.NEEDS_REVIEW,
                basis,
                None,
                disc,
                reason=R.SELF_REFERENCE,
                declared_ref=t.raw,
            )
        elif cls is MatchClass.RESOLVED and hit:
            resolved[hit.id].append(rel)
        else:
            reason = REASON[cls]
            disc = target_discriminator(reason, rel.action, t.raw)
            emit(EventType.NEEDS_REVIEW, basis, None, disc, reason=reason, declared_ref=t.raw)

    for tid, rels in resolved.items():
        actions = {r.action for r in rels}
        if any(c <= actions for c in CONTRADICTORY):
            items = [f"{a}>{tid}" for a in sorted(actions)]
            disc = conflict_discriminator(R.CONFLICTING_RELATIONS, items)
            emit(
                EventType.NEEDS_REVIEW,
                f"src={sid}|rel=conflict|target={tid}",
                None,
                disc,
                reason=R.CONFLICTING_RELATIONS,
            )
            continue
        for rel in rels:
            basis = f"src={sid}|rel={rel.action}|ref={rel.target.raw}"
            emit(ACTION_EVENT[rel.action], basis, tid)
    return result()


def detect_batch(
    records: Sequence[SourceRecord],
    index: RegulationIndex,
    seen: AbstractSet[str],
    detected_on: date,
) -> list[DetectionResult]:
    acc = set(seen)
    out = []
    for r in records:
        res = detect(r, index, acc, detected_on)
        acc.update(e.id for e in res.events)
        out.append(res)
    return out
