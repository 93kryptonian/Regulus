from pathlib import Path

import pytest

from regulus.documents import PdfPlumberReader, process
from regulus.generation import ExtractiveGenerator, GenerationInput, Status, generate
from regulus.generation.evaluate import run_mutations
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract

FILES = sorted((Path(__file__).parents[2] / "pdf").glob("lt*.pdf"))
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]


@pytest.fixture(scope="module", params=FILES, ids=lambda p: p.stem)
def run(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    doc = process(request.param.read_bytes(), "REG", PdfPlumberReader())
    changes = tuple(
        ChangedProvision(
            regulation_id="REG",
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )
    ex = extract(ExtractionInput(changes=changes, documents={"REG": doc}), RulesExtractor())
    cands = tuple(c for r in ex.results for c in r.candidates)
    out = generate(GenerationInput(candidates=cands, documents={"REG": doc}), ExtractiveGenerator())
    return doc, cands, out


def test_every_real_candidate_generates_and_stays_grounded(run) -> None:  # type: ignore[no-untyped-def]
    doc, cands, out = run
    assert len(out.results) == len(cands)
    texts = {a.id: a.text for a in doc.articles}
    for r in out.results:
        assert r.status is Status.GENERATED and r.obligation is not None, r.violations
        assert all(texts[e.owner_id][e.span[0] : e.span[1]] == e.quote for e in r.evidence)
        assert r.obligation.source_owner_id in texts and r.obligation.status.value == "GENERATED"


def test_every_mutation_of_real_outputs_is_detected(run) -> None:  # type: ignore[no-untyped-def]
    doc, cands, _ = run
    m = run_mutations([(c, doc) for c in cands])
    assert m.undetected == ()
