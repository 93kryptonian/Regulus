import random
from datetime import timedelta

import pytest
from rv_engine_helpers import BOB, OWNER, TEXT
from wf_helpers import LATER, generated, inputs

from regulus.notifications import (
    DeliveryResult,
    DeliveryStatus,
    MessageRejected,
    NotificationClass,
    NotificationEvent,
    NotificationKind,
    QueueStatus,
    State,
    assigned_events,
    check_message,
    compose,
    deliver_due,
    notification_state,
    queue_notification,
    reroute,
    review_decided_events,
    source_events,
    tick_events,
)
from regulus.notifications.compose import ALLOWED
from regulus.notifications.models import Message
from regulus.review import (
    Action,
    ActionRequest,
    OpenQuestionResolution,
    Resolution,
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
    Kind,
    Principal,
    ReviewerInfo,
    ScheduleConfig,
    WorkflowRole,
    submit_for_review,
    tick,
)

K = NotificationKind
CFG = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=3)


def ev(
    kind: K = K.TASK_OVERDUE, subject: str = "task-1", version: str = "v1", **payload
) -> NotificationEvent:  # type: ignore[no-untyped-def]
    base = {
        K.TASK_OVERDUE: {"task_id": subject, "due_at": "2026-09-01T10:00:00+00:00"},
        K.TASK_ASSIGNED: {"task_id": subject, "assignee": "amy"},
        K.OBLIGATIONS_READY: {
            "event_id": subject,
            "potential_obligations": 3,
            "similarity_candidates": 1,
        },
        K.REGULATION_DETECTED: {"regulation_id": "PP-33-2026", "event_id": subject},
    }[kind]
    return NotificationEvent(
        kind=kind, subject=subject, version=version, payload={**base, **payload}
    )


class Chan:
    def __init__(self, dedupes: bool = True) -> None:
        self.sent: list[tuple[str, tuple[str, ...], str]] = []
        self.script: list[object] = []
        self.dedupes, self.logical = dedupes, set()

    def send(self, message, recipients, idempotency_key):  # type: ignore[no-untyped-def]
        step = self.script.pop(0) if self.script else "ok"
        if step == "raise":
            raise ConnectionError("down")
        if step == "retry":
            return DeliveryResult(status=DeliveryStatus.FAILED_RETRYABLE, error_class="Unavailable")
        if step == "perm":
            return DeliveryResult(status=DeliveryStatus.FAILED_PERMANENT, error_class="Rejected")
        if not (self.dedupes and idempotency_key in self.logical):
            self.sent.append((message.title, tuple(recipients), idempotency_key))
        self.logical.add(idempotency_key)
        if step == "crash_after_send":
            raise Crash("after send")
        return DeliveryResult(status=DeliveryStatus.SENT)


class Who:
    def __init__(self, *ids: str) -> None:
        self.ids = list(ids)

    def resolve(self, event):  # type: ignore[no-untyped-def]
        return self.ids


class Dir:
    def reviewers(self, now):  # type: ignore[no-untyped-def]
        return [ReviewerInfo(id="amy")]


def store_with_task(store_cls=InMemoryWorkflowStore, questions: bool = False):  # type: ignore[no-untyped-def]
    s = store_cls()
    res = generated()
    if not questions:
        res = res.model_copy(update={"open_questions": ()})
    out = submit_for_review(s, res, inputs(), SYSTEM, LATER, {OWNER: TEXT})
    return s, out.task


