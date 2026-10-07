from datetime import date

import pytest
from sim_helpers import entries, one, query

from regulus.domain import EventType as T
from regulus.domain import ObligationStatus as OS
from regulus.lineage import LineageRelation, RelationType
from regulus.lineage.models import EvidenceKind, RelationEvidence
from regulus.similarity import (
    Label as L,
)
from regulus.similarity import (
    LexicalEmbedding,
    SearchConfig,
    build_index,
    classify,
    represent,
    search,
)
from regulus.similarity import (
    LineageContext as LC,
)
from regulus.similarity import (
    SearchStatus as S,
)
from regulus.similarity.embedding import _terms
from regulus.similarity.representation import embedding_text

BASE = "Pasal 1\nPengendali wajib menyimpan arsip paling lambat 3 hari."


def provider(texts: list[str]) -> LexicalEmbedding:
    return LexicalEmbedding.fit(texts)


def build(es):  # type: ignore[no-untyped-def]
    p = provider([embedding_text(represent(e.obligation, e.trace)) for e in es])
    return p, build_index(es, p, SearchConfig())


def test_duplicate_variant_and_contradiction_are_found_and_labelled() -> None:
    es = [
        one(BASE, "R1"),
        one("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 7 hari.", "R2"),
        one("Pasal 1\nPengendali dilarang menyimpan arsip paling lambat 3 hari.", "R3"),
        one("Pasal 1\nLembaga wajib menerbitkan sertifikat resmi.", "R4"),
    ]
    p, idx = build(es)
    r = search(query(BASE, "Q"), idx, p)
    assert r.status is S.MATCHES and len(r.matches) == 3
    labels = {m.obligation_id: m.verdict.label for m in r.matches}
    by_reg = {e.obligation.article_id.split(":")[0]: e.obligation.id for e in es}
    assert labels[by_reg["R1"]] is L.POSSIBLE_DUPLICATE
    assert labels[by_reg["R2"]] is L.VARIANT and labels[by_reg["R3"]] is L.CONTRADICTORY_MODALITY
    assert [m.rank for m in r.matches] == [1, 2, 3]
    assert (
        r.matches[0].verdict.label is L.POSSIBLE_DUPLICATE
        and r.matches[0].obligation_id == by_reg["R1"]
    )


def test_tiers_order_the_results_not_the_retrieval_score() -> None:
    es = [
        one(BASE, "R1"),
        one("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 7 hari.", "R2"),
    ]
    p, idx = build(es)
    r = search(query(BASE), idx, p)
    tiers = [m.verdict.label for m in r.matches]
    assert tiers == [L.POSSIBLE_DUPLICATE, L.VARIANT]


def test_a_high_retrieval_score_never_produces_a_duplicate() -> None:
    near = one("Pasal 1\nPengendali wajib menghapus arsip paling lambat 3 hari.", "R1")
    p, idx = build([near])
    q = query(BASE)
    r = search(q, idx, p)
    (m,) = r.matches
    assert m.retrieval_score > 0.5 and m.verdict.label is L.RELATED
    assert set(m.verdict.supporting_fields) == {"actor", "object", "deadline"}
    assert m.score_kind == "COSINE_UNCALIBRATED"


def test_swapped_actor_and_recipient_with_a_high_score_is_not_a_duplicate() -> None:
    a = one("Pasal 1\nPengendali wajib melaporkan insiden kepada Lembaga.", "R1")
    p, idx = build([a])
    r = search(query("Pasal 1\nLembaga wajib melaporkan insiden kepada Pengendali."), idx, p)
    assert r.matches[0].retrieval_score > 0.6 and r.matches[0].verdict.label is L.RELATED


def test_label_is_provider_independent() -> None:
    es = [
        one(BASE, "R1"),
        one("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 7 hari.", "R2"),
    ]
    q = query(BASE)
    p1, idx1 = build(es)
    p2 = LexicalEmbedding(dimension=64)
    idx2 = build_index(es, p2, SearchConfig())
    r1, r2 = search(q, idx1, p1), search(q, idx2, p2)
    l1 = {m.obligation_id: m.verdict.label for m in r1.matches}
    l2 = {m.obligation_id: m.verdict.label for m in r2.matches}
    assert l1 == l2
    assert r1.provider != r2.provider and r1.id != r2.id
    for e in es:
        assert (
            classify(represent(q.obligation, q.trace), represent(e.obligation, e.trace)).label
            is l1[e.obligation.id]
        )


