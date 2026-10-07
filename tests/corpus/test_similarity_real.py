from collections import Counter
from pathlib import Path

import pytest

from regulus.documents import PdfPlumberReader, process
from regulus.domain import ObligationStatus as OS
from regulus.generation import ExtractiveGenerator, GenerationInput, generate
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract
from regulus.similarity import (
    Label,
    LexicalEmbedding,
    SearchConfig,
    SearchStatus,
    SimilarityEntry,
    build_index,
    represent,
    search,
)
from regulus.similarity.representation import embedding_text

FILES = sorted((Path(__file__).parents[2] / "pdf").glob("lt*.pdf"))
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]


@pytest.fixture(scope="module")
def entries() -> list[SimilarityEntry]:
    out: list[SimilarityEntry] = []
    for f in FILES:
        reg = "R" + f.stem[-6:]
        doc = process(f.read_bytes(), reg, PdfPlumberReader())
        changes = tuple(
            ChangedProvision(
                regulation_id=reg,
                article_number=a.number,
                kind=ChangedKind.NEW_REGULATION_ARTICLE,
                text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
            )
            for a in doc.articles
        )
        ex = extract(ExtractionInput(changes=changes, documents={reg: doc}), RulesExtractor())
        cands = tuple(c for r in ex.results for c in r.candidates)
        gen = generate(
            GenerationInput(candidates=cands, documents={reg: doc}), ExtractiveGenerator()
        )
        by = {c.id: c for c in cands}
        out += [
            SimilarityEntry(
                obligation=r.obligation.model_copy(update={"status": OS.APPROVED}),
                trace=r.trace,
                candidate_id=r.candidate_id,
            )
            for r in gen.results
            if r.obligation is not None and r.candidate_id in by
        ]
    return out


def test_every_real_obligation_can_be_searched_with_the_safety_properties(entries) -> None:  # type: ignore[no-untyped-def]
    cfg = SearchConfig()
    provider = LexicalEmbedding.fit(
        [embedding_text(represent(e.obligation, e.trace)) for e in entries]
    )
    index = build_index(entries, provider, cfg)
    assert index.incomplete == 0 and len(index.records) == len(entries)
    labels: Counter[str] = Counter()
    for e in entries[::7]:
        q = e.model_copy(
            update={"obligation": e.obligation.model_copy(update={"status": OS.GENERATED})}
        )
        r = search(q, index, provider, cfg)
        assert r.status is SearchStatus.MATCHES and len(r.matches) == 3
        again = search(q, index, provider, cfg)
        assert r.model_dump_json() == again.model_dump_json()
        for m in r.matches:
            labels[m.verdict.label] += 1
            assert m.obligation_id != q.obligation.id
            if m.verdict.label is not Label.SIMILAR_TEXT_ONLY:
                assert m.verdict.supporting_fields
            if m.verdict.label is Label.POSSIBLE_DUPLICATE:
                assert all(
                    c.relation.value in ("EQUAL", "OVERLAP", "BOTH_NOT_STATED")
                    for c in m.verdict.comparisons
                )
    assert sum(labels.values()) == 3 * len(entries[::7])
