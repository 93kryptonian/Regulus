from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .models import Page, SourceSpan


@dataclass(frozen=True)
class Line:
    page: int
    start: int
    end: int
    text: str


def page_lines(page: Page) -> list[Line]:
    out, pos = [], 0
    for text in page.text.split("\n"):
        out.append(Line(page.number, pos, pos + len(text), text))
        pos += len(text) + 1
    return out


@dataclass(frozen=True)
class Built:
    text: str
    fragments: tuple[SourceSpan, ...]
    bases: tuple[int, ...]


def build(lines: Sequence[Line], pages: Mapping[int, Page], document_id: str) -> Built | None:
    groups: list[tuple[int, int, int]] = []
    for ln in lines:
        if groups and groups[-1][0] == ln.page:
            groups[-1] = (ln.page, groups[-1][1], ln.end)
        else:
            groups.append((ln.page, ln.start, ln.end))
    frags, parts, bases, base = [], [], [], 0
    for page, s, e in groups:
        t = pages[page].text
        while s < e and t[s].isspace():
            s += 1
        while e > s and t[e - 1].isspace():
            e -= 1
        if s == e:
            continue
        frags.append(SourceSpan(document_id=document_id, page=page, start=s, end=e))
        parts.append(t[s:e])
        bases.append(base)
        base += e - s + 1
    if not frags:
        return None
    return Built("\n".join(parts), tuple(frags), tuple(bases))


def reconstruct(fragments: Sequence[SourceSpan], pages: Mapping[int, Page]) -> str:
    return "\n".join(pages[f.page].text[f.start : f.end] for f in fragments)


def locate(fragments: Sequence[SourceSpan], start: int, end: int) -> tuple[SourceSpan, ...]:
    total = sum(f.end - f.start for f in fragments) + len(fragments) - 1
    if not 0 <= start < end <= total:
        raise ValueError("span outside owner text")
    out, base = [], 0
    for f in fragments:
        n = f.end - f.start
        lo, hi = max(start, base), min(end, base + n)
        if lo < hi:
            out.append(
                SourceSpan(
                    document_id=f.document_id,
                    page=f.page,
                    start=f.start + lo - base,
                    end=f.start + hi - base,
                )
            )
        base += n + 1
    return tuple(out)


def owner_offset(built: Built, line: Line, at_end: bool = False) -> int:
    for f, base in zip(built.fragments, built.bases, strict=True):
        if f.page == line.page and (line.start <= f.end and line.end >= f.start):
            pos = line.end if at_end else line.start
            return base + min(max(pos, f.start), f.end) - f.start
    return 0
