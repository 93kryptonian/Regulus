import random
from datetime import date, timedelta

import pytest
from rv_engine_helpers import OWNER, TEXT
from wf_helpers import LATER, generated, inputs

from regulus.domain import EventType, RegulatoryEvent
from regulus.domain.enums import ReviewReason
from regulus.notifications import queue_emitter
from regulus.notifications.outbox import notification_state
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Permanent,
    Principal,
    RunStatus,
    ScheduleConfig,
    Stage,
    Unavailable,
    WorkflowRole,
    requeue,
    run_event,
    run_key,
    run_state,
    unaccounted,
)

CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)
OP = Principal(id="op", roles=(WorkflowRole.OPERATOR,))


def event(eid: str = "evt-1", typ: EventType = EventType.NEW) -> RegulatoryEvent:
    kw = (
        {"target_id": "R-0"}
        if typ in (EventType.AMEND, EventType.REPEAL, EventType.PARTIAL_REPEAL)
        else {}
    )
    if typ is EventType.NEEDS_REVIEW:
        kw = {"reason": ReviewReason.METADATA_CONFLICT}
    return RegulatoryEvent(
        id=eid,
        type=typ,
        regulation_id="R-1",
        occurred_on=date(2026, 8, 1),
        detected_on=date(2026, 8, 2),
        basis="test",
        **kw,
    )


class Who:
    def resolve(self, e):  # type: ignore[no-untyped-def]
        return ["amy"]


class Fake:
    def __init__(self, n: int = 2) -> None:
        self.items = {f"obl-{i}": generated(f"obl-{i}") for i in range(n)}
        self.script: dict[str, list[object]] = {}
        self.calls: dict[str, int] = {}

    def _hit(self, name: str, key: str = "") -> None:
        k = f"{name}:{key}" if key else name
        self.calls[k] = self.calls.get(k, 0) + 1
        s = self.script.get(k, [])
        if s:
            act = s.pop(0)
            if act == "unavail":
                raise Unavailable()
            if act == "perm":
                raise Permanent()
            if act == "crash":
                raise Crash(k)

    def process(self, event):  # type: ignore[no-untyped-def]
        self._hit("process")
        return "ref-1"

    def generate(self, event, ref):  # type: ignore[no-untyped-def]
        self._hit("generate")
        return list(self.items)

    def result(self, item_id):  # type: ignore[no-untyped-def]
        return self.items[item_id]

    def enrich(self, item_id):  # type: ignore[no-untyped-def]
        self._hit("enrich", item_id)
        return inputs()

    def owner_texts(self, ref):  # type: ignore[no-untyped-def]
        return {OWNER: TEXT}


def go(store, pipe, ev=None, at=LATER, emit=None, principal=SYSTEM, cfg=CFG, version="1"):  # type: ignore[no-untyped-def]
    emit = emit or queue_emitter(store, Who(), SYSTEM, at)
    return run_event(store, pipe, ev or event(), principal, at, emit, version, cfg)


def notif_kinds(store) -> list[str]:  # type: ignore[no-untyped-def]
    out = []
    for s in store.streams_with("notification:"):
        st = notification_state(store, s[len("notification:") :])
        out.append(store.ledger(s)[0].details["event"]["kind"])
        assert st is not None
    return sorted(out)


def test_a_full_run_notifies_processes_generates_and_submits_every_item() -> None:
    s, p = InMemoryWorkflowStore(), Fake(2)
    rep = go(s, p)
    assert rep.status is RunStatus.COMPLETE and rep.submitted == 2 and len(s.tasks) == 2
    assert notif_kinds(s) == ["OBLIGATIONS_READY", "REGULATION_DETECTED"]
    st = run_state(s, run_key("evt-1", "1"))
    assert (
        st.stage(Stage.DETECTED).status.value == "DONE"
        and st.ready_emitted
        and s.verify()
        and s.violations() == []
    )
    ready = [
        s.ledger(x)[0]
        for x in s.streams_with("notification:")
        if "READY" in s.ledger(x)[0].details["event"]["kind"]
    ]
    assert (
        ready[0].details["message"]["cls"] == "AI_ENRICHED"
        and "unreviewed" in ready[0].details["message"]["body"]
    )


def test_an_amendment_event_names_its_target_in_a_deterministic_message() -> None:
    s, p = InMemoryWorkflowStore(), Fake(1)
    go(s, p, event(typ=EventType.AMEND))
    assert "AMENDMENT_DETECTED" in notif_kinds(s)


def test_a_duplicate_event_changes_nothing() -> None:
    s, p = InMemoryWorkflowStore(), Fake(2)
    go(s, p)
    before = ({k: s.ledger(k) for k in s.streams}, dict(s.tasks), dict(p.calls))
    again = go(s, p, at=LATER + timedelta(hours=1))
    assert again.status is RunStatus.COMPLETE and again.submitted == 0
    assert ({k: s.ledger(k) for k in s.streams}, dict(s.tasks), dict(p.calls)) == before


