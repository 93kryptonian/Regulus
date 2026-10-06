from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import NEUTRAL, NOW, OTHER, UU27, ctx
from regulus.domain import EventType as T
from regulus.relevance import (
    AssessmentConfig,
    ClassificationRequest,
    ClassificationResult,
    Decision,
    SemanticEvidence,
    assess,
    load_rules,
    load_scope,
    load_taxonomy,
)
from regulus.relevance import (
    Relevance as R,
)
from regulus.relevance.evaluate import GoldCase, evaluate, load_gold, run
from regulus.relevance.models import title_source

GOLD = Path(__file__).parents[2] / "evaluation" / "relevance" / "gold.v1.json"


@pytest.fixture(scope="module")
def cfg() -> AssessmentConfig:
    return AssessmentConfig(taxonomy=load_taxonomy(), scope=load_scope(), rules=load_rules())


@pytest.fixture(scope="module")
def cases() -> list[GoldCase]:
    return load_gold(GOLD)


def gold(cid: str, relevance: R, sectors: tuple[str, ...] = (), actor=NEUTRAL, **kw) -> GoldCase:  # type: ignore[no-untyped-def]
    c = ctx(actor, **kw)
    return GoldCase(
        case_id=cid,
        event=c.event,
        regulation=c.regulation,
        target=c.target,
        relevance=relevance,
        sectors=sectors,
        rationale="a reason for the label",
        annotator="t",
        guideline_version="g",
    )


def test_gold_set_is_well_formed(cases: list[GoldCase], cfg: AssessmentConfig) -> None:
    assert len(cases) == 40 and len({c.case_id for c in cases}) == 40
    assert all(len(c.rationale) >= 10 and c.annotator and c.guideline_version for c in cases)
    assert all(set(c.sectors) <= cfg.taxonomy.codes for c in cases)
    assert {c.relevance for c in cases} == {R.RELEVANT, R.NOT_RELEVANT}
    assert {c.event.type.value for c in cases} >= {"NEW", "AMEND", "REPEAL", "PARTIAL_REPEAL"}


def test_gold_requires_a_rationale() -> None:
    with pytest.raises(ValidationError):
        GoldCase.model_validate({**gold("x", R.RELEVANT).model_dump(), "rationale": "short"})


def test_pinned_metrics_on_the_gold_set(cases: list[GoldCase], cfg: AssessmentConfig) -> None:
    r = run(cases, cfg)
    assert r.total == 40
    assert r.confusion["RELEVANT"] == {
        "RELEVANT": 14,
        "NOT_RELEVANT": 0,
        "INSUFFICIENT_EVIDENCE": 4,
    }
    assert r.confusion["NOT_RELEVANT"] == {
        "RELEVANT": 2,
        "NOT_RELEVANT": 2,
        "INSUFFICIENT_EVIDENCE": 18,
    }
    assert r.false_not_relevant == ()
    assert set(r.false_relevant) == {"n-fp-pramuka", "n-fp-banksampah"}
    assert (r.precision, r.recall) == (14 / 16, 14 / 18) and r.recall_decided == 1.0
    assert r.abstention_rate == 22 / 40
    assert r.explainability_violations == ()
    assert round(r.sector_micro_f1 or 0, 3) == 0.897 and r.sector_exact_match == 0.825


def test_vocabulary_gaps_abstain_instead_of_guessing(
    cases: list[GoldCase], cfg: AssessmentConfig
) -> None:
    by = {c.case_id: c for c in cases}
    for cid in ("n-gap-privasi", "n-gap-keuangan", "n-text-dp", "n-text-both"):
        a = assess(by[cid].context(), cfg, None, NOW).assessment
        assert (
            a is not None
            and a.relevance is R.INSUFFICIENT_EVIDENCE
            and by[cid].relevance is R.RELEVANT
        )


def test_run_is_deterministic(cases: list[GoldCase], cfg: AssessmentConfig) -> None:
    assert run(cases, cfg).model_dump_json() == run(cases, cfg).model_dump_json()


class Pessimist:
    id, version = "pessimist", "1"

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        t = request.regulation.title
        ev = SemanticEvidence(
            source_id=title_source(request.regulation.id), span=(0, 4), quote=t[:4]
        )
        return ClassificationResult(decision=Decision.NOT_RELEVANT, evidence=(ev,))


def test_metric_surfaces_a_classifier_that_drops_relevant_changes(
    cases: list[GoldCase], cfg: AssessmentConfig
) -> None:
    r = run(cases, cfg, Pessimist())
    assert r.false_not_relevant
    assert set(r.false_not_relevant) >= {"n-gap-privasi", "n-gap-keuangan"}
    assert r.explainability_violations == ()


def test_evaluate_metrics_on_a_hand_made_set(cfg: AssessmentConfig) -> None:
    from conftest import PP33

    cs = [
        gold("a", R.RELEVANT, ("DATA_PROTECTION",), PP33, type=T.AMEND, target=UU27),
        gold("b", R.NOT_RELEVANT, (), NEUTRAL),
        gold("c", R.RELEVANT, ("FINANCIAL_SERVICES",), OTHER),
    ]
    results = [assess(c.context(), cfg, None, NOW).assessment for c in cs]
    assert all(x is not None for x in results)
    r = evaluate(cs, [x for x in results if x is not None])
    assert (
        r.confusion["RELEVANT"]["RELEVANT"] == 1
        and r.confusion["RELEVANT"]["INSUFFICIENT_EVIDENCE"] == 1
    )
    assert r.precision == 1.0 and r.recall == 0.5 and r.recall_decided == 1.0
    with pytest.raises(ValueError):
        evaluate(cs, [x for x in results[:2] if x is not None])
