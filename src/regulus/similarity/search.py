import hashlib
from collections.abc import Sequence

from regulus.domain import ObligationStatus
from regulus.lineage import LineageRelation, RelationType

from .embedding import EmbeddingProvider
from .index import VectorIndex
from .models import (
    TIER,
    LineageContext,
    Match,
    SearchConfig,
    SearchStatus,
    SimilarityEntry,
    SimilarityResult,
)
from .relation import classify
from .representation import embedding_text, represent


def lineage_context(
    query_article: str, match_article: str, relations: Sequence[LineageRelation] | None
) -> LineageContext:
    if query_article == match_article:
        return LineageContext.SAME_ARTICLE
    if relations is None:
        return LineageContext.UNKNOWN
    q, m = query_article.split(":")[0], match_article.split(":")[0]
    for r in relations:
        if r.type is RelationType.AMENDS and (r.source_id, r.target_id) == (q, m):
            return LineageContext.ARTICLE_AMENDS
        if r.type is RelationType.AMENDS and (r.source_id, r.target_id) == (m, q):
            return LineageContext.ARTICLE_AMENDED_BY
    return LineageContext.NONE


def _result(
    query_id: str,
    index: VectorIndex,
    provider: str,
    cfg: SearchConfig,
    status: SearchStatus,
    **kw: object,
) -> SimilarityResult:
    key = "|".join([query_id, index.version, provider, cfg.config_version, cfg.relation.version])
    return SimilarityResult(
        id="sim-" + hashlib.sha256(key.encode()).hexdigest()[:16],
        query_id=query_id,
        status=status,
        provider=provider,
        index_version=index.version,
        config_version=cfg.config_version,
        index_complete=index.incomplete == 0,
        **kw,
    )


def search(
    query: SimilarityEntry,
    index: VectorIndex,
    provider: EmbeddingProvider,
    cfg: SearchConfig | None = None,
    lineage: Sequence[LineageRelation] | None = None,
) -> SimilarityResult:
    cfg = cfg or SearchConfig()
    qid, pid = query.obligation.id, f"{provider.id}@{provider.version}"
    if (
        query.obligation.status is not ObligationStatus.GENERATED
        or not query.obligation.current.text.strip()
    ):
        return _result(
            qid, index, pid, cfg, SearchStatus.NOT_SEARCHABLE, reason="QUERY_NOT_GENERATED_OR_EMPTY"
        )
    if index.provider_id != pid or index.dimension != provider.dimension:
        return _result(qid, index, pid, cfg, SearchStatus.UNAVAILABLE, reason="PROVIDER_MISMATCH")
    rep = represent(query.obligation, query.trace)
    try:
        vec = list(provider.embed([embedding_text(rep)])[0])
    except Exception as e:
        return _result(qid, index, pid, cfg, SearchStatus.UNAVAILABLE, reason=type(e).__name__)
    exclude = {qid} | {
        oid
        for oid, r in index.records.items()
        if query.candidate_id is not None and r.candidate_id == query.candidate_id
    }
    pool = index.search(vec, cfg.k_retrieve, exclude)
    diags = (f"INDEX_INCOMPLETE({index.incomplete})",) if index.incomplete else ()
    if not pool:
        status = (
            SearchStatus.UNAVAILABLE
            if index.incomplete and not index.records
            else SearchStatus.NO_CANDIDATES
        )
        return _result(
            qid,
            index,
            pid,
            cfg,
            status,
            diagnostics=diags,
            reason="INDEX_INCOMPLETE" if status is SearchStatus.UNAVAILABLE else None,
        )
    scored = []
    for oid, score in pool:
        rec = index.records[oid]
        verdict = classify(rep, rec.representation, cfg.relation)
        scored.append((TIER[verdict.label], -verdict.composite, -score, oid, verdict, rec, score))
    scored.sort(key=lambda t: t[:4])
    matches = tuple(
        Match(
            obligation_id=oid,
            rank=i + 1,
            retrieval_score=score,
            verdict=verdict,
            lineage_context=lineage_context(query.obligation.article_id, rec.article_id, lineage),
            article_id=rec.article_id,
        )
        for i, (_, _, _, oid, verdict, rec, score) in enumerate(scored[: cfg.k])
    )
    return _result(
        qid,
        index,
        pid,
        cfg,
        SearchStatus.MATCHES,
        matches=matches,
        retrieved=len(pool),
        diagnostics=diags,
    )
