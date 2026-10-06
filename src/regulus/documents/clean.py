import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from .models import (
    Code,
    Diagnostic,
    Page,
    PageFailure,
    PageStatus,
    RawPage,
    RemovedLine,
    Severity,
)

LABEL = re.compile(r"^\s*-\s*(\d+)\s*-\s*$")
HEAD, TAIL, MIN_PAGES, SHARE = 6, 4, 4, 0.5
LOW_OCR = 0.6


def newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _key(line: str) -> str:
    return " ".join(line.split()).casefold()


def _edge_keys(lines: list[str]) -> set[str]:
    body = [_key(ln) for ln in lines if ln.strip()]
    return set(body[:HEAD]) | set(body[-TAIL:])


def clean(raws: Sequence[RawPage | PageFailure]) -> list[Page]:
    texts = {r.number: newlines(r.text).split("\n") for r in raws if isinstance(r, RawPage)}
    counts: Counter[str] = Counter()
    for lines in texts.values():
        counts.update(_edge_keys(lines))
    noise = (
        {k for k, c in counts.items() if c / len(texts) >= SHARE}
        if len(texts) >= MIN_PAGES
        else set()
    )
    pages: list[Page] = []
    for r in raws:
        if isinstance(r, PageFailure):
            pages.append(Page(number=r.number, status=PageStatus.FAILED, error=r.error))
            continue
        kept, removed, label = [], [], None
        for i, ln in enumerate(texts[r.number]):
            m = LABEL.match(ln)
            if m or (ln.strip() and _key(ln) in noise):
                removed.append(RemovedLine(index=i, text=ln))
                label = m.group(1) if m else label
            else:
                kept.append(ln)
        text = "\n".join(kept)
        pages.append(
            Page(
                number=r.number,
                label=label,
                source=r.source,
                status=PageStatus.OK if text.strip() else PageStatus.EMPTY,
                text=text,
                removed=tuple(removed),
                ocr_engine=r.ocr_engine,
                ocr_confidence=r.ocr_confidence,
            )
        )
    return pages


def page_diagnostics(pages: Sequence[Page]) -> list[Diagnostic]:
    out = []
    for p in pages:
        if p.status is PageStatus.FAILED:
            out.append(
                Diagnostic(
                    code=Code.PAGE_FAILED,
                    severity=Severity.ERROR,
                    page=p.number,
                    detail=p.error or "",
                )
            )
        if p.status is PageStatus.EMPTY:
            out.append(Diagnostic(code=Code.PAGE_EMPTY, severity=Severity.WARNING, page=p.number))
        if any(c == "�" or (unicodedata.category(c) == "Cc" and c not in "\n\t") for c in p.text):
            out.append(
                Diagnostic(code=Code.ENCODING_ISSUE, severity=Severity.WARNING, page=p.number)
            )
        if p.ocr_confidence is not None and p.ocr_confidence < LOW_OCR:
            out.append(
                Diagnostic(
                    code=Code.LOW_OCR_CONFIDENCE,
                    severity=Severity.WARNING,
                    page=p.number,
                    detail=f"{p.ocr_confidence:.2f}",
                )
            )
    return out
