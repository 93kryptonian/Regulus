import random

import pytest
from obs_helpers import make_observer, observed_run
from rel_helpers import (
    CFG,
    EVENT,
    NOW,
    RUN,
    STORES,
    Everyone,
    FakeChannel,
    FakePipeline,
    FaultKind,
    FaultPlan,
    clean_state,
    go,
    logical,
    recover,
    timedelta,
)
from rv_engine_helpers import OWNER, TEXT

from regulus.evaluation.harness import ACTORS, ReviewRun, generation_result
from regulus.notifications import (
    DeliveryResult,
    DeliveryStatus,
    NotificationEvent,
    NotificationKind,
    RequeueStatus,
    State,
    deliver_due,
    notification_state,
    queue_emitter,
    queue_notification,
    requeue_notification,
)
from regulus.reliability.faults import Fault, Timeout
from regulus.reliability.guard import GuardedReviewStore, GuardedStore, IntegrityError
from regulus.reliability.invariants import (
    corrupt_review_logs,
    corrupt_streams,
    duplicate_decisions,
    retry_bound_violations,
    state_safety,
)
from regulus.reliability.matrix import covers
from regulus.reliability.wrappers import (
    Corruption,
    FaultyChannel,
    FaultyPipeline,
    FaultyReviewStore,
    FaultyStore,
    corrupt,
)
from regulus.review import (
    Action,
    ActionRequest,
    RejectCode,
    RejectReason,
    ReviewConfig,
    Status,
    apply,
    claim,
)
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Principal,
    SnapshotInputs,
    SubmitStatus,
    WorkflowRole,
    obligation_stream,
    run_event,
    submit_for_review,
)

OP = Principal(id="op", roles=(WorkflowRole.OPERATOR,))
CHAN_CFG = CFG


class Chan(FakeChannel):
    def __init__(self, dedupes: bool = True) -> None:
        super().__init__(random.Random(0), 0.0)
        self.sent: list[str] = []
        self.dedupes = dedupes

    def send(self, message, recipients, idempotency_key):  # type: ignore[no-untyped-def]
        if not (self.dedupes and idempotency_key in self.sent):
            self.sent.append(idempotency_key)
        return DeliveryResult(status=DeliveryStatus.SENT)


def ev(version: str = "v1") -> NotificationEvent:
    return NotificationEvent(kind=NotificationKind.TASK_OVERDUE, subject="task-1", version=version,
                             payload={"task_id": "task-1", "due_at": "2026-09-01T10:00:00+00:00"})  # fmt: skip


def fresh():  # type: ignore[no-untyped-def]
    s = InMemoryWorkflowStore()
    go(s, FakePipeline(1))
    return s


@covers("R10")
def test_r10_channel_down_then_up_retries_then_dead_letters_and_an_operator_can_requeue_once() -> (
    None
):
    s = fresh()
    q = queue_notification(s, ev(), Everyone(), SYSTEM, NOW)
    key = q.key or ""
    down = FaultyChannel(
        Chan(),
        FaultPlan(
            [Fault(kind=FaultKind.UNAVAILABLE, point="channel.send", call=i) for i in range(1, 20)]
        ),
    )
    t = NOW
    for _ in range(6):
        t += timedelta(minutes=10)
        deliver_due(s, down, SYSTEM, t, CFG)
    st = notification_state(s, key)
    assert st is not None and st.state is State.DEAD_LETTER and state_safety(s) == []
    assert requeue_notification(s, key, SYSTEM, "channel restored", t) is RequeueStatus.DENIED
    assert requeue_notification(s, key, OP, " ", t) is RequeueStatus.REASON_REQUIRED
    assert requeue_notification(s, "ntf-none", OP, "why", t) is RequeueStatus.UNKNOWN
    chan = Chan()
    assert (
        requeue_notification(s, key, OP, "channel restored", t + timedelta(minutes=1))
        is RequeueStatus.REQUEUED
    )
    deliver_due(s, chan, SYSTEM, t + timedelta(minutes=2), CFG)
    done = notification_state(s, key)
    assert (
        done is not None
        and done.state is State.DELIVERED
        and done.requeues == 1
        and chan.sent == [key]
    )
    for _ in range(2):
        assert (
            requeue_notification(s, key, OP, "again", t + timedelta(hours=1))
            is RequeueStatus.NOT_DEAD_LETTERED
        )