def test_undetermined_actor_caps_even_identical_text() -> None:
    body = "Pasal 1\nDalam melakukan pemrosesan, Pengendali wajib menunjukkan bukti."
    a, q = one(body, "R1"), query(body)
    p, idx = build([a])
    (m,) = search(q, idx, p).matches
    assert m.verdict.label is L.RELATED and "CAPPED_BY_UNDETERMINED(actor)" in m.verdict.cap_reasons


def test_status_filter_and_self_and_sibling_exclusion() -> None:
    pending = one(BASE, "R1", OS.PENDING_REVIEW)
    approved = one(BASE, "R2")
    q = query(BASE, "Q")
    p, idx = build([pending, approved, q])
    assert {r for r in idx.records} == {approved.obligation.id}
    sib = approved.model_copy(update={"candidate_id": q.candidate_id})
    idx2 = build_index([sib], p, SearchConfig())
    assert search(q, idx2, p).status is S.NO_CANDIDATES
    both = build_index(
        [
            approved,
            q.model_copy(
                update={"obligation": q.obligation.model_copy(update={"status": OS.APPROVED})}
            ),
        ],
        p,
        SearchConfig(),
    )
    assert q.obligation.id not in {m.obligation_id for m in search(q, both, p).matches}


def test_empty_index_is_no_candidates_not_unavailable() -> None:
    p = LexicalEmbedding()
    r = search(query(BASE), build_index([], p, SearchConfig()), p)
    assert r.status is S.NO_CANDIDATES and r.matches == () and r.index_complete


class Failing:
    id, version, dimension = "failing", "1", 8

    def __init__(self, bad: set[str] | None = None) -> None:
        self.bad = bad

    def embed(self, texts):  # type: ignore[no-untyped-def]
        if self.bad is None or any(b in t for t in texts for b in self.bad):
            raise TimeoutError("provider down")
        return [[1.0] + [0.0] * 7 for _ in texts]


def test_provider_failure_is_unavailable_never_empty() -> None:
    a = one(BASE, "R1")
    idx = build_index([a], LexicalEmbedding(), SearchConfig()).__class__(
        provider_id="failing@1", dimension=8
    )
    r = search(query(BASE), idx, Failing())
    assert r.status is S.UNAVAILABLE and r.reason == "TimeoutError" and r.matches == ()


def test_partial_index_failure_is_flagged() -> None:
    a, b = one(BASE, "R1"), one("Pasal 1\nLembaga wajib menyimpan dokumen rahasia.", "R2")
    p = Failing(bad={"dokumen"})
    idx = build_index([a, b], p, SearchConfig())
    assert idx.incomplete == 1 and len(idx.records) == 1
    r = search(query(BASE), idx, Failing(bad=set()))
    assert (
        r.status is S.MATCHES and not r.index_complete and r.diagnostics == ("INDEX_INCOMPLETE(1)",)
    )
    empty = build_index([b], Failing(bad={"dokumen"}), SearchConfig())
    r2 = search(query(BASE), empty, Failing(bad=set()))
    assert r2.status is S.UNAVAILABLE and r2.reason == "INDEX_INCOMPLETE"


def test_query_must_be_generated_and_non_empty() -> None:
    p = LexicalEmbedding()
    idx = build_index([one(BASE, "R1")], p, SearchConfig())
    approved_query = one(BASE, "Q")
    assert search(approved_query, idx, p).status is S.NOT_SEARCHABLE


def test_index_never_mixes_providers_or_dimensions() -> None:
    es = [one(BASE, "R1")]
    idx = build_index(es, LexicalEmbedding(dimension=64), SearchConfig())
    with pytest.raises(ValueError):
        build_index(es, LexicalEmbedding(dimension=128), SearchConfig(), existing=idx)
    r = search(query(BASE), idx, LexicalEmbedding(dimension=128))
    assert r.status is S.UNAVAILABLE and r.reason == "PROVIDER_MISMATCH"


