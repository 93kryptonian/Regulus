import random
from datetime import timedelta

import pytest
from rv_engine_helpers import ALICE, BOB, OWNER, TEXT
from wf_helpers import LATER, generated, inputs, similarity

from regulus.domain import ObligationStatus as S
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
from regulus.similarity import Label
from regulus.workflow import (
    SYSTEM,
    AssignStatus,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Kind,
    Principal,
    ReviewerInfo,
    RiskClass,
    ScheduleConfig,
    SubmitStatus,
    TickKind,
    WorkflowRole,
    assign,
    backoff,
    current_assignment,
    current_due,
    next_attempt_at,
    overdue,
    reschedule,
    risk_class,
    sla_due,
    submit_for_review,
    task_stream,
    tick,
)

COORD = Principal(id="coord", roles=(WorkflowRole.COORDINATOR,))
CFG = ScheduleConfig()


class Dir:
    def __init__(self, *reviewers: tuple[str, bool]) -> None:
        self.rs = [ReviewerInfo(id=i, available=a) for i, a in reviewers]

    def reviewers(self, now):  # type: ignore[no-untyped-def]
        return self.rs


def world(n: int = 1, store_cls=InMemoryWorkflowStore, **kw):  # type: ignore[no-untyped-def]
    s = store_cls()
    tasks = []
    for i in range(n):
        out = submit_for_review(
            s, generated(f"obl-{i}"), inputs(**kw), SYSTEM, LATER, {OWNER: TEXT}
        )
        assert out.status is SubmitStatus.SUBMITTED
        tasks.append(out.task)
    return s, tasks


def test_auto_assignment_picks_the_least_loaded_then_lowest_id() -> None:
    s, tasks = world(4)
    d = Dir(("zed", True), ("amy", True), ("bob", True))
    got = [assign(s, t.id, SYSTEM, LATER, d).assignee for t in tasks]
    assert got == ["amy", "bob", "zed", "amy"]
    assert all(current_assignment(s, t.id).assignee == g for t, g in zip(tasks, got, strict=True))


def test_unavailable_reviewers_are_skipped_and_none_available_leaves_a_visible_pool() -> None:
    s, (t,) = world()
    out = assign(s, t.id, SYSTEM, LATER, Dir(("amy", False)))
    assert out.status is AssignStatus.UNASSIGNED and out.reasons == ("NO_REVIEWER_AVAILABLE",)
    assert current_assignment(s, t.id).unassigned_reason == "NO_REVIEWER_AVAILABLE"
    again = assign(s, t.id, SYSTEM, LATER + timedelta(seconds=1), Dir(("amy", False)))
    assert again.status is AssignStatus.UNCHANGED and len(s.ledger(task_stream(t.id))) == 1
    ok = assign(s, t.id, SYSTEM, LATER + timedelta(seconds=2), Dir(("amy", False), ("bob", True)))
    assert ok.status is AssignStatus.ASSIGNED and ok.assignee == "bob"


def test_reassignment_needs_a_coordinator_a_reason_and_an_available_reviewer() -> None:
    s, (t,) = world()
    d = Dir(("amy", True), ("bob", True), ("cat", False))
    assign(s, t.id, SYSTEM, LATER, d)
    assert assign(s, t.id, SYSTEM, LATER, d, to="bob", reason="r").status is AssignStatus.DENIED
    assert assign(s, t.id, COORD, LATER, d, to="bob").reasons == ("REASON_REQUIRED",)
    assert assign(s, t.id, COORD, LATER, d, to="cat", reason="r").reasons == (
        "NOT_AN_AVAILABLE_REVIEWER",
    )
    assert assign(s, t.id, COORD, LATER, d, to="nobody", reason="r").status is AssignStatus.REFUSED
    ok = assign(s, t.id, COORD, LATER + timedelta(seconds=1), d, to="bob", reason="amy on leave")
    assert ok.status is AssignStatus.ASSIGNED and current_assignment(s, t.id).assignee == "bob"
    assert (
        assign(s, t.id, COORD, LATER + timedelta(seconds=2), d, to="bob", reason="r").status
        is AssignStatus.UNCHANGED
    )
    kinds = [r.kind for r in s.ledger(task_stream(t.id))]
    assert kinds == [Kind.ASSIGNED, Kind.REASSIGNED] and s.verify()


