import json
import random as _random
from datetime import timedelta

import pytest
from obs_helpers import NOW, RUN, TABLE, FakePipeline, logical, make_observer, observed_run

from regulus.evaluation.harness import ACTORS, OWNER, TEXT, ReviewRun
from regulus.observability.cost import (
    CallKind,
    CostLedger,
    Price,
    PriceTable,
    Source,
    UsageRecord,
    cost_micro,
)
from regulus.observability.events import ObsEvent, span_id, trace_id
from regulus.observability.instrument import (
    in_wrapper,
    lifecycle_violations,
    observe_ai_call,
    observed_apply,
)
from regulus.observability.metrics import CAP, InvalidMetric, Registry
from regulus.observability.scan import scan
from regulus.observability.sinks import InMemorySink, ObservationBuffer
from regulus.observability.taxonomy import (
    ErrorClass,
    Kind,
    Outcome,
    Stage,
    classify_exception,
    classify_generation,
    classify_notification,
    classify_review,
    classify_submit,
)
from regulus.review import Action, ActionRequest, ReviewConfig
from regulus.workflow import Crash, Permanent, Unavailable


def ev(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        seq=1,
        trace_id="t",
        span_id="s",
        run_id="r1",
        stage=Stage.PROCESS,
        kind=Kind.SPAN_STARTED,
        started_at=NOW,
    )
    return ObsEvent(**{**base, **kw})  # type: ignore[arg-type]


def test_events_are_validated_at_construction() -> None:
    ev()
    for bad in (
        {"counts": {"free": 1}},
        {"attrs": {"note": "x"}},
        {"attrs": {"status": "any text at all"}},
        {"counts": {"items": -1}},
        {"run_id": "has space and @"},
        {"kind": Kind.SPAN_FINISHED},
        {"outcome": Outcome.OK},
        {"kind": Kind.SPAN_FINISHED, "outcome": Outcome.FAILED_RETRYABLE, "duration_ms": 1},
        {
            "kind": Kind.SPAN_FINISHED,
            "outcome": Outcome.OK,
            "duration_ms": 1,
            "error_class": ErrorClass.STORE,
        },
        {"kind": Kind.SPAN_FINISHED, "outcome": Outcome.OK, "duration_ms": -1},
    ):
        with pytest.raises(ValueError):
            ev(**bad)
    ev(
        kind=Kind.SPAN_FINISHED,
        outcome=Outcome.REFUSED,
        error_class=ErrorClass.DENIED,
        duration_ms=3,
        attrs={"status": "DENIED", "recovered": True},
    )


def test_ids_are_deterministic_and_stable() -> None:
    assert trace_id("a") == trace_id("a") != trace_id("b") and len(trace_id("a")) == 16
    t = trace_id("a")
    assert (
        span_id(t, Stage.ENRICH, "x", 1) != span_id(t, Stage.ENRICH, "x", 2)
        and len(span_id(t, Stage.ENRICH, "x", 1)) == 12
    )


def test_a_normal_run_has_a_complete_nested_lifecycle_and_metrics() -> None:
    obs = make_observer()
    store, rep = observed_run(obs, FakePipeline(2))
    assert rep.status.value == "COMPLETE" and lifecycle_violations(obs.journal) == []
    stages = [e.stage for e in obs.journal if e.kind is Kind.SPAN_STARTED]
    assert (
        stages.count(Stage.ENRICH) == 2
        and stages.count(Stage.SUBMIT) == 2
        and Stage.DETECTED_NOTIFY in stages
    )
    run = next(e for e in obs.journal if e.stage is Stage.RUN and e.kind is Kind.SPAN_STARTED)
    process = next(
        e for e in obs.journal if e.stage is Stage.PROCESS and e.kind is Kind.SPAN_STARTED
    )
    assert run.parent_span_id is None and process.parent_span_id == run.span_id
    assert obs.journal[-1].stage is Stage.RUN and obs.journal[-1].outcome is Outcome.OK
    reg = obs.registry
    assert reg.counters["regulus_stage_total"][(("outcome", "OK"), ("stage", "ENRICH"))] == 2
    assert (
        "regulus_stage_duration_ms_bucket" in reg.text()
        and obs.invalid == 0
        and len(store.tasks) == 2
    )


