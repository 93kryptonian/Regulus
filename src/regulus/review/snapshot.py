import hashlib
import json
from collections.abc import Sequence

from regulus.domain import Obligation, ObligationEvidence
from regulus.obligations import ObligationImpact
from regulus.obligations.models import ImpactKind
from regulus.similarity import SimilarityResult

from .models import SOURCE_CHANGED, SOURCE_INCOMPLETE, SOURCE_WITHDRAWN, ReviewSnapshot


def snapshot_hash(s: ReviewSnapshot) -> str:
    payload = json.dumps(
        s.model_dump(mode="json", exclude={"hash"}), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def source_flags(
    obligation: Obligation, source_complete: bool, impacts: Sequence[ObligationImpact]
) -> tuple[str, ...]:
    flags = [] if source_complete else [SOURCE_INCOMPLETE]
    for i in impacts:
        if obligation.id in i.affected_obligation_ids:
            if i.kind is ImpactKind.WITHDRAWN:
                flags.append(SOURCE_WITHDRAWN)
            else:
                flags.append(SOURCE_CHANGED)
    return tuple(dict.fromkeys(flags))


def build_snapshot(
    obligation: Obligation,
    evidence: Sequence[ObligationEvidence],
    open_questions: Sequence[str],
    source_complete: bool,
    similarity: SimilarityResult | None,
    impacts: Sequence[ObligationImpact] = (),
    permitted_source: str = "",
    previous: ReviewSnapshot | None = None,
) -> ReviewSnapshot:
    carried: list[str] = []
    if previous is not None:
        for q in (*previous.open_questions, *previous.carried_questions):
            if q not in open_questions and q not in carried:
                carried.append(q)
    snap = ReviewSnapshot(
        obligation=obligation,
        evidence=tuple(evidence),
        open_questions=tuple(open_questions),
        source_complete=source_complete,
        source_flags=source_flags(obligation, source_complete, impacts),
        similarity=similarity,
        permitted_source=permitted_source,
        carried_questions=tuple(carried),
    )
    return snap.model_copy(update={"hash": snapshot_hash(snap)})
