from .lexicon import Lexicon
from .models import (
    ChangeRef,
    Citation,
    ExtractionRequest,
    FieldState,
    FieldStatus,
    FieldValue,
    Modality,
    ObligationCandidate,
    RawCandidate,
    RawField,
    RawFieldState,
)
from .segment import find_markers


class _Counter:
    def __init__(self) -> None:
        self.dropped = 0


def _norm(word: str) -> str:
    return " ".join(word.lower().split())


def _verify(
    f: RawField, req: ExtractionRequest, within: list[tuple[int, int]]
) -> FieldValue | None:
    s, e = f.start, f.end
    ok = (
        0 <= s < e <= len(req.text)
        and req.text[s:e] == f.value
        and any(a <= s and e <= b for a, b in within)
    )
    if not ok:
        return None
    return FieldValue(
        value=f.value, citation=Citation(owner_id=req.owner_id, start=s, end=e, quote=f.value)
    )


def _state(
    st: RawFieldState, req: ExtractionRequest, within: list[tuple[int, int]], counter: _Counter
) -> FieldState:
    if st.status is FieldStatus.PRESENT and st.value is not None:
        v = _verify(st.value, req, within)
        if v is None:
            counter.dropped += 1
            return FieldState(status=FieldStatus.UNDETERMINED, reason="ungrounded value dropped")
        return FieldState(status=FieldStatus.PRESENT, value=v)
    if st.status is FieldStatus.UNDETERMINED:
        return FieldState(status=FieldStatus.UNDETERMINED, reason=st.reason or "undetermined")
    return FieldState(status=FieldStatus.NOT_STATED)


def ground(
    raw: RawCandidate,
    req: ExtractionRequest,
    lex: Lexicon,
    ref: ChangeRef,
    extractor: str,
    cand_id: str,
    counter: _Counter,
) -> ObligationCandidate | None:
    rs, re_ = req.region
    cs, ce = raw.clause
    if not (rs <= cs < ce <= re_):
        counter.dropped += 1
        return None
    word = _norm(raw.marker.value)
    mapping = {_norm(w): Modality.OBLIGATION for w in lex.obligation_markers}
    mapping |= {_norm(w): Modality.PROHIBITION for w in lex.prohibition_markers}
    if (
        mapping.get(word) is not raw.modality
        or find_markers(req.text, (raw.marker.start, raw.marker.end), lex)[:1] == []
    ):
        counter.dropped += 1
        return None
    clause_span = [(cs, ce)]
    marker = _verify(raw.marker, req, clause_span)
    if marker is None:
        counter.dropped += 1
        return None
    lead_in = None
    spans_for_lead = list(clause_span)
    if raw.lead_in is not None:
        ls, le = raw.lead_in
        if rs <= ls < le <= cs and req.text[ls:le].strip():
            lead_in = Citation(owner_id=req.owner_id, start=ls, end=le, quote=req.text[ls:le])
            spans_for_lead.append((ls, le))
        else:
            counter.dropped += 1
    structural = {tuple(p.span) for p in req.provisions}
    items = []
    for s, e in raw.items:
        if (s, e) in structural and cs <= s:
            items.append(Citation(owner_id=req.owner_id, start=s, end=e, quote=req.text[s:e]))
        else:
            counter.dropped += 1
    actor = _state(raw.actor, req, spans_for_lead, counter)
    action = _state(raw.action, req, clause_span, counter)
    if action.status is not FieldStatus.PRESENT:
        return None
    conditions, exceptions = [], []
    for f in raw.conditions:
        v = _verify(f, req, spans_for_lead)
        if v is None:
            counter.dropped += 1
        else:
            conditions.append(v)
    for f in raw.exceptions:
        v = _verify(f, req, clause_span)
        if v is None:
            counter.dropped += 1
        else:
            exceptions.append(v)
    try:
        return ObligationCandidate(
            id=cand_id,
            change_ref=ref,
            clause=Citation(owner_id=req.owner_id, start=cs, end=ce, quote=req.text[cs:ce]),
            modality=raw.modality,
            marker=marker,
            actor=actor,
            action=action,
            object=_state(raw.object, req, clause_span, counter),
            deadline=_state(raw.deadline, req, spans_for_lead, counter),
            frequency=_state(raw.frequency, req, clause_span, counter),
            conditions=tuple(conditions),
            exceptions=tuple(exceptions),
            undetermined=raw.undetermined,
            items=tuple(items),
            lead_in=lead_in,
            extractor=extractor,
        )
    except ValueError:
        counter.dropped += 1
        return None
