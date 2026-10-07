from pathlib import Path

from regulus.documents.evaluate import evaluate_gold, load_gold

from ..builder import EC, HARD0, HARD1, Builder

L = "documents"
POP = "documents.gold"


def evaluate(b: Builder, root: Path) -> None:
    cases = load_gold(root / "documents" / "gold.v1.json")
    r = evaluate_gold(cases)
    b.population(POP, "hand-authored page snippets with expected structure", "evaluation/documents/gold.v1.json", len(cases),
                 "system author, from the Phase 3 contract with a rationale per case",
                 "synthetic snippets, adversarial by design; no real scanned pages; OCR is not evaluated")  # fmt: skip
    m = b.metric
    b.record(
        m(
            f"{L}.status_accuracy",
            L,
            "document status accuracy",
            POP,
            "snippets with the expected status",
            "gold snippets",
            EC.REGRESSION,
        ),
        r.status_ok,
        r.cases,
    )
    b.record(
        m(
            f"{L}.structure_recovery",
            L,
            "structure recovery accuracy",
            POP,
            "expected articles and amendment units recovered with the exact number and text",
            "expected articles and amendment units",
            EC.REGRESSION,
        ),
        r.recovered_units,
        r.expected_units,
    )
    b.record(
        m(
            f"{L}.noise_removal",
            L,
            "noise removal accuracy",
            POP,
            "snippets whose removed noise is absent from every unit",
            "snippets that list noise to remove",
            EC.REGRESSION,
        ),
        r.noise_ok,
        r.noise_cases,
    )
    b.record(
        m(
            f"{L}.diagnostic_agreement",
            L,
            "diagnostic agreement",
            POP,
            "snippets whose diagnostic codes equal the gold's",
            "snippets with expected codes",
            EC.REGRESSION,
        ),
        r.code_ok,
        r.code_cases,
    )
    b.record(
        m(
            f"{L}.explicit_failure",
            L,
            "explicit failure rate on unreadable or incomplete input",
            POP,
            "failed or partial snippets reported as failed or partial",
            "gold snippets expected to fail or be partial",
            EC.REGRESSION,
            HARD1,
        ),
        r.explicit_failure_ok,
        r.explicit_failure_cases,
    )
    b.record(
        m(
            f"{L}.provenance_round_trip",
            L,
            "provenance round-trip violation rate",
            POP,
            "articles or units whose text is not reconstructible from their spans",
            "articles and units checked",
            EC.PROPERTY,
            HARD0,
        ),
        r.round_trip.violations,
        r.round_trip.checked,
        "self-consistency only",
    )
    for mm in r.mismatches:
        b.errors.append(f"documents gold mismatch: {mm}")
