from pathlib import Path

from regulus.change_detection.evaluate import evaluate_gold, load_gold

from ..builder import EC, HARD0, Builder

L = "detection"
POP = "detection.gold"


def evaluate(b: Builder, root: Path) -> None:
    gold = load_gold(root / "change_detection" / "gold.v1.json")
    r = evaluate_gold(gold)
    b.population(POP, "hand-authored source records with expected events, plus status projections",
                 "evaluation/change_detection/gold.v1.json", r.cases + r.projections, "system author, from the Phase 2 contract with a rationale per case",
                 "synthetic records over a three-regulation index; adversarial by design; not real intake traffic")  # fmt: skip
    m = b.metric
    b.record(
        m(
            f"{L}.outcome_accuracy",
            L,
            "outcome accuracy",
            POP,
            "records with the expected outcome (processed, empty, failed)",
            "gold records",
            EC.REGRESSION,
        ),
        r.outcome_ok,
        r.cases,
    )
    b.record(
        m(
            f"{L}.event_type_accuracy",
            L,
            "event type accuracy",
            POP,
            "records whose multiset of event types equals the gold's",
            "gold records",
            EC.REGRESSION,
        ),
        r.type_ok,
        r.cases,
    )
    b.record(
        m(
            f"{L}.target_resolution_accuracy",
            L,
            "target resolution accuracy",
            POP,
            "expected target-bound events produced with the right target",
            "expected target-bound events",
            EC.REGRESSION,
        ),
        r.target_ok,
        r.target_total,
    )
    b.record(
        m(
            f"{L}.false_resolution_rate",
            L,
            "false resolution rate",
            POP,
            "target-bound events whose type and target the gold does not expect",
            "target-bound events the system produced",
            EC.REGRESSION,
            HARD0,
        ),
        len(r.false_resolutions),
        r.resolved_events,
    )
    b.record(
        m(
            f"{L}.review_reason_agreement",
            L,
            "review reason agreement",
            POP,
            "expected review events produced with the expected reason",
            "expected review events",
            EC.REGRESSION,
        ),
        r.review_reason_ok,
        r.review_expected,
    )
    b.record(
        m(
            f"{L}.review_case_rate",
            L,
            "NEEDS_REVIEW case rate",
            POP,
            "records with at least one review event",
            "gold records",
            EC.REGRESSION,
        ),
        r.review_cases_predicted,
        r.cases,
    )
    b.record(
        m(
            f"{L}.projection_accuracy",
            L,
            "status projection accuracy",
            POP,
            "projections with the expected status and anomalies",
            "gold projections",
            EC.REGRESSION,
        ),
        r.projection_ok,
        r.projections,
    )
    b.record(
        m(
            f"{L}.order_invariance_violations",
            L,
            "ingestion-order violation rate",
            POP,
            "seeded permutations producing a different event set",
            "seeded permutations",
            EC.PROPERTY,
            HARD0,
        ),
        r.permutation_violations,
        r.permutations,
        "seed 7",
    )
    b.record(
        m(
            f"{L}.replay_violations",
            L,
            "replay violation rate",
            POP,
            "records that emit events again when their own events are already seen",
            "gold records",
            EC.PROPERTY,
            HARD0,
        ),
        r.replay_violations,
        r.replay_records,
    )
