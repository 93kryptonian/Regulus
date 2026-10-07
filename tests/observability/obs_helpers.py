import random
from datetime import date, timedelta

from regulus.domain import EventType, RegulatoryEvent
from regulus.evaluation.harness import NOW, Everyone, FakeChannel, FakePipeline
from regulus.notifications import queue_emitter
from regulus.observability.clock import FakeClock
from regulus.observability.cost import CostLedger, Price, PriceTable
from regulus.observability.instrument import Observer, observed_run_event
from regulus.observability.metrics import Registry
from regulus.observability.sinks import ObservationBuffer
from regulus.workflow import SYSTEM, InMemoryWorkflowStore, ScheduleConfig, run_key, run_state

EVENT = RegulatoryEvent(
    id="evt-1",
    type=EventType.NEW,
    regulation_id="R-1",
    occurred_on=date(2026, 8, 1),
    detected_on=date(2026, 8, 2),
    basis="obs",
)
RUN = run_key("evt-1", "1")
CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
TABLE = PriceTable(
    version="test",
    currency="XXX",
    entries={"fake-m": Price(input_micro_per_mtok=1_000_000, output_micro_per_mtok=3_000_000)},
)
__all__ = [
    "CFG",
    "EVENT",
    "NOW",
    "RUN",
    "TABLE",
    "Everyone",
    "FakeChannel",
    "FakePipeline",
    "random",
    "timedelta",
]


def make_observer(capacity: int = 1000, step: int = 5) -> Observer:
    reg = Registry(providers=frozenset({"rules", "fake-priced"}), currencies=frozenset({"XXX"}))
    return Observer(FakeClock(step_ms=step), ObservationBuffer(capacity), reg, CostLedger(TABLE))


def observed_run(obs: Observer | None, pipe: FakePipeline, at=NOW, store=None, cfg=CFG):  # type: ignore[no-untyped-def]
    store = store or InMemoryWorkflowStore()
    emit = queue_emitter(store, Everyone(), SYSTEM, at)
    if obs is None:
        from regulus.workflow import run_event

        return store, run_event(store, pipe, EVENT, SYSTEM, at, emit, "1", cfg)
    return store, observed_run_event(obs, store, pipe, EVENT, SYSTEM, at, emit, "1", cfg)


def logical(store) -> tuple:  # type: ignore[no-untyped-def,type-arg]
    return (
        sorted(store.tasks),
        sorted(
            (t.obligation_id, store.review.get(t.obligation_id)[0].model_dump_json())
            for t in store.tasks.values()
        ),
        sorted(store.streams),
        run_state(store, RUN).model_dump_json(),
    )
