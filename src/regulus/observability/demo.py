import json
import random
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from regulus.evaluation.harness import ACTORS, NOW, Everyone, FakeChannel, FakePipeline, ReviewRun
from regulus.notifications import queue_emitter
from regulus.review import Action, ActionRequest, ReviewConfig
from regulus.workflow import SYSTEM, InMemoryWorkflowStore, ScheduleConfig, run_key

from .clock import FakeClock
from .cost import CallKind, CostLedger, Price, PriceTable
from .instrument import (
    Observer,
    observe_ai_call,
    observed_apply,
    observed_deliver,
    observed_run_event,
)
from .metrics import Registry
from .scan import scan
from .sinks import JsonlSink, ObservationBuffer

CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
PRICES = PriceTable(
    version="demo",
    currency="XXX",
    entries={"fake-model": Price(input_micro_per_mtok=1_000_000, output_micro_per_mtok=3_000_000)},
)
SCOPE = (
    "Phase 13 validates observability behaviour under controlled local workloads and failure injection. "
    "No production traffic exists; no operational SLO, capacity or uptime claim is made."
)


def _call(tokens: tuple[int, int]) -> Callable[[], tuple[str, tuple[int, int]]]:
    return lambda: ("x", tokens)


def run(out: Path, seed: int = 13) -> dict[str, int]:
    from regulus.evaluation.layers.workflow import EVENT

    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    reg = Registry(providers=frozenset({"rules", "fake-priced"}), currencies=frozenset({"XXX"}))
    obs = Observer(FakeClock(), ObservationBuffer(500), reg, CostLedger(PRICES))
    run_id = run_key(EVENT.id, "1")
    store = InMemoryWorkflowStore()
    pipe = FakePipeline(4, rng, 0.2)
    chan = FakeChannel(rng, 0.3)
    for i in range(8):
        at = NOW + timedelta(seconds=40 * i)
        observed_run_event(
            obs,
            store,
            pipe,
            EVENT,
            SYSTEM,
            at,
            queue_emitter(store, Everyone(), SYSTEM, at),
            "1",
            CFG,
        )
        observed_deliver(obs, run_id, store, chan, SYSTEM, at, CFG)
    review = ReviewRun("obl-demo", random.Random(seed))
    for _ in range(6):
        actor = ACTORS[rng.randrange(len(ACTORS))]
        req = ActionRequest(action=rng.choice(list(Action)), task_id=review.task.id,
                            base_version=review.store.version("obl-demo"), actor=actor, at=review.clock)  # fmt: skip
        observed_apply(obs, run_id, review.store, review.task, req, ReviewConfig(), review.texts)
    for tokens in ((900, 120), (1100, 80), (400, 0)):
        observe_ai_call(obs, run_id, "fake-priced", "fake-model", CallKind.GENERATE, _call(tokens))
    observe_ai_call(
        obs, run_id, "fake-priced", "unlisted-model", CallKind.GENERATE, lambda: ("x", (50, 50))
    )
    obs.buffer.drain(JsonlSink(out / "events.jsonl"), 100_000)
    assert obs.ledger is not None
    (out / "metrics.txt").write_text(reg.text(), encoding="utf-8")
    totals = obs.ledger.totals()
    (out / "cost.json").write_text(
        json.dumps({"price_table_version": PRICES.version, "currency": PRICES.currency, "summary": obs.ledger.summary(),
                    "totals": totals.model_dump(), "records": [r.model_dump(mode="json") for r in obs.ledger.records]},
                   indent=1, sort_keys=True) + "\n", encoding="utf-8")  # fmt: skip
    kinds = {e.stage.value: 0 for e in obs.journal}
    for e in obs.journal:
        kinds[e.stage.value] += 1
    (out / "summary.md").write_text(
        "\n".join([
            "# Observability demonstration", "", SCOPE, "",
            f"Injected: pipeline outages (20%), channel failures (30%), scripted review actions, a fake priced AI provider, one model missing from the price table. Seed {seed}.", "",
            f"- events emitted: {obs.buffer.emitted}, delivered: {obs.buffer.delivered}, dropped: {obs.buffer.dropped_total}, buffered: {obs.buffer.buffered}",
            f"- spans by stage: {json.dumps(kinds, sort_keys=True)}",
            f"- AI accounting: {obs.ledger.summary()}; money total {totals.cost_micro} micro-units in {PRICES.currency}",
            "- events carry ids, counts and closed-enum values only; no source or obligation text.", ""]),
        encoding="utf-8")  # fmt: skip
    artifacts = {p.name: p.read_text(encoding="utf-8") for p in out.iterdir() if p.is_file()}
    findings = scan(artifacts)
    if findings:
        raise SystemExit(f"privacy scan found {len(findings)} problem(s)")
    return {"events": obs.buffer.emitted, "dropped": obs.buffer.dropped_total}


if __name__ == "__main__":
    print(run(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("evaluation/reports/observability")))