def test_every_kind_composes_with_a_minimal_payload_and_classes_are_separate() -> None:
    samples = {
        K.REGULATION_DETECTED: {"regulation_id": "R1", "event_id": "e1"},
        K.AMENDMENT_DETECTED: {"regulation_id": "R1", "target_id": "R0", "event_id": "e1"},
        K.OBLIGATIONS_READY: {
            "event_id": "e1",
            "potential_obligations": 2,
            "similarity_candidates": 0,
        },
        K.TASK_ASSIGNED: {"task_id": "t1", "assignee": "amy"},
        K.TASK_DUE_SOON: {"task_id": "t1", "due_at": "2026-09-01T10:00:00+00:00"},
        K.TASK_OVERDUE: {"task_id": "t1", "due_at": "2026-09-01T10:00:00+00:00"},
        K.SOURCE_CHANGED: {"task_id": "t1", "obligation_id": "o1"},
        K.SOURCE_WITHDRAWN: {"task_id": "t1", "obligation_id": "o1"},
        K.REVIEW_DECIDED: {
            "obligation_id": "o1",
            "status": "APPROVED",
            "record_hash": "abcdef0123456789",
        },
        K.PIPELINE_STAGE_FAILED: {
            "run_id": "r1",
            "stage": "GENERATE",
            "error_class": "Unavailable",
        },
        K.DEAD_LETTER: {"run_id": "r1", "stage": "GENERATE", "error_class": "Unavailable"},
    }
    assert set(samples) == set(ALLOWED)
    for kind, payload in samples.items():
        e = NotificationEvent(kind=kind, subject="s", version="v", payload=payload)
        m = compose(e)
        want = (
            NotificationClass.AI_ENRICHED
            if kind is K.OBLIGATIONS_READY
            else NotificationClass.DETERMINISTIC
        )
        assert m.cls is want
        if kind is K.OBLIGATIONS_READY:
            assert "unreviewed" in m.body and "potential" in m.body
    assert (
        compose(
            NotificationEvent(
                kind=K.TASK_OVERDUE, subject="s", version="v", payload=samples[K.TASK_OVERDUE]
            )
        ).link
        == "/tasks/t1"
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"task_id": "see https://x.example/y", "due_at": "2026-09-01T10:00:00+00:00"},
        {"task_id": "ana@example.com", "due_at": "2026-09-01T10:00:00+00:00"},
        {"task_id": "Budi Santoso", "due_at": "2026-09-01T10:00:00+00:00"},
        {"task_id": "t1", "due_at": "tomorrow please"},
        {"task_id": "t1"},
        {"task_id": "t1", "due_at": "2026-09-01T10:00:00+00:00", "name": "Budi"},
        {"task_id": "x" * 200, "due_at": "2026-09-01T10:00:00+00:00"},
        {"task_id": "approved", "due_at": "2026-09-01T10:00:00+00:00"},
        {"task_id": "token-123456", "due_at": "2026-09-01T10:00:00+00:00"},
    ],
)
def test_unsafe_or_authoritative_payloads_are_rejected(bad: dict[str, str]) -> None:
    with pytest.raises(MessageRejected):
        compose(NotificationEvent(kind=K.TASK_OVERDUE, subject="s", version="v", payload=bad))


def test_authority_words_are_only_allowed_in_review_decided() -> None:
    m = Message(cls=NotificationClass.DETERMINISTIC, title="Obligation approved", body="x")
    with pytest.raises(MessageRejected):
        check_message(m, K.TASK_OVERDUE)
    check_message(m, K.REVIEW_DECIDED)
    ai = Message(cls=NotificationClass.AI_ENRICHED, title="Obligations ready", body="3 items")
    with pytest.raises(MessageRejected):
        check_message(ai, K.OBLIGATIONS_READY)


def test_queue_delivers_once_to_the_recorded_recipients_with_the_dedupe_key() -> None:
    s, _ = store_with_task()
    chan, e = Chan(), ev()
    q = queue_notification(s, e, Who("bob", "amy"), SYSTEM, LATER)
    assert q.status is QueueStatus.QUEUED and q.key == e.dedupe_key
    st = notification_state(s, q.key)
    assert st.state is State.QUEUED and st.recipients == ("amy", "bob")  # type: ignore[union-attr]
    out = deliver_due(s, chan, SYSTEM, LATER)
    assert [d.state for d in out] == [State.DELIVERED] and chan.sent == [
        (st.message.title, ("amy", "bob"), q.key)
    ]  # type: ignore[union-attr]
    assert deliver_due(s, chan, SYSTEM, LATER + timedelta(hours=1)) == [] and len(chan.sent) == 1
    assert s.verify()


