from pathlib import Path

import pytest
from ing_helpers import READER, fresh

from regulus.ingestion.ingest import ingest
from regulus.ingestion.models import IngestionStatus as S

PDF = Path(__file__).parents[2] / "pdf"
pytestmark = pytest.mark.corpus


@pytest.mark.skipif(not (PDF / "lt6a9164bf1e96a.pdf").exists(), reason="local corpus absent")
def test_the_measured_glitch_in_the_real_regulation_is_normalized_and_flagged():
    data = (PDF / "lt6a9164bf1e96a.pdf").read_bytes()
    r = ingest(data, "lt6a9164bf1e96a", READER, fresh())
    assert [(n.article_number, n.original) for n in r.normalizations] == [(92, "Pasa192")]
    assert "92" in r.article_index and r.status is S.INGESTED_WITH_ISSUES
    off = ingest(data, "lt6a9164bf1e96a", READER, fresh(), normalize_headings=False)
    assert "92" not in off.article_index


@pytest.mark.skipif(not PDF.exists(), reason="local corpus absent")
def test_every_local_pdf_is_ingested_without_a_crash_and_with_an_honest_status():
    for f in sorted(PDF.glob("*.pdf")):
        r = ingest(f.read_bytes(), f.stem, READER, fresh())
        assert r.status in (S.INGESTED, S.INGESTED_WITH_ISSUES)
        assert r.identity.regulation_id == f.stem


@pytest.mark.skipif(not (PDF / "pp20_1980.pdf").exists(), reason="local corpus absent")
def test_an_amendment_style_document_has_units_and_no_article_claims():
    r = ingest((PDF / "pp20_1980.pdf").read_bytes(), "pp20_1980", READER, fresh())
    assert (
        r.article_index == {} and r.processed is not None and len(r.processed.amendment_units) >= 1
    )
