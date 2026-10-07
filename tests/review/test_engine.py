from datetime import timedelta

import pytest
from rv_engine_helpers import ALICE, BOB, CAROL, DAVE, TEXT, World, change, evidence, impact
from rv_helpers import NOW

from regulus.domain import ObligationStatus as S
from regulus.obligations.models import ImpactKind
from regulus.review import (
    Action as A,
)
from regulus.review import (
    ActionRequest,
    Actor,
    ClaimError,
    Disposition,
    MatchDisposition,
    OpenQuestionResolution,
    RejectCode,
    RejectReason,
    Resolution,
    Role,
    TaskStatus,
    apply,
    claim,
    obligation_version,
    replay,
    verify_chain,
)
from regulus.review import (
    Status as R,
)
from regulus.similarity import Label

QD = "deadline:undelimited trigger"


def approve(w: World, actor=BOB, **kw):  # type: ignore[no-untyped-def]
    return w.do(actor, A.APPROVE, **kw)


def durable_ok(w: World) -> None:
    ob, log = w.store.get("obl-1")
    assert verify_chain(log) and replay(make_ob(), log) == ob


def make_ob():  # type: ignore[no-untyped-def]
    from rv_helpers import make_obligation

    return make_obligation()


def test_approve_when_every_gate_is_satisfied() -> None:
    w = World()
    out = approve(w)
    assert out.status is R.APPLIED and out.obligation.status is S.APPROVED and len(out.records) == 1  # type: ignore[union-attr]
    rec = out.records[0]
    assert (
        rec.actor_id == "bob"
        and rec.decision.reviewer == "bob"
        and rec.snapshot_hash == w.task.snapshot.hash
    )
    assert w.task.status is TaskStatus.DONE
    durable_ok(w)


def test_approval_needs_verified_evidence() -> None:
    assert approve(World(with_evidence=False)).status is R.EVIDENCE_INVALID
    w = World()
    w.texts = {"R:1": "teks yang sudah berubah sama sekali dan tidak memuat kutipan"}
    assert approve(w).status is R.EVIDENCE_INVALID
    w2 = World()
    w2.texts = {}
    assert approve(w2).status is R.EVIDENCE_INVALID
    assert w2.store.get("obl-1")[1] == ()


def test_open_questions_block_approval_until_resolved() -> None:
    w = World(questions=(QD,))
    out = approve(w)
    assert out.status is R.INCOMPLETE_REVIEW and out.reasons == (f"OPEN_QUESTION:{QD}",)
    assert w.store.get("obl-1")[1] == ()
    res = OpenQuestionResolution(
        question=QD, resolution=Resolution.ACCEPTED_AS_IS, note="no deadline in source"
    )
    done = approve(w, resolutions=(res,))
    assert done.status is R.APPLIED and done.records[0].open_question_resolutions == (res,)


@pytest.mark.parametrize("label", [Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY])
def test_dangerous_matches_need_a_disposition(label: Label) -> None:
    w = World(labels=(label,))
    out = approve(w)
    assert out.status is R.INCOMPLETE_REVIEW and out.reasons == ("DISPOSITION:m0",)
    disp = MatchDisposition(match_id="m0", disposition=Disposition.NOT_A_DUPLICATE)
    assert approve(w, dispositions=(disp,)).status is R.APPLIED


def test_related_matches_may_stay_unreviewed() -> None:
    assert (
        approve(World(labels=(Label.RELATED, Label.SIMILAR_TEXT_ONLY, Label.VARIANT))).status
        is R.APPLIED
    )


def test_incomplete_and_changed_source_need_acknowledgement() -> None:
    w = World(complete=False)
    assert approve(w).reasons == ("ACKNOWLEDGE:SOURCE_INCOMPLETE",)
    assert approve(w, acknowledged_flags=("SOURCE_INCOMPLETE",)).status is R.APPLIED
    w2 = World(impacts=(impact(ImpactKind.MODIFIED),))
    assert approve(w2).reasons == ("ACKNOWLEDGE:SOURCE_CHANGED",)
    assert approve(w2, acknowledged_flags=("SOURCE_CHANGED",)).status is R.APPLIED


