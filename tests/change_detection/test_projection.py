from datetime import date
from itertools import permutations

from regulus.change_detection import project_status
from regulus.domain import EventType as T
from regulus.domain import RegulationStatus as S
from regulus.domain import RegulatoryEvent

U = "UU-27-2022"


def ev(
    i: str, t: T, on: date, reg: str = "PP-33-2026", target: str | None = None
) -> RegulatoryEvent:
    return RegulatoryEvent(
        id=i, type=t, regulation_id=reg, target_id=target, occurred_on=on, detected_on=on, basis="b"
    )


def test_unknown_and_in_force() -> None:
    assert project_status(U, []).status is S.UNKNOWN
    assert project_status(U, [ev("n", T.NEW, date(2022, 1, 1), U)]).status is S.IN_FORCE


def test_ignores_unrelated_and_needs_review() -> None:
    other = ev("a", T.AMEND, date(2023, 1, 1), target="OTHER")
    review = RegulatoryEvent(
        id="r",
        type=T.NEEDS_REVIEW,
        regulation_id="PP-1-2020",
        occurred_on=date(2023, 1, 1),
        detected_on=date(2023, 1, 1),
        basis="b",
        reason="METADATA_CONFLICT",
    )  # type: ignore[arg-type]
    assert project_status(U, [other, review]).status is S.UNKNOWN


def test_amend_then_repeal() -> None:
    n = ev("n", T.NEW, date(2022, 1, 1), U)
    a = ev("a", T.AMEND, date(2023, 1, 1), target=U)
    p = ev("p", T.PARTIAL_REPEAL, date(2023, 2, 1), target=U)
    r = ev("r", T.REPEAL, date(2024, 1, 1), target=U)
    assert project_status(U, [n, a, p]).status is S.AMENDED
    assert project_status(U, [n, a, p, r]).status is S.REPEALED


def test_repeal_then_later_amend_reports_anomaly() -> None:
    r = ev("r", T.REPEAL, date(2024, 1, 1), target=U)
    a = ev("a", T.AMEND, date(2024, 6, 1), target=U)
    out = project_status(U, [a, r])
    assert out.status is S.REPEALED and out.anomalies == ("a",)
    same_day = ev("s", T.AMEND, date(2024, 1, 1), target=U)
    assert project_status(U, [r, same_day]).anomalies == ()


def test_order_independent() -> None:
    evs = [
        ev("n", T.NEW, date(2022, 1, 1), U),
        ev("a", T.AMEND, date(2023, 1, 1), target=U),
        ev("r", T.REPEAL, date(2024, 1, 1), target=U),
        ev("l", T.AMEND, date(2025, 1, 1), target=U),
    ]
    results = {project_status(U, list(p)).model_dump_json() for p in permutations(evs)}
    assert len(results) == 1
