import json
import random
import re
from pathlib import Path

import pytest

from regulus.evaluation import EvidenceClass, Report, Status, claim_violations, f1
from regulus.evaluation.baseline import BaselineRefused, compare, snapshot, update
from regulus.evaluation.layers.review import four_eyes_violations
from regulus.evaluation.report import claim_problems, gate_failures, to_json, to_markdown
from regulus.evaluation.runner import build_report, check_registry
from regulus.obligations import RulesExtractor

ROOT = Path(__file__).parents[2] / "evaluation"
NOPDF = Path("/nonexistent-corpus")

HARD_GATES = {
    "detection.false_resolution_rate": 0, "detection.order_invariance_violations": 0, "detection.replay_violations": 0,
    "documents.explicit_failure": 1, "documents.provenance_round_trip": 0,
    "relevance.false_not_relevant": 0, "relevance.unexplained_decisions": 0,
    "lineage.false_resolution_rate": 0,
    "extraction.unsupported_claims": 0, "extraction.silent_deontic_loss": 0,
    "generation.undetected_mutations": 0, "generation.unexpected_accepted_contradictions": 0,
    "generation.hallucinated_tokens": 0, "generation.field_accounting": 0,
    "generation.open_question_preservation": 0, "generation.evidence_citation": 0,
    "similarity.ceiling_and_evidence_violations": 0,
    "review.four_eyes_violations": 0, "review.replay_violations": 0,
    "workflow.unaccounted_items": 0, "workflow.crash_divergence": 0,
    "workflow.duplicate_logical_notifications": 0, "workflow.independence_violations": 0,
    "observability.non_interference_violations": 0, "observability.lifecycle_violations": 0,
    "observability.nondeterminism": 0, "observability.vocabulary_violations": 0, "observability.sensitive_content": 0,
    "observability.cost_arithmetic_mismatches": 0, "observability.unpriced_summed_as_zero": 0,
    "observability.drop_accounting": 0, "observability.sink_calls_inside_wrappers": 0,
    "reliability.state_safety_violations": 0, "reliability.lost_items": 0, "reliability.duplicate_effects": 0,
    "reliability.undetected_corruption": 0, "reliability.writes_on_corrupted_streams": 0,
    "reliability.recovery_divergence": 0, "reliability.retry_bound_violations": 0, "reliability.weaker_snapshots": 0,
    "reliability.second_effects_after_timeout_before": 0, "reliability.second_effects_after_timeout_after": 0,
    "reliability.matrix_coverage": 1, "reliability.matrix_integrity": 0, "reliability.wrapper_transparency": 0,
    "governance.unclassified_fields": 0, "governance.stale_inventory_entries": 0, "governance.access_mismatches": 0,
    "governance.unlisted_operations_allowed": 0, "governance.separation_violations": 0,
    "governance.audit_accounting_violations": 0, "governance.restricted_served_with_audit_failing": 0,
    "governance.content_in_audit_artifacts": 0, "governance.unsafe_purges": 0, "governance.purges_without_intent": 0,
    "governance.contradictory_purge_evidence": 0, "governance.identity_links_surviving_erasure": 0,
    "governance.undetected_chain_corruption": 0, "governance.forbidden_free_text_stored": 0,
    "deployment.data_files_missing_from_package": 0, "deployment.lock_mismatches": 0,
    "deployment.invalid_configurations_accepted": 0, "deployment.secrets_in_artifacts": 0,
    "deployment.non_governed_routes": 0, "deployment.restart_divergence": 0,
    "deployment.corrupted_snapshots_accepted": 0, "deployment.non_atomic_snapshot_outcomes": 0,
    "deployment.misclassified_startup_state": 0, "deployment.untruthful_readiness": 0,
    "deployment.non_content_free_probe_bodies": 0, "deployment.nondeterministic_seeded_runs": 0,
    "deployment.runbook_failures": 0,
    "reference.instrument_failures": 0, "reference.nondeterministic_builds": 0,
    "reference.split_structure_violations": 0, "reference.instrument_failures_real": 0,
    "reference.split_violations": 0, "reference.content_leaks": 0,
    "reference.tracked_reference_files": 0, "reference.unknown_sector_links": 0,
    "reference.parse_error_rows": 0,
    "corpus.provenance_round_trip": 0, "corpus.citation_self_consistency": 0, "corpus.marker_accounting": 0,
    "corpus.generation_new_token_rate": 0, "corpus.generation_evidence_citation": 0, "corpus.generation_field_accounting": 0,
}  # fmt: skip


