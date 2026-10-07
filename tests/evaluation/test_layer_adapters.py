from pathlib import Path

import pytest

from regulus.evaluation import Report, Status
from regulus.evaluation.builder import Builder
from regulus.evaluation.layers import extraction, generation, lineage, relevance, similarity

ROOT = Path(__file__).parents[2] / "evaluation"


def run(mod, fn: str = "evaluate") -> Builder:  # type: ignore[no-untyped-def]
    b = Builder()
    getattr(mod, fn)(b, ROOT)
    return b


def val(b: Builder, id: str):  # type: ignore[no-untyped-def]
    return b.results[id]


def test_relevance_adapter_matches_the_pinned_confusion_counts() -> None:
    b = run(relevance)
    r = val(b, "relevance.relevant_precision")
    assert (r.numerator, r.denominator) == (14, 16)
    assert (
        val(b, "relevance.relevant_recall").numerator,
        val(b, "relevance.relevant_recall").denominator,
    ) == (14, 18)
    assert (
        val(b, "relevance.abstention_rate").numerator,
        val(b, "relevance.abstention_rate").denominator,
    ) == (22, 40)
    assert val(b, "relevance.decided_fraction").numerator == 18
    f1 = val(b, "relevance.relevant_f1")
    assert f1.value == pytest.approx(2 * (14 / 16) * (14 / 18) / ((14 / 16) + (14 / 18)))
    assert (
        val(b, "relevance.false_not_relevant").value == 0
        and val(b, "relevance.unexplained_decisions").value == 0
    )
    assert (
        b.definitions["relevance.relevant_precision"].qualified_by == "relevance.decided_fraction"
    )
    assert b.definitions["relevance.relevant_recall"].qualified_by == "relevance.abstention_rate"


def test_lineage_adapter_reports_what_the_gold_can_and_cannot_support() -> None:
    b = run(lineage)
    assert val(b, "lineage.target_binding_accuracy").status is Status.NO_GOLD
    assert val(b, "lineage.false_resolution_rate").value == 0
    assert (
        val(b, "lineage.kind_accuracy").denominator
        == val(b, "lineage.locator_accuracy").denominator
    )
    assert val(b, "lineage.recognition_recall").denominator > 0


def test_extraction_adapter_uses_citations_and_markers_as_denominators() -> None:
    b = run(extraction)
    assert (
        val(b, "extraction.unsupported_claims").value == 0
        and val(b, "extraction.unsupported_claims").denominator > 100
    )
    assert (
        val(b, "extraction.silent_deontic_loss").value == 0
        and val(b, "extraction.silent_deontic_loss").denominator > 30
    )
    p, r = val(b, "extraction.candidate_precision"), val(b, "extraction.candidate_recall")
    assert (
        p.numerator == r.numerator
        and p.denominator != r.denominator
        or p.denominator == r.denominator
    )


def test_generation_adapter_gates_hold_and_known_gaps_are_listed() -> None:
    b = run(generation)
    assert (
        val(b, "generation.undetected_mutations").denominator == 567
        and val(b, "generation.undetected_mutations").value == 0
    )
    assert val(b, "generation.unexpected_accepted_contradictions").value == 0
    assert val(b, "generation.accepted_known_gap_contradictions").numerator == len(b.known_gaps) > 0
    for k in (
        "hallucinated_tokens",
        "field_accounting",
        "open_question_preservation",
        "evidence_citation",
    ):
        r = val(b, f"generation.{k}")
        assert r.value == 0 and r.denominator > 0, k


def test_similarity_adapter_uses_the_contract_definitions() -> None:
    b = run(similarity, "evaluate_layer")
    rec, pre, mrr = (val(b, f"similarity.{k}") for k in ("recall_at_3", "precision_at_3", "mrr"))
    assert rec.denominator <= 12 and pre.denominator >= rec.denominator
    assert 0 <= rec.value <= 1 and 0 <= pre.value <= 1 and 0 <= mrr.value <= 1  # type: ignore[operator]
    assert b.definitions["similarity.mrr"].formula.value == "MEAN"
    assert val(b, "similarity.ceiling_and_evidence_violations").value == 0
    assert (
        "not independent model families" in val(b, "similarity.provider_label_disagreements").note
    )
    assert val(b, "similarity.false_duplicate_rate").gate_passed is True


def test_all_adapters_assemble_into_a_valid_report() -> None:
    b = Builder()
    for mod, fn in (
        (relevance, "evaluate"),
        (lineage, "evaluate"),
        (extraction, "evaluate"),
        (generation, "evaluate"),
        (similarity, "evaluate_layer"),
    ):
        getattr(mod, fn)(b, ROOT)
    rep = Report(
        inputs={},
        populations=tuple(b.populations.values()),
        definitions=tuple(b.definitions.values()),
        results=tuple(b.results.values()),
        known_gaps=tuple(b.known_gaps),
    )
    assert not [r for r in rep.results if r.status is Status.GATE_FAILED]


def test_detection_adapter_is_adversarial_and_gates_hold() -> None:
    from regulus.evaluation.layers import detection

    b = run(detection)
    assert (
        val(b, "detection.false_resolution_rate").value == 0
        and val(b, "detection.false_resolution_rate").denominator >= 10
    )
    assert (
        val(b, "detection.order_invariance_violations").value == 0
        and val(b, "detection.replay_violations").value == 0
    )
    assert (
        val(b, "detection.outcome_accuracy").numerator
        == val(b, "detection.outcome_accuracy").denominator
    )
    from regulus.change_detection.evaluate import evaluate_gold, load_gold

    tags = set(evaluate_gold(load_gold(ROOT / "change_detection" / "gold.v1.json")).tags)
    need = {
        "metadata-conflict",
        "ambiguous-target",
        "malformed-target",
        "self-reference",
        "contradictory-relations",
        "duplicate-relation",
        "post-repeal-anomaly",
        "invalid-input",
        "happy",
    }
    assert need <= tags


def test_documents_adapter_covers_the_required_structures_and_failures() -> None:
    from regulus.documents.evaluate import evaluate_gold, load_gold
    from regulus.evaluation.layers import documents

    b = run(documents)
    assert b.errors == []
    assert (
        val(b, "documents.explicit_failure").value == 1.0
        and val(b, "documents.explicit_failure").gate_passed is True
    )
    assert val(b, "documents.provenance_round_trip").value == 0
    tags = set(evaluate_gold(load_gold(ROOT / "documents" / "gold.v1.json")).tags)
    need = {
        "standard",
        "amending-unit",
        "quoted-pasal",
        "mixed-body-form",
        "catchword",
        "unicode-ellipsis",
        "page-boundary",
        "missing-page-text",
        "unreadable",
        "incomplete-source",
    }
    assert need <= tags