def test_withdrawn_source_is_never_approvable_or_publishable_by_acknowledgement() -> None:
    w = World(impacts=(impact(ImpactKind.WITHDRAWN),))
    out = approve(w, acknowledged_flags=("SOURCE_WITHDRAWN", "SOURCE_CHANGED", "SOURCE_INCOMPLETE"))
    assert out.status is R.INCOMPLETE_REVIEW and out.reasons == ("SOURCE_WITHDRAWN",)
    rej = w.do(BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))
    assert rej.status is R.APPLIED and rej.obligation.status is S.REJECTED  # type: ignore[union-attr]
    durable_ok(w)


def test_publish_is_blocked_while_the_source_is_withdrawn() -> None:
    w = World()
    approve(w)
    from regulus.review import build_snapshot, refresh

    ob, _ = w.store.get("obl-1")
    snap = build_snapshot(
        ob, [evidence()], (), True, None, (impact(ImpactKind.WITHDRAWN),), TEXT, w.task.snapshot
    )
    w.task = refresh(w.task, snap)
    out = w.do(CAROL, A.PUBLISH)
    assert out.status is R.INCOMPLETE_REVIEW and out.reasons == ("SOURCE_WITHDRAWN",)


def test_reject_with_each_closed_reason() -> None:
    for code in (
        RejectCode.NOT_AN_OBLIGATION,
        RejectCode.INCORRECT_EXTRACTION,
        RejectCode.OUT_OF_SCOPE,
        RejectCode.SOURCE_UNCLEAR,
    ):
        w = World()
        out = w.do(BOB, A.REJECT, reject_reason=RejectReason(code=code))
        assert out.status is R.APPLIED and out.records[0].reject_reason.code is code  # type: ignore[union-attr]
        assert out.records[0].decision.reason == code.value
    other = World().do(BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.OTHER, text="why"))
    assert other.status is R.APPLIED
    with pytest.raises(ValueError):
        RejectReason(code=RejectCode.OTHER)
    assert World().do(BOB, A.REJECT).status is R.INCOMPLETE_REVIEW


def test_duplicate_of_must_name_a_snapshot_match_and_links_without_merging() -> None:
    w = World(labels=(Label.POSSIBLE_DUPLICATE,))
    bad = w.do(
        BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.DUPLICATE_OF, match_id="nope")
    )
    assert bad.status is R.INCOMPLETE_REVIEW and bad.reasons == ("DUPLICATE_OF_NOT_IN_SNAPSHOT",)
    ok = w.do(
        BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.DUPLICATE_OF, match_id="m0")
    )
    assert ok.status is R.APPLIED and ok.records[0].reject_reason.match_id == "m0"  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        RejectReason(code=RejectCode.DUPLICATE_OF)


def test_edit_is_two_decisions_in_one_atomic_commit() -> None:
    w = World()
    out = w.do(
        ALICE,
        A.EDIT,
        reason="add deadline",
        changes=(change("deadline", None, "paling lambat 3 hari"),),
    )
    assert out.status is R.APPLIED and len(out.records) == 2
    d1, d2 = (r.decision for r in out.records)
    assert (d1.from_status, d1.to_status, d2.from_status, d2.to_status) == (
        S.PENDING_REVIEW,
        S.EDITED,
        S.EDITED,
        S.PENDING_REVIEW,
    )
    assert out.records[1].prev_hash == out.records[0].hash
    ob = w.store.get("obl-1")[0]
    assert (
        ob.status is S.PENDING_REVIEW
        and ob.current.deadline == "paling lambat 3 hari"
        and ob.generated.content.deadline is None
    )
    assert w.task.status is TaskStatus.OPEN and w.task.claimed_by is None
    durable_ok(w)


def test_editor_cannot_approve_own_edit_but_a_second_reviewer_can() -> None:
    w = World()
    w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "paling lambat 3 hari"),))
    own = w.do(ALICE, A.APPROVE)
    assert own.status is R.DENIED and own.reasons == ("FOUR_EYES",)
    assert w.do(BOB, A.APPROVE).status is R.APPLIED


def test_approver_cannot_publish_but_a_publisher_can() -> None:
    both = Actor(id="bob", roles=(Role.REVIEWER, Role.PUBLISHER))
    w = World()
    w.do(BOB, A.APPROVE)
    assert w.do(both, A.PUBLISH).reasons == ("FOUR_EYES",)
    out = w.do(CAROL, A.PUBLISH)
    assert out.status is R.APPLIED and out.obligation.status is S.PUBLISHED  # type: ignore[union-attr]
    durable_ok(w)


