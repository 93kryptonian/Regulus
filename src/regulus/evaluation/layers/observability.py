import json
import random
from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from regulus.notifications import queue_emitter
from regulus.observability.clock import FakeClock
from regulus.observability.cost import (
    CallKind,
    CostLedger,
    Price,
    PriceTable,
    Source,
    UsageRecord,
    cost_micro,
)
from regulus.observability.events import ObsEvent
from regulus.observability.instrument import (
    Observer,
    in_wrapper,
    lifecycle_violations,
    observe_ai_call,
    observed_run_event,
)
from regulus.observability.metrics import Registry
from regulus.observability.scan import scan
from regulus.observability.sinks import InMemorySink, ObservationBuffer
from regulus.observability.taxonomy import Kind, Outcome, Stage
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    ScheduleConfig,
    run_event,
    run_key,
    run_state,
)

from ..builder import EC, HARD0, Builder
from ..harness import NOW, Everyone, FakePipeline
from ..models import EvidenceClass, Formula, Gate
from .workflow import EVENT

L = "observability"
POP = "observability.harness_runs"
SEEDS, SEED0, ROUNDS = 20, 913000, 6
CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
RUN = run_key(EVENT.id, "1")
TABLE = PriceTable(
    version="harness",
    currency="XXX",
    entries={"fake-m": Price(input_micro_per_mtok=1_000_000, output_micro_per_mtok=3_000_000)},
)


def _observer(capacity: int = 1000) -> Observer:
    reg = Registry(providers=frozenset({"rules", "fake-priced"}), currencies=frozenset({"XXX"}))
    return Observer(FakeClock(), ObservationBuffer(capacity), reg, CostLedger(TABLE))


class _Probe(InMemorySink):
    def __init__(self) -> None:
        super().__init__()
        self.in_wrapper_calls: list[bool] = []

    def emit(self, event: ObsEvent) -> None:
        self.in_wrapper_calls.append(in_wrapper())
        super().emit(event)


class _Bad:
    def emit(self, event: object) -> None:
        raise RuntimeError("sink down")


def _crashing(pipe: FakePipeline, name: str, rng: random.Random) -> None:
    real = cast(Callable[..., Any], getattr(pipe, name))

    def wrapped(*args: Any) -> Any:
        if rng.random() < 0.3:
            raise Crash(name)
        return real(*args)

    setattr(pipe, name, wrapped)


def _scenario(seed: int, mode: str, crashes: bool = False) -> tuple[Observer | None, str, int]:
    rng = random.Random(seed)
    pipe = FakePipeline(3, rng, 0.3)
    obs = None if mode == "absent" else _observer(capacity=2 if mode == "failing" else 1000)
    store = InMemoryWorkflowStore()
    reports: list[str] = []
    crashed = 0
    if crashes:
        for name in ("process", "generate", "enrich"):
            _crashing(pipe, name, rng)
    for i in range(ROUNDS):
        at = NOW + timedelta(seconds=40 * i)
        emit = queue_emitter(store, Everyone(), SYSTEM, at)
        try:
            if obs is None:
                rep = run_event(store, pipe, EVENT, SYSTEM, at, emit, "1", CFG)
            else:
                rep = observed_run_event(obs, store, pipe, EVENT, SYSTEM, at, emit, "1", CFG)
            reports.append(rep.model_dump_json())
        except Crash:
            crashed += 1
            reports.append("CRASH")
        if obs is not None and mode == "failing":
            obs.buffer.drain(_Bad(), 5)
    state = run_state(store, RUN).model_dump_json()
    logical = json.dumps([reports, sorted(store.tasks), state], sort_keys=True)
    return obs, logical, crashed


