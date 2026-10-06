from pathlib import Path

from regulus.lineage.amendment import parse_operation
from regulus.lineage.evaluate import GoldOp, evaluate_ops, load_gold_ops

GOLD = Path(__file__).parents[2] / "evaluation" / "lineage" / "gold_ops.v1.json"


def test_gold_is_well_formed() -> None:
    cases = load_gold_ops(GOLD)
    assert len(cases) == 38 and len({c.case_id for c in cases}) == 38
    assert {c.source for c in cases} == {"SYNTHETIC", "PP20_1980", "UU21_1982"}
    assert all(len(c.rationale) >= 10 for c in cases)
    assert all(c.resolved == bool(c.kind) == (not c.unresolved_reason) for c in cases)


def test_pinned_operation_metrics_and_no_false_resolution() -> None:
    r = evaluate_ops(load_gold_ops(GOLD))
    assert (r.total, r.recognized, r.gold_recognized) == (38, 20, 20)
    assert (r.precision, r.recall, r.kind_accuracy, r.locator_accuracy) == (1.0, 1.0, 1.0, 1.0)
    assert r.false_resolutions == () and r.missed == () and r.wrong_unresolved_reason == ()
    assert round(r.unresolved_rate, 3) == 0.474


def test_evaluator_catches_a_wrong_resolution_and_a_miss() -> None:
    cases = load_gold_ops(GOLD)
    wrong = next(c for c in cases if c.case_id == "s-delete").model_copy(update={"kind": "MODIFY"})
    r = evaluate_ops([wrong])
    assert r.false_resolutions == ("s-delete",) and r.kind_accuracy == 0.0
    claim = GoldOp(
        case_id="x",
        source="SYNTHETIC",
        text="1. Pasal 5 diperbaiki seperlunya.",
        resolved=True,
        kind="MODIFY",
        rationale="a claim the grammar cannot meet",
    )
    assert evaluate_ops([claim]).missed == ("x",)
    ghost = GoldOp(
        case_id="g",
        source="SYNTHETIC",
        text="1. Pasal 7 dihapus.",
        resolved=False,
        unresolved_reason="UNSUPPORTED_OPERATION",
        rationale="a case the grammar wrongly resolves",
    )
    assert evaluate_ops([ghost]).false_resolutions == ("g",)


def test_every_unresolved_gold_case_is_really_unresolved() -> None:
    for c in load_gold_ops(GOLD):
        if not c.resolved:
            assert type(parse_operation(c.text)).__name__ == "Unresolved", c.case_id
