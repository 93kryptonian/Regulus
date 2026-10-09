from regulus.documents import DocStatus, ProcessedDocument
from regulus.documents.models import (
    AmendmentUnit,
    Code,
    Diagnostic,
    Document,
    Level,
    Provision,
    Severity,
)
from regulus.domain import Article
from regulus.domain.article import text_hash
from regulus.ingestion.models import (
    ArticleRef,
    DocumentIdentity,
    HeadingNormalization,
    IngestionResult,
    IngestionStatus,
    Issue,
    RegistryOutcome,
)

REG = "syn-ext-1"
BODY = "Setiap pelaku usaha wajib melaksanakan kewajiban dengan baik."


def article_text(n: str, body: str = BODY) -> str:
    return f"Pasal {n}\n{body}"


def identity(regulation_id: str = REG, key: str = "pk-1") -> DocumentIdentity:
    return DocumentIdentity(
        regulation_id=regulation_id,
        content_hash="c" * 64,
        text_fingerprint="f" * 64,
        size_bytes=10,
        ingestion_version="1",
        reader_config_hash="r" * 64,
        processing_key=key,
    )


def make_result(
    articles: list[tuple[str, str]] | None = None,
    amendments: list[tuple[str, str]] | None = None,
    status: IngestionStatus = IngestionStatus.INGESTED,
    issues: tuple[Issue, ...] = (),
    diagnostics: tuple[Diagnostic, ...] = (),
    provisions: tuple[Provision, ...] = (),
    normalizations: tuple[HeadingNormalization, ...] = (),
    key: str = "pk-1",
    ids: list[str] | None = None,
) -> IngestionResult:
    arts = (
        articles if articles is not None else [(str(i), article_text(str(i))) for i in range(1, 4)]
    )
    built = tuple(
        Article(
            id=(ids[i] if ids else f"{REG}:{n}"),
            regulation_id=REG,
            number=n,
            text=t,
            page_start=1 + i // 3,
            page_end=1 + i // 3,
            text_hash=text_hash(t),
        )
        for i, (n, t) in enumerate(arts)
    )
    units = tuple(
        AmendmentUnit(
            id=f"{REG}:unit-{label}",
            label=label,
            text=t,
            page_start=1,
            page_end=1,
            text_hash=text_hash(t),
        )
        for label, t in (amendments or [])
    )
    doc = ProcessedDocument(
        document=Document(
            id=REG,
            regulation_id=REG,
            content_hash="c" * 64,
            text_fingerprint="f" * 64,
            page_count=2,
        ),
        status=DocStatus.PROCESSED_OK,
        articles=built,
        amendment_units=units,
        provisions=provisions,
        diagnostics=diagnostics,
    )
    index = {
        a.number: ArticleRef(
            number=a.number, article_id=a.id, page_start=a.page_start, page_end=a.page_end
        )
        for a in built
    }
    return IngestionResult(
        identity=identity(key=key),
        status=status,
        registry=RegistryOutcome.NEW,
        processed=doc,
        normalizations=normalizations,
        article_index=index,
        issues=issues,
    )


def prov(
    owner: str, level: Level, path: tuple[str, ...], text: str, span: tuple[int, int]
) -> Provision:
    return Provision(owner_id=owner, level=level, path=path, text=text, span=span)


def diag(code: Code, page: int | None = None, detail: str = "") -> Diagnostic:
    return Diagnostic(code=code, severity=Severity.ERROR, page=page, detail=detail)
