from pathlib import Path

from regulus.relevance import AssessmentConfig, load_rules, load_scope, load_taxonomy
from regulus.relevance.evaluate import load_gold, run

from ..builder import EC, HARD0, Builder
from ..models import Formula

L = "relevance"
POP = "relevance.gold"


def evaluate(b: Builder, root: Path) -> None:
    cases = load_gold(root / "relevance" / "gold.v1.json")
    cfg = AssessmentConfig(taxonomy=load_taxonomy(), scope=load_scope(), rules=load_rules())
    r = run(cases, cfg)
    b.population(POP, "hand-authored relevance cases", "evaluation/relevance/gold.v1.json", len(cases),
                 "system author, against the rule set's own vocabulary",
                 "authored against the same rules; small; not a recall claim on unseen regulations")  # fmt: skip
    c = r.confusion
    abst = "INSUFFICIENT_EVIDENCE"
    tp = c["RELEVANT"]["RELEVANT"]
    gold_rel = sum(c["RELEVANT"].values())
    pred_rel = sum(row["RELEVANT"] for row in c.values())
    fp, fn = pred_rel - tp, gold_rel - tp
    abstained = sum(row[abst] for row in c.values())
    total = r.total
    m = b.metric
    frac = m(f"{L}.decided_fraction", L, "decided fraction", POP, "cases labelled RELEVANT or NOT_RELEVANT",
             "all gold cases", EC.REGRESSION)  # fmt: skip
    abst_rate = m(f"{L}.abstention_rate", L, "abstention rate", POP, "cases labelled INSUFFICIENT_EVIDENCE",
                  "all gold cases", EC.REGRESSION)  # fmt: skip
    b.record(frac, total - abstained, total)
    b.record(abst_rate, abstained, total)
    prec = m(f"{L}.relevant_precision", L, "precision of RELEVANT", POP, "gold-relevant among predicted RELEVANT (TP)",
             "predicted RELEVANT (TP + FP)", EC.REGRESSION, qualified_by=frac.id)  # fmt: skip
    rec = m(f"{L}.relevant_recall", L, "recall of RELEVANT", POP,
            "predicted RELEVANT among gold-relevant (TP)",
            "gold-relevant cases (TP + FN); an abstained gold-relevant case is a FN", EC.REGRESSION,
            qualified_by=abst_rate.id)  # fmt: skip
    f = m(f"{L}.relevant_f1", L, "F1 of RELEVANT", POP, "2 * TP", "2 * TP + FP + FN", EC.REGRESSION)
    b.record(prec, tp, pred_rel)
    b.record(rec, tp, gold_rel)
    b.record(f, 2 * tp, 2 * tp + fp + fn)
    fnr = m(f"{L}.false_not_relevant", L, "false NOT_RELEVANT rate", POP,
            "gold-relevant cases predicted NOT_RELEVANT", "gold-relevant cases", EC.REGRESSION, HARD0)  # fmt: skip
    b.record(fnr, c["RELEVANT"]["NOT_RELEVANT"], gold_rel)
    stp = sum(s.tp for s in r.sectors.values())
    sfp = sum(s.fp for s in r.sectors.values())
    sfn = sum(s.fn for s in r.sectors.values())
    mi = m(
        f"{L}.sector_micro_f1",
        L,
        "sector micro F1",
        POP,
        "2 * pooled TP",
        "2 * pooled TP + FP + FN",
        EC.REGRESSION,
    )
    b.record(mi, 2 * stp, 2 * stp + sfp + sfn)
    ma = m(f"{L}.sector_macro_f1", L, "sector macro F1", POP, "sum of per-sector F1", "sectors", EC.REGRESSION,
           formula=Formula.MEAN)  # fmt: skip
    b.record(ma, sum(s.f1 or 0.0 for s in r.sectors.values()), len(r.sectors))
    ev = m(f"{L}.unexplained_decisions", L, "decided assessments without deciding evidence violations", POP,
           "decided assessments lacking verifiable evidence", "decided assessments", EC.PROPERTY, HARD0)  # fmt: skip
    b.record(ev, len(r.explainability_violations), total - abstained)
