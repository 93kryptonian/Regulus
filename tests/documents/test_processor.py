import pytest
from helpers import REG
from pdfgen import Scan, make_pdf

from regulus.documents import (
    Code,
    DocStatus,
    OcrResult,
    PageStatus,
    PdfPlumberReader,
    UnreadableDocument,
    locate,
    process,
    reconstruct,
)
from regulus.documents.models import PageFailure, PageSource, RawPage

P1 = (
    "BAB I\nKETENTUAN UMUM\nPasal 1\n"
    "(1) Pengendali wajib melapor kepada Lembaga setiap tahun.\n(2) Laporan memuat:\n"
    "a. identitas pengendali data pribadi;\nb. alasan pemrosesan data pribadi."
)
P2 = "Pasal 2\nSetiap orang wajib menjaga kerahasiaan data pribadi yang diperolehnya."
P3 = "Pasal 3\nLembaga berwenang melakukan pengawasan terhadap seluruh pengendali data pribadi."


class FakeOcr:
    name = "fake-1"

    def __init__(self, outputs: list[str | Exception]) -> None:
        self.outputs, self.calls = outputs, 0

    def recognize(self, png: bytes) -> OcrResult:
        self.calls += 1
        out = self.outputs[self.calls - 1]
        if isinstance(out, Exception):
            raise out
        return OcrResult(text=out, confidence=0.9)


def run(pages, ocr=None, **kw):  # type: ignore[no-untyped-def]
    return process(make_pdf(pages, **kw), REG, PdfPlumberReader(ocr))


def test_clean_text_pdf_end_to_end() -> None:
    r = run([P1, P2, P3])
    assert r.status is DocStatus.PROCESSED_OK and r.diagnostics == ()
    assert [a.number for a in r.articles] == ["1", "2", "3"]
    assert all(p.source is PageSource.NATIVE for p in r.pages)
    assert r.document.page_count == 3 and r.document.id.startswith("doc-")
    pmap = {p.number: p for p in r.pages}
    for a in r.articles:
        assert reconstruct(r.provenance[a.id], pmap) == a.text
        assert locate(r.provenance[a.id], 0, len(a.text))[0].document_id == r.document.id
    assert any(p.path == ("(2)", "a") for p in r.provisions)


def test_scanned_page_goes_through_ocr_and_mixed_document() -> None:
    ocr = FakeOcr([P2])
    r = run([P1, Scan("scan"), P3], ocr)
    assert [p.source for p in r.pages] == [PageSource.NATIVE, PageSource.OCR, PageSource.NATIVE]
    assert r.pages[1].ocr_engine == "fake-1" and ocr.calls == 1
    assert r.status is DocStatus.PROCESSED_OK and [a.number for a in r.articles] == ["1", "2", "3"]


def test_ocr_failure_gives_partial_with_readable_articles() -> None:
    r = run([P1, Scan("x"), P3], FakeOcr([TimeoutError("slow")]))
    assert r.status is DocStatus.PARTIAL
    assert r.pages[1].status is PageStatus.FAILED and "TimeoutError" in (r.pages[1].error or "")
    assert Code.PAGE_FAILED in [d.code for d in r.diagnostics]
    assert [a.number for a in r.articles] == ["1", "3"]


def test_scanned_page_without_ocr_engine_fails_not_empty() -> None:
    r = run([P1, Scan("x")])
    assert r.status is DocStatus.PARTIAL and r.pages[1].status is PageStatus.FAILED


def test_all_pages_failing_is_failed() -> None:
    r = run([Scan("a"), Scan("b")], FakeOcr([RuntimeError("x"), RuntimeError("y")]))
    assert r.status is DocStatus.FAILED and r.articles == ()


def test_ocr_misread_marker_is_not_corrected() -> None:
    r = run(
        [P1, Scan("x")],
        FakeOcr(["Pasal I\nSetiap orang wajib menjaga kerahasiaan data pribadi."]),
    )
    assert r.status is DocStatus.PROCESSED_WITH_ISSUES
    assert Code.MIXED_BODY_FORMS in [d.code for d in r.diagnostics]
    assert [a.number for a in r.articles] == ["1"] and "Pasal I" in r.articles[0].text


def test_ocr_encoding_and_confidence_warnings() -> None:
    r = run([P1, Scan("x")], FakeOcr(["Pasal 2\nada�lah wajib menjaga kerahasiaan data pribadi."]))
    assert (
        Code.ENCODING_ISSUE in [d.code for d in r.diagnostics]
        and r.status is DocStatus.PROCESSED_OK
    )


def test_blank_page_is_empty_but_does_not_fail() -> None:
    r = run([P1, "", P2])
    assert r.pages[1].status is PageStatus.EMPTY and r.status is DocStatus.PROCESSED_OK
    assert Code.PAGE_EMPTY in [d.code for d in r.diagnostics]


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4\ngarbage"])
def test_corrupt_files_fail(data: bytes) -> None:
    r = process(data, REG, PdfPlumberReader())
    assert (
        r.status is DocStatus.FAILED
        and r.pages == ()
        and r.diagnostics[0].code is Code.UNREADABLE_DOCUMENT
    )


def test_encrypted_pdf_fails() -> None:
    r = process(make_pdf([P1], password="secret"), REG, PdfPlumberReader())
    assert r.status is DocStatus.FAILED


def test_text_without_pasal_is_processed_empty_with_text() -> None:
    r = run(["Ini hanya surat biasa tanpa struktur peraturan sama sekali, sekedar teks panjang."])
    assert r.status is DocStatus.PROCESSED_EMPTY and r.pages[0].text and r.articles == ()
    assert Code.NO_BODY_UNITS in [d.code for d in r.diagnostics]


def test_gap_gives_processed_with_issues() -> None:
    r = run([P1, P3])
    assert r.status is DocStatus.PROCESSED_WITH_ISSUES and Code.ARTICLE_GAP in [
        d.code for d in r.diagnostics
    ]


def test_same_bytes_idempotent_and_identity() -> None:
    a, b = run([P1, P2]), run([P1, P2])
    assert a.model_dump_json() == b.model_dump_json()
    c = run([P1, P2], title="other")
    assert (
        c.document.id != a.document.id
        and c.document.text_fingerprint == a.document.text_fingerprint
    )


def test_reader_protocol_accepts_plain_callables() -> None:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        return [RawPage(number=1, source=PageSource.NATIVE, text="BAB I\nPasal 1\nisi")]

    assert process(b"x", REG, reader).status is DocStatus.PROCESSED_OK

    def broken(data: bytes) -> list[RawPage | PageFailure]:
        raise UnreadableDocument("nope")

    assert process(b"x", REG, broken).status is DocStatus.FAILED


def test_articles_are_valid_phase1_articles() -> None:
    from regulus.domain import Article

    for a in run([P1, P2]).articles:
        assert Article.model_validate_json(a.model_dump_json()) == a
