from datetime import UTC, datetime

import pytest

from conftest import NEUTRAL, NOW, OJK, OTHER, PP30, PP33, UU27, ctx, event, reg, with_scope
from regulus.domain import EventType as T
from regulus.domain import RegulationKind as K
from regulus.relevance import (
    AssessmentContext,
    AssessStatus,
    ClassificationRequest,
    ClassificationResult,
    ClassifierError,
    Decision,
    SemanticEvidence,
    TextSource,
    assess,
)
from regulus.relevance import (
    Confidence as C,
)
from regulus.relevance import (
    Relevance as R,
)
from regulus.relevance.models import (
    Kind,
    Method,
    ScoreKind,
    SectorStatus,
    SemanticStatus,
    title_source,
)


class Fake:
    id, version = "fake", "1"

    def __init__(self, result: ClassificationResult | Exception) -> None:
        self.result, self.calls = result, 0

    def classify(self, request: ClassificationRequest) -> ClassificationResult:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def one(c, config, classifier=None, at=NOW):  # type: ignore[no-untyped-def]
    res = assess(c, config, classifier, at)
    assert res.status is AssessStatus.ASSESSED and res.assessment
    return res.assessment


def sem(
    source: str, span: tuple[int, int], quote: str, sector: str | None = None
) -> SemanticEvidence:
    return SemanticEvidence(source_id=source, span=span, quote=quote, sector=sector)


NEUTRAL_T = title_source(NEUTRAL.id)


def test_needs_review_and_mismatches_are_not_assessable(config) -> None:  # type: ignore[no-untyped-def]
    nr = AssessmentContext(
        event=event(OJK, T.NEEDS_REVIEW, reason="UNRESOLVED_TARGET", declared_ref="x"),  # type: ignore[arg-type]
        regulation=OJK,
    )
    assert assess(nr, config, None, NOW).status is AssessStatus.NOT_ASSESSABLE
    wrong = AssessmentContext(event=event(OJK), regulation=PP33)
    assert assess(wrong, config, None, NOW).status is AssessStatus.NOT_ASSESSABLE
    no_target = AssessmentContext(event=event(OJK, T.AMEND, UU27), regulation=OJK)
    r = assess(no_target, config, None, NOW)
    assert r.status is AssessStatus.NOT_ASSESSABLE and r.assessment is None and r.reason
    extra = AssessmentContext(event=event(OJK), regulation=OJK, target=UU27)
    assert assess(extra, config, None, NOW).status is AssessStatus.NOT_ASSESSABLE


def test_amend_of_watchlisted_target_is_relevant_high(config) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(PP33, T.AMEND, UU27), config)
    assert (a.relevance, a.confidence, a.method) == (R.RELEVANT, C.HIGH, Method.RULES)
    assert any(e.rule_id == "WATCHLIST_TARGET" for e in a.evidence)
    assert a.sectors == ("DATA_PROTECTION",) and a.sector_status is SectorStatus.DETERMINED


def test_exclusion_only_is_not_relevant_high(config) -> None:  # type: ignore[no-untyped-def]
    cfg = with_scope(config, exclusions=(OTHER.id,))
    a = one(ctx(OTHER), cfg)
    assert (a.relevance, a.confidence) == (R.NOT_RELEVANT, C.HIGH) and not a.conflict


def test_watchlist_and_exclusion_conflict(config) -> None:  # type: ignore[no-untyped-def]
    cfg = with_scope(config, exclusions=(UU27.id,))
    a = one(ctx(PP33, T.AMEND, UU27), cfg)
    assert (a.relevance, a.confidence, a.conflict) == (R.INSUFFICIENT_EVIDENCE, C.NONE, True)


def test_new_with_in_scope_title_is_relevant_medium(config) -> None:  # type: ignore[no-untyped-def]
    pojk = reg(K.PERMEN, "5", 2020, "Pembiayaan dan Asuransi Mikro")
    a = one(ctx(pojk), config)
    assert (a.relevance, a.confidence, a.method) == (R.RELEVANT, C.MEDIUM, Method.RULES)
    assert a.sectors == ("FINANCIAL_SERVICES",)


def test_out_of_scope_sector_does_not_exclude(config) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(PP30), config)
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.confidence is C.NONE
    assert a.sectors == ("ENERGY_UTILITIES",) and not a.conflict


def test_weak_text_hit_only_records_evidence_not_sector(config) -> None:  # type: ignore[no-untyped-def]
    t = TextSource(owner_id="a1", text="Pengendali Data Pribadi wajib melapor.")
    a = one(ctx(NEUTRAL, texts=(t,)), config)
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.sectors == ()
    assert a.sector_status is SectorStatus.UNDETERMINED
    assert any(e.rule_id == "TEXT_LEXICON" and e.sector == "DATA_PROTECTION" for e in a.evidence)


