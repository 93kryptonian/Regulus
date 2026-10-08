from enum import StrEnum

from regulus.documents import ProcessedDocument
from regulus.domain.base import Model


class IngestionStatus(StrEnum):
    INGESTED = "INGESTED"
    INGESTED_WITH_ISSUES = "INGESTED_WITH_ISSUES"
    FAILED = "FAILED"
    REFUSED = "REFUSED"


class RegistryOutcome(StrEnum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    NEW_VERSION = "NEW_VERSION"
    RERENDERED = "RERENDERED"
    REPROCESSED = "REPROCESSED"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    NOT_REGISTERED = "NOT_REGISTERED"


class IssueCode(StrEnum):
    HEADING_NORMALIZED = "HEADING_NORMALIZED"
    ARTICLE_GAP = "ARTICLE_GAP"
    DUPLICATE_ARTICLE = "DUPLICATE_ARTICLE"
    PAGE_FAILED = "PAGE_FAILED"
    NO_BODY_UNITS = "NO_BODY_UNITS"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"
    ANNEX_NOT_PROCESSED = "ANNEX_NOT_PROCESSED"
    OTHER_ERROR = "OTHER_ERROR"


class Issue(Model):
    code: IssueCode
    article_number: str | None = None
    detail: str = ""


class DocumentIdentity(Model):
    regulation_id: str
    content_hash: str
    text_fingerprint: str
    size_bytes: int
    ingestion_version: str
    reader_config_hash: str
    processing_key: str


class ArticleRef(Model):
    number: str
    article_id: str
    page_start: int
    page_end: int


class HeadingNormalization(Model):
    article_number: int
    page: int
    line_index: int
    original: str
    normalized: str
    previous_article: int
    next_article: int


class IngestionResult(Model):
    identity: DocumentIdentity
    status: IngestionStatus
    registry: RegistryOutcome
    processed: ProcessedDocument | None = None
    normalizations: tuple[HeadingNormalization, ...] = ()
    article_index: dict[str, ArticleRef] = {}
    issues: tuple[Issue, ...] = ()