def test_a_duplicate_dedupe_key_is_one_logical_notification() -> None:
    s, _ = store_with_task()
    first = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    n = len(s.ledger("notification:" + first.key))  # type: ignore[operator]
    again = queue_notification(s, ev(), Who("bob"), SYSTEM, LATER + timedelta(seconds=1))
    assert again.status is QueueStatus.DUPLICATE and len(s.ledger("notification:" + first.key)) == n  # type: ignore[operator]
    other = queue_notification(s, ev(version="v2"), Who("amy"), SYSTEM, LATER)
    assert other.status is QueueStatus.QUEUED and other.key != first.key


def test_retries_use_a_deterministic_backoff_then_dead_letter() -> None:
    s, _ = store_with_task()
    chan = Chan()
    chan.script = ["retry", "raise", "retry"]
    q = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    t = LATER
    assert deliver_due(s, chan, SYSTEM, t, CFG)[0].state is State.RETRYING
    st = notification_state(s, q.key)
    assert st.next_attempt_at == t + timedelta(seconds=10) and st.attempts == 1  # type: ignore[union-attr]
    assert deliver_due(s, chan, SYSTEM, t + timedelta(seconds=5), CFG) == []
    t2 = t + timedelta(seconds=10)
    assert deliver_due(s, chan, SYSTEM, t2, CFG)[0].state is State.RETRYING
    assert notification_state(s, q.key).next_attempt_at == t2 + timedelta(seconds=20)  # type: ignore[union-attr]
    t3 = t2 + timedelta(seconds=20)
    assert deliver_due(s, chan, SYSTEM, t3, CFG)[0].state is State.DEAD_LETTER
    assert deliver_due(s, chan, SYSTEM, t3 + timedelta(days=1), CFG) == []
    assert notification_state(s, q.key).attempts == 3 and chan.sent == []  # type: ignore[union-attr]
    kinds = [r.kind for r in s.ledger("notification:" + q.key)]  # type: ignore[operator]
    assert kinds[-1] is Kind.NOTIFICATION_DEAD_LETTER and s.verify()


def test_permanent_failure_and_missing_recipients_are_terminal_and_visible() -> None:
    s, _ = store_with_task()
    chan = Chan()
    chan.script = ["perm"]
    q = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    assert deliver_due(s, chan, SYSTEM, LATER)[0].state is State.FAILED_PERMANENT
    assert deliver_due(s, chan, SYSTEM, LATER + timedelta(days=1)) == []
    assert notification_state(s, q.key).error_class == "Rejected"  # type: ignore[union-attr]
    none = queue_notification(s, ev(version="v9"), Who(), SYSTEM, LATER)
    assert none.status is QueueStatus.NO_RECIPIENT
    st = notification_state(s, none.key)  # type: ignore[arg-type]
    assert st.state is State.FAILED_PERMANENT and st.error_class == "NO_RECIPIENT"  # type: ignore[union-attr]
    assert deliver_due(s, chan, SYSTEM, LATER) == [] and chan.sent == []


def test_the_recipient_set_is_fixed_at_queue_time_and_rerouting_is_a_new_linked_notification() -> (
    None
):
    s, _ = store_with_task()
    chan, who = Chan(), Who("alice")
    q = queue_notification(s, ev(), who, SYSTEM, LATER)
    who.ids = ["bob"]
    deliver_due(s, chan, SYSTEM, LATER)
    assert chan.sent[0][1] == ("alice",)
    assert (
        reroute(s, q.key, ev(version="r1"), who, "", SYSTEM, LATER).status is QueueStatus.REJECTED
    )  # type: ignore[arg-type]
    assert (
        reroute(s, "ntf-missing", ev(version="r1"), who, "why", SYSTEM, LATER).status
        is QueueStatus.REJECTED
    )
    r = reroute(
        s, q.key, ev(version="r1"), who, "alice left the team", SYSTEM, LATER + timedelta(seconds=1)
    )  # type: ignore[arg-type]
    deliver_due(s, chan, SYSTEM, LATER + timedelta(seconds=2))
    assert chan.sent[1][1] == ("bob",) and chan.sent[1][2] == r.key != q.key
    assert notification_state(s, r.key).reroute_of == q.key  # type: ignore[arg-type,union-attr]
    assert notification_state(s, q.key).recipients == ("alice",)  # type: ignore[arg-type,union-attr]


