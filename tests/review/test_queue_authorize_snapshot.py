from datetime import timedelta

import pytest
from rv_engine_helpers import (
    ALICE,
    BOB,
    CAROL,
    DAVE,
    TEXT,
    World,
    change,
    evidence,
    impact,
    similarity,
)
from rv_helpers import NOW, make_obligation, record

from regulus.domain import ObligationStatus as S
from regulus.obligations.models import ImpactKind
from regulus.review import (
    Action,
    ClaimError,
    ReviewConfig,
    TaskStatus,
    authorize,
    build_snapshot,
    claim,
    new_task,
    ordered,
    priority_key,
    refresh,
    release_if_expired,
)
from regulus.review.snapshot import snapshot_hash
from regulus.similarity import Label

CFG = ReviewConfig()


def task(**kw):  # type: ignore[no-untyped-def]
    return World(**kw).task


def test_roles_decide_who_may_attempt_what() -> None:
    allowed = {
        (a.id, act): authorize(a, act, [], CFG).allowed
        for a in (ALICE, CAROL, DAVE)
        for act in Action
    }
    assert (
        allowed[("alice", Action.APPROVE)]
        and allowed[("alice", Action.EDIT)]
        and allowed[("alice", Action.REJECT)]
    )
    assert not allowed[("alice", Action.PUBLISH)] and allowed[("carol", Action.PUBLISH)]
    assert not any(allowed[("dave", a)] for a in Action) and not allowed[("carol", Action.APPROVE)]


def test_four_eyes_can_be_disabled_by_configuration_only() -> None:
    log = [
        record(
            [],
            "obl-1",
            S.PENDING_REVIEW,
            S.EDITED,
            actor="alice",
            reason="r",
            changes=(change("deadline", None, "x"),),
        )
    ]
    assert authorize(ALICE, Action.APPROVE, log, CFG).reason == "FOUR_EYES"
    assert authorize(ALICE, Action.APPROVE, log, ReviewConfig(four_eyes=False)).allowed
    assert authorize(DAVE, Action.APPROVE, log, ReviewConfig(four_eyes=False)).reason == "ROLE"


def test_snapshot_hash_is_deterministic_and_covers_its_inputs() -> None:
    ob = make_obligation()
    a = build_snapshot(ob, [evidence()], ("q",), True, similarity(Label.RELATED), (), TEXT)
    assert a == build_snapshot(ob, [evidence()], ("q",), True, similarity(Label.RELATED), (), TEXT)
    assert a.hash == snapshot_hash(a)
    for other in (
        build_snapshot(ob, [], ("q",), True, similarity(Label.RELATED), (), TEXT),
        build_snapshot(ob, [evidence()], (), True, similarity(Label.RELATED), (), TEXT),
        build_snapshot(ob, [evidence()], ("q",), False, similarity(Label.RELATED), (), TEXT),
        build_snapshot(
            ob, [evidence()], ("q",), True, similarity(Label.POSSIBLE_DUPLICATE), (), TEXT
        ),
        build_snapshot(ob, [evidence()], ("q",), True, None, (), TEXT),
    ):
        assert other.hash != a.hash


def test_source_flags_follow_completeness_and_impact_kind() -> None:
    ob = make_obligation()

    def flags(c: bool, *k: ImpactKind) -> tuple[str, ...]:
        return build_snapshot(ob, [], (), c, None, tuple(impact(x) for x in k)).source_flags

    assert flags(True) == ()
    assert flags(False) == ("SOURCE_INCOMPLETE",)
    assert flags(True, ImpactKind.MODIFIED) == ("SOURCE_CHANGED",)
    assert "SOURCE_WITHDRAWN" in flags(True, ImpactKind.WITHDRAWN)


def test_a_new_snapshot_carries_outstanding_questions_forward_once() -> None:
    ob = make_obligation()
    first = build_snapshot(ob, [], ("q1", "q2"), True, None)
    second = build_snapshot(ob, [], ("q2",), True, None, previous=first)
    assert second.open_questions == ("q2",) and second.carried_questions == ("q1",)
    third = build_snapshot(ob, [], (), True, None, previous=second)
    assert third.carried_questions == ("q2", "q1") or set(third.carried_questions) == {"q1", "q2"}


