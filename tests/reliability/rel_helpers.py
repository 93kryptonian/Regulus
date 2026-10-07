import random
from datetime import timedelta

from regulus.evaluation.harness import NOW, Everyone, FakeChannel, FakePipeline
from regulus.evaluation.layers.workflow import EVENT
from regulus.notifications import queue_emitter
from regulus.reliability.faults import FaultKind, FaultPlan
from regulus.workflow import (
    SYSTEM,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    ScheduleConfig,
    run_event,
    run_key,
    run_state,
)

CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
RUN = run_key(EVENT.id, "1")
STORES = [InMemoryWorkflowStore, IntentWorkflowStore]
__all__ = ["CFG", "EVENT", "NOW", "RUN", "STORES", "Everyone", "FakeChannel", "FakePipeline", "FaultKind", "FaultPlan",
           "random", "timedelta"]  # fmt: skip


def go(store, pipe, at=NOW, cfg=CFG):  # type: ignore[no-untyped-def]
    return run_event(
        store, pipe, EVENT, SYSTEM, at, queue_emitter(store, Everyone(), SYSTEM, at), "1", cfg
    )


def logical(store) -> tuple:  # type: ignore[no-untyped-def,type-arg]
    obs = sorted(
        (t.obligation_id, store.review.get(t.obligation_id)[0].model_dump_json())
        for t in store.tasks.values()
    )
    notes = sorted(
        s
        for s in store.streams_with("notification:")
        if store.ledger(s)[0].details["event"]["kind"]
        in ("REGULATION_DETECTED", "OBLIGATIONS_READY")
    )
    return sorted(store.tasks), obs, notes, run_state(store, RUN).status.value


def clean_state(store_cls=InMemoryWorkflowStore, n: int = 2):  # type: ignore[no-untyped-def]
    s = store_cls()
    go(s, FakePipeline(n))
    return s, logical(s)


def recover(store, pipe, rounds: int = 12, start: int = 1):  # type: ignore[no-untyped-def]
    from regulus.evaluation.layers.workflow import OPERATOR, requeue
    from regulus.workflow.runs import Status

    t = NOW + timedelta(days=start)
    for _ in range(rounds):
        st = run_state(store, RUN)
        for stage, u in st.stages.items():
            if u.status is Status.DEAD_LETTER:
                requeue(store, RUN, f"stage:{stage.value}", OPERATOR, t)
        for item, u in st.items.items():
            if u.status is Status.DEAD_LETTER:
                requeue(store, RUN, f"item:{item}", OPERATOR, t)
        t += timedelta(hours=2)
        go(
            store,
            pipe,
            t,
            ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=60),
        )
