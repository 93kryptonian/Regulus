import pytest

from regulus.reference.matching import BASELINE
from regulus.reference.metrics import (
    alter_text,
    drop,
    duplicate,
    instrument_problems,
    null,
    oracle,
    rotate_articles,
    score,
    shift_articles,
    wrong_sector,
)
from regulus.reference.models import MatchKind, PredictedObligation
from regulus.reference.synthetic import synthetic_corpus

C = synthetic_corpus()


def test_the_oracle_matches_everything_and_the_null_system_nothing():
    for rid in ("syn-a", "syn-b", "syn-c"):
        n = len(C.obligations_of(rid))
        s = score(C, oracle(C, rid))
        assert (s.matched, s.missing, s.over_generated, s.duplicate_predicted) == (n, 0, 0, 0)
        assert (
            s.link_hit == s.link_reference == s.link_predicted
            and s.covered_articles == s.reference_articles
        )
        z = score(C, null(rid))
        assert (z.matched, z.missing, z.over_generated) == (0, n, 0)


@pytest.mark.parametrize("k", [1, 2])
def test_each_mutation_moves_exactly_its_metric(k):
    o = oracle(C, "syn-a")
    n = len(o.obligations)
    d = score(C, drop(o, k))
    assert (d.matched, d.missing, d.over_generated, d.duplicate_predicted) == (n - k, k, 0, 0)
    u = score(C, duplicate(o, k))
    assert (u.matched, u.duplicate_predicted, u.over_generated, u.missing) == (n, k, 0, 0)
    a = score(C, alter_text(o, k))
    assert (a.matched, a.over_generated, a.missing, a.article_overlap_only) == (n - k, k, k, k)


def test_shifted_and_rotated_articles_are_detected_without_changing_matches():
    o = oracle(C, "syn-a")
    h = score(C, shift_articles(o))
    assert h.matched == len(o.obligations) and h.covered_articles == 0 and h.link_hit == 0
    r = score(C, rotate_articles(o))
    assert r.matched == len(o.obligations) and r.link_hit < r.link_reference


def test_wrong_sector_is_detected_without_changing_matches():
    o = oracle(C, "syn-a")
    w = score(C, wrong_sector(o, C.sectors))
    assert w.matched == len(o.obligations) and w.sector_agreed < w.sector_checked


def test_a_repeated_prediction_is_a_duplicate_not_a_second_match():
    p = PredictedObligation(text="MELAKUKAN  pendaftaran usaha", articles=(1, 2))
    from regulus.reference.models import SystemOutput

    s = score(C, SystemOutput(regulation_id="syn-a", obligations=(p, p)))
    assert (s.matched, s.duplicate_predicted, s.over_generated) == (1, 1, 0)


def test_repeated_reference_obligations_absorb_repeated_predictions():
    p = PredictedObligation(text="Melaporkan kegiatan usaha", articles=(3,))
    from regulus.reference.models import SystemOutput

    s = score(C, SystemOutput(regulation_id="syn-a", obligations=(p, p, p)))
    assert (s.matched, s.duplicate_predicted) == (2, 1)


def test_article_overlap_is_a_diagnostic_not_a_match():
    refs = C.obligations_of("syn-a")
    arts = {o.obligation_id: frozenset({1}) for o in refs}
    near = BASELINE.match(PredictedObligation(text="beda total", articles=(1,)), refs, arts)
    none = BASELINE.match(PredictedObligation(text="beda total", articles=(99,)), refs, arts)
    assert near.kind is MatchKind.ARTICLE_OVERLAP and not near.matched and near.overlapping
    assert none.kind is MatchKind.NONE and BASELINE.version == near.matcher_version


def test_unreconciled_counts_are_flagged_on_the_score():
    assert (
        score(C, oracle(C, "syn-b")).count_unreconciled
        and not score(C, oracle(C, "syn-a")).count_unreconciled
    )
    assert score(C, oracle(C, "syn-b")).declared_count == 3


def test_the_instrument_passes_on_the_synthetic_corpus():
    assert instrument_problems(C) == []


def test_the_instrument_notices_a_broken_matcher():
    from regulus.reference.models import MatchResult

    class Lenient:
        version = "lenient"

        def match(self, predicted, candidates, articles):  # type: ignore[no-untyped-def]
            ids = tuple(o.obligation_id for o in candidates)
            return MatchResult(
                kind=MatchKind.EXACT_NORMALIZED, matched=ids, matcher_version="lenient"
            )

    assert instrument_problems(C, Lenient()) != []


def test_the_instrument_notices_a_matcher_that_never_matches():
    from regulus.reference.models import MatchResult

    class Blind:
        version = "blind"

        def match(self, predicted, candidates, articles):  # type: ignore[no-untyped-def]
            return MatchResult(kind=MatchKind.NONE, matcher_version="blind")

    assert instrument_problems(C, Blind()) != []