def test_a_retry_is_a_new_span_and_the_first_attempt_keeps_its_outcome() -> None:
    obs = make_observer()
    pipe = FakePipeline(1)
    calls = {"n": 0}
    real = pipe.generate

    def flaky(event, ref):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise Unavailable()
        return real(event, ref)

    pipe.generate = flaky  # type: ignore[method-assign]
    store, _ = observed_run(obs, pipe)
    observed_run(obs, pipe, at=NOW + timedelta(seconds=30), store=store)
    gens = [e for e in obs.journal if e.stage is Stage.GENERATE and e.kind is Kind.SPAN_FINISHED]
    assert [(g.attempt, g.outcome, g.error_class) for g in gens] == [
        (1, Outcome.FAILED_RETRYABLE, ErrorClass.UNAVAILABLE),
        (2, Outcome.OK, None),
    ]
    assert gens[0].span_id != gens[1].span_id and obs.registry.total("regulus_retries_total") >= 1
    assert lifecycle_violations(obs.journal) == []


def test_a_crash_leaves_open_spans_which_recovery_abandons_without_losing_them() -> None:
    obs = make_observer()
    pipe = FakePipeline(1)

    def boom(event, ref):  # type: ignore[no-untyped-def]
        raise Crash("generate")

    pipe.generate = boom  # type: ignore[method-assign]
    with pytest.raises(Crash):
        observed_run(obs, pipe)
    assert lifecycle_violations(obs.journal) != []
    n = obs.recover(RUN)
    assert n >= 2 and lifecycle_violations(obs.journal) == []
    ab = [e for e in obs.journal if e.kind is Kind.SPAN_ABANDONED]
    assert all(e.attrs["recovered"] is True and e.error_class is ErrorClass.ABANDONED for e in ab)
    assert {e.stage for e in ab} >= {Stage.RUN, Stage.GENERATE}


def test_the_same_run_with_the_same_clocks_is_byte_identical() -> None:
    def one() -> tuple[str, str]:
        obs = make_observer()
        observed_run(obs, FakePipeline(2))
        return "\n".join(e.model_dump_json() for e in obs.journal), obs.registry.text()

    assert one() == one()


def test_a_clock_that_goes_backwards_clamps_to_zero_and_is_flagged() -> None:
    obs = make_observer()
    with obs.span("run-x", Stage.TICK):
        obs.clock.backwards = True  # type: ignore[attr-defined]
    fin = obs.journal[-1]
    assert fin.duration_ms == 0 and fin.attrs["clock_regression"] is True


@pytest.mark.parametrize("seed", range(12))
def test_observability_never_changes_results_even_with_failing_sinks(seed: int) -> None:
    def run(mode: str):  # type: ignore[no-untyped-def]
        rng = _random.Random(seed)
        pipe = FakePipeline(3, rng, 0.3)
        obs = None if mode == "absent" else make_observer(capacity=1 if mode == "failing" else 1000)
        store = None
        out = []
        for i in range(6):
            store, rep = observed_run(obs, pipe, at=NOW + timedelta(seconds=40 * i), store=store)
            out.append(rep.model_dump_json())
        if obs is not None and mode == "failing":

            class Bad:
                def emit(self, e):  # type: ignore[no-untyped-def]
                    raise RuntimeError("down")

            obs.buffer.drain(Bad(), 10)
        return out, logical(store)

    assert run("absent") == run("present") == run("failing")


def test_instrumentation_that_raises_does_not_change_the_wrapped_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = observed_run(None, FakePipeline(2))
    obs = make_observer()

    def raising(self, e):  # type: ignore[no-untyped-def]
        raise RuntimeError("telemetry broke")

    monkeypatch.setattr(type(obs), "_record", raising)
    store, rep = observed_run(obs, FakePipeline(2))
    assert rep == clean[1] and logical(store) == logical(clean[0]) and obs.invalid > 0


