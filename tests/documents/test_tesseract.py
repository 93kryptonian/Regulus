import shutil

import pytest
from pdfgen import Scan, make_pdf

from regulus.documents import DocStatus, PdfPlumberReader, TesseractOcr, process

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")

TEXT = "BAB I\nPasal 1\nEvery controller shall report annually."


def test_real_ocr_recovers_structure_from_a_scanned_page() -> None:
    ocr = TesseractOcr(lang="eng")
    r = process(make_pdf([Scan(TEXT)]), "REG-1", PdfPlumberReader(ocr))
    page = r.pages[0]
    assert (
        page.source.value == "OCR" and page.ocr_engine and page.ocr_engine.startswith("tesseract")
    )
    assert "Pasal 1" in page.text and r.status is DocStatus.PROCESSED_OK
    assert [a.number for a in r.articles] == ["1"]
