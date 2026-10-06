from pathlib import Path

import pytest

from regulus.documents import PdfPlumberReader, locate, process
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, ResultStatus, RulesExtractor, extract, load_lexicon
from regulus.obligations.segment import find_markers

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
    return doc, extract(ExtractionInput(changes=changes, documents={"REG": doc}), RulesExtractor())


def test_every_citation_equals_its_text_and_resolves_to_pages(run) -> None:  # type: ignore[no-untyped-def]
    doc, out = run
    texts = {a.id: a.text for a in doc.articles}
    pages = {p.number: p for p in doc.pages}
    for r in out.results:
        assert r.dropped_ungrounded == 0
        for c in r.candidates:
            cites = [c.clause, c.marker.citation, *c.items]
            cites += [
                v.value.citation
                for v in (c.actor, c.action, c.object, c.deadline, c.frequency)
                if v.value
            ]
            cites += [v.citation for v in (*c.conditions, *c.exceptions)]
            for ct in cites:
                assert texts[ct.owner_id][ct.start : ct.end] == ct.quote
            spans = locate(doc.provenance[c.clause.owner_id], c.clause.start, c.clause.end)
            assert spans and all(pages[s.page].text[s.start : s.end] for s in spans)


def test_no_silent_deontic_loss_and_no_failures(run) -> None:  # type: ignore[no-untyped-def]
    doc, out = run
    lex = load_lexicon()
    texts = {a.id: a.text for a in doc.articles}
    for r in out.results:
        assert r.status is not ResultStatus.FAILED
        markers = [
            m
            for m in find_markers(texts[r.change.owner_id], (0, len(texts[r.change.owner_id])), lex)
            if not m.negated
        ]
        covered = {c.marker.citation.start for c in r.candidates} | {
            d.span[0] for d in r.diagnostics if d.code.value == "UNEXTRACTED_DEONTIC" and d.span
        }
        # markers inside the stripped heading cannot occur; every other marker is a candidate or a diagnostic
        assert {m.start for m in markers} <= covered, r.change.article_number