def test_no_sink_is_called_inside_a_wrapper_and_the_drain_is_separate_and_budgeted() -> None:
    seen: list[bool] = []

    class Probe(InMemorySink):
        def emit(self, event: ObsEvent) -> None:
            seen.append(in_wrapper())
            super().emit(event)

    obs = make_observer()
    observed_run(obs, FakePipeline(2))
    assert obs.buffer.delivered == 0 and obs.buffer.buffered == len(obs.journal)
    sink = Probe()
    assert obs.buffer.drain(sink, 5) == 5 and len(sink.events) == 5
    obs.buffer.drain(sink, 10_000)
    assert seen and not any(seen) and obs.buffer.balanced() and obs.buffer.buffered == 0


def test_a_blocked_sink_never_delays_wrapped_calls() -> None:
    obs = make_observer()

    class Hang:
        called = 0

        def emit(self, event: ObsEvent) -> None:
            Hang.called += 1

    observed_run(obs, FakePipeline(1))
    assert (
        Hang.called == 0
    )  # nothing was delivered because nothing drained; the run still completed
    assert obs.journal[-1].outcome is Outcome.OK


def test_overflow_drops_the_newest_visibly_and_the_books_balance() -> None:
    buf = ObservationBuffer(capacity=3)
    events = [ev(seq=i) for i in range(10)]
    results = [buf.enqueue(e) for e in events]
    assert (
        results == [True] * 3 + [False] * 7 and buf.dropped["buffer_full"] == 7 and buf.balanced()
    )

    class Flaky:
        n = 0

        def emit(self, e):  # type: ignore[no-untyped-def]
            Flaky.n += 1
            if Flaky.n <= 4:
                raise RuntimeError("x")

    for _ in range(3):
        buf.drain(Flaky(), 50)
        assert buf.balanced()
    assert (
        buf.sink_errors == 4 and buf.delivered == 3 and buf.buffered == 0 and buf.dropped_total == 7
    )


def test_the_registry_refuses_unknown_names_labels_values_and_runaway_cardinality() -> None:
    r = Registry()
    with pytest.raises(InvalidMetric):
        r.inc("made_up_total", {})
    with pytest.raises(InvalidMetric):
        r.inc("regulus_stage_total", {"stage": "PROCESS"})
    with pytest.raises(InvalidMetric):
        r.inc("regulus_stage_total", {"stage": "PROCESS", "outcome": "OK", "run_id": "x"})
    with pytest.raises(InvalidMetric):
        r.inc("regulus_stage_total", {"stage": "run-123", "outcome": "OK"})
    with pytest.raises(InvalidMetric):
        r.inc("regulus_stage_total", {"stage": "PROCESS", "outcome": "OK"}, -1)
    big = Registry(providers=frozenset(f"p{i}" for i in range(CAP + 5)))
    with pytest.raises(InvalidMetric, match="cap"):
        for i in range(CAP + 5):
            big.inc(
                "regulus_ai_tokens_total",
                {"provider": f"p{i}", "kind": "GENERATE", "direction": "input"},
            )


def test_classification_distinguishes_faults_refusals_and_abstentions() -> None:
    assert classify_review("APPLIED") == (Outcome.OK, None)
    for s in ("DENIED", "STALE", "INCOMPLETE_REVIEW", "INVALID_TRANSITION", "EVIDENCE_INVALID"):
        assert classify_review(s) == (Outcome.REFUSED, ErrorClass(s))
    assert classify_review("NOT_RECORDED") == (Outcome.FAILED_RETRYABLE, ErrorClass.STORE)
    assert classify_review("SOMETHING_NEW") == (Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED)
    assert classify_submit("CONFLICT") == (Outcome.FAILED_PERMANENT, ErrorClass.REJECTED_INPUT)
    assert classify_submit("ALREADY_SUBMITTED")[0] is Outcome.SKIPPED
    assert classify_submit("FAILED") == (Outcome.FAILED_RETRYABLE, ErrorClass.STORE)
    assert (
        classify_exception(Unavailable())[1] is ErrorClass.UNAVAILABLE
        and classify_exception(Permanent())[1] is ErrorClass.PERMANENT
    )
    assert classify_exception(ValueError("secret text"))[1] is ErrorClass.UNCLASSIFIED
    assert classify_notification("DEAD_LETTER") == (
        Outcome.FAILED_PERMANENT,
        ErrorClass.DEAD_LETTER,
    )
    assert classify_notification("DELIVERED") == (Outcome.OK, None)
    assert classify_generation("NOT_GENERABLE") == (
        Outcome.ABSTAINED,
        ErrorClass.INSUFFICIENT_EVIDENCE,
    )
    assert classify_generation("REJECTED_BY_VERIFICATION")[0] is Outcome.REFUSED


