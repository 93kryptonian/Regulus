import re
from collections.abc import Sequence

from regulus.documents import PdfPlumberReader  # noqa: F401  (type of reader wrapped below)
from regulus.documents.models import PageFailure, RawPage

from .models import HeadingNormalization

GLITCH = re.compile(r"^\s*Pasa([lI1|])\s*(\d{1,4})\s*$")
HEADING = re.compile(r"^\s*Pasal\s+(\d{1,4})\s*$")
Pages = Sequence[RawPage | PageFailure]
Position = tuple[int, int]


class PatchedReader:
    def __init__(self, inner: object, patches: dict[Position, str]) -> None:
        self.inner, self.patches = inner, patches

    def __call__(self, data: bytes) -> list[RawPage | PageFailure]:
        pages = self.inner(data)  # type: ignore[operator]
        out: list[RawPage | PageFailure] = []
        for p in pages:
            if isinstance(p, RawPage) and any(k[0] == p.number for k in self.patches):
                lines = p.text.split("\n")
                for (pg, ln), text in self.patches.items():
                    if pg == p.number:
                        lines[ln] = text
                out.append(p.model_copy(update={"text": "\n".join(lines)}))
            else:
                out.append(p)
        return out


def _lines(pages: Pages) -> list[tuple[Position, str]]:
    out: list[tuple[Position, str]] = []
    for p in pages:
        if isinstance(p, RawPage):
            out += [((p.number, i), t) for i, t in enumerate(p.text.split("\n"))]
    return out


def single_gaps(numbers: Sequence[int]) -> list[tuple[int, int, int]]:
    ordered = sorted(set(numbers))
    return [(a, a + 1, b) for a, b in zip(ordered, ordered[1:], strict=False) if b - a == 2]


def candidates(
    pages: Pages, numbers: Sequence[int], reported_gaps: set[int]
) -> list[HeadingNormalization]:
    lines = _lines(pages)
    headings = [(pos, int(m.group(1))) for pos, t in lines if (m := HEADING.match(t))]
    found: list[HeadingNormalization] = []
    for before, missing, after in single_gaps(numbers):
        if missing not in reported_gaps:
            continue
        hits = []
        for pos, text in lines:
            m = GLITCH.match(text)
            if not m or HEADING.match(text) or int(m.group(2)) != missing:
                continue
            prev = [n for p, n in headings if p < pos]
            nxt = [n for p, n in headings if p > pos]
            if prev and nxt and prev[-1] == before and nxt[0] == after:
                hits.append((pos, text))
        if len(hits) != 1:
            continue
        (pos, text) = hits[0]
        found.append(
            HeadingNormalization(
                article_number=missing,
                page=pos[0],
                line_index=pos[1],
                original=text,
                normalized=f"Pasal {missing}",
                previous_article=before,
                next_article=after,
            )
        )
    return found


def reverify(n: HeadingNormalization, present: dict[int, tuple[int, int]]) -> list[str]:
    bad: list[str] = []
    m = GLITCH.match(n.original)
    if not m or HEADING.match(n.original) or int(m.group(2)) != n.article_number:
        bad.append("original is not a glitched heading for this article")
    if n.normalized != f"Pasal {n.article_number}":
        bad.append("normalized heading does not name the article")
    if (n.previous_article, n.next_article) != (n.article_number - 1, n.article_number + 1):
        bad.append("neighbours are not the adjacent articles")
    for k in (n.previous_article, n.article_number, n.next_article):
        if k not in present:
            bad.append(f"article {k} is not in the processed document")
    if not bad:
        lo, hi = present[n.previous_article][0], present[n.next_article][1]
        if not lo <= n.page <= hi:
            bad.append("heading page lies outside its neighbours")
    return bad
