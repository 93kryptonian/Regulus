from collections.abc import Iterable

from .models import (
    ArticleProjection,
    ArticleStatus,
    Effect,
    ImpactItem,
    ImpactStatus,
    LineageRelation,
)


def project_article_status(
    impacts: Iterable[ImpactItem], regulation_id: str, article_number: str
) -> ArticleProjection:
    items = [
        i
        for i in impacts
        if i.target_regulation_id == regulation_id
        and i.article_number == article_number
        and i.status is ImpactStatus.RESOLVED
    ]
    withdrawn = [i.occurred_on for i in items if i.effect in (Effect.DELETED, Effect.REPEALED)]
    if withdrawn:
        cutoff = min(withdrawn)
        late = sorted(
            (i for i in items if i.occurred_on > cutoff), key=lambda i: (i.occurred_on, i.id)
        )
        return ArticleProjection(
            status=ArticleStatus.WITHDRAWN, anomalies=tuple(i.id for i in late)
        )
    if any(i.effect in (Effect.ADDED, Effect.MODIFIED) for i in items):
        return ArticleProjection(status=ArticleStatus.AMENDED)
    return ArticleProjection(status=ArticleStatus.IN_FORCE)


def lineage_of(
    relations: Iterable[LineageRelation], regulation_id: str
) -> tuple[LineageRelation, ...]:
    mine = [r for r in relations if regulation_id in (r.source_id, r.target_id)]
    return tuple(sorted(mine, key=lambda r: (r.evidence[0].occurred_on, r.id)))
