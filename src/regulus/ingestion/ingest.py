from regulus.documents import DocStatus, ProcessedDocument, process
from regulus.documents.models import Code
from regulus.documents.reader import PageReader

from .headings import PatchedReader, candidates, reverify
from .identity import INGESTION_VERSION, identity_for, processing_key, reader_config_hash, sha256
from .models import (
    ArticleRef,
    DocumentIdentity,
    HeadingNormalization,
    IngestionResult,
    IngestionStatus,
    Issue,
    IssueCode,
    RegistryOutcome,
)
from .registry import IngestionRegistry

_CODES = {c.value: IssueCode(c.value) for c in Code if c.value in IssueCode.__members__}


def _plain_numbers(doc: ProcessedDocument) -> list[int]:
    return [int(a.number) for a in doc.articles if a.number.isdigit()]


def _reported_gaps(doc: ProcessedDocument) -> set[int]:
    out: set[int] = set()
    for d in doc.diagnostics:
        if d.code is Code.ARTICLE_GAP and d.detail.isdigit():
            out.add(int(d.detail))
    return out


def _index(doc: ProcessedDocument) -> dict[str, ArticleRef]:
    return {
        a.number: ArticleRef(
            number=a.number, article_id=a.id, page_start=a.page_start, page_end=a.page_end
        )
        for a in doc.articles
    }


def _issues(doc: ProcessedDocument, norms: tuple[HeadingNormalization, ...]) -> tuple[Issue, ...]:
    out = [
        Issue(
            code=IssueCode.HEADING_NORMALIZED,
            article_number=str(n.article_number),
            detail=n.original,
        )
        for n in norms
    ]
    for d in doc.diagnostics:
        if d.severity.value == "ERROR" or d.code is Code.ANNEX_NOT_PROCESSED:
            out.append(
                Issue(
                    code=_CODES.get(d.code.value, IssueCode.OTHER_ERROR),
                    article_number=d.article_number,
                    detail=d.detail,
                )
            )
    return tuple(out)


def _refused(
    regulation_id: str, data: bytes, owner: str, reader: PageReader, normalize: bool
) -> IngestionResult:
    ident = identity_for(regulation_id, data, "", reader, normalize)
    return IngestionResult(
        identity=ident,
        status=IngestionStatus.REFUSED,
        registry=RegistryOutcome.DUPLICATE_CONTENT,
        issues=(
            Issue(
                code=IssueCode.DUPLICATE_CONTENT, detail=f"content already registered under {owner}"
            ),
        ),
    )


def _outcome(registry: IngestionRegistry, ident: DocumentIdentity) -> RegistryOutcome:
    versions = registry.versions(ident.regulation_id)
    if any(h == ident.content_hash for h, _ in versions):
        return RegistryOutcome.REPROCESSED
    if not versions:
        return RegistryOutcome.NEW
    if any(fp == ident.text_fingerprint for _, fp in versions):
        return RegistryOutcome.RERENDERED
    return RegistryOutcome.NEW_VERSION


def ingest(
    data: bytes,
    regulation_id: str,
    reader: PageReader,
    registry: IngestionRegistry,
    normalize_headings: bool = True,
) -> IngestionResult:
    content = sha256(data)
    owner = registry.owner_of(content)
    if owner is not None and owner != regulation_id:
        return _refused(regulation_id, data, owner, reader, normalize_headings)
    key = processing_key(content, INGESTION_VERSION, reader_config_hash(reader, normalize_headings))
    known = registry.find(regulation_id, key)
    if known is not None:
        return known.model_copy(update={"registry": RegistryOutcome.UNCHANGED})
    doc = process(data, regulation_id, reader)
    norms: tuple[HeadingNormalization, ...] = ()
    if normalize_headings and doc.status is not DocStatus.FAILED:
        gaps = _reported_gaps(doc)
        if gaps:
            raw = reader(data)
            found = candidates(raw, _plain_numbers(doc), gaps)
            if found:
                patched = process(
                    data,
                    regulation_id,
                    PatchedReader(reader, {(n.page, n.line_index): n.normalized for n in found}),
                )
                present = {
                    int(a.number): (a.page_start, a.page_end)
                    for a in patched.articles
                    if a.number.isdigit()
                }
                good = tuple(
                    n for n in found if n.article_number in present and not reverify(n, present)
                )
                if good and len(good) == len(found):
                    doc, norms = patched, good
    ident = identity_for(
        regulation_id, data, doc.document.text_fingerprint, reader, normalize_headings
    )
    if doc.status is DocStatus.FAILED:
        return IngestionResult(
            identity=ident,
            status=IngestionStatus.FAILED,
            registry=RegistryOutcome.NOT_REGISTERED,
            processed=doc,
            issues=(
                Issue(
                    code=IssueCode.UNREADABLE_DOCUMENT if not doc.pages else IssueCode.PAGE_FAILED
                ),
            ),
        )
    issues = _issues(doc, norms)
    clean = doc.status is DocStatus.PROCESSED_OK and not norms
    result = IngestionResult(
        identity=ident,
        status=IngestionStatus.INGESTED if clean else IngestionStatus.INGESTED_WITH_ISSUES,
        registry=_outcome(registry, ident),
        processed=doc,
        normalizations=norms,
        article_index=_index(doc),
        issues=issues,
    )
    registry.add(result)
    return result


__all__ = ["ingest"]