def test_ai_pipeline_unavailable_still_sends_detection_then_retries_then_dead_letters_visibly() -> (
    None
):
    s, p = InMemoryWorkflowStore(), Fake(2)
    p.script["generate"] = ["unavail"] * 5
    t = LATER
    r1 = go(s, p, at=t)
    assert (
        r1.status is RunStatus.WAITING and s.tasks == {} and "REGULATION_DETECTED" in notif_kinds(s)
    )
    assert (
        go(s, p, at=t + timedelta(seconds=5)).status is RunStatus.WAITING
        and p.calls["generate"] == 1
    )
    r2 = go(s, p, at=t + timedelta(seconds=10))
    assert r2.status is RunStatus.WAITING and p.calls["generate"] == 2
    r3 = go(s, p, at=t + timedelta(seconds=40))
    assert r3.status is RunStatus.DEAD and p.calls["generate"] == 3 and s.tasks == {}
    assert "DEAD_LETTER" in notif_kinds(s) and "PIPELINE_STAGE_FAILED" in notif_kinds(s)
    assert go(s, p, at=t + timedelta(days=1)).status is RunStatus.DEAD and p.calls["generate"] == 3
    key = run_key("evt-1", "1")
    assert not requeue(s, key, "stage:GENERATE", SYSTEM, t + timedelta(days=1))
    assert requeue(s, key, "stage:GENERATE", OP, t + timedelta(days=1, seconds=1))
    p.script["generate"] = []
    done = go(s, p, at=t + timedelta(days=1, seconds=2))
    assert done.status is RunStatus.COMPLETE and len(s.tasks) == 2 and unaccounted(s) == []


def test_a_permanent_deterministic_failure_is_dead_lettered_without_retry() -> None:
    s, p = InMemoryWorkflowStore(), Fake(1)
    p.script["process"] = ["perm"]
    assert go(s, p).status is RunStatus.DEAD and p.calls == {"process": 1} and s.tasks == {}
    assert "DEAD_LETTER" in notif_kinds(s)


def test_partial_completion_resumes_without_redoing_done_items() -> None:
    s, p = InMemoryWorkflowStore(), Fake(3)
    p.script["enrich:obl-1"] = ["unavail"]
    first = go(s, p)
    assert first.status is RunStatus.WAITING and first.submitted == 2 and len(s.tasks) == 2
    mid = dict(p.calls)
    done = go(s, p, at=LATER + timedelta(seconds=30))
    assert done.status is RunStatus.COMPLETE and len(s.tasks) == 3 and done.submitted == 1
    assert p.calls["enrich:obl-0"] == mid["enrich:obl-0"] == 1 and p.calls["enrich:obl-1"] == 2
    assert p.calls["process"] == 1 and p.calls["generate"] == 1


def test_an_unverifiable_item_is_dead_lettered_while_the_rest_proceed() -> None:
    s, p = InMemoryWorkflowStore(), Fake(2)
    p.items["obl-1"] = p.items["obl-1"].model_copy(update={"evidence": ()})
    rep = go(s, p)
    assert rep.status is RunStatus.PARTIAL_DEAD and len(s.tasks) == 1 and rep.submitted == 1
    st = run_state(s, run_key("evt-1", "1"))
    assert (
        st.items["obl-1"].status.value == "DEAD_LETTER"
        and st.items["obl-1"].error_class == "EVIDENCE_INVALID"
    )
    assert "DEAD_LETTER" in notif_kinds(s) and "OBLIGATIONS_READY" in notif_kinds(s)


def test_a_new_pipeline_config_version_is_a_new_run_and_duplicates_nothing() -> None:
    s, p = InMemoryWorkflowStore(), Fake(2)
    go(s, p)
    old = run_state(s, run_key("evt-1", "1"))
    rep = go(s, p, at=LATER + timedelta(hours=1), version="2")
    assert rep.status is RunStatus.COMPLETE and rep.submitted == 0 and len(s.tasks) == 2
    assert run_state(s, run_key("evt-1", "1")) == old and run_key("evt-1", "2") != run_key(
        "evt-1", "1"
    )


def test_a_non_processable_event_is_rejected_and_recorded_without_calls() -> None:
    s, p = InMemoryWorkflowStore(), Fake(1)
    ev = event(typ=EventType.NEEDS_REVIEW)
    rep = go(s, p, ev)
    assert rep.status is RunStatus.REJECTED and p.calls == {} and s.tasks == {}
    assert go(s, p, ev, at=LATER + timedelta(seconds=1)).status is RunStatus.REJECTED


def test_only_system_or_operator_may_run() -> None:
    s, p = InMemoryWorkflowStore(), Fake(1)
    rep = go(s, p, principal=Principal(id="c", roles=(WorkflowRole.COORDINATOR,)))
    assert rep.status is RunStatus.UNSTARTED and p.calls == {} and s.streams == {}


