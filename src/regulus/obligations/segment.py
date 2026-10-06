import re
from dataclasses import dataclass

from regulus.documents.models import Level, Provision

from .lexicon import Lexicon, alternation
from .models import Modality

_HEADING = re.compile(r"^[ \t]*Pasal\s*\d+[A-Z]?[ \t]*(?:\n|$)")
_LABEL = re.compile(r"^(?:\(\s*\d+[a-z]?\s*\)|[a-z]\.|\d+\.)\s+")


@dataclass(frozen=True)
class Marker:
    start: int
    end: int
    word: str
    modality: Modality | None
    negated: bool


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    term: str


def prepare_region(text: str, region: tuple[int, int]) -> tuple[int, int]:
    s, e = region
    while s < e and text[s].isspace():
        s += 1
    while (m := _HEADING.match(text[s:e])) and m.end() > 0:
        s += m.end()
        while s < e and text[s].isspace():
            s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


def marker_pattern(lex: Lexicon) -> re.Pattern[str]:
    terms = lex.negated_markers + lex.prohibition_markers + lex.obligation_markers
    return re.compile(r"(?<!\w)(?:" + alternation(terms) + r")(?!\w)", re.IGNORECASE)


def _classify(word: str, lex: Lexicon) -> tuple[Modality | None, bool]:
    w = " ".join(word.lower().split())
    if w in lex.negated_markers:
        return None, True
    if w in lex.prohibition_markers:
        return Modality.PROHIBITION, False
    return Modality.OBLIGATION, False


def find_markers(text: str, region: tuple[int, int], lex: Lexicon) -> list[Marker]:
    pat = marker_pattern(lex)
    out = []
    for m in pat.finditer(text, region[0], region[1]):
        modality, negated = _classify(m.group(0), lex)
        out.append(
            Marker(m.start(), m.end(), " ".join(m.group(0).lower().split()), modality, negated)
        )
    return out


def sentences(
    text: str, region: tuple[int, int], lex: Lexicon, provisions: tuple[Provision, ...]
) -> list[Sentence]:
    s0, e0 = region
    cuts = {p.span[0] for p in provisions if s0 < p.span[0] < e0}
    abbr = {a.lower() for a in lex.abbreviations}
    out: list[Sentence] = []
    start, depth, i = s0, 0, s0
    while i < e0:
        ch = text[i]
        if i in cuts and i > start:
            out.append(Sentence(start, i, ""))
            start, depth = i, 0
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in ".;:" and depth == 0 and (i + 1 == e0 or text[i + 1].isspace()):
            ws = i
            while ws > start and not text[ws - 1].isspace():
                ws -= 1
            tok = text[ws:i].lower()
            line_start = ws == start or text[ws - 1] == "\n"
            listmark = ch == "." and line_start and (re.fullmatch(r"\d+|[a-z]", tok) is not None)
            if not (ch == "." and (tok in abbr or listmark)):
                out.append(Sentence(start, i, ch))
                start = i + 1
        i += 1
    if start < e0:
        out.append(Sentence(start, e0, ""))
    trimmed = []
    for s in out:
        a, b = s.start, s.end
        while a < b and text[a].isspace():
            a += 1
        if (m := _LABEL.match(text[a:b])) and (a in cuts or a == s0 or text[a - 1] == "\n"):
            a += m.end()
        while b > a and text[b - 1].isspace():
            b -= 1
        if a < b:
            trimmed.append(Sentence(a, b, s.term))
    return trimmed


def enclosing(provisions: tuple[Provision, ...], pos: int) -> Provision | None:
    inside = [p for p in provisions if p.span[0] <= pos < p.span[1]]
    return max(inside, key=lambda p: len(p.path), default=None)


def items_after(provisions: tuple[Provision, ...], sentence: Sentence) -> tuple[Provision, ...]:
    parent = enclosing(provisions, sentence.start)
    base = parent.path if parent else ()
    out = []
    for p in sorted(provisions, key=lambda p: p.span):
        if p.span[0] < sentence.end:
            continue
        if len(p.path) <= len(base) or p.path[: len(base)] != base:
            break
        if len(p.path) == len(base) + 1 and p.level in (Level.HURUF, Level.ANGKA):
            out.append(p)
    return tuple(out)
