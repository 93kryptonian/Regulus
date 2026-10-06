from enum import StrEnum

from pydantic import ConfigDict, Field, model_validator

from regulus.domain import Article
from regulus.domain.base import Model


class PageSource(StrEnum):
    NATIVE = "NATIVE"
    OCR = "OCR"


class PageStatus(StrEnum):
    OK = "OK"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


class DocStatus(StrEnum):
    PROCESSED_OK = "PROCESSED_OK"
    PROCESSED_WITH_ISSUES = "PROCESSED_WITH_ISSUES"
    PARTIAL = "PARTIAL"
    PROCESSED_EMPTY = "PROCESSED_EMPTY"
    FAILED = "FAILED"


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class Code(StrEnum):
    PAGE_FAILED = "PAGE_FAILED"
    ARTICLE_GAP = "ARTICLE_GAP"
    DUPLICATE_ARTICLE = "DUPLICATE_ARTICLE"
    BODY_MODE_CONFLICT = "BODY_MODE_CONFLICT"
    MIXED_BODY_FORMS = "MIXED_BODY_FORMS"
    NO_BODY_UNITS = "NO_BODY_UNITS"
    MARKER_OUT_OF_SEQUENCE = "MARKER_OUT_OF_SEQUENCE"
    PAGE_EMPTY = "PAGE_EMPTY"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    ENCODING_ISSUE = "ENCODING_ISSUE"
    ANNEX_NOT_PROCESSED = "ANNEX_NOT_PROCESSED"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"


ERRORS = {
    Code.PAGE_FAILED,
    Code.ARTICLE_GAP,
    Code.DUPLICATE_ARTICLE,
    Code.BODY_MODE_CONFLICT,
    Code.MIXED_BODY_FORMS,
    Code.NO_BODY_UNITS,
}


class Level(StrEnum):
    AYAT = "AYAT"
    HURUF = "HURUF"
    ANGKA = "ANGKA"


class Exact(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=False)


class RawPage(Exact):
    number: int = Field(ge=1)
    source: PageSource
    text: str
    ocr_engine: str | None = None
    ocr_confidence: float | None = None


class PageFailure(Model):
    number: int = Field(ge=1)
    error: str


class RemovedLine(Exact):
    index: int = Field(ge=0)
    text: str


class Page(Exact):
    number: int = Field(ge=1)
    label: str | None = None
    source: PageSource = PageSource.NATIVE
    status: PageStatus
    text: str = ""
    removed: tuple[RemovedLine, ...] = ()
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    error: str | None = None


class SourceSpan(Model):
    document_id: str
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> "SourceSpan":
        if self.end < self.start:
            raise ValueError("end < start")
        return self


class Document(Model):
    id: str
    regulation_id: str
    content_hash: str
    text_fingerprint: str
    page_count: int = Field(ge=0)


class AmendmentUnit(Model):
    id: str
    label: str
    text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    text_hash: str


class Provision(Exact):
    owner_id: str
    level: Level
    path: tuple[str, ...]
    text: str
    span: tuple[int, int]


class Explanation(Model):
    article_number: str
    text: str = Field(min_length=1)
    fragments: tuple[SourceSpan, ...]


class Diagnostic(Model):
    code: Code
    severity: Severity
    page: int | None = None
    article_number: str | None = None
    detail: str = ""


class ProcessedDocument(Model):
    document: Document
    status: DocStatus
    pages: tuple[Page, ...] = ()
    articles: tuple[Article, ...] = ()
    amendment_units: tuple[AmendmentUnit, ...] = ()
    provenance: dict[str, tuple[SourceSpan, ...]] = {}
    provisions: tuple[Provision, ...] = ()
    explanations: tuple[Explanation, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