def test_edit_validation_and_stale_edit_leave_nothing_recorded() -> None:
    w = World()
    stale = w.do(ALICE, A.EDIT, reason="r", changes=(change("actor", "Lain", "Y"),))
    assert stale.status is R.INVALID_TRANSITION and w.store.get("obl-1")[1] == ()
    empty = w.do(ALICE, A.EDIT, reason="r", changes=(change("text", TEXT, None),))
    assert empty.status is R.INVALID_TRANSITION and w.store.get("obl-1")[1] == ()
    assert (
        w.do(ALICE, A.EDIT, reason=None, changes=(change("deadline", None, "x"),)).status
        is R.INCOMPLETE_REVIEW
    )
    assert w.do(ALICE, A.EDIT, reason="r").status is R.INCOMPLETE_REVIEW
    durable_ok(w)


def test_edit_adding_new_words_is_applied_and_divergence_is_recorded() -> None:
    w = World()
    out = w.do(
        ALICE,
        A.EDIT,
        reason="clarify",
        changes=(change("text", TEXT, TEXT + " sesuai kebijakan baru"),),
    )
    assert out.status is R.APPLIED and out.records[0].divergence == ("sesuai", "kebijakan", "baru")
    same = World().do(
        ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "paling lambat 3 hari"),)
    )
    assert same.records[0].divergence == ()


def test_resolved_by_edit_is_derived_from_the_history_even_after_the_snapshot_is_rebuilt() -> None:
    from regulus.review import build_snapshot, refresh

    w = World(questions=("deadline:undelimited trigger",))
    w.do(
        ALICE, A.EDIT, reason="set it", changes=(change("deadline", None, "paling lambat 3 hari"),)
    )
    ob, _ = w.store.get("obl-1")
    rebuilt = build_snapshot(ob, [evidence()], (), True, None, (), TEXT, w.task.snapshot)
    assert rebuilt.open_questions == () and rebuilt.carried_questions == (
        "deadline:undelimited trigger",
    )
    w.task = refresh(w.task, rebuilt)
    assert w.do(BOB, A.APPROVE).status is R.APPLIED


def test_an_edit_that_does_not_set_the_named_field_does_not_erase_the_question() -> None:
    from regulus.review import build_snapshot, refresh

    w = World(questions=("actor:comma inside the actor phrase",))
    w.do(
        ALICE,
        A.EDIT,
        reason="other field",
        changes=(change("deadline", None, "paling lambat 3 hari"),),
    )
    ob, _ = w.store.get("obl-1")
    w.task = refresh(
        w.task, build_snapshot(ob, [evidence()], (), True, None, (), TEXT, w.task.snapshot)
    )
    out = w.do(BOB, A.APPROVE)
    assert out.status is R.INCOMPLETE_REVIEW and out.reasons == (
        "OPEN_QUESTION:actor:comma inside the actor phrase",
    )
    cleared = w.do(
        BOB, A.EDIT, reason="set actor", changes=(change("actor", "Pengendali", "Pengendali Data"),)
    )
    assert cleared.status is R.APPLIED


def test_disposition_carries_forward_while_the_match_label_is_unchanged() -> None:
    from regulus.review import build_snapshot, refresh

    w = World(labels=(Label.POSSIBLE_DUPLICATE,))
    disp = MatchDisposition(match_id="m0", disposition=Disposition.NOT_A_DUPLICATE)
    w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "x"),), dispositions=(disp,))
    ob, _ = w.store.get("obl-1")
    from rv_engine_helpers import similarity

    w.task = refresh(
        w.task,
        build_snapshot(
            ob,
            [evidence()],
            (),
            True,
            similarity(Label.POSSIBLE_DUPLICATE),
            (),
            TEXT,
            w.task.snapshot,
        ),
    )
    out = w.do(BOB, A.APPROVE)
    assert (
        out.status is R.INCOMPLETE_REVIEW
    )  # the edit record did not carry a disposition for the new snapshot