def test_unknown_and_closed_tasks_cannot_be_assigned() -> None:
    s, (t,) = world()
    d = Dir(("amy", True))
    assert assign(s, "task-nope", SYSTEM, LATER, d).reasons == ("UNKNOWN_TASK",)
    task = claim(t, "bob", LATER, 900)
    req = ActionRequest(
        action=Action.REJECT,
        task_id=task.id,
        base_version=s.review.version("obl-0"),
        actor=BOB,
        at=LATER + timedelta(seconds=1),
        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE),
    )
    assert apply(s.review, task, req, ReviewConfig(), {OWNER: TEXT}).status is Status.APPLIED
    assert assign(s, t.id, SYSTEM, LATER + timedelta(seconds=2), d).reasons == ("TASK_CLOSED",)


def test_a_role_without_system_or_coordinator_cannot_assign() -> None:
    s, (t,) = world()
    assert (
        assign(s, t.id, Principal(id="x"), LATER, Dir(("amy", True))).status is AssignStatus.DENIED
    )


@pytest.mark.parametrize("assignee", [None, "bob", "alice"])
def test_assignment_never_changes_a_phase_9_outcome_or_claim(assignee) -> None:  # type: ignore[no-untyped-def]
    s, (t,) = world()
    if assignee:
        assign(s, t.id, COORD, LATER, Dir((assignee, True)), to=assignee, reason="route")
    task = claim(t, "bob", LATER, 900)
    held = (task.claimed_by, task.claim_expires_at)
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=task.id,
        base_version=s.review.version("obl-0"),
        actor=BOB,
        at=LATER + timedelta(seconds=1),
    )
    res = apply(s.review, task, req, ReviewConfig(), {OWNER: TEXT})
    assert (task.claimed_by, task.claim_expires_at) == held
    assert res.status is Status.INCOMPLETE_REVIEW and res.reasons == ("OPEN_QUESTION:deadline:x",)
    other = ActionRequest(
        action=Action.APPROVE,
        task_id=task.id,
        base_version=s.review.version("obl-0"),
        actor=ALICE,
        at=LATER + timedelta(seconds=1),
    )
    assert apply(s.review, task, other, ReviewConfig(), {OWNER: TEXT}).reasons == ("NO_CLAIM",)


def test_risk_class_and_sla_follow_the_snapshot_not_the_ui() -> None:
    s_plain, (tp,) = world()
    assert risk_class(tp) is RiskClass.ELEVATED  # the helper result carries one open question
    s_dup, (td,) = world(similarity=similarity(Label.POSSIBLE_DUPLICATE))
    s_wd, (tw,) = world(source_complete=False)
    assert risk_class(td) is RiskClass.HIGH and risk_class(tw) is RiskClass.HIGH
    assert sla_due(td, CFG) - td.created_at == timedelta(hours=4)
    assert sla_due(tp, CFG) - tp.created_at == timedelta(hours=24)


def test_due_is_a_projection_and_overdue_blocks_nothing() -> None:
    s, (t,) = world()
    d = Dir(("amy", True))
    tick(s, LATER, d, SYSTEM)
    due = current_due(s, t.id)
    assert due == sla_due(t, CFG) and not overdue(due, LATER) and overdue(due, due)
    later = due + timedelta(hours=1)
    acts = tick(s, later, d, SYSTEM)
    assert [a.kind for a in acts] == [TickKind.TASK_OVERDUE]
    assert s.review.get("obl-0")[0].status is S.PENDING_REVIEW
    task = claim(t, "bob", later, 900)
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=task.id,
        base_version=s.review.version("obl-0"),
        actor=BOB,
        at=later + timedelta(seconds=1),
    )
    assert (
        apply(s.review, task, req, ReviewConfig(), {OWNER: TEXT}).status is Status.INCOMPLETE_REVIEW
    )


