import random
from datetime import timedelta

import pytest
from rv_engine_helpers import ALICE, BOB, OWNER, TEXT
from wf_helpers import LATER, NOW, generated, inputs, similarity, submit_it

from regulus.domain import ObligationStatus as S
from regulus.generation import Status as GS
from regulus.review import Action, ActionRequest, ReviewConfig, Status, apply, claim
from regulus.review import Role as ReviewRole
from regulus.similarity import Label
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Phase,
    Principal,
    SubmitStatus,
    WorkflowRole,
    obligation_stream,
    submit_for_review,
)
from regulus.workflow.store import STEPS

STORES = [InMemoryWorkflowStore, IntentWorkflowStore]
OID = "obl-1"


def kinds(s) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.kind.value for r in s.ledger(obligation_stream(OID))]


def logical(s):  # type: ignore[no-untyped-def]
    st = s.submission(OID)
    ob = s.review.get(OID)[0] if s.registered(OID) else None
    return (
        st.phase,
        st.key,
        ob.model_dump_json() if ob else None,
        s.task(st.task_id).model_dump_json() if st.task_id and s.task(st.task_id) else None,
        [k for k in kinds(s) if k not in ("SUBMIT_FAILED",)],
        sorted(s.tasks),
    )


@pytest.mark.parametrize("store_cls", STORES)
def test_a_valid_result_becomes_one_pending_review_obligation_and_one_task(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    out = submit_it(s)
    assert out.status is SubmitStatus.SUBMITTED and out.task is not None
    ob, log = s.review.get(OID)
    assert ob.status is S.PENDING_REVIEW and log == () and ob.generated.content == ob.current
    assert (
        out.task.snapshot.obligation == ob
        and out.task.status.value == "OPEN"
        and len(out.task.snapshot.evidence) == 1
    )
    assert kinds(s) == ["SUBMISSION_INTENT", "SUBMITTED"] and s.verify() and s.violations() == []
    assert list(s.tasks) == [out.task.id] and out.task.created_at == LATER


@pytest.mark.parametrize("store_cls", STORES)
def test_the_submitted_task_is_reviewable_by_phase_9_unchanged(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    out = submit_it(s)
    task = claim(out.task, "bob", LATER, 900)  # type: ignore[arg-type]
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=task.id,
        base_version=s.review.version(OID),
        actor=BOB,
        at=LATER + timedelta(seconds=1),
        resolutions=(),
    )
    res = apply(s.review, task, req, ReviewConfig(), {OWNER: TEXT})
    assert res.status is Status.INCOMPLETE_REVIEW and res.reasons == ("OPEN_QUESTION:deadline:x",)
    assert ReviewRole.REVIEWER in BOB.roles and ALICE


@pytest.mark.parametrize("store_cls", STORES)
def test_submitting_twice_is_idempotent(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    first = submit_it(s)
    before = (s.ledger(obligation_stream(OID)), dict(s.tasks))
    again = submit_it(s, at=LATER + timedelta(hours=1))
    assert again.status is SubmitStatus.ALREADY_SUBMITTED and again.task == first.task
    assert (s.ledger(obligation_stream(OID)), dict(s.tasks)) == before
    assert s.review.get(OID)[0].status is S.PENDING_REVIEW


@pytest.mark.parametrize("store_cls", STORES)
def test_same_id_with_different_content_is_a_conflict_and_changes_nothing(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    first = submit_it(s)
    out = submit_it(s, generated(deadline="paling lambat 3 hari"))
    assert out.status is SubmitStatus.CONFLICT and out.task is None
    assert s.task(first.task.id) == first.task and s.review.get(OID)[0].current.deadline is None  # type: ignore[union-attr]
    assert kinds(s) == ["SUBMISSION_INTENT", "SUBMITTED", "SUBMIT_REFUSED"] and list(s.tasks) == [
        first.task.id
    ]  # type: ignore[union-attr]


@pytest.mark.parametrize("store_cls", STORES)
def test_an_obligation_registered_elsewhere_is_a_conflict(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    s.review.register(generated().obligation.model_copy(update={"status": S.PENDING_REVIEW}))  # type: ignore[union-attr]
    out = submit_it(s)
    assert (
        out.status is SubmitStatus.CONFLICT
        and out.reasons == ("REGISTERED_ELSEWHERE",)
        and s.tasks == {}
    )


@pytest.mark.parametrize("store_cls", STORES)
def test_non_generated_inputs_are_refused_without_effects(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    assert submit_it(s, generated(status=GS.NOT_GENERABLE)).status is SubmitStatus.NOT_GENERATED
    reviewed = generated()
    reviewed = reviewed.model_copy(
        update={"obligation": reviewed.obligation.model_copy(update={"status": S.APPROVED})}
    )  # type: ignore[union-attr]
    assert submit_it(s, reviewed).status is SubmitStatus.NOT_SUBMITTABLE
    assert s.tasks == {} and not s.registered(OID) and s.ledger(obligation_stream(OID)) == ()


@pytest.mark.parametrize("store_cls", STORES)
def test_evidence_that_no_longer_verifies_is_refused_and_recorded(store_cls) -> None:  # type: ignore[no-untyped-def]
    for texts in ({OWNER: "teks yang berubah sama sekali tanpa kutipan"}, {}):
        s = store_cls()
        out = submit_it(s, texts=texts)
        assert out.status is SubmitStatus.EVIDENCE_INVALID
        assert s.tasks == {} and not s.registered(OID) and kinds(s) == ["SUBMIT_REFUSED"]
    s = store_cls()
    no_trace = generated().model_copy(update={"trace": None})
    assert submit_it(s, no_trace).status is SubmitStatus.EVIDENCE_INVALID
    none = generated().model_copy(update={"evidence": ()})
    assert submit_it(s, none).status is SubmitStatus.EVIDENCE_INVALID and s.tasks == {}


@pytest.mark.parametrize("store_cls", STORES)
def test_only_system_or_operator_may_submit(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    for p in (Principal(id="c", roles=(WorkflowRole.COORDINATOR,)), Principal(id="x")):
        out = submit_for_review(s, generated(), inputs(), p, LATER, {OWNER: TEXT})
        assert out.status is SubmitStatus.DENIED
    op = Principal(id="o", roles=(WorkflowRole.OPERATOR,))
    assert (
        submit_for_review(s, generated(), inputs(), op, LATER, {OWNER: TEXT}).status
        is SubmitStatus.SUBMITTED
    )


@pytest.mark.parametrize("store_cls", STORES)
def test_a_failed_transaction_makes_no_submission_effect_durable_and_retry_succeeds_once(
    store_cls,
) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    s.fail_store = 1
    out = submit_it(s)
    assert out.status is SubmitStatus.FAILED and not s.registered(OID) and s.tasks == {}
    assert kinds(s) == ["SUBMIT_FAILED"]
    s2 = store_cls()
    s2.fail_store = 2
    assert submit_it(s2).status is SubmitStatus.FAILED
    assert s2.ledger(obligation_stream(OID)) == () and s2.tasks == {} and not s2.registered(OID)
    assert submit_it(s).status is SubmitStatus.SUBMITTED and len(s.tasks) == 1
    assert submit_it(s).status is SubmitStatus.ALREADY_SUBMITTED and len(s.tasks) == 1


@pytest.mark.parametrize("step", STEPS)
@pytest.mark.parametrize("store_cls", STORES)
def test_a_crash_after_every_step_recovers_to_the_uninterrupted_logical_state(
    store_cls, step
) -> None:  # type: ignore[no-untyped-def]
    clean = store_cls()
    submit_it(clean)
    s = store_cls()
    s.fail_after = step
    with pytest.raises(Crash):
        submit_it(s)
    assert s.violations() == [] and s.verify()
    if s.registered(OID):
        assert any(t.obligation_id == OID for t in s.tasks.values())
    out = submit_it(s)
    assert out.status in (SubmitStatus.SUBMITTED, SubmitStatus.ALREADY_SUBMITTED)
    assert out.status is not SubmitStatus.NOT_SUBMITTABLE
    assert s.submission(OID).phase is Phase.COMPLETE and s.violations() == []
    a, b = logical(s), logical(clean)
    assert a == b
    assert len(s.tasks) == 1 and s.verify()


@pytest.mark.parametrize("step", ("intent", "task", "obligation"))
def test_recovery_completes_from_the_intent_payload_not_live_data(step) -> None:  # type: ignore[no-untyped-def]
    s = IntentWorkflowStore()
    s.fail_after = step
    with pytest.raises(Crash):
        submit_it(s)
    original = s.submission(OID).prepared
    assert original is not None
    out = submit_it(
        s,
        at=LATER + timedelta(hours=2),
        similarity=similarity(Label.POSSIBLE_DUPLICATE),
        source_complete=False,
    )
    assert out.status is SubmitStatus.SUBMITTED and out.task == original.task
    assert (
        s.task(original.task.id).snapshot.similarity is None
        and s.task(original.task.id).snapshot.source_complete
    )  # type: ignore[union-attr]


@pytest.mark.parametrize("store_cls", STORES)
def test_a_second_crash_during_completion_still_converges(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    s.fail_after = "task"
    with pytest.raises(Crash):
        submit_it(s)
    s.fail_after = "obligation"
    with pytest.raises(Crash):
        submit_it(s, at=LATER + timedelta(seconds=1))
    assert s.violations() == []
    assert submit_it(s, at=LATER + timedelta(seconds=2)).status in (
        SubmitStatus.SUBMITTED,
        SubmitStatus.ALREADY_SUBMITTED,
    )
    assert (
        s.submission(OID).phase is Phase.COMPLETE
        and len(s.tasks) == 1
        and kinds(s)[-1] == "SUBMITTED"
    )


def test_the_transactional_store_never_exposes_a_partial_submission() -> None:
    for step in STEPS:
        s = InMemoryWorkflowStore()
        s.fail_after = step
        with pytest.raises(Crash):
            submit_it(s)
        assert not s.registered(OID) and s.tasks == {} and s.ledger(obligation_stream(OID)) == ()


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize("store_cls", STORES)
def test_random_submit_crash_retry_sequences_keep_the_invariants(store_cls, seed) -> None:  # type: ignore[no-untyped-def]
    rng = random.Random(seed)
    s = store_cls()
    ids = [f"obl-{i}" for i in range(3)]
    variants = {i: [generated(i), generated(i, deadline="paling lambat 3 hari")] for i in ids}
    wanted: dict[str, int] = {}
    now = LATER
    for _ in range(25):
        oid = rng.choice(ids)
        v = rng.randrange(2)
        s.fail_after = rng.choice([None, None, *STEPS])
        s.fail_store = 1 if rng.random() < 0.1 else 0
        before_tasks = len(s.tasks)
        try:
            out = submit_for_review(s, variants[oid][v], inputs(), SYSTEM, now, {OWNER: TEXT})
            if out.status is SubmitStatus.SUBMITTED:
                wanted.setdefault(oid, v)
        except Crash:
            pass
        s.fail_after, s.fail_store = None, 0
        now += timedelta(seconds=1)
        assert s.violations() == [] and s.verify()
        assert len(s.tasks) >= before_tasks and len(s.tasks) <= len(ids)
    for oid in ids:
        for v in range(2):
            submit_for_review(s, variants[oid][v], inputs(), SYSTEM, now, {OWNER: TEXT})
        st = s.submission(oid)
        assert st.phase is Phase.COMPLETE
        assert sum(t.obligation_id == oid for t in s.tasks.values()) == 1
        assert s.review.get(oid)[0].status is S.PENDING_REVIEW
    assert s.violations() == [] and s.verify() and NOW
