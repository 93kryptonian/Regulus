from pathlib import Path

import pytest

from regulus.similarity.evaluate import SimilarityGold, evaluate, load_gold
from regulus.similarity.models import Label, RelationConfig

GOLD = Path(__file__).parents[2] / "evaluation" / "similarity" / "gold.v1.json"


@pytest.fixture(scope="module")
def gold() -> SimilarityGold:
    return load_gold(GOLD)


def test_gold_is_well_formed(gold: SimilarityGold) -> None:
    assert (len(gold.corpus), len(gold.queries), len(gold.pairs)) == (71, 12, 71)
    assert {p.label for p in gold.pairs} == set(Label)
    assert all(len(p.rationale) >= 10 for p in gold.pairs)
    assert all(q.obligation.status.value == "GENERATED" for q in gold.queries)
    assert all(e.obligation.status.value == "APPROVED" for e in gold.corpus)
    ids = {e.obligation.id for e in gold.corpus}
    assert all(p.match_id in ids for p in gold.pairs)


def test_hard_gates_and_pinned_metrics(gold: SimilarityGold) -> None:
    r = evaluate(gold)
    assert r.unevidenced_labels == 0 and r.cap_violations == 0 and r.provider_disagreements == 0
    assert r.deterministic and r.false_duplicates == () and r.duplicate_precision == 1.0
    assert r.label_accuracy == 1.0 and r.mrr == 1.0
    assert (round(r.recall_at_3, 3), round(r.precision_at_3, 3)) == (0.944, 0.944)
    assert r.confusion["POSSIBLE_DUPLICATE"]["POSSIBLE_DUPLICATE"] == 12
    assert (
        r.confusion["RELATED"]["RELATED"] == 24
        and r.confusion["SIMILAR_TEXT_ONLY"]["SIMILAR_TEXT_ONLY"] == 12
    )


def test_hard_negatives_are_in_the_gold_and_never_duplicates(gold: SimilarityGold) -> None:
    related = [p for p in gold.pairs if p.label is Label.RELATED]
    assert len(related) == 24 and any("hard negative" in p.rationale for p in related)
    r = evaluate(gold)
    assert r.confusion["RELATED"]["POSSIBLE_DUPLICATE"] == 0


def test_tightening_the_threshold_never_creates_duplicates(gold: SimilarityGold) -> None:
    strict = evaluate(gold, RelationConfig(tau_dup=0.99))
    assert strict.false_duplicates == () and strict.cap_violations == 0


def test_the_cap_metric_catches_a_classifier_that_ignores_the_ceiling(
    gold: SimilarityGold, monkeypatch: pytest.MonkeyPatch
) -> None:
    from regulus.similarity import evaluate as ev
    from regulus.similarity.models import Verdict

    def always_duplicate(q, m, cfg=None):  # type: ignore[no-untyped-def]
        return Verdict(label=Label.POSSIBLE_DUPLICATE, comparisons=(), supporting_fields=("actor",))

    monkeypatch.setattr(ev, "classify", always_duplicate)
    import sys

    monkeypatch.setattr(sys.modules["regulus.similarity.search"], "classify", always_duplicate)
    r = evaluate(gold)
    assert r.false_duplicates and r.label_accuracy < 1.0