def _usage_checks(seed: int) -> tuple[int, int, int, int]:
    rng = random.Random(seed)
    led = CostLedger(TABLE)
    unpriced = bad_unpriced = 0
    for _ in range(12):
        model = rng.choice(["fake-m", "fake-m", "unknown-m"])
        src = Source.ESTIMATED if rng.random() < 0.2 else Source.REPORTED
        u = UsageRecord(run_id="r", span_id="s", provider="fake-priced", model=model, kind=CallKind.GENERATE,
                        input_tokens=rng.randint(0, 5000), output_tokens=rng.randint(0, 5000), source=src)  # fmt: skip
        led.add(u)
        unpriced += model == "unknown-m"
    t = led.totals()
    recomputed = sum(
        (cost_micro(u, TABLE) or 0) for u in led.records if u.source is Source.REPORTED
    )
    mism = int(t.cost_micro != recomputed)
    bad_unpriced = (
        sum(led.totals(model="unknown-m").cost_micro != 0 for _ in range(1)) if unpriced else 0
    )
    return mism, 1, bad_unpriced, unpriced


def evaluate(b: Builder) -> None:
    tot: Counter[str] = Counter()
    stage_ms: dict[str, list[int]] = {}
    for i in range(SEEDS):
        seed = SEED0 + i
        _, base, _ = _scenario(seed, "absent")
        present, present_logical, _ = _scenario(seed, "present")
        failing, failing_logical, _ = _scenario(seed, "failing")
        tot["noninterf"] += not (base == present_logical == failing_logical)
        crashed_obs, _, ncrash = _scenario(seed, "present", crashes=True)
        assert crashed_obs is not None and present is not None and failing is not None
        tot["abandoned"] += crashed_obs.recover(RUN)
        tot["lifecycle"] += bool(lifecycle_violations(crashed_obs.journal))
        tot["crash_runs"] += 1
        again, _, _ = _scenario(seed, "present")
        assert again is not None
        tot["nondeterm"] += not (
            "\n".join(e.model_dump_json() for e in present.journal)
            == "\n".join(e.model_dump_json() for e in again.journal)
            and present.registry.text() == again.registry.text()
        )
        events = len(present.journal) + len(crashed_obs.journal)
        tot["events"] += events
        tot["invalid"] += present.invalid + crashed_obs.invalid
        observe_ai_call(
            present, RUN, "fake-priced", "fake-m", CallKind.GENERATE, lambda: ("x", (100, 40))
        )
        arts = {
            f"{seed}.events": "\n".join(e.model_dump_json() for e in present.journal),
            f"{seed}.metrics": present.registry.text(),
            f"{seed}.cost": json.dumps(
                [
                    r.model_dump(mode="json")
                    for r in (present.ledger.records if present.ledger else [])
                ]
            ),
        }
        tot["artifacts"] += len(arts)
        tot["sensitive"] += len(
            {f.artifact for f in scan(arts, ["Pengendali wajib menyimpan arsip"])}
        )
        mism, n, bu, nu = _usage_checks(seed)
        tot["cost_mism"] += mism
        tot["cost_checked"] += n
        tot["unpriced_zero"] += bu
        tot["unpriced"] += nu
        nonok = [
            e for e in present.journal + crashed_obs.journal if e.outcome not in (None, Outcome.OK)
        ]
        tot["nonok"] += len(nonok)
        tot["unclassified"] += sum(
            1 for e in nonok if e.error_class is not None and e.error_class.value == "UNCLASSIFIED"
        )
        tot["books_runs"] += 1
        tot["books_bad"] += not failing.buffer.balanced()
        tot["wrapped"] += sum(1 for e in present.journal if e.kind is Kind.SPAN_STARTED)
        probe = _Probe()
        present.buffer.drain(probe, 10_000)
        tot["sink_in_wrapper"] += sum(probe.in_wrapper_calls)
        for e in present.journal:
            if (
                e.kind is Kind.SPAN_FINISHED
                and e.duration_ms is not None
                and e.stage in (Stage.PROCESS, Stage.GENERATE, Stage.ENRICH, Stage.SUBMIT)
            ):
                stage_ms.setdefault(e.stage.value, []).append(e.duration_ms)
    b.population(POP, "seeded faulty runs observed with injected clocks and failing sinks", f"seeds {SEED0}..{SEED0 + SEEDS - 1}, {ROUNDS} rounds each", SEEDS,
                 "evaluation harness", "fake pipeline, channel and sinks; injected clocks; describes the instrumentation, not any real system's speed")  # fmt: skip
    m = b.metric

    def add(
        id: str,
        name: str,
        num: str,
        den: str,
        nv: float,
        dv: float,
        cls: EvidenceClass = EC.PROPERTY,
        gate: Gate | None = None,
        note: str = "",
        formula: Formula = Formula.RATIO,
    ) -> None:
        b.record(m(f"{L}.{id}", L, name, POP, num, den, cls, gate, formula), nv, dv, note)

    add(
        "non_interference_violations",
        "non-interference violation rate",
        "seeded runs whose outputs differ with observability absent, present or failing",
        "seeded runs",
        tot["noninterf"],
        SEEDS,
        gate=HARD0,
        note="three variants per seed, faults and failing sinks",
    )
    add(
        "lifecycle_violations",
        "lifecycle violation rate",
        "runs with an orphan, double-closed or unresolved-parent span after recovery",
        "seeded runs with injected crashes",
        tot["lifecycle"],
        tot["crash_runs"],
        gate=HARD0,
        note=f"{tot['abandoned']} open spans abandoned by injected crashes and recovered",
    )
    add(
        "nondeterminism",
        "nondeterminism rate",
        "runs whose replayed event stream or metric text differs",
        "seeded runs",
        tot["nondeterm"],
        SEEDS,
        gate=HARD0,
    )
    add(
        "vocabulary_violations",
        "vocabulary and cardinality violation rate",
        "events or metric updates rejected as outside the allow-lists",
        "events emitted",
        tot["invalid"],
        tot["events"],
        gate=HARD0,
    )
    add(
        "sensitive_content",
        "sensitive-content hit rate",
        "emitted artifacts containing a forbidden pattern or the source text",
        "artifacts scanned",
        tot["sensitive"],
        tot["artifacts"],
        gate=HARD0,
    )
    add(
        "cost_arithmetic_mismatches",
        "cost arithmetic mismatch rate",
        "ledger money totals differing from exact integer recomputation",
        "totals checked",
        tot["cost_mism"],
        tot["cost_checked"],
        EC.REGRESSION,
        HARD0,
    )
    add(
        "unpriced_summed_as_zero",
        "unpriced calls summed into money",
        "unpriced models contributing to a money total",
        "unpriced calls",
        tot["unpriced_zero"],
        tot["unpriced"],
        EC.REGRESSION,
        HARD0,
    )
    add(
        "unclassified_outcomes",
        "unclassified outcome share",
        "non-OK outcomes with error class UNCLASSIFIED",
        "non-OK outcomes",
        tot["unclassified"],
        tot["nonok"],
        note="counted, not gated",
    )
    add(
        "drop_accounting",
        "drop accounting violation rate",
        "runs where emitted differs from delivered + dropped + buffered",
        "seeded runs with failing sinks",
        tot["books_bad"],
        tot["books_runs"],
        gate=HARD0,
    )
    add(
        "sink_calls_inside_wrappers",
        "sink calls inside a wrapped call",
        "sink invocations made while a wrapped call was executing",
        "wrapped calls",
        tot["sink_in_wrapper"],
        tot["wrapped"],
        gate=HARD0,
    )
    for stage, vals in sorted(stage_ms.items()):
        add(
            f"mean_duration_ms_{stage.lower()}",
            f"mean {stage} span duration (ms, injected clock)",
            "sum of span durations in the injected clock's milliseconds",
            "finished spans",
            sum(vals),
            len(vals),
            note="descriptive only: measures that the measurement works, not how fast the system is",
            formula=Formula.MEAN,
        )