def test_stale_actions_are_never_applied() -> None:
    w = World()
    w.claim(BOB)
    req = w.req(BOB, A.APPROVE)
    w.store.commit  # noqa: B018
    other = World.__new__(World)
    del other
    first = w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "x"),))
    assert first.status is R.APPLIED
    w.task = w.task.model_copy(
        update={
            "status": TaskStatus.CLAIMED,
            "claimed_by": "bob",
            "claim_expires_at": NOW + timedelta(hours=1),
        }
    )
    out = apply(w.store, w.task, req, texts_cfg(), w.texts)
    assert out.status is R.STALE
    assert w.store.get("obl-1")[1] and len(w.store.get("obl-1")[1]) == 2


def texts_cfg():  # type: ignore[no-untyped-def]
    from regulus.review import ReviewConfig

    return ReviewConfig()


def test_claims_are_exclusive_expire_and_are_required() -> None:
    w = World()
    t = claim(w.task, "alice", NOW, 60)
    with pytest.raises(ClaimError):
        claim(t, "bob", NOW + timedelta(seconds=30), 60)
    again = claim(t, "bob", NOW + timedelta(seconds=61), 60)
    assert again.claimed_by == "bob"
    no_claim = apply(w.store, w.task, w.req(BOB, A.APPROVE), texts_cfg(), w.texts)
    assert no_claim.status is R.DENIED and no_claim.reasons == ("NO_CLAIM",)
    w.task = t
    expired = ActionRequest(
        action=A.APPROVE,
        task_id=w.task.id,
        base_version=w.store.version("obl-1"),
        actor=ALICE,
        at=NOW + timedelta(seconds=120),
    )
    assert apply(w.store, w.task, expired, texts_cfg(), w.texts).reasons == ("NO_CLAIM",)
    wrong_holder = apply(w.store, w.task, w.req(BOB, A.APPROVE), texts_cfg(), w.texts)
    assert wrong_holder.reasons == ("NO_CLAIM",)


def test_roles_and_task_mismatch_are_denied_without_effect() -> None:
    w = World()
    assert w.do(DAVE, A.APPROVE).reasons == ("ROLE",)
    assert w.do(CAROL, A.APPROVE).reasons == ("ROLE",)
    assert w.do(BOB, A.PUBLISH).reasons == ("ROLE",)
    req = w.req(BOB, A.APPROVE).model_copy(update={"task_id": "task-other"})
    assert apply(w.store, w.task, req, texts_cfg(), w.texts).reasons == ("TASK_MISMATCH",)
    assert w.store.get("obl-1")[1] == () and w.store.get("obl-1")[0] == w.ob


def test_invalid_transitions_come_from_phase_1() -> None:
    w = World()
    assert w.do(CAROL, A.PUBLISH).status is R.INVALID_TRANSITION
    approve(w)
    w.task = w.task.model_copy(update={"status": TaskStatus.OPEN})
    again = w.do(ALICE, A.APPROVE)
    assert again.status is R.INVALID_TRANSITION
    w2 = World()
    w2.do(BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))
    assert w2.do(ALICE, A.APPROVE).status is R.INVALID_TRANSITION
    durable_ok(w)
    durable_ok(w2)


def test_store_failure_is_not_recorded_and_state_stays_replay_equal() -> None:
    w = World()
    w.store.fail_next = 1
    out = w.do(BOB, A.APPROVE)
    assert out.status is R.NOT_RECORDED
    assert w.store.get("obl-1") == (w.ob, ()) and w.store.version("obl-1") == obligation_version(
        w.ob, 0
    )
    assert w.do(BOB, A.APPROVE).status is R.APPLIED
    durable_ok(w)


def test_failure_between_the_two_decisions_of_an_edit_records_neither() -> None:
    w = World()
    w.store.fail_next = 1
    out = w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "x"),))
    assert out.status is R.NOT_RECORDED and w.store.get("obl-1") == (w.ob, ())


def test_same_inputs_give_byte_identical_records() -> None:
    def run() -> str:
        w = World(questions=(QD,))
        res = OpenQuestionResolution(question=QD, resolution=Resolution.NOT_APPLICABLE)
        return w.do(BOB, A.APPROVE, resolutions=(res,)).model_dump_json()

    assert run() == run()


def test_the_record_names_exactly_the_acting_actor() -> None:
    w = World()
    out = approve(w)
    assert out.records[0].actor_id == out.records[0].decision.reviewer == "bob"
    assert out.records[0].actor_roles == (Role.REVIEWER,)
