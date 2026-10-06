import re
from dataclasses import dataclass, field

from regulus.documents.models import Level, Provision

from .lexicon import Lexicon, alternation, load_lexicon
from .models import (
    ExtractionRequest,
    FieldStatus,
    Modality,
    RawCandidate,
    RawField,
    RawFieldState,
)
from .segment import Marker, Sentence, enclosing, find_markers, items_after, sentences

NOT_STATED = RawFieldState(status=FieldStatus.NOT_STATED)
_TRIM = " \t\r\n,;:."


def undetermined(reason: str) -> RawFieldState:
    return RawFieldState(status=FieldStatus.UNDETERMINED, reason=reason)


def _field(text: str, s: int, e: int) -> RawField | None:
    while s < e and text[s] in _TRIM:
        s += 1
    while e > s and text[e - 1] in _TRIM:
        e -= 1
    return RawField(value=text[s:e], start=s, end=e) if s < e else None


def _present(f: RawField | None) -> RawFieldState:
    return RawFieldState(status=FieldStatus.PRESENT, value=f) if f else NOT_STATED


def _top_level_comma(text: str, s: int, e: int) -> int | None:
    depth = 0
    for i in range(s, e):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth = max(0, depth - 1)
        elif text[i] == "," and depth == 0:
            return i
    return None


@dataclass
class _Patterns:
    deadline_full: re.Pattern[str]
    triggers: re.Pattern[str]
    boundary: re.Pattern[str]
    verb: re.Pattern[str]
    lead_dead: re.Pattern[str]
    lead_cond: re.Pattern[str]


def _compile(lex: Lexicon) -> _Patterns:
    units = "|".join(re.escape(u) for u in lex.duration_units)
    freq_units = "|".join(re.escape(u) for u in lex.frequency_units)
    dead, cond = alternation(lex.deadline_triggers), alternation(lex.condition_triggers)
    exc, freq_ph = alternation(lex.exception_triggers), alternation(lex.frequency_phrases)
    full = (
        rf"(?:{dead})\s+(?:\d+(?:\s*x\s*\d+)?\s*(?:\([^)]*\)\s*)?(?:{units})(?:\s+(?:kerja|kalender))?"
        r"(?:\s+(?:setelah|sejak|sebelum)\s+[^,;.:]+)?|tanggal\s+\d{1,2}\s+\w+\s+\d{4})"
    )
    trig = (
        rf"(?P<dead>(?<!\w)(?:{dead})(?!\w))"
        rf"|(?P<freq>(?<!\w)(?:setiap\s+(?:\d+\s+)?(?:\(\w+\)\s+)?(?:{freq_units})|{freq_ph})(?!\w))"
        rf"|(?P<exc>(?<!\w)(?:{exc})(?!\w))|(?P<cond>(?<!\w)(?:{cond})(?!\w))"
    )
    verbs = "|".join(sorted(lex.verb_prefixes, key=len, reverse=True))
    return _Patterns(
        deadline_full=re.compile(full, re.IGNORECASE),
        triggers=re.compile(trig, re.IGNORECASE),
        boundary=re.compile(
            r"(?<!\w)(?:" + alternation(lex.object_boundaries) + r")(?!\w)", re.IGNORECASE
        ),
        verb=re.compile(rf"^(?:{verbs})[a-z]{{3,}}$", re.IGNORECASE),
        lead_dead=re.compile(rf"^(?:{dead})(?!\w)", re.IGNORECASE),
        lead_cond=re.compile(rf"^(?:{cond})(?!\w)", re.IGNORECASE),
    )


@dataclass
class _Lead:
    pos: int
    conditions: list[RawField] = field(default_factory=list)
    deadline: RawFieldState = NOT_STATED
    undetermined: list[str] = field(default_factory=list)
    broken: bool = False