@pytest.fixture(scope="module")
def report() -> Report:
    return build_report(ROOT, NOPDF, "test")


def test_every_layer_is_present_and_no_gate_fails(report: Report) -> None:
    layers = {d.layer for d in report.definitions}
    assert {
        "detection",
        "documents",
        "relevance",
        "lineage",
        "extraction",
        "generation",
        "similarity",
        "review",
        "workflow",
        "observability",
        "reliability",
        "governance",
        "deployment",
        "reference",
        "corpus",
    } <= layers
    assert report.errors == () and gate_failures(report) == []
    assert set(report.classes_absent) == {EvidenceClass.GENERALIZATION, EvidenceClass.PRODUCTION}
    assert EvidenceClass.GENERALIZATION not in report.classes_present


def test_gate_definitions_equal_the_contract_constants(report: Report) -> None:
    got = {d.id: d.gate for d in report.definitions if d.gate and d.gate.kind.value == "HARD"}
    assert {k: g.expect for k, g in got.items()} == {k: float(v) for k, v in HARD_GATES.items()}
    for d in report.definitions:
        if d.evidence_class is EvidenceClass.CORPUS_COVERAGE:
            assert d.gate is None


def test_a_missing_corpus_makes_corpus_rows_not_measurable_and_nothing_else(report: Report) -> None:
    corpus = [r for r in report.results if r.definition_id.startswith("corpus.")]
    assert corpus and all(r.status is Status.NOT_MEASURABLE for r in corpus)
    others = [r for r in report.results if not r.definition_id.startswith("corpus.")]
    assert all(r.status in (Status.OK, Status.NOT_MEASURABLE, Status.NO_GOLD) for r in others)
    assert not [r for r in corpus if r.value is not None]


def test_unmeasurable_rows_are_named_and_never_zero(report: Report) -> None:
    res = {r.definition_id: r for r in report.results}
    for k in ("review.reviewer_time_per_obligation", "review.stale_and_denied_actions"):
        assert res[k].status is Status.NOT_MEASURABLE and res[k].value is None
    assert res["lineage.target_binding_accuracy"].status is Status.NO_GOLD
    assert "scripted clock" in res["review.submit_to_decision_seconds"].note


def test_the_report_is_deterministic(report: Report) -> None:
    again = build_report(ROOT, NOPDF, "test")
    assert to_json(report) == to_json(again) and to_markdown(report) == to_markdown(again)


def test_known_gaps_are_listed_and_counted(report: Report) -> None:
    assert any("gap-deadline-attachment" in g for g in report.known_gaps)
    res = {r.definition_id: r for r in report.results}
    assert res["generation.accepted_known_gap_contradictions"].numerator == len(
        [g for g in report.known_gaps if g.startswith("generation:")]
    )


def test_rates_print_beside_their_coverage_and_the_text_makes_no_overreaching_claim(
    report: Report,
) -> None:
    md = to_markdown(report)
    assert "(with decided fraction:" in md and "(with abstention rate:" in md
    assert claim_problems(report) == []
    assert (
        "overall" not in md.lower().replace("overall score", "") or "no overall score" in md.lower()
    )
    assert "end-to-end" in md.lower() and "no end-to-end precision or recall exists" in md


def test_no_source_or_obligation_text_appears_in_the_report(report: Report) -> None:
    blob = to_json(report) + to_markdown(report)
    for gold in ("obligations/gold.v1.json", "relevance/gold.v1.json"):
        for case in json.loads((ROOT / gold).read_text(encoding="utf-8")):
            text = case.get("text") if isinstance(case, dict) else None
            if text:
                assert text[:60] not in blob
    for needle in ("Pengendali wajib", "http://", "https://"):
        assert needle not in blob
    assert not re.search(r"\S+@\S+\.\S+", blob)


def test_population_sizes_match_the_registry_and_a_change_is_caught(
    report: Report, tmp_path: Path
) -> None:
    assert check_registry(report, ROOT / "populations.v1.json") == []
    rows = json.loads((ROOT / "populations.v1.json").read_text(encoding="utf-8"))
    row = next(r for r in rows if not r["id"].startswith("corpus."))
    row["n"] += 1
    bad = tmp_path / "reg.json"
    bad.write_text(json.dumps(rows), encoding="utf-8")
    assert len(check_registry(report, bad)) == 1
    assert any(
        "not in the registry" in p for p in check_registry(report, tmp_path / "missing.json")
    )