def test_a_task_needs_a_pending_review_obligation() -> None:
    snap = build_snapshot(make_obligation(status=S.APPROVED), [], (), True, None)
    with pytest.raises(ValueError):
        new_task(snap, NOW)


def test_claims_expire_and_closed_tasks_cannot_be_claimed() -> None:
    t = task()
    held = claim(t, "alice", NOW, 60)
    assert release_if_expired(held, NOW + timedelta(seconds=59)).status is TaskStatus.CLAIMED
    assert release_if_expired(held, NOW + timedelta(seconds=60)).status is TaskStatus.OPEN
    for status in (TaskStatus.DONE, TaskStatus.SUPERSEDED):
        with pytest.raises(ClaimError):
            claim(t.model_copy(update={"status": status}), "bob", NOW, 60)
    assert (
        refresh(held, held.snapshot).status is TaskStatus.OPEN
        and len(refresh(held, held.snapshot).snapshots) == 2
    )


def test_queue_orders_by_risk_then_age_then_id_and_ties_are_stable() -> None:
    contra = task(labels=(Label.CONTRADICTORY_MODALITY,))
    dup = task(labels=(Label.POSSIBLE_DUPLICATE,))
    degraded = task(complete=False)
    many = task(questions=("a:x", "b:y"))
    plain = task()
    done = plain.model_copy(update={"id": "task-done", "status": TaskStatus.DONE})
    pool = [plain, many, degraded, dup, contra, done]
    out = ordered(pool)
    assert out == [contra, dup, degraded, many, plain] and done not in out
    assert ordered(list(reversed(pool))) == out
    older = plain.model_copy(
        update={"id": "task-a", "created_at": plain.created_at - timedelta(days=1)}
    )
    twin = plain.model_copy(update={"id": "task-b"})
    assert ordered([twin, plain, older])[0] == older
    assert [t.id for t in ordered([twin, plain.model_copy(update={"id": "task-a"})])] == [
        "task-a",
        "task-b",
    ]
    assert priority_key(contra) < priority_key(plain)
    assert BOB


def candidate():  # type: ignore[no-untyped-def]
    from regulus.obligations.models import (
        ChangeRef,
        Citation,
        FieldState,
        FieldStatus,
        FieldValue,
        Modality,
        ObligationCandidate,
    )

    def val(a: int, b: int) -> FieldValue:
        return FieldValue(
            value=TEXT[a:b], citation=Citation(owner_id="R:1", start=a, end=b, quote=TEXT[a:b])
        )

    action = val(TEXT.index("menyimpan"), TEXT.index("menyimpan") + 9)
    return ObligationCandidate(
        id="c1",
        change_ref=ChangeRef(regulation_id="R", article_number="1", owner_id="R:1"),
        clause=Citation(owner_id="R:1", start=0, end=len(TEXT), quote=TEXT),
        modality=Modality.OBLIGATION,
        marker=val(TEXT.index("wajib"), TEXT.index("wajib") + 5),
        actor=FieldState(status=FieldStatus.NOT_STATED),
        action=FieldState(status=FieldStatus.PRESENT, value=action),
        object=FieldState(status=FieldStatus.NOT_STATED),
        deadline=FieldState(status=FieldStatus.NOT_STATED),
        frequency=FieldState(status=FieldStatus.NOT_STATED),
        extractor="rules",
    )


def test_the_candidate_is_display_data_covered_by_the_snapshot_hash() -> None:
    ob = make_obligation()
    plain = build_snapshot(ob, [evidence()], (), True, None)
    with_c = build_snapshot(ob, [evidence()], (), True, None, candidate=candidate())
    assert plain.candidate is None and with_c.candidate == candidate()
    assert with_c.hash == snapshot_hash(with_c) and with_c.hash != plain.hash
    other = candidate().model_copy(update={"extractor": "other"})
    assert build_snapshot(ob, [evidence()], (), True, None, candidate=other).hash != with_c.hash


def test_a_candidate_never_changes_a_review_verdict() -> None:
    w1, w2 = World(), World()
    w2.task = new_task(
        build_snapshot(
            w2.ob, [evidence()], (), True, None, permitted_source=TEXT, candidate=candidate()
        ),
        NOW,
    )
    w1.claim(BOB)
    w2.claim(BOB)
    assert w1.do(BOB, Action.APPROVE).status is w2.do(BOB, Action.APPROVE).status
