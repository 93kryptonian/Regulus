from datetime import date

import pytest

from regulus.change_detection import (
    Action,
    DeclaredRelation,
    RegulationIndex,
    SourceRecord,
    TargetRef,
)
from regulus.domain import Regulation
from regulus.domain import RegulationKind as K

D = date(2026, 7, 16)
DET = date(2026, 7, 17)


def rec(number: str = "33", year: int = 2026, kind: K | None = K.PP, **kw: object) -> SourceRecord:
    base: dict[str, object] = {
        "source_id": "s1",
        "kind": kind,
        "number": number,
        "year": year,
        "title": "Title",
        "promulgated_on": D,
    }
    return SourceRecord(**{**base, **kw})  # type: ignore[arg-type]


def rel(
    action: Action,
    kind: K | None = K.UU,
    number: str | None = "27",
    year: int | None = 2022,
    raw: str = "UU 27/2022",
) -> DeclaredRelation:
    return DeclaredRelation(
        action=action, target=TargetRef(raw=raw, kind=kind, number=number, year=year)
    )


@pytest.fixture
def index() -> RegulationIndex:
    return RegulationIndex(
        [
            Regulation.of(K.UU, "27", 2022, title="PDP"),
            Regulation.of(K.PP, "27", 2022, title="Other"),
            Regulation.of(K.PP, "5", 2020, title="Five", promulgated_on=date(2020, 1, 1)),
        ]
    )