def test_tick_is_idempotent_and_windows_are_deterministic() -> None:
    s, (t,) = world()
    d = Dir(("amy", True))
    first = tick(s, LATER, d, SYSTEM)
    assert first == [] and current_assignment(s, t.id).assignee == "amy"
    due = current_due(s, t.id)
    soon = due - timedelta(minutes=30)
    a = tick(s, soon, d, SYSTEM)
    assert [x.kind for x in a] == [TickKind.TASK_DUE_SOON]
    n = len(s.ledger(task_stream(t.id)))
    assert tick(s, soon, d, SYSTEM) == [] and tick(s, soon + timedelta(minutes=1), d, SYSTEM) == []
    assert len(s.ledger(task_stream(t.id))) == n
    day1 = due + timedelta(hours=1)
    assert (
        len(tick(s, day1, d, SYSTEM)) == 1 and tick(s, day1 + timedelta(minutes=5), d, SYSTEM) == []
    )
    assert len(tick(s, day1 + timedelta(days=1), d, SYSTEM)) == 1


def test_reschedule_opens_a_new_window_and_needs_a_reason() -> None:
    s, (t,) = world()
    d = Dir(("amy", True))
    tick(s, LATER, d, SYSTEM)
    due = current_due(s, t.id)
    soon = due - timedelta(minutes=30)
    assert len(tick(s, soon, d, SYSTEM)) == 1
    new = due + timedelta(days=1)
    assert not reschedule(s, t.id, new, "", COORD, soon)
    assert reschedule(s, t.id, new, "extension granted", COORD, soon + timedelta(seconds=1))
    assert current_due(s, t.id) == new and not reschedule(
        s, t.id, new, "again", COORD, soon + timedelta(seconds=2)
    )
    assert tick(s, soon + timedelta(seconds=3), d, SYSTEM) == []
    assert len(tick(s, new - timedelta(minutes=30), d, SYSTEM)) == 1


def test_closed_tasks_are_not_scheduled_or_escalated() -> None:
    s, (t,) = world()
    task = claim(t, "bob", LATER, 900)
    req = ActionRequest(
        action=Action.REJECT,
        task_id=task.id,
        base_version=s.review.version("obl-0"),
        actor=BOB,
        at=LATER + timedelta(seconds=1),
        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE),
    )
    apply(s.review, task, req, ReviewConfig(), {OWNER: TEXT})
    assert tick(s, LATER + timedelta(days=30), Dir(("amy", True)), SYSTEM) == []
    assert current_due(s, t.id) is None


def test_backoff_is_deterministic_capped_and_exhausts() -> None:
    cfg = ScheduleConfig(backoff_base_seconds=10, backoff_cap_seconds=100, max_attempts=4)
    assert [backoff(n, cfg).total_seconds() for n in range(6)] == [10, 20, 40, 80, 100, 100]
    assert next_attempt_at(LATER, 0, cfg) == LATER + timedelta(seconds=10)
    assert next_attempt_at(LATER, 2, cfg) == LATER + timedelta(seconds=40)
    assert next_attempt_at(LATER, 3, cfg) is None


@pytest.mark.parametrize("store_cls", [InMemoryWorkflowStore, IntentWorkflowStore])
@pytest.mark.parametrize("seed", range(15))
def test_random_ticks_and_assignments_stay_idempotent_and_consistent(store_cls, seed) -> None:  # type: ignore[no-untyped-def]
    rng = random.Random(seed)
    s, tasks = world(3, store_cls)
    now = LATER
    for _ in range(20):
        d = Dir(*[(n, rng.random() < 0.7) for n in ("amy", "bob", "cat")])
        now += timedelta(minutes=rng.choice((1, 30, 600)))
        first = tick(s, now, d, SYSTEM)
        before = {t.id: s.ledger(task_stream(t.id)) for t in tasks}
        assert tick(s, now, d, SYSTEM) == []
        assert {t.id: s.ledger(task_stream(t.id)) for t in tasks} == before
        if rng.random() < 0.3:
            who = rng.choice(["amy", "bob", "cat"])
            assign(s, rng.choice(tasks).id, COORD, now, d, to=who, reason="r")
        assert s.verify() and s.violations() == [] and len(first) <= 3
    for t in tasks:
        a = current_assignment(s, t.id)
        assert a.assignee is not None or a.unassigned_reason == "NO_REVIEWER_AVAILABLE"
