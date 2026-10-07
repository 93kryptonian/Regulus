import random
from collections import Counter
from datetime import date, timedelta

from regulus.domain import EventType, RegulatoryEvent
from regulus.notifications import (
    State,
    deliver_due,
    notification_state,
    queue_emitter,
)
from regulus.review import Action, ActionRequest, ReviewConfig, apply, claim
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Kind,
    Principal,
    ReviewerInfo,
    ScheduleConfig,
    WorkflowRole,
    WorkflowStore,
    requeue,
    run_event,
    run_key,
    run_state,
    tick,
)
from regulus.workflow.runs import Status as UnitStatus

from ..builder import EC, HARD0, Builder
from ..harness import ACTORS, NOW, OWNER, TEXT, Everyone, FakeChannel, FakePipeline
from ..models import Gate

L = "workflow"
POP = "workflow.harness_runs"
SEEDS, ITEMS, SEED0 = 25, 3, 777000
CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
DRAIN = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=60)
EVENT = RegulatoryEvent(id="evt-1", type=EventType.NEW, regulation_id="R-1", occurred_on=date(2026, 8, 1),
                        detected_on=date(2026, 8, 2), basis="harness")  # fmt: skip


class Dir:
    def reviewers(self, now):  # type: ignore[no-untyped-def]
        return [ReviewerInfo(id="r1"), ReviewerInfo(id="r2")]


def logical(store: WorkflowStore) -> tuple:  # type: ignore[type-arg]
    obs = {
        t.obligation_id: store.review.get(t.obligation_id)[0].model_dump_json()
        for t in store.tasks.values()
    }
    keys = []
    for s in store.streams_with("notification:"):
        first = store.ledger(s)[0].details["event"]["kind"]
        if first in ("REGULATION_DETECTED", "OBLIGATIONS_READY"):
            st = notification_state(store, s[len("notification:") :])
            keys.append((s, st.state.value if st else None))
    return sorted(store.tasks), sorted(obs.items()), sorted(keys)


OPERATOR = Principal(id="operator", roles=(WorkflowRole.OPERATOR,))


def drain(store: WorkflowStore, pipe: FakePipeline, chan: FakeChannel, start: float = 0) -> None:
    t = NOW + timedelta(days=1 + start)
    key = run_key(EVENT.id, "1")
    for _ in range(3):
        st = run_state(store, key)
        for stage, unit in st.stages.items():
            if unit.status is UnitStatus.DEAD_LETTER:
                requeue(store, key, f"stage:{stage.value}", OPERATOR, t)
        for item, unit in st.items.items():
            if unit.status is UnitStatus.DEAD_LETTER:
                requeue(store, key, f"item:{item}", OPERATOR, t)
        t += timedelta(hours=2)
        run_event(
            store, pipe, EVENT, SYSTEM, t, queue_emitter(store, Everyone(), SYSTEM, t), "1", DRAIN
        )
    for _ in range(40):
        t += timedelta(hours=2)
        run_event(
            store, pipe, EVENT, SYSTEM, t, queue_emitter(store, Everyone(), SYSTEM, t), "1", DRAIN
        )
        deliver_due(store, chan, SYSTEM, t, DRAIN)


def _faulty_run(i: int, base: tuple) -> dict[str, int]:  # type: ignore[type-arg]
    rng = random.Random(SEED0 + i)
    store = (InMemoryWorkflowStore if i % 2 == 0 else IntentWorkflowStore)()
    pipe, chan = FakePipeline(ITEMS, rng, 0.25), FakeChannel(rng, 0.0)
    t = NOW
    out = dict.fromkeys(
        (
            "unaccounted",
            "observed",
            "dead",
            "dead_unnotified",
            "dup",
            "streams",
            "divergent",
            "independence",
        ),
        0,
    )
    for _ in range(25):
        t += timedelta(seconds=rng.choice((1, 15, 200)))
        store.fail_after = rng.choice([None, None, None, "intent", "task", "obligation", "record"])
        store.fail_store = 1 if rng.random() < 0.08 else 0
        aborted = False
        try:
            emit = queue_emitter(store, Everyone(), SYSTEM, t)
            rep = run_event(store, pipe, EVENT, SYSTEM, t, emit, "1", CFG)
            aborted = rep.store_unavailable
            deliver_due(store, chan, SYSTEM, t, CFG)
        except Crash:
            aborted = True
        store.fail_after, store.fail_store = None, 0
        if not aborted:
            st = run_state(store, run_key(EVENT.id, "1"))
            for item in st.item_ids:
                out["observed"] += 1
                out["unaccounted"] += item not in st.items
    st = run_state(store, run_key(EVENT.id, "1"))
    dead_i = sum(u.status is UnitStatus.DEAD_LETTER for u in st.items.values())
    dl = [
        s
        for s in store.streams_with("notification:")
        if store.ledger(s)[0].details["event"]["kind"] == "DEAD_LETTER"
    ]
    out["dead"] += dead_i
    out["dead_unnotified"] += dead_i if not dl else 0
    drain(store, FakePipeline(ITEMS), FakeChannel(random.Random(0), 0.0))
    out["divergent"] += logical(store) != base
    for s in store.streams_with("notification:"):
        out["streams"] += 1
        out["dup"] += sum(r.kind is Kind.NOTIFICATION_QUEUED for r in store.ledger(s)) > 1
    out["independence"] += _independence_violation(rng)
    return out


