import re
from collections import Counter
from collections.abc import Sequence

from regulus.domain import Obligation, ObligationEvidence, ObligationStatus, Origin
from regulus.obligations import FieldStatus, Lexicon, ObligationCandidate
from regulus.obligations.models import ENUMERATED_ITEMS
from regulus.obligations.segment import find_markers

from .models import PermittedSource, RawGenerated, Violation
from .trace import expected

NEGATIONS = {"tidak", "bukan", "jangan", "tanpa"}


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _find(hay: list[str], needle: list[str], start: int = 0) -> int | None:
    n = len(needle)
    for i in range(start, len(hay) - n + 1):
        if hay[i : i + n] == needle:
            return i
    return None


def _spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"\w+", text)]


class _Field:
    def __init__(self, role: str, toks: list[str], seg: int, a: int, b: int) -> None:
        self.role, self.toks, self.seg, self.a, self.b = role, toks, seg, a, b


def _layout(candidate: ObligationCandidate, source: PermittedSource) -> list[_Field]:
    segments: list[tuple[int, str]] = []
    if candidate.lead_in is not None and source.lead_in is not None:
        segments.append((candidate.lead_in.start, source.lead_in))
    segments.append((candidate.clause.start, source.clause))
    for item, text in zip(candidate.items, source.items, strict=False):
        segments.append((item.start, text))
    spans = [_spans(t) for _, t in segments]

    def place(role: str, start: int, end: int) -> _Field | None:
        for i, (off, text) in enumerate(segments):
            if off <= start and end <= off + len(text):
                idx = [
                    j for j, (x, y) in enumerate(spans[i]) if off + x >= start and off + y <= end
                ]
                if idx:
                    return _Field(
                        role, tokens(text[start - off : end - off]), i, idx[0], idx[-1] + 1
                    )
        return None

    out: list[tuple[int, _Field]] = []
    seen: set[tuple[int, int]] = set()

    def add(role: str, start: int, end: int) -> None:
        if (start, end) in seen:
            return
        seen.add((start, end))
        f = place(role, start, end)
        if f is not None:
            out.append((start, f))

    add("marker", candidate.marker.citation.start, candidate.marker.citation.end)
    for role in ("actor", "action", "object", "deadline", "frequency"):
        st = getattr(candidate, role)
        if st.status is FieldStatus.PRESENT and st.value:
            add(role, st.value.citation.start, st.value.citation.end)
    for role, values in (("condition", candidate.conditions), ("exception", candidate.exceptions)):
        for v in values:
            add(role, v.citation.start, v.citation.end)
    for c in candidate.items:
        add("item", c.start, c.end)
    return [f for _, f in sorted(out, key=lambda t: (t[0], t[1].role))]


def _chain(text: list[str], fields: list[_Field], i: int, pos: int, prev: _Field | None) -> bool:
    if i == len(fields):
        return True
    f = fields[i]
    if prev is not None and prev.seg == f.seg and f.a >= prev.b:
        at = pos + (f.a - prev.b)
        starts = [at] if text[at : at + len(f.toks)] == f.toks else []
    else:
        starts = [
            j
            for j in range(pos, len(text) - len(f.toks) + 1)
            if text[j : j + len(f.toks)] == f.toks
        ]
    return any(_chain(text, fields, i + 1, st + len(f.toks), f) for st in starts)