@pytest.mark.parametrize("dedupes", [True, False])
def test_sent_but_not_recorded_is_resent_with_the_same_key(dedupes: bool) -> None:
    s, _ = store_with_task()
    chan = Chan(dedupes)
    q = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    s.fail_store = 1
    out = deliver_due(s, chan, SYSTEM, LATER)
    assert out[0].unrecorded and notification_state(s, q.key).state is State.QUEUED  # type: ignore[arg-type,union-attr]
    again = deliver_due(s, chan, SYSTEM, LATER + timedelta(seconds=1))
    assert again[0].state is State.DELIVERED
    assert {k for _, _, k in chan.sent} == {q.key}
    assert len(chan.sent) == (1 if dedupes else 2)


def test_a_crash_between_send_and_record_resends_on_recovery() -> None:
    s, _ = store_with_task()
    chan = Chan()
    chan.script = ["crash_after_send"]
    q = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    with pytest.raises(Crash):
        deliver_due(s, chan, SYSTEM, LATER)
    assert notification_state(s, q.key).state is State.QUEUED  # type: ignore[arg-type,union-attr]
    assert deliver_due(s, chan, SYSTEM, LATER + timedelta(seconds=1))[0].state is State.DELIVERED
    assert len(chan.sent) == 1


def test_a_failed_queue_commit_leaves_nothing_and_roles_are_enforced() -> None:
    s, _ = store_with_task()
    s.fail_store = 1
    assert queue_notification(s, ev(), Who("amy"), SYSTEM, LATER).status is QueueStatus.FAILED
    assert s.streams_with("notification:") == []
    assert (
        queue_notification(
            s, ev(), Who("amy"), Principal(id="c", roles=(WorkflowRole.COORDINATOR,)), LATER
        ).status
        is QueueStatus.DENIED
    )
    bad = NotificationEvent(
        kind=K.TASK_OVERDUE,
        subject="s",
        version="v",
        payload={"task_id": "a@b.c", "due_at": "2026-09-01T10:00:00+00:00"},
    )
    assert queue_notification(s, bad, Who("amy"), SYSTEM, LATER).status is QueueStatus.REJECTED
    assert s.streams_with("notification:") == []


def test_review_decided_is_observed_from_the_phase_9_log_only() -> None:
    s, task = store_with_task()
    assert review_decided_events(s) == []
    t = claim(task, "bob", LATER, 900)  # type: ignore[arg-type]
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=t.id,
        base_version=s.review.version("obl-1"),
        actor=BOB,
        at=LATER + timedelta(seconds=1),
    )
    assert apply(s.review, t, req, ReviewConfig(), {OWNER: TEXT}).status is Status.APPLIED
    (e,) = review_decided_events(s)
    log = s.review.get("obl-1")[1]
    assert e.payload == {
        "obligation_id": "obl-1",
        "status": "APPROVED",
        "record_hash": log[0].hash[:16],
    }
    assert "APPROVED" in compose(e).body
    assert {OpenQuestionResolution, Resolution}


def test_workflow_events_produce_safe_deterministic_messages() -> None:
    s, task = store_with_task()
    d = Dir()
    tick(s, LATER, d, SYSTEM)
    evs = assigned_events(s)
    assert [e.kind for e in evs] == [K.TASK_ASSIGNED] and "routing hint" in compose(evs[0]).body
    from regulus.workflow import current_due

    due = current_due(s, task.id)  # type: ignore[union-attr]
    acts = tick(s, due + timedelta(hours=1), d, SYSTEM)  # type: ignore[operator]
    (e,) = tick_events(s, acts)
    assert e.kind is K.TASK_OVERDUE and compose(e).link == f"/tasks/{task.id}"  # type: ignore[union-attr]
    assert source_events(s) == []
    s2 = InMemoryWorkflowStore()
    out = submit_for_review(
        s2, generated(), inputs(source_complete=False), SYSTEM, LATER, {OWNER: TEXT}
    )
    assert out.task is not None and source_events(s2) == []


