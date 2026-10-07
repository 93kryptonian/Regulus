import pytest

from regulus.evaluation import (
    EvidenceClass,
    Formula,
    Gate,
    GateKind,
    MetricDefinition,
    MetricResult,
    Population,
    Report,
    Status,
    claim_violations,
    f1,
    make_result,
    wilson,
)
from regulus.evaluation.models import SMALL_N

POP = Population(id="gold.x", description="d", source="s", n=40, built_by="author", limitations="l")


def defn(
    id: str = "x.metric",
    cls: EvidenceClass = EvidenceClass.REGRESSION,
    gate: Gate | None = None,
    name: str = "metric",
    **kw,
) -> MetricDefinition:  # type: ignore[no-untyped-def]
    return MetricDefinition(
        id=id,
        layer="x",
        name=name,
        population_id="gold.x",
        numerator_definition="n",
        denominator_definition="d",
        evidence_class=cls,
        gate=gate,
        **kw,
    )


def test_zero_denominator_is_not_measurable_never_zero_or_nan() -> None:
    r = make_result(defn(), 0, 0, 40)
    assert r.status is Status.NOT_MEASURABLE and r.value is None and r.interval is None


def test_value_and_interval_follow_the_counts_for_small_populations_only() -> None:
    r = make_result(defn(), 31, 36, 40)
    assert (
        r.value == pytest.approx(31 / 36)
        and r.interval is not None
        and r.interval[0] < r.value < r.interval[1]
    )
    big = make_result(defn(), 150, 200, 40)
    assert big.interval is None and SMALL_N == 100


def test_wilson_matches_known_values_and_rejects_nonsense() -> None:
    lo, hi = wilson(31, 36)
    assert (round(lo, 2), round(hi, 2)) == (0.71, 0.94)
    assert wilson(0, 10)[0] == 0.0 and wilson(10, 10)[1] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        wilson(5, 0)
    assert f1(0.5, 0.5) == 0.5 and f1(None, 0.5) is None and f1(0.0, 0.0) is None


def test_a_hard_gate_fails_the_result_and_a_target_only_reports() -> None:
    hard, target, report_only = (
        defn(gate=Gate(kind=k)) for k in (GateKind.HARD, GateKind.TARGET, GateKind.REPORT_ONLY)
    )
    assert (
        make_result(hard, 0, 10, 40).status is Status.OK
        and make_result(hard, 0, 10, 40).gate_passed is True
    )
    failed = make_result(hard, 1, 10, 40)
    assert failed.status is Status.GATE_FAILED and failed.gate_passed is False
    t = make_result(target, 1, 10, 40)
    assert t.status is Status.OK and t.gate_passed is False
    assert make_result(report_only, 1, 10, 40).gate_passed is None
    assert (
        make_result(defn(gate=Gate(kind=GateKind.HARD, expect=1.0)), 5, 5, 40).gate_passed is True
    )


def test_impossible_results_cannot_be_constructed() -> None:
    with pytest.raises(ValueError):
        MetricResult(
            definition_id="a",
            population_n=1,
            numerator=1,
            denominator=0,
            value=1.0,
            status=Status.OK,
        )
    with pytest.raises(ValueError):
        MetricResult(
            definition_id="a",
            population_n=1,
            numerator=1,
            denominator=2,
            value=0.9,
            status=Status.OK,
        )
    with pytest.raises(ValueError):
        MetricResult(
            definition_id="a",
            population_n=1,
            numerator=0,
            denominator=0,
            value=0.0,
            status=Status.NO_GOLD,
        )
    with pytest.raises(ValueError):
        MetricResult(
            definition_id="a",
            population_n=1,
            numerator=1,
            denominator=2,
            value=0.5,
            status=Status.OK,
            interval=(0.1, 0.9),
        ) if False else MetricResult(
            definition_id="a",
            population_n=1,
            numerator=150,
            denominator=200,
            value=0.75,
            status=Status.OK,
            interval=(0.7, 0.8),
        )


def test_corpus_coverage_cannot_carry_a_gate_or_a_correctness_name() -> None:
    with pytest.raises(ValueError):
        defn(cls=EvidenceClass.CORPUS_COVERAGE, gate=Gate(kind=GateKind.HARD))
    for bad in ("precision on the corpus", "recall", "unsupported claims", "accuracy"):
        with pytest.raises(ValueError):
            defn(cls=EvidenceClass.CORPUS_COVERAGE, name=bad)
    ok = defn(cls=EvidenceClass.CORPUS_COVERAGE, name="outcome counts")
    assert ok.gate is None


def test_absent_classes_cannot_be_used() -> None:
    for c in (EvidenceClass.GENERALIZATION, EvidenceClass.PRODUCTION):
        with pytest.raises(ValueError):
            defn(cls=c)


def report(results, definitions=None, populations=(POP,)) -> Report:  # type: ignore[no-untyped-def]
    return Report(
        inputs={},
        populations=tuple(populations),
        definitions=tuple(definitions or (defn(),)),
        results=tuple(results),
    )


def test_the_report_enforces_definitions_populations_and_uniqueness() -> None:
    d = defn()
    ok = make_result(d, 1, 2, 40)
    report([ok])
    with pytest.raises(ValueError, match="without a definition"):
        report([make_result(defn(id="y.m"), 1, 2, 40)])
    with pytest.raises(ValueError, match="two results"):
        report([ok, ok])
    with pytest.raises(ValueError, match="registry"):
        report([make_result(d, 1, 2, 39)])
    with pytest.raises(ValueError, match="unregistered"):
        report([ok], populations=())
    with pytest.raises(ValueError, match="duplicate"):
        report([ok], definitions=(d, d))


def test_a_qualified_metric_cannot_appear_without_its_coverage() -> None:
    cov = defn(id="x.decided", name="decided fraction")
    prec = defn(id="x.precision", name="precision", qualified_by="x.decided")
    with pytest.raises(ValueError, match="qualifying"):
        report([make_result(prec, 3, 4, 40)], definitions=(prec,))
    report([make_result(prec, 3, 4, 40), make_result(cov, 20, 40, 40)], definitions=(prec, cov))


def test_the_schema_has_no_overall_or_cross_layer_field() -> None:
    names = (
        set(Report.model_fields)
        | set(MetricResult.model_fields)
        | set(MetricDefinition.model_fields)
    )
    for bad in ("overall", "score", "accuracy", "total_score", "weighted", "aggregate", "grade"):
        assert not any(bad in n for n in names), bad
    with pytest.raises(ValueError):
        Report(inputs={}, populations=(), definitions=(), results=(), overall_score=0.9)  # type: ignore[call-arg]


def test_classes_cannot_be_both_present_and_absent() -> None:
    with pytest.raises(ValueError):
        Report(
            inputs={},
            populations=(),
            definitions=(),
            results=(),
            classes_present=(EvidenceClass.PRODUCTION,),
        )


def test_the_claim_check_rejects_unqualified_and_overreaching_statements() -> None:
    bad = [
        "Regulus accuracy is 91%.",
        "The overall accuracy improved.",
        "The pipeline is production ready.",
        "Recall was 86%.",
        "On the real corpus, extraction precision was high.",
        "Extraction is better than the lineage layer.",
    ]
    for text in bad:
        assert claim_violations(text), text
    good = [
        "On the 38-case extraction regression set, field recall was 31/36 (86%).",
        "Over the 40 gold cases, 0 of 40 false resolutions occurred.",
    ]
    for text in good:
        assert claim_violations(text) == [], text
    assert Formula.MEAN.value == "MEAN"