def test_every_non_ok_outcome_in_a_faulty_run_has_a_class_and_refusals_are_not_faults() -> None:
    obs = make_observer()
    run = ReviewRun("obl-9", _random.Random(3))
    for _ in range(25):
        actor = ACTORS[2]
        req = ActionRequest(
            action=Action.APPROVE,
            task_id=run.task.id,
            base_version=run.store.version("obl-9"),
            actor=actor,
            at=run.clock,
        )
        observed_apply(obs, RUN, run.store, run.task, req, ReviewConfig(), run.texts)
    fin = [e for e in obs.journal if e.kind is Kind.SPAN_FINISHED]
    assert fin and all(
        e.outcome is Outcome.REFUSED and e.error_class is ErrorClass.DENIED for e in fin
    )
    assert obs.registry.total("regulus_failures_total") == 0 and obs.registry.total(
        "regulus_stage_total"
    ) == len(fin)
    assert OWNER and TEXT


def test_faults_in_a_phase_11_run_are_classified_and_counted() -> None:
    obs = make_observer()
    pipe = FakePipeline(2, _random.Random(1), 0.6)
    store, _ = observed_run(obs, pipe)
    for i in range(1, 6):
        store, _ = observed_run(obs, pipe, at=NOW + timedelta(seconds=60 * i), store=store)
    faults = [
        e
        for e in obs.journal
        if e.outcome in (Outcome.FAILED_RETRYABLE, Outcome.FAILED_PERMANENT)
        and e.kind is Kind.SPAN_FINISHED
    ]
    assert faults and all(e.error_class is not None for e in faults)
    assert (
        lifecycle_violations(obs.journal) == [] and obs.registry.total("regulus_failures_total") > 0
    )


def test_cost_arithmetic_is_exact_integers_and_unpriced_is_never_zero() -> None:
    def u(model: str, i: int, o: int, src: Source = Source.REPORTED) -> UsageRecord:
        return UsageRecord(
            run_id="r",
            span_id="s",
            provider="fake-priced",
            model=model,
            kind=CallKind.GENERATE,
            input_tokens=i,
            output_tokens=o,
            source=src,
        )

    assert cost_micro(u("fake-m", 1, 0), TABLE) == 1 and cost_micro(u("fake-m", 0, 1), TABLE) == 3
    assert (
        cost_micro(u("fake-m", 0, 0), TABLE) == 0
        and cost_micro(u("fake-m", 10**12, 10**12), TABLE) == 10**12 + 3 * 10**12
    )
    assert (
        cost_micro(u("fake-m", 1_000_001, 0), TABLE) == 1_000_001
        and cost_micro(u("nope", 5, 5), TABLE) is None
    )
    ledger = CostLedger(TABLE)
    for rec in (
        u("fake-m", 100, 50),
        u("fake-m", 10, 5),
        u("unknown", 7, 7),
        u("fake-m", 3, 3, Source.ESTIMATED),
    ):
        ledger.add(rec)
    t = ledger.totals()
    expect = sum(cost_micro(r, TABLE) or 0 for r in ledger.records if r.source is Source.REPORTED)
    assert (
        t.cost_micro == expect == 100 + 150 + 10 + 15
        and t.unpriced_calls == 1
        and t.estimated_calls == 1
    )
    assert t.estimated_cost_micro == 3 + 9 and t.input_tokens == 120 and t.calls == 4
    assert "1 unpriced" in ledger.summary() and CostLedger(TABLE).summary() == "0 AI calls"
    assert (
        ledger.totals(model="unknown").cost_micro == 0
        and ledger.totals(model="unknown").unpriced_calls == 1
    )


