import hashlib
from collections.abc import Sequence

from regulus.domain import Obligation
from regulus.lineage import ChangedProvision, WithdrawnProvision
from regulus.lineage.models import ChangedKind

from .models import ImpactKind, ObligationImpact


def _impact(
    kind: ImpactKind,
    regulation_id: str,
    article_number: str,
    impact_id: str | None,
    obligations: Sequence[Obligation],
    complete: bool,
) -> ObligationImpact:
    article_id = f"{regulation_id}:{article_number}"
    ids = tuple(sorted(o.id for o in obligations if o.article_id == article_id))
    key = "|".join([kind, article_id, impact_id or ""])
    return ObligationImpact(
        id="oim-" + hashlib.sha256(key.encode()).hexdigest()[:16],
        kind=kind,
        regulation_id=regulation_id,
        article_number=article_number,
        article_id=article_id,
        affected_obligation_ids=ids,
        review_required=bool(ids) or not complete,
        store_complete=complete,
        impact_id=impact_id,
    )


def impacts(
    withdrawn: Sequence[WithdrawnProvision],
    changes: Sequence[ChangedProvision],
    obligations: Sequence[Obligation],
    complete: bool,
) -> list[ObligationImpact]:
    out = [
        _impact(
            ImpactKind.WITHDRAWN,
            w.regulation_id,
            w.article_number,
            w.impact_id,
            obligations,
            complete,
        )
        for w in withdrawn
    ]
    for c in changes:
        if c.kind in (ChangedKind.MODIFIED, ChangedKind.TERM_REPLACED):
            kind = (
                ImpactKind.MODIFIED if c.kind is ChangedKind.MODIFIED else ImpactKind.TERM_REPLACED
            )
            out.append(
                _impact(kind, c.regulation_id, c.article_number, c.impact_id, obligations, complete)
            )
    return sorted({i.id: i for i in out}.values(), key=lambda i: (i.article_id, i.kind, i.id))
