from pathlib import Path

import pytest
from ing_helpers import READER, fresh

from regulus.extraction import PackageStatus, UnitKind, build_package
from regulus.ingestion.ingest import ingest

PDF = Path(__file__).parents[2] / "pdf"
pytestmark = pytest.mark.corpus


@pytest.mark.skipif(not PDF.exists(), reason="local corpus absent")
def test_every_local_pdf_packages_with_complete_coverage_and_deterministically() -> None:
    for f in sorted(PDF.glob("*.pdf")):
        r = ingest(f.read_bytes(), f.stem, READER, fresh())
        p = build_package(r)
        assert p.status is not PackageStatus.FAILED
        assert len(p.units) == len(r.article_index) + (
            len(r.processed.amendment_units) if r.processed else 0
        )
        assert p.model_dump_json() == build_package(r).model_dump_json()


@pytest.mark.skipif(not (PDF / "pp20_1980.pdf").exists(), reason="local corpus absent")
def test_amendment_style_document_gives_amendment_units_without_article_ids() -> None:
    r = ingest((PDF / "pp20_1980.pdf").read_bytes(), "pp20_1980", READER, fresh())
    p = build_package(r)
    assert p.units and all(
        u.kind is UnitKind.AMENDMENT_UNIT and u.article_id is None for u in p.units
    )
