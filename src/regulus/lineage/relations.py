import hashlib
from collections import defaultdict

from regulus.domain import EventType, RegulatoryEvent

from .models import (
    Declaration,
    EvidenceKind,
    LineageRelation,
    RelationEvidence,
    RelationType,
    UnresolvedRelation,
)

EVENT_RELATION = {
    EventType.AMEND: RelationType.AMENDS,
    EventType.REPEAL: RelationType.REPEALS,
    EventType.PARTIAL_REPEAL: RelationType.PARTIALLY_REPEALS,
}


def sha(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def relation_id(type: RelationType, source_id: str, target_id: str) -> str:
    return "lin-" + sha(type, source_id, target_id)[:16]


def build_relations(
    events: tuple[RegulatoryEvent, ...], declarations: tuple[Declaration, ...]
) -> tuple[list[LineageRelation], list[UnresolvedRelation], list[str]]:
    ev: dict[tuple[RelationType, str, str], list[RelationEvidence]] = defaultdict(list)
    unresolved: list[UnresolvedRelation] = []
    dups: list[str] = []
    for e in events:
        if e.type is EventType.NEEDS_REVIEW:
            unresolved.append(
                UnresolvedRelation(event_id=e.id, reason=str(e.reason), declared_ref=e.declared_ref)
            )
        elif e.type in EVENT_RELATION and e.target_id:
            key = (EVENT_RELATION[e.type], e.regulation_id, e.target_id)
            ev[key].append(
                RelationEvidence(kind=EvidenceKind.EVENT, ref=e.id, occurred_on=e.occurred_on)
            )
    for d in declarations:
        key = (RelationType.IMPLEMENTS, d.source_id, d.target_id)
        ev[key].append(
            RelationEvidence(kind=EvidenceKind.DECLARATION, ref=d.id, occurred_on=d.occurred_on)
        )
    out = []
    for (t, s, g), evidence in ev.items():
        uniq = {(x.kind, x.ref): x for x in evidence}.values()
        if len(uniq) < len(evidence):
            dups.append(relation_id(t, s, g))
        ordered = tuple(sorted(uniq, key=lambda x: (x.occurred_on, x.kind, x.ref)))
        out.append(
            LineageRelation(
                id=relation_id(t, s, g), type=t, source_id=s, target_id=g, evidence=ordered
            )
        )
    out.sort(key=lambda r: (r.source_id, r.target_id, r.type))
    unresolved.sort(key=lambda u: u.event_id)
    return out, unresolved, sorted(dups)
