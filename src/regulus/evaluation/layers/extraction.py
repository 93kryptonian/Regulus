from pathlib import Path

from regulus.obligations.evaluate import evaluate_gold, load_gold

from ..builder import EC, HARD0, Builder

L = "extraction"
POP = "extraction.gold"


def evaluate(b: Builder, root: Path) -> None:
    cases = load_gold(root / "obligations" / "gold.v1.json")
    r = evaluate_gold(cases)
    b.population(POP, "hand-authored extraction cases", "evaluation/obligations/gold.v1.json", len(cases),
                 "system author, against the extractor's own grammar and lexicon",
                 "authored against the same grammar; regression evidence, not recall on unseen regulations")  # fmt: skip
    m = b.metric
    c = r.candidates
    b.record(
        m(
            f"{L}.candidate_precision",
            L,
            "candidate precision",
            POP,
            "predicted candidates matching a gold candidate (TP)",
            "predicted candidates (TP + FP)",
            EC.REGRESSION,
        ),
        c.tp,
        c.tp + c.fp,
    )
    b.record(
        m(
            f"{L}.candidate_recall",
            L,
            "candidate recall",
            POP,
            "gold candidates matched (TP)",
            "gold candidates (TP + FN)",
            EC.REGRESSION,
        ),
        c.tp,
        c.tp + c.fn,
    )
    b.record(
        m(f"{L}.candidate_f1", L, "candidate F1", POP, "2 * TP", "2 * TP + FP + FN", EC.REGRESSION),
        2 * c.tp,
        2 * c.tp + c.fp + c.fn,
    )
    tp = sum(x.tp for x in r.fields.values())
    fp = sum(x.fp for x in r.fields.values())
    fn = sum(x.fn for x in r.fields.values())
    b.record(
        m(
            f"{L}.field_precision",
            L,
            "field precision",
            POP,
            "populated fields equal to the gold value (TP)",
            "populated fields of matched candidates (TP + FP)",
            EC.REGRESSION,
        ),
        tp,
        tp + fp,
    )
    b.record(
        m(
            f"{L}.field_recall",
            L,
            "field recall",
            POP,
            "gold fields recovered (TP)",
            "gold fields of matched candidates (TP + FN)",
            EC.REGRESSION,
        ),
        tp,
        tp + fn,
    )
    b.record(
        m(
            f"{L}.not_stated_agreement",
            L,
            "NOT_STATED agreement",
            POP,
            "fields reported NOT_STATED where the gold has no value",
            "fields the gold marks without a value",
            EC.REGRESSION,
        ),
        r.not_stated_ok,
        r.not_stated_total,
    )
    b.record(
        m(
            f"{L}.multiplicity_agreement",
            L,
            "multiplicity agreement",
            POP,
            "cases with the gold's candidate count",
            "gold cases",
            EC.REGRESSION,
        ),
        r.multiplicity_ok,
        r.total,
    )
    b.record(
        m(
            f"{L}.unsupported_claims",
            L,
            "unsupported claim rate",
            POP,
            "citations whose quoted text is not at their span",
            "citations checked",
            EC.REGRESSION,
            HARD0,
        ),
        r.unsupported_claims,
        r.citations_checked,
    )
    b.record(
        m(
            f"{L}.silent_deontic_loss",
            L,
            "silent deontic loss rate",
            POP,
            "marker occurrences with neither candidate nor diagnostic",
            "marker occurrences",
            EC.REGRESSION,
            HARD0,
        ),
        r.silent_loss,
        r.markers,
    )
