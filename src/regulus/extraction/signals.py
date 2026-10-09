import re

from regulus.documents.models import Level, Provision
from regulus.obligations.lexicon import Lexicon, alternation
from regulus.obligations.models import Modality
from regulus.obligations.segment import find_markers

from .crossrefs import mentions
from .lexicon import SignalsLexicon
from .models import Signal, SignalKind

_ORDER = {k: i for i, k in enumerate(SignalKind)}
_LEVELS = (Level.HURUF, Level.ANGKA)


def _words(terms: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{alternation(terms)})(?!\w)", re.IGNORECASE)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


class SignalMatcher:
    def __init__(self, sig: SignalsLexicon, lex: Lexicon) -> None:
        self.version = sig.version
        self.lex = lex
        units = "|".join(re.escape(u) for u in lex.frequency_units)
        freq = (
            rf"setiap\s+(?:\d+\s+)?(?:\(\w+\)\s+)?(?:{units})|{alternation(lex.frequency_phrases)}"
        )
        self.patterns: tuple[tuple[SignalKind, re.Pattern[str]], ...] = (
            (SignalKind.PERMISSION, _words(sig.permission)),
            (SignalKind.SANCTION, _words(sig.sanction)),
            (SignalKind.RESPONSIBILITY, _words(sig.responsibility)),
            (SignalKind.DUTY_VERB, _words(sig.duty_verbs)),
            (SignalKind.PASSIVE_DUTY, _words(sig.passive_duties)),
            (SignalKind.CONDITION, _words(lex.condition_triggers + lex.exception_triggers)),
            (SignalKind.DEADLINE, _words(lex.deadline_triggers)),
            (SignalKind.FREQUENCY, re.compile(rf"(?<!\w)(?:{freq})(?!\w)", re.IGNORECASE)),
            (SignalKind.DEFINITION, _words(sig.definition)),
        )

    def signals(
        self, text: str, provisions: tuple[Provision, ...] = (), own_label: str | None = None
    ) -> tuple[Signal, ...]:
        v = self.version
        out: list[Signal] = []
        marks = find_markers(text, (0, len(text)), self.lex)
        for mk in marks:
            if mk.negated:
                continue
            kind = (
                SignalKind.EXPLICIT_PROHIBITION
                if mk.modality is Modality.PROHIBITION
                else SignalKind.EXPLICIT_OBLIGATION
            )
            out.append(
                Signal(kind=kind, term=mk.word, start=mk.start, end=mk.end, signals_version=v)
            )
        for kind, pat in self.patterns:
            for m in pat.finditer(text):
                if kind is SignalKind.PERMISSION and any(
                    k.start <= m.start() and m.end() <= k.end for k in marks
                ):
                    continue
                out.append(
                    Signal(
                        kind=kind,
                        term=_norm(m.group(0)),
                        start=m.start(),
                        end=m.end(),
                        signals_version=v,
                    )
                )
        for r in mentions(text):
            if own_label is None or r.label == own_label.upper():
                continue
            out.append(
                Signal(
                    kind=SignalKind.CROSS_REFERENCE,
                    term=_norm(text[r.start : r.end]),
                    start=r.start,
                    end=r.end,
                    signals_version=v,
                )
            )
        items = [p for p in provisions if p.level in _LEVELS]
        if len(items) >= 2:
            out.append(
                Signal(
                    kind=SignalKind.ENUMERATION,
                    term="",
                    start=min(p.span[0] for p in items),
                    end=max(p.span[1] for p in items),
                    signals_version=v,
                )
            )
        if not out:
            out.append(
                Signal(kind=SignalKind.NO_SIGNAL, term="", start=0, end=0, signals_version=v)
            )
        return tuple(sorted(out, key=lambda s: (s.start, s.end, _ORDER[s.kind], s.term)))


def selects_term(text: str, s: Signal) -> bool:
    if s.kind is SignalKind.NO_SIGNAL:
        return (s.start, s.end) == (0, 0)
    if s.kind is SignalKind.ENUMERATION:
        return 0 <= s.start < s.end <= len(text)
    return 0 <= s.start < s.end <= len(text) and _norm(text[s.start : s.end]) == s.term
