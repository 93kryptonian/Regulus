from ing_helpers import READER, REG, fresh, pdf

from regulus.extraction import PackageStatus, build_package
from regulus.ingestion.ingest import ingest


def test_pdf_end_to_end_covers_every_ingested_article() -> None:
    r = ingest(pdf(), REG, READER, fresh())
    p = build_package(r)
    assert p.status is PackageStatus.PACKAGED
    assert [u.label for u in p.units] == list(r.article_index)
    assert all(u.signals for u in p.units)


def test_normalized_heading_flows_through() -> None:
    r = ingest(pdf(glitch={3: "PasaI 3"}), REG, READER, fresh())
    p = build_package(r)
    assert [u.label for u in p.units if u.heading_normalized] == ["3"]
    assert len(p.units) == len(r.article_index)


def test_unrecoverable_gap_is_reported_not_filled() -> None:
    r = ingest(pdf(glitch={3: "Pasal 3x"}), REG, READER, fresh())
    p = build_package(r)
    assert p.status is PackageStatus.PACKAGED_WITH_ISSUES
    assert "3" in p.missing_articles and "3" not in [u.label for u in p.units]
    assert len(p.units) == len(r.article_index)


def test_failed_pdf_gives_failed_package() -> None:
    p = build_package(ingest(b"not a pdf", REG, READER, fresh()))
    assert p.status is PackageStatus.FAILED and p.units == ()
