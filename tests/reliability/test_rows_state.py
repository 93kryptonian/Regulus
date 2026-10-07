import random
from pathlib import Path

import pytest
from rel_helpers import (
    CFG,
    NOW,
    RUN,
    STORES,
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

from regulus.documents import DocStatus, process
from regulus.documents.evaluate import GoldCase, GoldPage, reader_for
from regulus.domain import ObligationStatus as S
from regulus.evaluation.harness import ACTORS, ReviewRun, generation_result
from regulus.generation import ExtractiveGenerator, GenerationInput, generate
from regulus.generation import Status as GS
from regulus.generation.evaluate import candidates_for
from regulus.obligations import RulesExtractor
from regulus.obligations.evaluate import evaluate_gold, load_gold
from regulus.reliability.faults import Timeout
from regulus.reliability.invariants import duplicate_decisions, state_safety, unaccounted_items
from regulus.reliability.matrix import covers
from regulus.reliability.wrappers import (
    FaultyDirectory,
    FaultyPipeline,
    FaultyReviewStore,
    FaultyStore,
)
from regulus.review import (
    Action,
    ActionRequest,
    RejectCode,
    RejectReason,
    ReviewConfig,
    Status,
    apply,
    build_snapshot,
    claim,
    new_task,
)
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    Permanent,
    ReviewerInfo,
    SnapshotInputs,
    SubmitStatus,
    assign,
    current_assignment,
    run_state,
    source_complete_for,
    submit_for_review,
)
from regulus.workflow.store import STEPS, ClockRegression

ROOT = Path(__file__).parents[2] / "evaluation"


@covers("R01")
def test_r01_an_unreadable_source_fails_explicitly_and_creates_nothing() -> None:
    doc = process(
        b"x",
        "PP-1-2026",
        reader_for(
            GoldCase(
                case_id="u",
                unreadable=True,
                expected_status=DocStatus.FAILED,
                rationale="unreadable gold case",
            )
        ),
    )
    assert doc.status is DocStatus.FAILED and doc.articles == ()
    s = InMemoryWorkflowStore()
    pipe = FakePipeline(2)

    def dead(event):  # type: ignore[no-untyped-def]
        raise Permanent()

    pipe.process = dead  # type: ignore[method-assign]
    rep = go(s, pipe)
    assert rep.status.value == "DEAD" and s.tasks == {} and state_safety(s) == []
    assert (
        run_state(s, RUN)
        .stage(__import__("regulus.workflow", fromlist=["Stage"]).Stage.PROCESS)
        .error_class
        == "Permanent"
    )


def _doc(*pages: object):  # type: ignore[no-untyped-def]
    case = GoldCase(
        case_id="d",
        pages=tuple(GoldPage(**p) if isinstance(p, dict) else GoldPage(text=str(p)) for p in pages),
        expected_status=DocStatus.PARTIAL,
        rationale="reliability fixture",
    )
    return process(b"d", "PP-1-2026", reader_for(case))


def _approval_needs_ack(complete: bool) -> tuple[str, ...]:
    ob = generation_result("obl-c").obligation
    from regulus.evaluation.harness import evidence

    snap = build_snapshot(
        ob.model_copy(update={"status": S.PENDING_REVIEW}),
        [evidence("obl-c")],
        (),
        complete,
        None,
        permitted_source=TEXT,
    )
    task = claim(new_task(snap, NOW), "r1", NOW, 900)
    s = __import__("regulus.review", fromlist=["InMemoryReviewStore"]).InMemoryReviewStore()
    s.register(ob.model_copy(update={"status": S.PENDING_REVIEW}))
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=task.id,
        base_version=s.version("obl-c"),
        actor=ACTORS[0],
        at=NOW + timedelta(seconds=1),
    )
    out = apply(s, task, req, ReviewConfig(), {OWNER: TEXT})
    return out.reasons


@covers("R02")
def test_r02_a_partial_document_marks_the_snapshot_incomplete_and_approval_needs_acknowledgement() -> (
    None
):
    doc = _doc("BAB I\nPasal 1\nsatu", {"failure": "page broke"})
    assert doc.status is DocStatus.PARTIAL and [a.number for a in doc.articles] == ["1"]
    assert source_complete_for(doc.status.value) is False
    assert _approval_needs_ack(source_complete_for(doc.status.value)) == (
        "ACKNOWLEDGE:SOURCE_INCOMPLETE",
    )
    assert _approval_needs_ack(True) == ()


