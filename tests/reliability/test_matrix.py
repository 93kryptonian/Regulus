from pathlib import Path

from regulus.reliability.matrix import Row, load, validate

ROOT = Path(__file__).parents[2]
MATRIX = ROOT / "evaluation" / "reliability" / "matrix.v1.json"


def test_every_matrix_row_has_a_real_claiming_test_and_no_test_claims_a_missing_row() -> None:
    assert validate(load(MATRIX), ROOT) == []


def test_the_matrix_validator_rejects_every_kind_of_defect(tmp_path: Path) -> None:
    rows = load(MATRIX)
    good = rows[0]
    bad = [
        good.model_copy(update={"id": "R01"}),
        good.model_copy(update={"id": "R99", "tests": ()}),
        good.model_copy(update={"id": "R98", "fault": "MAGIC"}),
        good.model_copy(update={"id": "R97", "guarantees": ("G11",)}),
        good.model_copy(update={"id": "R96", "recovery": " "}),
        good.model_copy(
            update={"id": "R95", "tests": ("tests/reliability/test_rows_state.py::test_nope",)}
        ),
        good.model_copy(update={"id": "R94"}),
        good.model_copy(update={"id": "bad-id"}),
    ]
    problems = validate([*rows, *bad], ROOT)
    for needle in (
        "duplicate row ids",
        "R99: no test",
        "unknown fault",
        "guarantee ids",
        "must be declared",
        "does not exist",
        "nothing claims this row",
        "id format",
    ):
        assert any(needle in p for p in problems), needle
    assert isinstance(good, Row)
    assert any(
        "does not claim the row" in p
        for p in validate([good.model_copy(update={"id": "R03", "tests": good.tests})], ROOT)
    )


def test_a_claim_for_an_unknown_row_is_reported() -> None:
    rows = [r for r in load(MATRIX) if r.id != "R22"]
    assert any("unknown row R22" in p for p in validate(rows, ROOT))
