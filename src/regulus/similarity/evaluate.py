import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from regulus.domain.base import Model

from .embedding import EmbeddingProvider, LexicalEmbedding
from .index import build_index
from .models import Label, RelationConfig, SearchConfig, SearchStatus, SimilarityEntry
from .relation import classify
from .representation import embedding_text, represent
from .search import search


class GoldPair(Model):
    query_id: str
    match_id: str
    label: Label
    rationale: str = Field(min_length=10)


class SimilarityGold(Model):
    corpus: tuple[SimilarityEntry, ...]
    queries: tuple[SimilarityEntry, ...]
    pairs: tuple[GoldPair, ...]


class SimilarityReport(Model):
    queries: int
    pairs: int
    label_accuracy: float
    confusion: dict[str, dict[str, int]]
    recall_at_3: float
    precision_at_3: float
    mrr: float
    duplicate_precision: float | None
    false_duplicates: tuple[str, ...]
    unevidenced_labels: int
    cap_violations: int
    provider_disagreements: int
    deterministic: bool


def load_gold(path: Path) -> SimilarityGold:
    return SimilarityGold.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _fit(entries: Sequence[SimilarityEntry], dimension: int) -> LexicalEmbedding:
    return LexicalEmbedding.fit(
        [embedding_text(represent(e.obligation, e.trace)) for e in entries], dimension
    )


def evaluate(
    gold: SimilarityGold,
    relation: RelationConfig | None = None,
    alt_provider: EmbeddingProvider | None = None,
) -> SimilarityReport:
    cfg = SearchConfig(relation=relation or RelationConfig())
    corpus = {e.obligation.id: e for e in gold.corpus}
    queries = {q.obligation.id: q for q in gold.queries}
    labels = [lb.value for lb in Label]
    confusion = {g: dict.fromkeys(labels, 0) for g in labels}
    for p in gold.pairs:
        got = classify(
            represent(queries[p.query_id].obligation, queries[p.query_id].trace),
            represent(corpus[p.match_id].obligation, corpus[p.match_id].trace),
            cfg.relation,
        ).label
        confusion[p.label.value][got.value] += 1
    correct = sum(confusion[k][k] for k in labels)
    provider = _fit(gold.corpus, 1024)
    index = build_index(gold.corpus, provider, cfg)
    alt = alt_provider or LexicalEmbedding(dimension=64)
    alt_index = build_index(gold.corpus, alt, cfg)
    relevant: dict[str, set[str]] = {}
    gold_dups: set[tuple[str, str]] = set()
    for p in gold.pairs:
        if p.label is not Label.SIMILAR_TEXT_ONLY:
            relevant.setdefault(p.query_id, set()).add(p.match_id)
        if p.label is Label.POSSIBLE_DUPLICATE:
            gold_dups.add((p.query_id, p.match_id))
    rec = prec = mrr = 0.0
    false_dups: list[str] = []
    dup_found = dup_true = 0
    unevidenced = cap_viol = disagree = 0
    deterministic = True
    for qid, q in queries.items():
        r = search(q, index, provider, cfg)
        r2 = search(q, index, provider, cfg)
        deterministic &= r.model_dump_json() == r2.model_dump_json()
        if r.status is not SearchStatus.MATCHES:
            continue
        top = [m.obligation_id for m in r.matches]
        rel = relevant.get(qid, set())
        hits = [m for m in top if m in rel]
        if rel:
            rec += len(hits) / min(cfg.k, len(rel))
            prec += len(hits) / len(top)
            rr = next((1 / (i + 1) for i, m in enumerate(top) if m in rel), 0.0)
            mrr += rr
        for m in r.matches:
            if m.verdict.label is Label.POSSIBLE_DUPLICATE:
                dup_found += 1
                if (qid, m.obligation_id) in gold_dups:
                    dup_true += 1
                else:
                    false_dups.append(f"{qid}->{m.obligation_id}")
            if m.verdict.label is not Label.SIMILAR_TEXT_ONLY and not m.verdict.supporting_fields:
                unevidenced += 1
            c = corpus[m.obligation_id]
            if any(
                f.state.value == "UNDETERMINED"
                for n, f in represent(c.obligation, c.trace).fields.items()
                if n in ("actor", "action", "object")
            ) and m.verdict.label in (
                Label.POSSIBLE_DUPLICATE,
                Label.VARIANT,
                Label.CONTRADICTORY_MODALITY,
            ):
                cap_viol += 1
        alt_res = search(q, alt_index, alt, cfg)
        mine = {m.obligation_id: m.verdict.label for m in r.matches}
        for m in alt_res.matches:
            if m.obligation_id in mine and mine[m.obligation_id] is not m.verdict.label:
                disagree += 1
    n = len(queries) or 1
    return SimilarityReport(
        queries=len(queries),
        pairs=len(gold.pairs),
        label_accuracy=correct / len(gold.pairs),
        confusion=confusion,
        recall_at_3=rec / n,
        precision_at_3=prec / n,
        mrr=mrr / n,
        duplicate_precision=dup_true / dup_found if dup_found else None,
        false_duplicates=tuple(false_dups),
        unevidenced_labels=unevidenced,
        cap_violations=cap_viol,
        provider_disagreements=disagree,
        deterministic=deterministic,
    )
