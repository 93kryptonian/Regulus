from collections.abc import Iterable
from enum import StrEnum

from regulus.domain import Regulation, RegulationKind

from .models import TargetRef


def norm_number(number: str) -> str:
    return "".join(number.split()).upper()


def norm_text(text: str) -> str:
    return " ".join(text.split()).casefold()


class RegulationIndex:
    def __init__(self, regulations: Iterable[Regulation] = ()) -> None:
        self._by_key = {(r.kind, norm_number(r.number), r.year): r for r in regulations}

    def get(self, kind: RegulationKind, number: str, year: int) -> Regulation | None:
        return self._by_key.get((kind, norm_number(number), year))

    def candidates(self, number: str, year: int) -> list[Regulation]:
        n = norm_number(number)
        return [r for (_, rn, ry), r in self._by_key.items() if rn == n and ry == year]


class MatchClass(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    MALFORMED = "MALFORMED"


def classify(ref: TargetRef, index: RegulationIndex) -> tuple[MatchClass, Regulation | None]:
    if not ref.number or not ref.number.strip() or ref.year is None:
        return MatchClass.MALFORMED, None
    if ref.kind is None:
        found = index.candidates(ref.number, ref.year)
        return (MatchClass.AMBIGUOUS if len(found) >= 2 else MatchClass.MALFORMED), None
    hit = index.get(ref.kind, ref.number, ref.year)
    return (MatchClass.RESOLVED, hit) if hit else (MatchClass.UNRESOLVED, None)
