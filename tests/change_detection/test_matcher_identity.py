import pytest

from regulus.change_detection.identity import (
    conflict_discriminator,
    event_id,
    target_discriminator,
)
from regulus.change_detection.matcher import MatchClass, RegulationIndex, classify
from regulus.change_detection.models import Action, TargetRef
from regulus.domain import EventType, Regulation
from regulus.domain import RegulationKind as K
from regulus.domain import ReviewReason as R


@pytest.fixture
def index() -> RegulationIndex:
    return RegulationIndex(
        [
            Regulation.of(K.UU, "27", 2022, title="PDP"),
            Regulation.of(K.PP, "27", 2022, title="Other"),
            Regulation.of(K.PP, "5", 2020, title="Five"),
        ]
    )


def ref(**kw: object) -> TargetRef:
    return TargetRef(raw="raw", **kw)  # type: ignore[arg-type]


def test_resolved(index: RegulationIndex) -> None:
    c, r = classify(ref(kind=K.PP, number="5", year=2020), index)
    assert c is MatchClass.RESOLVED and r is not None and r.id == "PP-5-2020"


def test_number_normalized(index: RegulationIndex) -> None:
    c, _ = classify(ref(kind=K.PP, number=" 5 ", year=2020), index)
    assert c is MatchClass.RESOLVED


def test_unresolved(index: RegulationIndex) -> None:
    assert classify(ref(kind=K.PP, number="9", year=2020), index)[0] is MatchClass.UNRESOLVED


def test_ambiguous_when_kind_missing_and_many(index: RegulationIndex) -> None:
    assert classify(ref(number="27", year=2022), index) == (MatchClass.AMBIGUOUS, None)


@pytest.mark.parametrize(
    "kw",
    [
        {"number": "5", "year": 2020},
        {"number": "999", "year": 2020},
        {"kind": K.PP, "year": 2020},
        {"kind": K.PP, "number": "5"},
        {"kind": K.PP, "number": "  ", "year": 2020},
        {},
    ],
)
def test_malformed_never_guesses(index: RegulationIndex, kw: dict[str, object]) -> None:
    assert classify(ref(**kw), index) == (MatchClass.MALFORMED, None)  # type: ignore[arg-type]


def test_event_id_deterministic_and_discriminating() -> None:
    a = event_id(EventType.AMEND, "r", "t")
    assert a == event_id(EventType.AMEND, "r", "t") and a.startswith("evt-") and len(a) == 20
    assert a != event_id(EventType.REPEAL, "r", "t")
    assert a != event_id(EventType.AMEND, "r", "u")
    assert a != event_id(EventType.AMEND, "q", "t")
    assert event_id(EventType.NEW, "r") != event_id(EventType.NEW, "r", None, "x")


def test_target_discriminator_separates_actions_and_normalizes_ref() -> None:
    d = target_discriminator
    assert d(R.UNRESOLVED_TARGET, Action.MENGUBAH, "UU  123") == d(
        R.UNRESOLVED_TARGET, Action.MENGUBAH, "uu 123"
    )
    assert d(R.UNRESOLVED_TARGET, Action.MENGUBAH, "x") != d(
        R.UNRESOLVED_TARGET, Action.MENCABUT, "x"
    )
    assert d(R.UNRESOLVED_TARGET, Action.MENGUBAH, "x") != d(
        R.MALFORMED_TARGET, Action.MENGUBAH, "x"
    )


def test_conflict_discriminator_order_independent() -> None:
    d = conflict_discriminator
    assert d(R.METADATA_CONFLICT, ["a", "b"]) == d(R.METADATA_CONFLICT, ["b", "a"])
    assert d(R.METADATA_CONFLICT, ["a"]) != d(R.METADATA_CONFLICT, ["b"])