def verify_raw(
    candidate: ObligationCandidate, source: PermittedSource, raw: RawGenerated, lex: Lexicon
) -> list[Violation]:
    found: list[Violation] = []

    def add(v: Violation) -> None:
        if v not in found:
            found.append(v)

    text = " ".join(raw.text.split())
    t_tokens, s_tokens = tokens(text), tokens(source.all_text())
    if not text:
        add(Violation.REQUIRED_MISSING)
    enumerated = (
        candidate.action.status is FieldStatus.UNDETERMINED
        and candidate.action.reason == ENUMERATED_ITEMS
    )
    if candidate.action.status is not FieldStatus.PRESENT and not (enumerated and candidate.items):
        add(Violation.REQUIRED_MISSING)
    extra = Counter(t_tokens) - Counter(s_tokens)
    if extra:
        add(Violation.NEW_WORD)
    layout = _layout(candidate, source)
    for f in layout:
        if f.toks and _find(t_tokens, f.toks) is None:
            add(Violation.FIELD_LOST)
    if Violation.FIELD_LOST not in found and not _chain(
        t_tokens, [f for f in layout if f.toks], 0, 0, None
    ):
        add(Violation.ORDER_CHANGED)
    present = [(0, f.role, f.toks) for f in layout if f.toks]
    marks = Counter(m.word for m in find_markers(text, (0, len(text)), lex))
    allowed = Counter(
        m.word for m in find_markers(source.all_text(), (0, len(source.all_text())), lex)
    )
    if marks - allowed or " ".join(tokens(candidate.marker.value)) not in {
        " ".join(tokens(m)) for m in marks.elements()
    }:
        add(Violation.MODALITY_CHANGED)
    if Counter(w for w in t_tokens if w in NEGATIONS) - Counter(
        w for w in s_tokens if w in NEGATIONS
    ):
        add(Violation.MODALITY_CHANGED)
    digits, src_digits = (
        Counter(re.findall(r"\d+", text)),
        Counter(re.findall(r"\d+", source.all_text())),
    )
    field_digits: Counter[str] = Counter()
    for _, _, toks in present:
        field_digits.update(w for w in toks if w.isdigit())
    if digits - src_digits or field_digits - digits:
        add(Violation.NUMBER_CHANGED)
    want_content, want_trace = expected(candidate)
    if raw.content != want_content:
        add(Violation.FIELD_ALTERED)
    if raw.trace != want_trace:
        add(Violation.TRACE_INVALID)
    return found


def verify_evidence(
    evidence: Sequence[ObligationEvidence],
    candidate: ObligationCandidate,
    owner_text: str,
    obligation_id: str,
) -> list[Violation]:
    cites = {(candidate.clause.owner_id, candidate.clause.start, candidate.clause.end)}
    cites.add(
        (
            candidate.marker.citation.owner_id,
            candidate.marker.citation.start,
            candidate.marker.citation.end,
        )
    )
    for c in (*candidate.items, *([candidate.lead_in] if candidate.lead_in else [])):
        cites.add((c.owner_id, c.start, c.end))
    for role in ("actor", "action", "object", "deadline", "frequency"):
        v = getattr(candidate, role).value
        if v:
            cites.add((v.citation.owner_id, v.citation.start, v.citation.end))
    for v in (*candidate.conditions, *candidate.exceptions):
        cites.add((v.citation.owner_id, v.citation.start, v.citation.end))
    if not evidence:
        return [Violation.CITATION_MISMATCH]
    for e in evidence:
        if (
            e.obligation_id != obligation_id
            or (e.owner_id, e.span[0], e.span[1]) not in cites
            or owner_text[e.span[0] : e.span[1]] != e.quote
        ):
            return [Violation.CITATION_MISMATCH]
    if (candidate.clause.owner_id, candidate.clause.start, candidate.clause.end) not in {
        (e.owner_id, e.span[0], e.span[1]) for e in evidence
    }:
        return [Violation.CITATION_MISMATCH]
    return []


def verify_obligation(
    obligation: Obligation, candidate: ObligationCandidate, origin: Origin
) -> list[Violation]:
    bad = (
        obligation.status is not ObligationStatus.GENERATED
        or obligation.current != obligation.generated.content
        or obligation.origin is not origin
        or (obligation.generated.meta is not None) != (origin is Origin.AI)
        or obligation.source_owner_id != candidate.clause.owner_id
    )
    return [Violation.LIFECYCLE_INVALID] if bad else []