def test_no_signal_no_classifier(config) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(NEUTRAL), config)
    assert (a.relevance, a.confidence, a.sectors, a.sector_status, a.semantic) == (
        R.INSUFFICIENT_EVIDENCE,
        C.NONE,
        (),
        SectorStatus.UNDETERMINED,
        None,
    )


def test_relevant_without_sector_evidence_has_undetermined_sectors(config) -> None:  # type: ignore[no-untyped-def]
    cfg = with_scope(config, watchlist=(OTHER.id,), sector_map={})
    a = one(ctx(NEUTRAL, T.AMEND, OTHER), cfg)
    assert (
        a.relevance is R.RELEVANT
        and a.sectors == ()
        and a.sector_status is SectorStatus.UNDETERMINED
    )


def test_semantic_relevant_on_undecided_is_low(config) -> None:  # type: ignore[no-untyped-def]
    q = NEUTRAL.title[:4]
    f = Fake(
        ClassificationResult(
            decision=Decision.RELEVANT,
            evidence=(sem(NEUTRAL_T, (0, 4), q),),
            score=0.97,
            score_kind=ScoreKind.UNCALIBRATED,
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert (a.relevance, a.confidence, a.method) == (R.RELEVANT, C.LOW, Method.SEMANTIC)
    assert (
        a.semantic and a.semantic.score == 0.97 and a.semantic.score_kind is ScoreKind.UNCALIBRATED
    )
    assert (
        any(e.kind is Kind.SEMANTIC for e in a.evidence) and a.semantic.status is SemanticStatus.OK
    )


def test_ungrounded_semantic_evidence_is_dropped_then_abstains(config) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=Decision.RELEVANT,
            evidence=(sem(NEUTRAL_T, (0, 5), "WRONG"), sem("unknown-source", (0, 3), "abc")),
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.semantic
    assert a.semantic.dropped_ungrounded == 2 and a.semantic.status is SemanticStatus.ABSTAINED
    assert not any(e.kind is Kind.SEMANTIC for e in a.evidence)


def test_semantic_sector_outside_taxonomy_is_dropped(config) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=Decision.RELEVANT,
            evidence=(sem(NEUTRAL_T, (0, 4), NEUTRAL.title[:4], "MADE_UP"),),
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and "MADE_UP" not in a.sectors


def test_abstain_and_empty_evidence_decisions(config) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(NEUTRAL), config, Fake(ClassificationResult(decision=Decision.ABSTAIN)))
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.semantic.status is SemanticStatus.ABSTAINED  # type: ignore[union-attr]
    b = one(ctx(NEUTRAL), config, Fake(ClassificationResult(decision=Decision.NOT_RELEVANT)))
    assert b.relevance is R.INSUFFICIENT_EVIDENCE


def test_classifier_never_overrides_a_deterministic_decision(config) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=Decision.NOT_RELEVANT,
            evidence=(sem(title_source(PP33.id), (0, 5), PP33.title[:5]),),
        )
    )
    strong = one(ctx(PP33, T.AMEND, UU27), config, f)
    assert strong.relevance is R.RELEVANT and strong.confidence is C.HIGH and f.calls == 0
    mod = one(ctx(reg(K.PERMEN, "5", 2020, "Pembiayaan dan Asuransi Mikro")), config, f)
    assert mod.relevance is R.RELEVANT and mod.confidence is C.MEDIUM and f.calls == 0


def test_semantic_negative_with_weak_support_is_a_conflict(config) -> None:  # type: ignore[no-untyped-def]
    t = TextSource(owner_id="a1", text="Pengendali Data Pribadi wajib melapor.")
    f = Fake(
        ClassificationResult(
            decision=Decision.NOT_RELEVANT, evidence=(sem("a1", (0, 10), "Pengendali"),)
        )
    )
    a = one(ctx(NEUTRAL, texts=(t,)), config, f)
    assert (a.relevance, a.conflict) == (R.INSUFFICIENT_EVIDENCE, True)


def test_semantic_negative_alone_is_not_relevant_low(config) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=Decision.NOT_RELEVANT, evidence=(sem(NEUTRAL_T, (0, 4), NEUTRAL.title[:4]),)
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert (a.relevance, a.confidence, a.method) == (R.NOT_RELEVANT, C.LOW, Method.SEMANTIC)