def test_a_failing_notification_path_never_blocks_the_pipeline_and_catches_up() -> None:
    s, p = InMemoryWorkflowStore(), Fake(1)
    rep = go(s, p, emit=lambda *a: False)
    assert rep.status is RunStatus.WAITING or rep.status is RunStatus.COMPLETE
    assert len(s.tasks) == 1
    st = run_state(s, run_key("evt-1", "1"))
    assert st.stage(Stage.DETECTED).status.value == "PENDING" and not st.ready_emitted
    go(s, p, at=LATER + timedelta(seconds=1))
    st = run_state(s, run_key("evt-1", "1"))
    assert (
        st.stage(Stage.DETECTED).status.value == "DONE" and st.ready_emitted and len(s.tasks) == 1
    )
    assert sorted(notif_kinds(s)) == ["OBLIGATIONS_READY", "REGULATION_DETECTED"]


def test_a_store_failure_stops_the_operation_whole_and_the_next_run_resumes() -> None:
    s, p = InMemoryWorkflowStore(), Fake(2)
    s.fail_store = 1
    rep = go(s, p)
    assert rep.store_unavailable and s.tasks == {}
    ok = go(s, p, at=LATER + timedelta(seconds=1))
    assert ok.status is RunStatus.COMPLETE and len(s.tasks) == 2 and s.violations() == []


@pytest.mark.parametrize("store_cls", [InMemoryWorkflowStore, IntentWorkflowStore])
@pytest.mark.parametrize("seed", range(25))
def test_random_faults_and_crashes_converge_to_the_uninterrupted_logical_state(
    store_cls, seed
) -> None:  # type: ignore[no-untyped-def]
    rng = random.Random(seed)
    clean_s, clean_p = store_cls(), Fake(3)
    go(clean_s, clean_p)
    s, p = store_cls(), Fake(3)
    t = LATER
    for _ in range(40):
        for name in ("process", "generate", "enrich:obl-0", "enrich:obl-1", "enrich:obl-2"):
            p.script[name] = [rng.choice([None, None, "unavail", "crash"]) for _ in range(2)]
        s.fail_after = rng.choice([None, None, None, "intent", "task", "obligation", "record"])
        s.fail_store = 1 if rng.random() < 0.1 else 0
        try:
            go(s, p, at=t)
        except Crash:
            pass
        s.fail_after, s.fail_store = None, 0
        t += timedelta(seconds=rng.choice((1, 15, 200)))
        assert s.verify() and s.violations() == []
    p.script.clear()
    for _ in range(12):
        t += timedelta(hours=1)
        go(
            s,
            p,
            at=t,
            cfg=ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=50),
        )
    st = run_state(s, run_key("evt-1", "1"))
    if st.status is RunStatus.DEAD:
        assert requeue(
            s,
            run_key("evt-1", "1"),
            f"stage:{[k for k, v in st.stages.items() if v.status.value == 'DEAD_LETTER'][0].value}",
            OP,
            t,
        )
        for _ in range(3):
            t += timedelta(hours=1)
            go(s, p, at=t, cfg=ScheduleConfig(max_attempts=50))
    for _ in range(3):
        st = run_state(s, run_key("evt-1", "1"))
        dead = [k for k, v in st.items.items() if v.status.value == "DEAD_LETTER"]
        for k in dead:
            requeue(s, run_key("evt-1", "1"), f"item:{k}", OP, t)
        t += timedelta(hours=1)
        go(s, p, at=t, cfg=ScheduleConfig(max_attempts=50))
    assert run_state(s, run_key("evt-1", "1")).status is RunStatus.COMPLETE
    assert sorted(s.tasks) == sorted(clean_s.tasks) and len(s.tasks) == 3
    assert {o: s.review.get(o)[0] for o in ("obl-0", "obl-1", "obl-2")} == {
        o: clean_s.review.get(o)[0] for o in ("obl-0", "obl-1", "obl-2")
    }
    assert (
        notif_kinds(s).count("REGULATION_DETECTED") == 1
        and notif_kinds(s).count("OBLIGATIONS_READY") == 1
    )
    assert unaccounted(s) == [] and s.verify() and s.violations() == []


def test_obligation_text_appears_in_no_record_but_the_submission_intent() -> None:
    from regulus.workflow import Kind

    s, p = InMemoryWorkflowStore(), Fake(2)
    p.script["generate"] = ["unavail"]
    go(s, p)
    go(s, p, at=LATER + timedelta(seconds=30))
    seen_intent = 0
    for stream in s.streams:
        for r in s.ledger(stream):
            blob = r.model_dump_json()
            if r.kind is Kind.SUBMISSION_INTENT:
                seen_intent += TEXT in blob
            else:
                assert TEXT not in blob and "Pengendali" not in blob, (stream, r.kind)
    assert seen_intent == 2
