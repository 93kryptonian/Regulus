import io
from collections.abc import Sequence
from typing import Protocol

import pdfplumber

from regulus.domain.base import Model

from .models import PageFailure, PageSource, RawPage


class UnreadableDocument(Exception):
    pass


class OcrResult(Model):
    text: str
    confidence: float | None = None


class OcrEngine(Protocol):
    name: str

    def recognize(self, png: bytes) -> OcrResult: ...


class PageReader(Protocol):
    def __call__(self, data: bytes) -> Sequence[RawPage | PageFailure]: ...


def _chars(text: str) -> int:
    return sum(not c.isspace() for c in text)


class PdfPlumberReader:
    def __init__(self, ocr: OcrEngine | None = None, min_chars: int = 50, dpi: int = 200) -> None:
        self.ocr, self.min_chars, self.dpi = ocr, min_chars, dpi

    def __call__(self, data: bytes) -> list[RawPage | PageFailure]:
        try:
            pdf = pdfplumber.open(io.BytesIO(data))
        except Exception as e:
            raise UnreadableDocument(f"{type(e).__name__}: {e}") from e
        out: list[RawPage | PageFailure] = []
        with pdf:
            if not pdf.pages:
                raise UnreadableDocument("no pages")
            for n, page in enumerate(pdf.pages, 1):
                try:
                    out.append(self._page(n, page))
                except Exception as e:
                    out.append(PageFailure(number=n, error=f"{type(e).__name__}: {e}"))
        return out

    def _page(self, n: int, page: pdfplumber.page.Page) -> RawPage | PageFailure:
        text = page.extract_text() or ""
        if _chars(text) >= self.min_chars:
            return RawPage(number=n, source=PageSource.NATIVE, text=text)
        if self.ocr is None:
            if _chars(text) == 0 and page.images:
                return PageFailure(number=n, error="no text layer and no OCR engine")
            return RawPage(number=n, source=PageSource.NATIVE, text=text)
        buf = io.BytesIO()
        page.to_image(resolution=self.dpi).original.save(buf, format="PNG")
        res = self.ocr.recognize(buf.getvalue())
        if _chars(res.text) < _chars(text):
            return RawPage(number=n, source=PageSource.NATIVE, text=text)
        return RawPage(
            number=n,
            source=PageSource.OCR,
            text=res.text,
            ocr_engine=self.ocr.name,
            ocr_confidence=res.confidence,
        )


class TesseractOcr:
    def __init__(self, lang: str = "ind") -> None:
        import pytesseract

        self._t, self.lang = pytesseract, lang
        self.name = f"tesseract-{pytesseract.get_tesseract_version()}-{lang}"

    def recognize(self, png: bytes) -> OcrResult:
        from PIL import Image

        img = Image.open(io.BytesIO(png))
        text = self._t.image_to_string(img, lang=self.lang)
        d = self._t.image_to_data(img, lang=self.lang, output_type=self._t.Output.DICT)
        conf = [float(c) for c in d["conf"] if float(c) >= 0]
        return OcrResult(text=text, confidence=sum(conf) / len(conf) / 100 if conf else None)