@pytest.mark.parametrize("exc", [ClassifierError("x"), TimeoutError("slow"), RuntimeError("boom")])
def test_classifier_failure_never_becomes_not_relevant(config, exc) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(NEUTRAL), config, Fake(exc))
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.semantic.status is SemanticStatus.FAILED  # type: ignore[union-attr]


def test_classifier_adds_sectors_to_relevant_without_sectors(config) -> None:  # type: ignore[no-untyped-def]
    cfg = with_scope(config, watchlist=(OTHER.id,), sector_map={})
    f = Fake(
        ClassificationResult(
            decision=Decision.ABSTAIN,
            evidence=(sem(title_source(OTHER.id), (0, 8), OTHER.title[:8], "DATA_PROTECTION"),),
        )
    )
    a = one(ctx(NEUTRAL, T.AMEND, OTHER), cfg, f)
    assert (a.relevance, a.confidence, a.method) == (R.RELEVANT, C.HIGH, Method.HYBRID)
    assert a.sectors == ("DATA_PROTECTION",) and f.calls == 1


def test_multiple_sectors_sorted_with_evidence(config) -> None:  # type: ignore[no-untyped-def]
    both = reg(K.PERMEN, "7", 2020, "Pergadaian dan Pelindungan Data Pribadi")
    a = one(ctx(both), config)
    assert a.sectors == ("DATA_PROTECTION", "FINANCIAL_SERVICES")
    assert {e.sector for e in a.evidence if e.sector} >= set(a.sectors)


def test_identity_determinism_and_versioning(config) -> None:  # type: ignore[no-untyped-def]
    c = ctx(PP33, T.AMEND, UU27)
    a = one(c, config)
    later = one(c, config, at=datetime(2030, 1, 1, tzinfo=UTC))
    assert a.id == later.id and a.model_dump(exclude={"assessed_at"}) == later.model_dump(
        exclude={"assessed_at"}
    )
    assert a.model_dump_json() == one(c, config).model_dump_json()
    other = with_scope(config, version="2")
    assert one(c, other).id != a.id
    assert one(c, config, Fake(ClassificationResult(decision=Decision.ABSTAIN))).id != a.id


def test_evidence_quotes_verify_and_decided_assessments_have_evidence(config) -> None:  # type: ignore[no-untyped-def]
    for c in (ctx(PP33, T.AMEND, UU27), ctx(OJK)):
        a = one(c, config)
        texts = {title_source(c.regulation.id): c.regulation.title}
        if c.target:
            texts[title_source(c.target.id)] = c.target.title
        for e in a.evidence:
            if e.span:
                assert texts[e.source_id][e.span[0] : e.span[1]] == e.quote
        assert a.evidence and a.summary.startswith(a.relevance.value)


def test_inputs_are_not_mutated(config) -> None:  # type: ignore[no-untyped-def]
    c = ctx(PP33, T.AMEND, UU27)
    snap = (c.model_dump_json(), config.scope.model_dump_json())
    one(c, config)
    assert (c.model_dump_json(), config.scope.model_dump_json()) == snap


def test_real_domain_objects_roundtrip(config) -> None:  # type: ignore[no-untyped-def]
    a = one(ctx(PP33, T.AMEND, UU27), config)
    from regulus.relevance import RelevanceAssessment

    assert RelevanceAssessment.model_validate_json(a.model_dump_json()) == a


@pytest.mark.parametrize("decision", [Decision.RELEVANT, Decision.NOT_RELEVANT])
def test_sector_only_semantic_evidence_never_decides_relevance(config, decision) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=decision,
            evidence=(sem(NEUTRAL_T, (0, 4), NEUTRAL.title[:4], "DATA_PROTECTION"),),
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert a.relevance is R.INSUFFICIENT_EVIDENCE and a.confidence is C.NONE
    assert a.method is Method.RULES and a.sectors == ()
    assert not any(e.kind is Kind.SEMANTIC for e in a.evidence)
    assert a.semantic is not None and a.semantic.status is SemanticStatus.ABSTAINED


def test_relevance_evidence_alongside_sector_evidence_still_decides(config) -> None:  # type: ignore[no-untyped-def]
    f = Fake(
        ClassificationResult(
            decision=Decision.RELEVANT,
            evidence=(
                sem(NEUTRAL_T, (0, 4), NEUTRAL.title[:4]),
                sem(NEUTRAL_T, (5, 9), NEUTRAL.title[5:9], "DATA_PROTECTION"),
            ),
        )
    )
    a = one(ctx(NEUTRAL), config, f)
    assert (a.relevance, a.confidence, a.method) == (R.RELEVANT, C.LOW, Method.SEMANTIC)
    assert a.sectors == ("DATA_PROTECTION",)
