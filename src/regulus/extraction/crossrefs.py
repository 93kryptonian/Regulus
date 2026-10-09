import re
from dataclasses import dataclass

from .models import CrossReferenceGraph, Edge, UnitKind, UnresolvedReference

_MENTION = re.compile(
    r"(?<!\w)Pasal\s+(?P<n>\d+[A-Za-z]?)(?!\w)(?:\s+ayat\s*\(\s*\d+[A-Za-z]?\s*\))?", re.IGNORECASE
)
_EXTERNAL = re.compile(
    r"\s+(?:huruf\s+[a-z]\s+)?(?:angka\s+\d+\s+)?(?:Undang-Undang|Peraturan|UU|PP|Perppu|Perpu|Kitab|Keputusan)(?!\w)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Mention:
    label: str
    start: int
    end: int
    external: bool


def mentions(text: str) -> list[Mention]:
    out = []
    for m in _MENTION.finditer(text):
        ext = _EXTERNAL.match(text, m.end()) is not None
        out.append(Mention(m.group("n").upper(), m.start(), m.end(), ext))
    return out


def build_graph(units: list[tuple[str, UnitKind, str, str]]) -> CrossReferenceGraph:
    by_label = {label.upper(): uid for uid, kind, label, _ in units if kind is UnitKind.ARTICLE}
    edges: list[Edge] = []
    unresolved: list[UnresolvedReference] = []
    for uid, kind, label, text in units:
        if kind is not UnitKind.ARTICLE:
            continue
        for m in mentions(text):
            if m.label == label.upper() and not m.external:
                continue
            target = by_label.get(m.label)
            if target is None or m.external:
                unresolved.append(
                    UnresolvedReference(
                        from_unit=uid, label=m.label, start=m.start, end=m.end, external=m.external
                    )
                )
            else:
                edges.append(Edge(from_unit=uid, to_unit=target, start=m.start, end=m.end))
    return CrossReferenceGraph(
        edges=tuple(sorted(edges, key=lambda e: (e.from_unit, e.start, e.end, e.to_unit))),
        unresolved=tuple(sorted(unresolved, key=lambda u: (u.from_unit, u.start, u.end, u.label))),
    )