@covers("R10")
def test_r10_a_requeue_starts_a_new_attempt_window_so_it_gets_its_own_retries() -> None:
    s = fresh()
    key = queue_notification(s, ev(), Everyone(), SYSTEM, NOW).key or ""
    t = NOW
    bad = FaultyChannel(
        Chan(),
        FaultPlan(
            [Fault(kind=FaultKind.UNAVAILABLE, point="channel.send", call=i) for i in range(1, 40)]
        ),
    )
    for _ in range(5):
        t += timedelta(minutes=10)
        deliver_due(s, bad, SYSTEM, t, CFG)
    assert notification_state(s, key).state is State.DEAD_LETTER  # type: ignore[union-attr]
    requeue_notification(s, key, OP, "retry window", t)
    t += timedelta(minutes=10)
    deliver_due(s, bad, SYSTEM, t, CFG)
    st = notification_state(s, key)
    assert st is not None and st.state is State.RETRYING and st.attempts - st.window_start == 1


@covers("R11")
@pytest.mark.parametrize("store_cls", STORES)
def test_r11_a_duplicate_event_changes_nothing(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    pipe = FakePipeline(2)
    go(s, pipe)
    before = ({k: s.ledger(k) for k in s.streams}, dict(s.tasks))
    for _ in range(3):
        go(s, pipe, NOW + timedelta(hours=1))
    assert ({k: s.ledger(k) for k in s.streams}, dict(s.tasks)) == before and state_safety(s) == []


@covers("R12")
@pytest.mark.parametrize("store_cls", STORES)
def test_r12_a_duplicate_submission_returns_the_original_task_once(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    res = generation_result("obl-d")
    first = submit_for_review(
        s, res, SnapshotInputs(permitted_source=TEXT), SYSTEM, NOW, {OWNER: TEXT}
    )
    again = submit_for_review(
        s,
        res,
        SnapshotInputs(permitted_source=TEXT),
        SYSTEM,
        NOW + timedelta(hours=1),
        {OWNER: TEXT},
    )
    assert first.status is SubmitStatus.SUBMITTED and again.status is SubmitStatus.ALREADY_SUBMITTED
    assert again.task == first.task and len(s.tasks) == 1 and state_safety(s) == []


@covers("R13")
def test_r13_a_duplicate_review_request_records_one_decision() -> None:
    run = ReviewRun("obl-rel", random.Random(2))
    run.task = claim(run.task, ACTORS[0].id, run.clock, 900)
    req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=run.store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
    outs = [apply(run.store, run.task, req, ReviewConfig(), run.texts) for _ in range(3)]
    assert outs[0].status is Status.APPLIED and all(
        o.status is not Status.APPLIED for o in outs[1:]
    )
    assert len(run.store.get("obl-rel")[1]) == 1 and duplicate_decisions(run.store, "obl-rel") == []


@covers("R14")
@pytest.mark.parametrize("dedupes", [True, False])
def test_r14_a_crash_after_the_send_resends_with_the_same_key(dedupes: bool) -> None:
    s = InMemoryWorkflowStore()
    key = queue_notification(s, ev(), Everyone(), SYSTEM, NOW).key or ""
    inner = Chan(dedupes)
    chan = FaultyChannel(
        inner, FaultPlan([Fault(kind=FaultKind.CRASH, point="channel.send", call=1)])
    )
    with pytest.raises(Crash):
        deliver_due(s, chan, SYSTEM, NOW, CFG)
    assert notification_state(s, key).state is State.QUEUED  # type: ignore[union-attr]
    deliver_due(s, chan, SYSTEM, NOW + timedelta(seconds=1), CFG)
    assert notification_state(s, key).state is State.DELIVERED  # type: ignore[union-attr]
    assert inner.sent.count(key) == (1 if dedupes else 2)


@covers("R15a")
def test_r15a_a_timeout_before_the_effect_retries_to_exactly_one_effect() -> None:
    s = InMemoryWorkflowStore()
    key = queue_notification(s, ev(), Everyone(), SYSTEM, NOW).key or ""
    inner = Chan()
    chan = FaultyChannel(
        inner, FaultPlan([Fault(kind=FaultKind.TIMEOUT_BEFORE, point="channel.send", call=1)])
    )
    deliver_due(s, chan, SYSTEM, NOW, CFG)
    assert key not in inner.sent and notification_state(s, key).state is State.RETRYING  # type: ignore[union-attr]
    deliver_due(s, chan, SYSTEM, NOW + timedelta(minutes=5), CFG)
    assert inner.sent.count(key) == 1 and notification_state(s, key).state is State.DELIVERED  # type: ignore[union-attr]
    st = IntentWorkflowStore()
    plan = FaultPlan(
        [Fault(kind=FaultKind.TIMEOUT_BEFORE, point="store.commit_submission", call=1)]
    )
    out = submit_for_review(
        FaultyStore(st, plan),
        generation_result("obl-t"),
        SnapshotInputs(permitted_source=TEXT),
        SYSTEM,
        NOW,
        {OWNER: TEXT},
    )  # type: ignore[arg-type]
    assert out.status is SubmitStatus.FAILED and st.tasks == {}
    again = submit_for_review(
        st,
        generation_result("obl-t"),
        SnapshotInputs(permitted_source=TEXT),
        SYSTEM,
        NOW,
        {OWNER: TEXT},
    )
    assert again.status is SubmitStatus.SUBMITTED and len(st.tasks) == 1


@covers("R15b")
@pytest.mark.parametrize("store_cls", STORES)
def test_r15b_a_timeout_after_the_effect_still_yields_exactly_one_effect(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = InMemoryWorkflowStore()
    key = queue_notification(s, ev(), Everyone(), SYSTEM, NOW).key or ""
    inner = Chan()
    chan = FaultyChannel(
        inner, FaultPlan([Fault(kind=FaultKind.TIMEOUT_AFTER, point="channel.send", call=1)])
    )
    deliver_due(s, chan, SYSTEM, NOW, CFG)
    deliver_due(s, chan, SYSTEM, NOW + timedelta(minutes=5), CFG)
    assert inner.sent.count(key) == 1 and notification_state(s, key).state is State.DELIVERED  # type: ignore[union-attr]
    st = store_cls()
    plan = FaultPlan([Fault(kind=FaultKind.TIMEOUT_AFTER, point="store.commit_submission", call=1)])
    res = generation_result("obl-after")
    out = submit_for_review(
        FaultyStore(st, plan),
        res,
        SnapshotInputs(permitted_source=TEXT),
        SYSTEM,
        NOW,
        {OWNER: TEXT},
    )  # type: ignore[arg-type]
    assert out.status is SubmitStatus.FAILED and len(st.tasks) == 1
    again = submit_for_review(
        st,
        res,
        SnapshotInputs(permitted_source=TEXT),
        SYSTEM,
        NOW + timedelta(seconds=1),
        {OWNER: TEXT},
    )
    assert (
        again.status is SubmitStatus.ALREADY_SUBMITTED
        and len(st.tasks) == 1
        and state_safety(st) == []
    )
    run = ReviewRun("obl-rel", random.Random(4))
    inner_store = run.store
    plan2 = FaultPlan([Fault(kind=FaultKind.TIMEOUT_AFTER, point="review.commit", call=1)])
    run.store = FaultyReviewStore(inner_store, plan2)  # type: ignore[assignment]
    run.task = claim(run.task, ACTORS[0].id, run.clock, 900)
    req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=inner_store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
    first = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert first.status is Status.NOT_RECORDED and len(inner_store.get("obl-rel")[1]) == 1
    retry = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert retry.status is not Status.APPLIED and len(inner_store.get("obl-rel")[1]) == 1
    assert duplicate_decisions(inner_store, "obl-rel") == [] and Timeout


def _corrupt_ledger(store, stream, mode, seed=0):  # type: ignore[no-untyped-def]
    store.streams[stream] = corrupt(
        store.streams[stream],
        mode,
        random.Random(seed),
        foreign=store.streams[stream][0].model_copy(update={"id": "wrec-foreign"}),
    )


@covers("R16")
@pytest.mark.parametrize("mode", list(Corruption))
@pytest.mark.parametrize("store_cls", STORES)
def test_r16_each_ledger_corruption_is_detected_and_a_guarded_write_is_refused(
    store_cls, mode
) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    go(s, FakePipeline(2))
    stream = obligation_stream("obl-0")
    guarded = GuardedStore(s)
    assert corrupt_streams(s) == []
    guarded.append(
        stream,
        __import__("regulus.workflow", fromlist=["Kind"]).Kind.SUBMIT_REFUSED,
        SYSTEM,
        NOW + timedelta(days=1),
        None,
        {"reasons": ["probe"]},
    )
    _corrupt_ledger(s, stream, mode)
    assert stream in corrupt_streams(s) or mode is Corruption.TRUNCATE
    before = s.ledger(stream)
    with pytest.raises(IntegrityError):
        guarded.append(
            stream,
            __import__("regulus.workflow", fromlist=["Kind"]).Kind.SUBMIT_REFUSED,
            SYSTEM,
            NOW + timedelta(days=2),
            None,
            {"reasons": ["x"]},
        )
    assert s.ledger(stream) == before


@covers("R16")
def test_r16_a_guard_on_an_intact_stream_changes_nothing() -> None:
    s = InMemoryWorkflowStore()
    plain = InMemoryWorkflowStore()
    go(s, FakePipeline(2))
    go(plain, FakePipeline(2))
    guarded = GuardedStore(s)
    res = run_event(
        guarded,
        FakePipeline(2),
        EVENT,
        SYSTEM,
        NOW + timedelta(hours=1),
        queue_emitter(guarded, Everyone(), SYSTEM, NOW),
        "1",
        CFG,
    )  # type: ignore[arg-type]
    assert res.status.value == "COMPLETE" and logical(s) == logical(plain)


@covers("R17")
@pytest.mark.parametrize("mode", list(Corruption))
def test_r17_each_review_log_corruption_is_detected_and_the_guarded_review_store_refuses(
    mode,
) -> None:  # type: ignore[no-untyped-def]
    run = ReviewRun("obl-rel", random.Random(7))
    for _ in range(60):
        run.step()
        if len(run.store.get("obl-rel")[1]) >= 3:
            break
    inner = run.store
    log = inner.get("obl-rel")[1]
    if len(log) < 3:
        pytest.skip("scripted run produced too short a log")
    assert corrupt_review_logs(inner) == []
    inner._log["obl-rel"] = corrupt(
        log, mode, random.Random(1), foreign=log[0].model_copy(update={"id": "rrec-x"})
    )
    assert corrupt_review_logs(inner) == ["obl-rel"]
    guarded = GuardedReviewStore(inner)
    req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=inner.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
    claimed = claim(
        run.task.model_copy(
            update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
        ),
        ACTORS[0].id,
        run.clock,
        900,
    )
    out = apply(guarded, claimed, req, ReviewConfig(), run.texts)
    assert out.status is not Status.APPLIED and inner.get("obl-rel")[1] == inner._log["obl-rel"]


@covers("R18")
def test_r18_an_altered_intent_payload_is_detected_and_recovery_refuses_to_complete() -> None:
    s = IntentWorkflowStore()
    s.fail_after = "intent"
    with pytest.raises(Crash):
        go(s, FakePipeline(1))
    stream = obligation_stream("obl-0")
    recs = s.ledger(stream)
    assert len(recs) == 1 and corrupt_streams(s) == []
    forged = recs[0].model_copy(
        update={"details": {"prepared": {**recs[0].details["prepared"], "key": "sub-forged"}}}
    )
    s.streams[stream] = (forged,)
    assert stream in corrupt_streams(s)
    with pytest.raises(IntegrityError):
        GuardedStore(s).complete_submission("obl-0", SYSTEM, NOW)
    assert not s.registered("obl-0")


@covers("R20")
@pytest.mark.parametrize("store_cls", STORES)
@pytest.mark.parametrize("seed", range(20))
def test_r20_one_to_three_seeded_faults_converge_after_removal(store_cls, seed) -> None:  # type: ignore[no-untyped-def]
    _, clean_l = clean_state(store_cls, 3)
    points = [
        "pipeline.process",
        "pipeline.generate",
        "pipeline.enrich",
        "store.commit_submission",
        "store.append",
        "channel.send",
    ]
    kinds = [
        FaultKind.UNAVAILABLE,
        FaultKind.TIMEOUT_BEFORE,
        FaultKind.TIMEOUT_AFTER,
        FaultKind.CRASH,
        FaultKind.PERMANENT,
    ]
    plan = FaultPlan.seeded(seed, points, kinds, max_faults=3)
    assert 1 <= len(plan.faults) <= 3
    s = store_cls()
    pipe = FaultyPipeline(FakePipeline(3), plan)
    store = FaultyStore(s, plan)
    chan = FaultyChannel(Chan(), plan)
    t = NOW
    for _ in range(10):
        t += timedelta(seconds=30)
        try:
            run_event(
                store, pipe, EVENT, SYSTEM, t, queue_emitter(store, Everyone(), SYSTEM, t), "1", CFG
            )  # type: ignore[arg-type]
            deliver_due(s, chan, SYSTEM, t, CFG)
        except Crash:
            pass
        assert state_safety(s) == [] and retry_bound_violations(s, RUN, 3) == []
    plan.clear()
    recover(s, FakePipeline(3))
    assert logical(s) == clean_l and state_safety(s) == []


@covers("R22")
def test_r22_a_failing_sink_changes_no_result() -> None:
    clean = observed_run(None, FakePipeline(2))
    obs = make_observer(capacity=1)

    class Bad:
        def emit(self, e):  # type: ignore[no-untyped-def]
            raise RuntimeError("down")

    store, rep = observed_run(obs, FakePipeline(2))
    obs.buffer.drain(Bad(), 10)
    assert (
        rep == clean[1] and sorted(store.tasks) == sorted(clean[0].tasks) and obs.buffer.balanced()
    )