def test_the_f1_identity_used_by_the_adapters_is_exact() -> None:
    rng = random.Random(1)
    for _ in range(200):
        tp, fp, fn = rng.randint(1, 50), rng.randint(0, 50), rng.randint(0, 50)
        p, r = tp / (tp + fp), tp / (tp + fn)
        assert f1(p, r) == pytest.approx(2 * tp / (2 * tp + fp + fn))


def test_degrading_the_verifier_trips_the_hard_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("regulus.generation.evaluate.verify_raw", lambda *a, **k: [])
    broken = build_report(ROOT, NOPDF, "degraded")
    failed = set(gate_failures(broken))
    assert "generation.undetected_mutations" in failed


def test_degrading_the_extractor_shows_up_as_baseline_drift(
    report: Report, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RulesExtractor, "extract", lambda self, request: ())
    broken = build_report(ROOT, NOPDF, "test")
    base = {"inputs": dict(report.inputs), "metrics": snapshot(report)}
    v = compare(broken, base)
    moved = {d.metric for d in v.drift}
    assert "extraction.candidate_recall" in moved and v.defect is True
    res = {r.definition_id: r for r in broken.results}
    assert (
        res["extraction.candidate_recall"].value == 0
        and res["extraction.silent_deontic_loss"].value == 0
    )


def test_baseline_policy(report: Report, tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    update(report, path, "initial baseline", "code", None)
    base = json.loads(path.read_text(encoding="utf-8"))
    assert compare(report, base).drift == () and base["history"][0]["reason"] == "initial baseline"
    with pytest.raises(BaselineRefused):
        update(report, path, "", "code", base)
    shifted = json.loads(json.dumps(base))
    first = next(iter(shifted["metrics"]))
    shifted["metrics"][first]["numerator"] += 1
    v = compare(report, shifted)
    assert [d.metric for d in v.drift] == [first] and v.defect is True
    with pytest.raises(BaselineRefused, match="unchanged inputs"):
        update(report, path, "metric moved", "code", shifted)
    changed = json.loads(json.dumps(shifted))
    changed["inputs"]["gold:relevance"] = "0" * 64
    v2 = compare(report, changed)
    assert v2.defect is False and "gold:relevance" in v2.changed_inputs
    with pytest.raises(BaselineRefused, match="did not change"):
        update(report, path, "gold edited", "code", changed)
    update(report, path, "gold edited", "gold:relevance", changed)
    assert (
        json.loads(path.read_text(encoding="utf-8"))["history"][-1]["changed_input"]
        == "gold:relevance"
    )


def test_a_failing_hard_gate_or_error_cannot_be_baselined(report: Report, tmp_path: Path) -> None:
    errored = report.model_copy(update={"errors": ("x: boom",)})
    with pytest.raises(BaselineRefused, match="cannot be baselined"):
        update(errored, tmp_path / "b.json", "r", "code", None)


def test_a_worse_hard_gate_metric_cannot_be_baselined(report: Report) -> None:
    from regulus.evaluation.baseline import _hard_worse

    hard = next(r for r in report.results if r.definition_id == "relevance.false_not_relevant")
    previous = {"inputs": {}, "metrics": snapshot(report)}
    bumped = report.model_copy(
        update={
            "results": tuple(
                r.model_copy(update={"numerator": 1.0, "value": 1.0 / r.denominator})
                if r.definition_id == hard.definition_id
                else r
                for r in report.results
            )
        }
    )
    assert _hard_worse(bumped, previous) == ["relevance.false_not_relevant"]
    assert _hard_worse(report, previous) == []


def test_the_four_eyes_scan_detects_an_injected_violation() -> None:
    from regulus.domain import ObligationStatus as S
    from regulus.evaluation.harness import ReviewRun

    run = ReviewRun("obl-x", random.Random(5))
    for _ in range(40):
        run.step()
    log = list(run.log())
    assert four_eyes_violations(log)[0] == 0
    forged_log = [
        log[0].model_copy(
            update={
                "actor_id": "same",
                "decision": log[0].decision.model_copy(update={"to_status": S.EDITED}),
            }
        ),
        log[0].model_copy(
            update={
                "actor_id": "same",
                "decision": log[0].decision.model_copy(update={"to_status": S.APPROVED}),
            }
        ),
    ]
    assert four_eyes_violations(forged_log) == (1, 1)


def test_claim_phrases_are_rejected() -> None:
    assert claim_violations("Regulus accuracy is 91%.") and claim_violations(
        "The pipeline is production ready."
    )