class RulesExtractor:
    id = "rules"

    def __init__(self, lexicon: Lexicon | None = None) -> None:
        self.lex = lexicon or load_lexicon()
        self.version = f"1+lex{self.lex.version}"
        self._p = _compile(self.lex)

    def extract(self, request: ExtractionRequest) -> tuple[RawCandidate, ...]:
        text, region, provs = request.text, request.region, request.provisions
        markers = [m for m in find_markers(text, region, self.lex) if not m.negated]
        sents = sentences(text, region, self.lex, provs)
        out: list[RawCandidate] = []
        for sent in sents:
            inside = [m for m in markers if sent.start <= m.start < sent.end]
            if inside:
                out += self._sentence(text, sent, inside, provs, sents)
        return tuple(out)

    def _leading(self, text: str, sent: Sentence, first: Marker) -> _Lead:
        lead = _Lead(pos=sent.start)
        while True:
            seg = text[lead.pos : first.start].lstrip()
            kind = (
                "dead"
                if self._p.lead_dead.match(seg)
                else "cond"
                if self._p.lead_cond.match(seg)
                else None
            )
            if kind is None:
                return lead
            comma = _top_level_comma(text, lead.pos, first.start)
            if comma is None:
                lead.broken = True
                lead.undetermined.append("conditions")
                return lead
            f = _field(text, lead.pos, comma)
            if f is None:
                return lead
            if kind == "cond":
                lead.conditions.append(f)
            elif lead.deadline.status is FieldStatus.NOT_STATED:
                lead.deadline = _present(f)
            else:
                lead.deadline = undetermined("two leading deadline adjuncts")
            lead.pos = comma + 1

    def _sentence(
        self,
        text: str,
        sent: Sentence,
        marks: list[Marker],
        provs: tuple[Provision, ...],
        sents: list[Sentence],
    ) -> list[RawCandidate]:
        lead = self._leading(text, sent, marks[0])
        lead_in: tuple[int, int] | None = None
        if lead.broken:
            actor = undetermined("leading adjunct without a comma delimiter")
        else:
            f = _field(text, lead.pos, marks[0].start)
            if f is None:
                li = self._lead_in_actor(text, sent, provs, sents)
                actor = _present(li) if li else NOT_STATED
                lead_in = (li.start, li.end) if li else None
            elif _top_level_comma(text, f.start, f.end) is not None:
                actor = undetermined("comma inside the actor phrase")
            else:
                actor = _present(f)
        items = tuple(it.span for it in items_after(provs, sent)) if sent.term == ":" else ()
        out = []
        for i, m in enumerate(marks):
            end = marks[i + 1].start if i + 1 < len(marks) else sent.end
            if i + 1 < len(marks) and (
                c := re.search(r"\s+(?:dan|serta|atau)\s*$", text[m.end : end])
            ):
                end = m.end + c.start()
            out.append(self._predicate(text, sent, m, end, actor, lead, items, lead_in))
        return out

    def _lead_in_actor(
        self, text: str, sent: Sentence, provs: tuple[Provision, ...], sents: list[Sentence]
    ) -> RawField | None:
        parent = enclosing(provs, sent.start)
        if parent is None or parent.level not in (Level.HURUF, Level.ANGKA):
            return None
        want = parent.path[:-1]
        best: Sentence | None = None
        for s in sents:
            enc = enclosing(provs, s.start)
            if s.end > sent.start or s.term != ":" or (enc.path if enc else ()) != want:
                continue
            if not find_markers(text, (s.start, s.end), self.lex):
                best = s
        return _field(text, best.start, best.end) if best else None

    def _predicate(
        self,
        text: str,
        sent: Sentence,
        m: Marker,
        end: int,
        actor: RawFieldState,
        lead: _Lead,
        items: tuple[tuple[int, int], ...],
        lead_in: tuple[int, int] | None,
    ) -> RawCandidate:
        start = m.end
        if un := re.match(r"\s*untuk\s+", text[start:end], re.IGNORECASE):
            start += un.end()
        triggers = self._triggers(text, start, end)
        head_end = triggers[0][1] if triggers else end
        action, obj = self._action_object(text, start, head_end)
        conditions, exceptions = list(lead.conditions), []
        und, deadline, frequency = list(lead.undetermined), lead.deadline, NOT_STATED
        for idx, (kind, ts, te) in enumerate(triggers):
            nxt = triggers[idx + 1][1] if idx + 1 < len(triggers) else end
            if kind == "dead":
                full = self._p.deadline_full.match(text, ts, end)
                state = (
                    _present(_field(text, ts, full.end()))
                    if full
                    else undetermined("deadline trigger without a duration")
                )
                deadline = (
                    state
                    if deadline.status is FieldStatus.NOT_STATED
                    else undetermined("two deadlines")
                )
            elif kind == "freq":
                f = _field(text, ts, te)
                frequency = (
                    _present(f)
                    if frequency.status is FieldStatus.NOT_STATED
                    else undetermined("two frequencies")
                )
            else:
                f = _field(text, ts, nxt)
                if f is None or not text[te:nxt].strip(_TRIM + " "):
                    und.append("exceptions" if kind == "exc" else "conditions")
                elif kind == "exc":
                    exceptions.append(f)
                else:
                    conditions.append(f)
        return RawCandidate(
            clause=(sent.start, sent.end),
            modality=m.modality or Modality.OBLIGATION,
            marker=RawField(value=text[m.start : m.end], start=m.start, end=m.end),
            actor=actor,
            action=action,
            object=obj,
            deadline=deadline,
            frequency=frequency,
            conditions=tuple(conditions),
            exceptions=tuple(exceptions),
            undetermined=tuple(dict.fromkeys(und)),
            items=items,
            lead_in=lead_in,
        )

    def _triggers(self, text: str, start: int, end: int) -> list[tuple[str, int, int]]:
        out: list[tuple[str, int, int]] = []
        pos = start
        while pos < end:
            m = self._p.triggers.search(text, pos, end)
            if not m:
                break
            kind = m.lastgroup or ""
            out.append((kind, m.start(), m.end()))
            full = self._p.deadline_full.match(text, m.start(), end) if kind == "dead" else None
            pos = full.end() if full else m.end()
        return out

    def _action_object(self, text: str, s: int, e: int) -> tuple[RawFieldState, RawFieldState]:
        ws = re.match(r"\s*", text[s:e])
        a0 = s + (ws.end() if ws else 0)
        word = re.match(r"[A-Za-z]+", text[a0:e])
        if not word or not self._p.verb.match(word.group(0)):
            return undetermined("first word after the marker is not an affixed verb"), NOT_STATED
        word_end = a0 + word.end()
        coordinated = re.search(r"\sdan\s+([A-Za-z]+)", text[word_end:e])
        if coordinated and self._p.verb.match(coordinated.group(1)):
            return _present(_field(text, a0, e)), undetermined(
                "coordinated predicates under one marker"
            )
        action = _present(_field(text, a0, word_end))
        b = self._p.boundary.search(text, word_end, e)
        obj = _field(text, word_end, b.start() if b else e)
        if obj is None:
            return action, NOT_STATED
        if _top_level_comma(text, obj.start, obj.end) is not None:
            return action, undetermined("comma inside the object phrase")
        return action, _present(obj)
