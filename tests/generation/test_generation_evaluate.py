from pathlib import Path

import pytest
from gen_helpers import make_doc

from regulus.generation import ExtractiveGenerator, GenerationRequest, Violation
from regulus.generation.evaluate import (
    MUTATIONS,
    candidates_for,
    load_contradictions,
    run_contradictions,
    run_generation,
    run_mutations,
    source_of,
)
from regulus.generation.verify import verify_raw
from regulus.obligations import load_lexicon
from regulus.obligations.evaluate import GoldCase, load_gold

ROOT = Path(__file__).parents[2] / "evaluation"


@pytest.fixture(scope="module")
def pairs():  # type: ignore[no-untyped-def]
    return candidates_for(load_gold(ROOT / "obligations" / "gold.v1.json"))


def test_gold_candidates_all_generate_with_zero_hallucination(pairs) -> None:  # type: ignore[no-untyped-def]
    r = run_generation(pairs)
    assert r.total == 36 and r.generated == 36 and r.rejected == 0
    assert (
        r.hallucinated_tokens,
        r.citation_failures,
        r.incomplete_fields,
        r.unaccounted_fields,
    ) == (0, 0, 0, 0)
    assert r.open_questions == 13


def test_every_mutation_is_detected_and_every_class_is_exercised(pairs) -> None:  # type: ignore[no-untyped-def]
    m = run_mutations(pairs)
    assert m.undetected == ()
    assert set(m.applicable) == set(MUTATIONS)
    assert m.detected == m.applicable and sum(m.applicable.values()) == 567


EXPECTED = {
    "drop_condition": Violation.FIELD_LOST,
    "drop_exception": Violation.FIELD_LOST,
    "drop_deadline": Violation.FIELD_LOST,
    "drop_frequency": Violation.FIELD_LOST,
    "drop_actor": Violation.FIELD_LOST,
    "replace_actor": Violation.NEW_WORD,
    "swap_modality": Violation.NEW_WORD,
    "add_negation": Violation.MODALITY_CHANGED,
    "duplicate_marker": Violation.NEW_WORD,
    "invent_requirement": Violation.NEW_WORD,
    "invent_deadline": Violation.NEW_WORD,
    "invent_exception": Violation.NEW_WORD,
    "expand_term": Violation.NEW_WORD,
    "convert_number": Violation.NUMBER_CHANGED,
    "actor_to_end": Violation.ORDER_CHANGED,
    "object_before_action": Violation.ORDER_CHANGED,
    "move_deadline": Violation.ORDER_CHANGED,
    "alter_content_actor": Violation.FIELD_ALTERED,
    "drop_trace_entry": Violation.TRACE_INVALID,
    "forge_trace_entry": Violation.TRACE_INVALID,
    "bad_drop_reason": Violation.TRACE_INVALID,
    "empty_text": Violation.REQUIRED_MISSING,
}


def test_each_mutation_class_raises_its_specific_violation(pairs) -> None:  # type: ignore[no-untyped-def]
    lex = load_lexicon()
    seen: set[str] = set()
    for c, doc in pairs:
        text = doc.articles[0].text
        src = source_of(c, text)
        raw = ExtractiveGenerator().generate(
            GenerationRequest(candidate=c, source=src, config_version="1")
        )
        for name, fn in MUTATIONS.items():
            m = fn(c, raw)
            if m is None or m == raw or name in seen:
                continue
            seen.add(name)
            assert EXPECTED[name] in verify_raw(c, src, m, lex), name
    assert seen == set(MUTATIONS)


def test_reference_output_always_verifies(pairs) -> None:  # type: ignore[no-untyped-def]
    lex = load_lexicon()
    for c, doc in pairs:
        src = source_of(c, doc.articles[0].text)
        raw = ExtractiveGenerator().generate(
            GenerationRequest(candidate=c, source=src, config_version="1")
        )
        assert verify_raw(c, src, raw, lex) == []


def test_contradictions_are_rejected_except_the_listed_known_gaps() -> None:
    cases = load_contradictions(ROOT / "generation" / "contradictions.v1.json")
    r = run_contradictions(cases)
    assert r.total == 10 and r.accepted_unexpected == () and r.rejected == 8
    assert set(r.accepted_known_gaps) == {"gap-deadline-attachment", "gap-unfielded-recipients"}
    assert all(c.known_gap for c in cases if c.case_id in r.accepted_known_gaps)


def test_a_verifier_gap_not_listed_would_fail_the_gate() -> None:
    cases = load_contradictions(ROOT / "generation" / "contradictions.v1.json")
    unlabeled = [c.model_copy(update={"known_gap": False}) for c in cases]
    r = run_contradictions(unlabeled)
    assert set(r.accepted_unexpected) == {"gap-deadline-attachment", "gap-unfielded-recipients"}


def test_token_multiplicity_is_enforced() -> None:
    doc = make_doc("Pasal 1\nPengendali wajib menyimpan arsip.")
    ((c, _),) = candidates_for(
        [
            GoldCase(
                case_id="x",
                source="S",
                text="Pasal 1\nPengendali wajib menyimpan arsip.",
                rationale="multiplicity probe",
            )
        ]
    )
    src = source_of(c, doc.articles[0].text)
    raw = ExtractiveGenerator().generate(
        GenerationRequest(candidate=c, source=src, config_version="1")
    )
    assert Violation.NEW_WORD in verify_raw(
        c,
        src,
        raw.model_copy(update={"text": "Pengendali wajib wajib menyimpan arsip"}),
        load_lexicon(),
    )