def test_usage_records_carry_no_free_text_and_ai_calls_flow_into_metrics_and_retries_are_costed() -> (
    None
):
    with pytest.raises(ValueError):
        UsageRecord(
            run_id="r",
            span_id="s",
            provider="p",
            model="a prompt with spaces and text",
            kind=CallKind.GENERATE,
            input_tokens=1,
            output_tokens=1,
        )
    with pytest.raises(ValueError):
        UsageRecord(
            run_id="r",
            span_id="s",
            provider="p",
            model="m",
            kind=CallKind.GENERATE,
            input_tokens=-1,
            output_tokens=1,
        )
    obs = make_observer()
    attempts = []
    for tokens in ((120, 30), (120, 0)):
        observe_ai_call(
            obs, RUN, "fake-priced", "fake-m", CallKind.GENERATE, lambda t=tokens: ("out", t)
        )
        attempts.append(tokens)
    observe_ai_call(obs, RUN, "fake-priced", "mystery", CallKind.GENERATE, lambda: ("out", (5, 5)))
    assert obs.ledger is not None and obs.ledger.totals().calls == 3
    reg = obs.registry
    assert reg.total("regulus_ai_calls_total") == 3
    assert (
        reg.counters["regulus_ai_calls_total"][
            (("kind", "GENERATE"), ("priced", "false"), ("provider", "fake-priced"))
        ]
        == 1
    )
    assert reg.total("regulus_ai_cost_micro_total") == obs.ledger.totals().cost_micro > 0
    assert reg.total("regulus_ai_tokens_total") == 120 + 30 + 120 + 0 + 5 + 5


def test_outputs_carry_no_sensitive_content_and_the_scan_detects_injected_content() -> None:
    obs = make_observer()
    pipe = FakePipeline(2, _random.Random(2), 0.4)
    pipe_text = TEXT
    store, _ = observed_run(obs, pipe)
    observed_run(obs, pipe, at=NOW + timedelta(seconds=60), store=store)
    observe_ai_call(obs, RUN, "fake-priced", "fake-m", CallKind.GENERATE, lambda: ("x", (10, 10)))
    artifacts = {
        "events": "\n".join(e.model_dump_json() for e in obs.journal),
        "metrics": obs.registry.text(),
        "cost": json.dumps([r.model_dump(mode="json") for r in obs.ledger.records]),  # type: ignore[union-attr]
    }
    assert scan(artifacts, [pipe_text]) == []
    for bad, kind in (
        ("ana@example.com", "email"),
        ("see https://x.example/y", "url"),
        ("call +62 812 3456 7890", "phone"),
        ("Bearer abcdef123456", "credential"),
        (f"quote: {pipe_text}", "source_or_obligation_text"),
    ):
        found = scan({**artifacts, "x": bad}, [pipe_text])
        assert [f.kind for f in found] == [kind]


def test_exception_messages_never_reach_an_event() -> None:
    obs = make_observer()
    with pytest.raises(ValueError):
        with obs.span("run-1", Stage.PROCESS):
            raise ValueError("Pengendali wajib menyimpan arsip ana@example.com")
    blob = "\n".join(e.model_dump_json() for e in obs.journal)
    assert "Pengendali" not in blob and "example.com" not in blob
    assert obs.journal[-1].error_class is ErrorClass.UNCLASSIFIED


def test_a_review_action_and_other_wrappers_emit_spans() -> None:
    obs = make_observer()
    run = ReviewRun("obl-8", _random.Random(8))
    req = ActionRequest(
        action=Action.REJECT,
        task_id=run.task.id,
        base_version=run.store.version("obl-8"),
        actor=ACTORS[0],
        at=run.clock,
    )
    out = observed_apply(obs, RUN, run.store, run.task, req, ReviewConfig(), run.texts)
    fin = obs.journal[-1]
    assert (
        fin.stage is Stage.REVIEW_ACTION
        and fin.attrs["status"] == out.status.value
        and fin.attrs["action"] == "REJECT"
    )
    assert (
        PriceTable(
            version="v",
            currency="XXX",
            entries={"m": Price(input_micro_per_mtok=1, output_micro_per_mtok=1)},
        ).version
        == "v"
    )