@covers("R03")
def test_r03_a_document_processed_with_issues_marks_the_snapshot_incomplete() -> None:
    doc = _doc("BAB I\nPasal 1\nsatu\nPasal 3\ntiga")
    assert (
        doc.status is DocStatus.PROCESSED_WITH_ISSUES
        and source_complete_for(doc.status.value) is False
    )
    assert source_complete_for(DocStatus.PROCESSED_OK.value) is True
    assert _approval_needs_ack(False) == ("ACKNOWLEDGE:SOURCE_INCOMPLETE",)
    s = InMemoryWorkflowStore()
    out = submit_for_review(
        s,
        generation_result("obl-i"),
        SnapshotInputs(source_complete=False, permitted_source=TEXT),
        SYSTEM,
        NOW,
        {OWNER: TEXT},
    )
    assert (
        out.task is not None
        and out.task.snapshot.source_complete is False
        and "SOURCE_INCOMPLETE" in out.task.snapshot.source_flags
    )


@covers("R04")
def test_r04_an_extractor_that_yields_nothing_never_loses_a_marker_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RulesExtractor, "extract", lambda self, request: ())
    r = evaluate_gold(load_gold(ROOT / "obligations" / "gold.v1.json"))
    assert r.silent_loss == 0 and r.candidates.tp == 0 and len(r.unresolved_cases) > 0


@covers("R05")
def test_r05_a_failing_generator_yields_no_obligation_and_a_recorded_reason() -> None:
    pairs = candidates_for(load_gold(ROOT / "obligations" / "gold.v1.json"))[:5]

    class Boom:
        id, version = "boom", "1"
        origin = ExtractiveGenerator.origin
        model = prompt_version = None

        def generate(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("generator down")

    for c, doc in pairs:
        out = generate(
            GenerationInput(candidates=(c,), documents={c.change_ref.owner_id.split(":")[0]: doc}),
            Boom(),
        )
        (r,) = out.results
        assert (
            r.status is GS.GENERATOR_FAILED and r.obligation is None and r.reason == "RuntimeError"
        )


@covers("R06")
@pytest.mark.parametrize("store_cls", STORES)
def test_r06_unavailable_similarity_retries_then_dead_letters_and_never_submits_unenriched(
    store_cls,
) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    pipe = FaultyPipeline(
        FakePipeline(2),
        FaultPlan(
            [
                __import__("regulus.reliability.faults", fromlist=["Fault"]).Fault(
                    kind=FaultKind.UNAVAILABLE, point="pipeline.enrich", call=i
                )
                for i in range(1, 12)
            ]
        ),
    )
    t = NOW
    for _ in range(8):
        t += timedelta(minutes=5)
        go(s, pipe, t)
    st = run_state(s, RUN)
    assert (
        s.tasks == {}
        and all(u.status.value == "DEAD_LETTER" for u in st.items.values())
        and len(st.items) == 2
    )
    assert state_safety(s) == [] and unaccounted_items(s, RUN) == 0


@covers("R07")
@pytest.mark.parametrize("store_cls", STORES)
@pytest.mark.parametrize("point", ["store.commit_submission", "store.append"])
def test_r07_a_failing_store_write_leaves_a_consistent_state_and_the_retry_converges(
    store_cls, point
) -> None:  # type: ignore[no-untyped-def]
    clean_s, clean_l = clean_state(store_cls)
    s = store_cls()
    plan = FaultPlan(
        [
            __import__("regulus.reliability.faults", fromlist=["Fault"]).Fault(
                kind=FaultKind.UNAVAILABLE, point=point, call=k
            )
            for k in (1, 2)
        ]
    )
    faulty = FaultyStore(s, plan)
    go(faulty, FakePipeline(2))
    assert state_safety(s) == [] and plan.fired
    recover(s, FakePipeline(2))
    assert logical(s) == clean_l and state_safety(s) == []
    assert clean_s.tasks


@covers("R08")
@pytest.mark.parametrize("store_cls", STORES)
@pytest.mark.parametrize("step", STEPS)
def test_r08_a_crash_at_each_commit_step_never_exposes_a_partial_state_and_recovers(
    store_cls, step
) -> None:  # type: ignore[no-untyped-def]
    _, clean_l = clean_state(store_cls)
    s = store_cls()
    s.fail_after = step
    with pytest.raises(Crash):
        go(s, FakePipeline(2))
    assert state_safety(s) == []
    recover(s, FakePipeline(2))
    assert logical(s) == clean_l and state_safety(s) == []


def _review_run() -> ReviewRun:
    return ReviewRun("obl-rel", random.Random(1))


def _req(run: ReviewRun, action: Action, actor_i: int = 0, **kw):  # type: ignore[no-untyped-def]
    run.task = claim(
        run.task.model_copy(
            update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
        ),
        ACTORS[actor_i].id,
        run.clock,
        900,
    )
    return ActionRequest(
        action=action,
        task_id=run.task.id,
        base_version=run.store.version("obl-rel"),
        actor=ACTORS[actor_i],
        at=run.clock,
        **kw,
    )


@covers("R09", "R13")
def test_r09_a_crash_or_failure_mid_review_changes_nothing_and_a_repeat_applies_once() -> None:
    run = _review_run()
    reject = dict(reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))
    before = run.store.get("obl-rel")
    run.store = FaultyReviewStore(
        run.store._inner if hasattr(run.store, "_inner") else run.store,
        FaultPlan(
            [
                __import__("regulus.reliability.faults", fromlist=["Fault"]).Fault(
                    kind=FaultKind.CRASH, point="review.commit", call=1
                )
            ]
        ),
    )  # type: ignore[assignment]
    req = _req(run, Action.REJECT, **reject)
    with pytest.raises(Crash):
        apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert run.store.get("obl-rel") == before
    first = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert first.status is Status.APPLIED
    second = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert (
        second.status in (Status.STALE, Status.INVALID_TRANSITION)
        and len(run.store.get("obl-rel")[1]) == 1
    )
    assert duplicate_decisions(run.store, "obl-rel") == []