def test_vectors_are_cached_and_invalidated_by_content() -> None:
    calls: list[int] = []

    class Counting(LexicalEmbedding):
        def embed(self, texts):  # type: ignore[no-untyped-def]
            calls.append(len(texts))
            return super().embed(texts)

    p = Counting()
    a = one(BASE, "R1")
    idx = build_index([a], p, SearchConfig())
    build_index([a], p, SearchConfig(), existing=idx)
    assert calls == [1]
    changed = one("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 9 hari.", "R1")
    build_index([changed], p, SearchConfig(), existing=idx)
    assert calls == [1, 1]


def test_ties_are_broken_by_obligation_id_and_results_are_deterministic() -> None:
    es = [one(BASE, f"R{i}") for i in range(4)]
    p, idx = build(es)
    q = query(BASE)
    a, b = search(q, idx, p), search(q, idx, p)
    assert a.model_dump_json() == b.model_dump_json()
    ids = [m.obligation_id for m in a.matches]
    assert ids == sorted(ids)
    assert len(a.matches) == 3 and a.retrieved == 4


def test_k_limits_the_returned_matches_ordered_by_tier() -> None:
    es = [
        one(BASE, "R1"),
        one("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 7 hari.", "R2"),
        one("Pasal 1\nPengendali dilarang menyimpan arsip paling lambat 3 hari.", "R3"),
        one("Pasal 1\nPengendali wajib menghapus data lain.", "R4"),
        one("Pasal 1\nLembaga wajib menghapus data.", "R5"),
    ]
    p, idx = build(es)
    r = search(query(BASE), idx, p, SearchConfig(k=2))
    assert [m.verdict.label for m in r.matches] == [L.POSSIBLE_DUPLICATE, L.CONTRADICTORY_MODALITY]
    assert r.retrieved == 5


def amends(src: str, tgt: str) -> LineageRelation:
    ev = RelationEvidence(kind=EvidenceKind.EVENT, ref="e", occurred_on=date(2026, 1, 1))
    return LineageRelation(
        id="lin-1", type=RelationType.AMENDS, source_id=src, target_id=tgt, evidence=(ev,)
    )


def test_lineage_context_is_an_annotation_and_never_changes_the_label() -> None:
    old = one(BASE, "R-OLD")
    p, idx = build([old])
    q = query("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 7 hari.", "R-NEW")
    bare = search(q, idx, p)
    assert bare.matches[0].lineage_context is LC.UNKNOWN
    none = search(q, idx, p, lineage=[])
    amended = search(q, idx, p, lineage=[amends("R-NEW", "R-OLD")])
    by = search(q, idx, p, lineage=[amends("R-OLD", "R-NEW")])
    assert (
        none.matches[0].lineage_context,
        amended.matches[0].lineage_context,
        by.matches[0].lineage_context,
    ) == (LC.NONE, LC.ARTICLE_AMENDS, LC.ARTICLE_AMENDED_BY)
    assert {m.matches[0].verdict.label for m in (bare, none, amended, by)} == {L.VARIANT}


def test_same_article_successive_versions_are_variant_and_same_article() -> None:
    old = one(BASE, "R1", OS.PUBLISHED)
    q = query("Pasal 1\nPengendali wajib menyimpan arsip paling lambat 10 hari.", "R1")
    p, idx = build([old])
    (m,) = search(q, idx, p).matches
    assert (
        m.lineage_context is LC.SAME_ARTICLE
        and m.verdict.label is L.VARIANT
        and m.article_id == "R1:1"
    )


def test_inputs_unchanged() -> None:
    es = [one(BASE, "R1")]
    q = query(BASE)
    snap = (q.model_dump_json(), es[0].model_dump_json())
    p, idx = build(es)
    search(q, idx, p)
    assert (q.model_dump_json(), es[0].model_dump_json()) == snap


def test_lexical_embedding_is_deterministic_and_normalized() -> None:
    p = LexicalEmbedding.fit(["a b c", "b c d"])
    v1, v2 = p.embed(["a b c"])[0], LexicalEmbedding.fit(["a b c", "b c d"]).embed(["a b c"])[0]
    assert v1 == v2 and abs(sum(x * x for x in v1) - 1.0) < 1e-9
    assert p.embed([""])[0] == [0.0] * p.dimension
    assert _terms("a b") == ["a", "b", "a_b"]


def test_entries_helper_roundtrip() -> None:
    assert len(entries(BASE + "\nPasal 2\nSetiap Orang dilarang menggunakan data.")) == 2
    assert date(2026, 1, 1) and T.NEW