def evaluate(b: Builder) -> None:
    clean = InMemoryWorkflowStore()
    run_event(
        clean,
        FakePipeline(ITEMS),
        EVENT,
        SYSTEM,
        NOW,
        queue_emitter(clean, Everyone(), SYSTEM, NOW),
    )
    deliver_due(clean, FakeChannel(random.Random(0), 0.0), SYSTEM, NOW)
    base = logical(clean)
    tot: Counter[str] = Counter()
    for i in range(SEEDS):
        tot.update(_faulty_run(i, base))
    b.population(POP, "seeded fault, crash and retry runs over a fake pipeline, channel and directory", f"seeds {SEED0}..{SEED0 + SEEDS - 1}", SEEDS,
                 "evaluation harness", "fake infrastructure; describes the orchestration and outbox logic, not a real channel or scheduler")  # fmt: skip
    m = b.metric

    def add(
        id: str,
        name: str,
        num: str,
        den: str,
        num_v: float,
        den_v: float,
        gate: Gate | None = None,
        note: str = "",
    ) -> None:
        b.record(m(f"{L}.{id}", L, name, POP, num, den, EC.PROPERTY, gate), num_v, den_v, note)

    add(
        "unaccounted_items",
        "unaccounted item rate",
        "items with no state after a run returned normally",
        "items observed after runs that neither crashed nor lost the store",
        tot["unaccounted"],
        tot["observed"],
        HARD0,
    )
    add(
        "crash_divergence",
        "crash divergence rate",
        "fault runs whose final logical state differs from the uninterrupted run",
        "seeded fault runs",
        tot["divergent"],
        SEEDS,
        HARD0,
        f"seeds {SEED0}..{SEED0 + SEEDS - 1}, both stores; crashes, store faults and pipeline outages; reliable channel",
    )
    add(
        "duplicate_logical_notifications",
        "duplicate logical notification rate",
        "notification streams queued more than once",
        "notification streams",
        tot["dup"],
        tot["streams"],
        HARD0,
    )
    delivered, dead_n, total_n = _delivery_mix()
    add(
        "notifications_delivered",
        "notifications delivered over a flaky channel",
        "notifications in state DELIVERED after ten delivery rounds",
        "notifications queued",
        delivered,
        total_n,
        None,
        "fake channel failing 30% of sends, at most 3 attempts",
    )
    add(
        "notifications_dead_lettered",
        "notifications dead-lettered over a flaky channel",
        "notifications in state DEAD_LETTER after ten delivery rounds",
        "notifications queued",
        dead_n,
        total_n,
        None,
        "no operator requeue exists for dead-lettered notifications",
    )
    b.known_gaps.append(
        "workflow: a dead-lettered notification has no operator requeue (items and stages do)"
    )
    add(
        "dead_letter_without_notification",
        "dead-lettered items in runs with no dead-letter notification",
        "dead-lettered items in runs that queued no dead-letter notification",
        "dead-lettered items",
        tot["dead_unnotified"],
        tot["dead"],
        None,
        "counted, not gated",
    )
    add(
        "independence_violations",
        "assignment and notification independence violation rate",
        "seeded runs whose review outcome differs with assignment and failing notifications",
        "seeded runs",
        tot["independence"],
        SEEDS,
        HARD0,
    )


def _delivery_mix() -> tuple[int, int, int]:
    delivered = dead = total = 0
    for i in range(SEEDS):
        rng = random.Random(SEED0 + 5000 + i)
        store = InMemoryWorkflowStore()
        chan = FakeChannel(rng, 0.3)
        run_event(
            store,
            FakePipeline(ITEMS),
            EVENT,
            SYSTEM,
            NOW,
            queue_emitter(store, Everyone(), SYSTEM, NOW),
        )
        t = NOW
        for _ in range(10):
            t += timedelta(minutes=5)
            deliver_due(store, chan, SYSTEM, t, CFG)
        for s in store.streams_with("notification:"):
            n = notification_state(store, s[len("notification:") :])
            total += 1
            delivered += bool(n and n.state is State.DELIVERED)
            dead += bool(n and n.state is State.DEAD_LETTER)
    return delivered, dead, total


def _independence_violation(rng: random.Random) -> int:
    def run(noisy: bool) -> str:
        store = InMemoryWorkflowStore()
        pipe = FakePipeline(1)
        run_event(store, pipe, EVENT, SYSTEM, NOW, queue_emitter(store, Everyone(), SYSTEM, NOW))
        (task,) = store.tasks.values()
        r = random.Random(rng.random())
        t = NOW
        for _ in range(12):
            t += timedelta(seconds=30)
            if noisy:
                tick(store, t, Dir(), SYSTEM)
                deliver_due(store, FakeChannel(r, 1.0), SYSTEM, t, CFG)
            actor = ACTORS[r.randrange(len(ACTORS))]
            action = list(Action)[r.randrange(4)]
            task = claim(
                task.model_copy(
                    update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
                ),
                actor.id,
                t,
                900,
            )
            req = ActionRequest(
                action=action,
                task_id=task.id,
                base_version=store.review.version(task.obligation_id),
                actor=actor,
                at=t,
            )
            out = apply(store.review, task, req, ReviewConfig(), {OWNER: TEXT})
            if out.task is not None:
                task = out.task
        return store.review.get(task.obligation_id)[0].model_dump_json()

    state = rng.getstate()
    a = run(True)
    rng.setstate(state)
    b2 = run(False)
    return int(a != b2)
