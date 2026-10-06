from pathlib import Path

import pytest

from regulus.documents import DocStatus, PdfPlumberReader, locate, process, reconstruct
from regulus.documents.models import Code, ProcessedDocument

FILES = sorted((Path(__file__).parents[2] / "pdf").glob("*.pdf"))
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]


@pytest.fixture(scope="module", params=FILES, ids=lambda p: p.stem)
def doc(request: pytest.FixtureRequest) -> ProcessedDocument:
    return process(request.param.read_bytes(), "REG", PdfPlumberReader())


def test_every_document_is_processed(doc: ProcessedDocument) -> None:
    assert doc.status in (DocStatus.PROCESSED_OK, DocStatus.PROCESSED_WITH_ISSUES)
    assert doc.articles and not doc.amendment_units


def test_provenance_round_trips_for_every_article(doc: ProcessedDocument) -> None:
    pages = {p.number: p for p in doc.pages}
    for a in doc.articles:
        frags = doc.provenance[a.id]
        assert reconstruct(frags, pages) == a.text
        assert locate(frags, 0, len(a.text)) == frags
        assert (frags[0].page, frags[-1].page) == (a.page_start, a.page_end)


def test_no_explanation_text_leaks_into_articles(doc: ProcessedDocument) -> None:
    assert all("PENJELASAN" not in a.text.split("\n") for a in doc.articles)
    assert len({a.id for a in doc.articles}) == len(doc.articles)


def test_body_numbering_is_contiguous_unless_a_gap_is_reported(doc: ProcessedDocument) -> None:
    nums = [int("".join(c for c in a.number if c.isdigit())) for a in doc.articles]
    assert nums == sorted(nums)
    gaps = [d for d in doc.diagnostics if d.code is Code.ARTICLE_GAP]
    missing = {int(x) for d in gaps for x in d.detail.split(",") if x.isdigit()}
    assert missing.isdisjoint(nums)
    expected = set(range(1, nums[-1] + 1)) - set(nums)
    assert expected == missing
    assert (doc.status is DocStatus.PROCESSED_OK) == (not gaps)