def test_review_outcomes_are_identical_with_notifications_failing_working_or_absent() -> None:
    def run(mode: str):  # type: ignore[no-untyped-def]
        s, task = store_with_task()
        chan = Chan()
        chan.script = ["raise"] * 50 if mode == "failing" else []
        if mode != "absent":
            queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
            deliver_due(s, chan, SYSTEM, LATER, CFG)
            deliver_due(s, chan, SYSTEM, LATER + timedelta(minutes=5), CFG)
        t = claim(task, "bob", LATER, 900)  # type: ignore[arg-type]
        req = ActionRequest(
            action=Action.APPROVE,
            task_id=t.id,
            base_version=s.review.version("obl-1"),
            actor=BOB,
            at=LATER + timedelta(seconds=1),
        )
        res = apply(s.review, t, req, ReviewConfig(), {OWNER: TEXT})
        return res.status, s.review.get("obl-1")

    assert run("failing") == run("working") == run("absent")


@pytest.mark.parametrize("store_cls", [InMemoryWorkflowStore, IntentWorkflowStore])
@pytest.mark.parametrize("seed", range(25))
def test_random_queue_deliver_fault_sequences_never_lose_a_notification(store_cls, seed) -> None:  # type: ignore[no-untyped-def]
    rng = random.Random(seed)
    s, _ = store_with_task(store_cls)
    chan = Chan(dedupes=rng.random() < 0.5)
    queued: set[str] = set()
    now = LATER
    states_seen: dict[str, list[State]] = {}
    for _ in range(30):
        now += timedelta(seconds=rng.choice((1, 10, 120)))
        if rng.random() < 0.4:
            e = ev(version=f"v{rng.randrange(6)}")
            s.fail_store = 1 if rng.random() < 0.1 else 0
            out = queue_notification(
                s, e, Who(*rng.sample(["amy", "bob", "cat"], rng.randint(0, 3))), SYSTEM, now
            )
            s.fail_store = 0
            if out.status in (QueueStatus.QUEUED, QueueStatus.NO_RECIPIENT, QueueStatus.DUPLICATE):
                queued.add(out.key)  # type: ignore[arg-type]
        chan.script = [
            rng.choice(["ok", "ok", "retry", "raise", "perm", "crash_after_send"]) for _ in range(3)
        ]
        s.fail_store = 1 if rng.random() < 0.1 else 0
        try:
            deliver_due(s, chan, SYSTEM, now, CFG)
        except Crash:
            pass
        s.fail_store = 0
        assert s.verify() and s.violations() == []
        for k in s.streams_with("notification:"):
            st = notification_state(s, k[len("notification:") :])
            states_seen.setdefault(k, []).append(st.state)  # type: ignore[union-attr]
    for k, seq in states_seen.items():
        done = {State.DELIVERED, State.FAILED_PERMANENT, State.DEAD_LETTER}
        first = next((i for i, x in enumerate(seq) if x in done), None)
        assert first is None or all(x is seq[first] for x in seq[first:]), (k, seq)
    chan.script = []
    for _ in range(10):
        now += timedelta(hours=1)
        deliver_due(s, chan, SYSTEM, now, CFG)
    for k in s.streams_with("notification:"):
        st = notification_state(s, k[len("notification:") :])
        assert st.state in (State.DELIVERED, State.FAILED_PERMANENT, State.DEAD_LETTER)  # type: ignore[union-attr]
    assert {k[len("notification:") :] for k in s.streams_with("notification:")} == queued


def test_the_notification_ledger_is_tamper_evident() -> None:
    s, _ = store_with_task()
    q = queue_notification(s, ev(), Who("amy"), SYSTEM, LATER)
    deliver_due(s, Chan(), SYSTEM, LATER)
    stream = "notification:" + q.key  # type: ignore[operator]
    s.streams[stream] = (
        s.streams[stream][0].model_copy(update={"principal_id": "mallory"}),
        *s.streams[stream][1:],
    )
    assert not s.verify()
