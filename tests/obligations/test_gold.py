from pathlib import Path

import pytest

from regulus.obligations import FieldStatus
from regulus.obligations.evaluate import PRF, GoldCase, evaluate_gold, load_gold
from regulus.obligations.models import RawCandidate, RawField, RawFieldState
from regulus.obligations.rules import RulesExtractor

GOLD = Path(__file__).parents[2] / "evaluation" / "obligations" / "gold.v1.json"


@pytest.fixture(scope="module")
def cases() -> list[GoldCase]:
    return load_gold(GOLD)


def test_gold_is_well_formed(cases: list[GoldCase]) -> None:
    assert len(cases) == 38 and len({c.case_id for c in cases}) == 38
    assert {c.source for c in cases} == {
        "SYNTHETIC",
        "REAL_PP33_2026",
        "REAL_POJK_31_2016",
        "REAL_PERMEN_LH_18_2009",
    }
    assert all(len(c.rationale) >= 10 for c in cases)
    assert all(c.citation for c in cases if c.source != "SYNTHETIC")
    assert any(not c.candidates for c in cases)


def test_hard_gates_on_the_gold_set(cases: list[GoldCase]) -> None:
    r = evaluate_gold(cases)
    assert r.unsupported_claims == 0 and r.citation_failures == 0 and r.silent_loss == 0


def f(prf: PRF) -> tuple[int, int, int]:
    return prf.tp, prf.fp, prf.fn


def test_pinned_metrics_and_known_gaps(cases: list[GoldCase]) -> None:
    r = evaluate_gold(cases)
    assert f(r.candidates) == (36, 0, 2)
    assert {k: f(v) for k, v in r.fields.items()} == {
        "actor": (28, 3, 8),
        "action": (35, 0, 2),
        "object": (26, 3, 5),
        "deadline": (4, 0, 1),
        "frequency": (1, 0, 0),
        "condition": (6, 0, 2),
        "exception": (2, 0, 0),
    }
    assert (
        round(r.not_stated_accuracy or 0, 3) == 0.909 and round(r.multiplicity_accuracy, 3) == 0.947
    )
    assert r.false_no_obligation == ("s-unlisted-lexeme",) and r.unresolved_cases == (
        "s-non-verb",
        "s-colon-no-items",
    )


def test_run_is_deterministic(cases: list[GoldCase]) -> None:
    assert evaluate_gold(cases).model_dump_json() == evaluate_gold(cases).model_dump_json()


class Fabricator:
    id, version = "fabricator", "1"

    def __init__(self) -> None:
        self.base = RulesExtractor()

    def extract(self, request):  # type: ignore[no-untyped-def]
        out = []
        for c in self.base.extract(request):
            if c.action.value is None:
                out.append(c)
                continue
            fake = RawFieldState(
                status=FieldStatus.PRESENT,
                value=RawField(
                    value="dibuat-buat", start=c.action.value.start, end=c.action.value.end
                ),
            )
            out.append(c.model_copy(update={"object": fake}))
        return tuple(out)


def test_a_fabricating_extractor_cannot_raise_the_unsupported_claim_count(
    cases: list[GoldCase],
) -> None:
    r = evaluate_gold(cases, Fabricator())
    assert r.unsupported_claims == 0 and r.silent_loss == 0
    assert r.fields["object"].tp == 0 and r.fields["object"].fp == 0


def test_evaluator_scores_a_wrong_value_as_fp_and_fn() -> None:
    from regulus.obligations.evaluate import GoldCandidate

    case = GoldCase(
        case_id="x",
        source="SYNTHETIC",
        text="Pasal 1\nA wajib menyampaikan laporan.",
        rationale="a deliberately wrong label",
        candidates=(
            GoldCandidate(
                marker_index=0,
                modality="OBLIGATION",
                fields={"actor": "B", "action": "menyampaikan", "object": "laporan"},
            ),
        ),
    )
    r = evaluate_gold([case])
    assert f(r.fields["actor"]) == (0, 1, 1) and f(r.fields["action"]) == (1, 0, 0)


def test_rawcandidate_type_is_importable() -> None:
    assert RawCandidate.model_fields["clause"]
