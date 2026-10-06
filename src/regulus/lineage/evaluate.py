import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from regulus.domain.base import Model

from .amendment import Operation, Unresolved, parse_operation


class ExpectedLocator(Model):
    article: str
    path: tuple[str, ...] = ()


class GoldOp(Model):
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    text: str
    resolved: bool
    kind: str | None = None
    target_level: str | None = None
    locators: tuple[ExpectedLocator, ...] = ()
    unresolved_reason: str | None = None
    rationale: str = Field(min_length=10)


class OpReport(Model):
    total: int
    recognized: int
    gold_recognized: int
    precision: float | None
    recall: float | None
    kind_accuracy: float | None
    locator_accuracy: float | None
    unresolved_rate: float
    false_resolutions: tuple[str, ...]
    missed: tuple[str, ...]
    wrong_unresolved_reason: tuple[str, ...]


def load_gold_ops(path: Path) -> list[GoldOp]:
    return [GoldOp.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def _ratio(n: int, d: int) -> float | None:
    return n / d if d else None


def evaluate_ops(cases: Sequence[GoldOp]) -> OpReport:
    tp = fp = fn = kind_ok = loc_ok = both = 0
    false_res, missed, bad_reason = [], [], []
    for c in cases:
        got = parse_operation(c.text)
        pred = isinstance(got, Operation)
        tp += pred and c.resolved
        fp += pred and not c.resolved
        fn += (not pred) and c.resolved
        if pred and not c.resolved:
            false_res.append(c.case_id)
        if not pred and c.resolved:
            missed.append(c.case_id)
        if isinstance(got, Unresolved) and not c.resolved and c.unresolved_reason != got.reason:
            bad_reason.append(c.case_id)
        if isinstance(got, Operation) and c.resolved:
            both += 1
            same_kind = got.kind == c.kind and (
                c.target_level is None or got.target_level == c.target_level
            )
            same_loc = [(x.article, x.path) for x in got.locators] == [
                (x.article, x.path) for x in c.locators
            ]
            kind_ok += same_kind
            loc_ok += same_loc
            if not (same_kind and same_loc):
                false_res.append(c.case_id)
    predicted = tp + fp
    return OpReport(
        total=len(cases),
        recognized=predicted,
        gold_recognized=tp + fn,
        precision=_ratio(tp, predicted),
        recall=_ratio(tp, tp + fn),
        kind_accuracy=_ratio(kind_ok, both),
        locator_accuracy=_ratio(loc_ok, both),
        unresolved_rate=(len(cases) - predicted) / len(cases) if cases else 0.0,
        false_resolutions=tuple(false_res),
        missed=tuple(missed),
        wrong_unresolved_reason=tuple(bad_reason),
    )
