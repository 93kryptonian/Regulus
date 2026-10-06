import hashlib

from .clean import clean, page_diagnostics
from .models import (
    ERRORS,
    Code,
    Diagnostic,
    DocStatus,
    Document,
    PageStatus,
    ProcessedDocument,
    Severity,
)
from .reader import PageReader, UnreadableDocument
from .segment import segment


def _sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def process(data: bytes, regulation_id: str, reader: PageReader) -> ProcessedDocument:
    content_hash = _sha(data)
    doc_id = f"doc-{content_hash[:16]}"
    try:
        raws = reader(data)
    except UnreadableDocument as e:
        doc = Document(
            id=doc_id,
            regulation_id=regulation_id,
            content_hash=content_hash,
            text_fingerprint=_sha(""),
            page_count=0,
        )
        diag = Diagnostic(code=Code.UNREADABLE_DOCUMENT, severity=Severity.ERROR, detail=str(e))
        return ProcessedDocument(document=doc, status=DocStatus.FAILED, diagnostics=(diag,))
    pages = clean(raws)
    seg = segment(pages, regulation_id, doc_id)
    diags = page_diagnostics(pages) + seg.diagnostics
    failed = sum(p.status is PageStatus.FAILED for p in pages)
    if failed == len(pages):
        status = DocStatus.FAILED
    elif failed:
        status = DocStatus.PARTIAL
    elif not (seg.articles or seg.units):
        status = DocStatus.PROCESSED_EMPTY
        diags.append(Diagnostic(code=Code.NO_BODY_UNITS, severity=Severity.ERROR))
    elif any(d.code in ERRORS for d in diags):
        status = DocStatus.PROCESSED_WITH_ISSUES
    else:
        status = DocStatus.PROCESSED_OK
    doc = Document(
        id=doc_id,
        regulation_id=regulation_id,
        content_hash=content_hash,
        text_fingerprint=_sha("\n".join(p.text for p in pages)),
        page_count=len(pages),
    )
    return ProcessedDocument(
        document=doc,
        status=status,
        pages=tuple(pages),
        articles=tuple(seg.articles),
        amendment_units=tuple(seg.units),
        provenance=seg.provenance,
        provisions=tuple(seg.provisions),
        explanations=tuple(seg.explanations),
        diagnostics=tuple(diags),
    )