@covers("R09")
def test_r09_an_edit_is_both_decisions_or_neither() -> None:
    from regulus.domain import FieldChange

    run = _review_run()
    inner = run.store
    plan = FaultPlan(
        [
            __import__("regulus.reliability.faults", fromlist=["Fault"]).Fault(
                kind=FaultKind.UNAVAILABLE, point="review.commit", call=1
            )
        ]
    )
    run.store = FaultyReviewStore(inner, plan)  # type: ignore[assignment]
    req = _req(
        run,
        Action.EDIT,
        reason="r",
        changes=(FieldChange(field="deadline", before=None, after="paling lambat 3 hari"),),
    )
    out = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert out.status is Status.NOT_RECORDED and inner.get("obl-rel")[1] == ()
    ok = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert (
        ok.status is Status.APPLIED
        and len(inner.get("obl-rel")[1]) == 2
        and inner.get("obl-rel")[0].status is S.PENDING_REVIEW
    )


@covers("R19")
@pytest.mark.parametrize("store_cls", STORES)
def test_r19_a_clock_going_backwards_is_refused_recorded_and_changes_nothing(store_cls) -> None:  # type: ignore[no-untyped-def]
    from rel_helpers import EVENT

    from regulus.workflow import Kind, run_event

    s = store_cls()
    late = NOW + timedelta(hours=1)
    run_event(s, FakePipeline(1), EVENT, SYSTEM, late, lambda *a: False, "1", CFG)
    before = logical(s)
    rep = go(s, FakePipeline(1), NOW)
    after = logical(s)
    assert rep.store_unavailable and after[:2] == before[:2] and after[3] == before[3]
    assert any(r.kind is Kind.CLOCK_REGRESSION for stream in s.streams for r in s.ledger(stream))
    assert state_safety(s) == [] and ClockRegression
    go(s, FakePipeline(1), late + timedelta(minutes=1))
    assert run_state(s, RUN).stage_done("DETECTED")
    detected = [
        x
        for x in s.streams_with("notification:")
        if s.ledger(x)[0].details["event"]["kind"] == "REGULATION_DETECTED"
    ]
    assert len(detected) == 1


class _Dir:
    def reviewers(self, now):  # type: ignore[no-untyped-def]
        return [ReviewerInfo(id="r1")]


@covers("R21")
def test_r21_an_unavailable_directory_leaves_the_task_unassigned_and_review_unblocked() -> None:
    s = InMemoryWorkflowStore()
    go(s, FakePipeline(1))
    (task,) = s.tasks.values()
    plan = FaultPlan(
        [
            __import__("regulus.reliability.faults", fromlist=["Fault"]).Fault(
                kind=FaultKind.UNAVAILABLE, point="directory.reviewers", call=1
            )
        ]
    )
    out = assign(s, task.id, SYSTEM, NOW, FaultyDirectory(_Dir(), plan))
    assert (
        out.status.value == "UNASSIGNED"
        and current_assignment(s, task.id).unassigned_reason == "NO_REVIEWER_AVAILABLE"
    )
    assert assign(s, task.id, SYSTEM, NOW + timedelta(seconds=1), _Dir()).assignee == "r1"
    t = claim(task, "r1", NOW, 900)
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=t.id,
        base_version=s.review.version(task.obligation_id),
        actor=ACTORS[0],
        at=NOW + timedelta(seconds=1),
    )
    assert apply(s.review, t, req, ReviewConfig(), {OWNER: TEXT}).status is Status.INCOMPLETE_REVIEW
    assert Timeout and SubmitStatus and CFG and RUN
