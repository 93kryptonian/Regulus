from pathlib import Path

from regulus.lineage.evaluate import evaluate_ops, load_gold_ops

from ..builder import EC, HARD0, Builder
from ..models import Status

L = "lineage"
POP = "lineage.gold_ops"


def evaluate(b: Builder, root: Path) -> None:
    cases = load_gold_ops(root / "lineage" / "gold_ops.v1.json")
    r = evaluate_ops(cases)
    b.population(POP, "hand-authored amendment operations", "evaluation/lineage/gold_ops.v1.json", len(cases),
                 "system author, from the declared drafting formulas",
                 "authored against the same grammar; operation parsing only, not target binding")  # fmt: skip
    m = b.metric
    pr = m(f"{L}.recognition_precision", L, "operation recognition precision", POP, "recognized operations the gold also resolves (TP)",
           "recognized operations (TP + FP)", EC.REGRESSION)  # fmt: skip
    rc = m(f"{L}.recognition_recall", L, "operation recognition recall", POP, "gold-resolved operations recognized (TP)",
           "gold-resolved operations (TP + FN)", EC.REGRESSION)  # fmt: skip
    b.record(pr, r.tp, r.tp + r.fp)
    b.record(rc, r.tp, r.tp + r.fn)
    b.record(m(f"{L}.kind_accuracy", L, "operation kind accuracy", POP, "correct kind and target level",
               "operations both recognized and gold-resolved", EC.REGRESSION), r.kind_correct, r.compared)  # fmt: skip
    b.record(m(f"{L}.locator_accuracy", L, "locator accuracy", POP, "correct locators",
               "operations both recognized and gold-resolved", EC.REGRESSION), r.locator_correct, r.compared)  # fmt: skip
    bind = m(f"{L}.target_binding_accuracy", L, "target binding accuracy", POP, "correctly bound operations",
             "operations with an expected binding", EC.REGRESSION)  # fmt: skip
    b.unmeasurable(
        bind,
        "the gold records operation parsing only; no expected event-target binding exists",
        status=Status.NO_GOLD,
    )
    fr = m(f"{L}.false_resolution_rate", L, "false resolution rate", POP, "operations resolved with a wrong kind, level or locator, or resolved where the gold is unresolved",
           "operations the system resolved", EC.REGRESSION, HARD0)  # fmt: skip
    b.record(fr, len(r.false_resolutions), r.recognized)
    gold_unres = r.total - (r.tp + r.fn)
    b.record(m(f"{L}.expected_unresolved_agreement", L, "expected-unresolved agreement", POP,
               "gold-unresolved operations left unresolved", "gold-unresolved operations", EC.REGRESSION),
             gold_unres - r.fp, gold_unres)  # fmt: skip
