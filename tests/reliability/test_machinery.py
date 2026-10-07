import random
from datetime import timedelta

import pytest
from obs_helpers import make_observer
from rel_helpers import CFG, NOW, RUN, FakeChannel, FakePipeline, FaultKind, FaultPlan, go, logical
from rv_engine_helpers import OWNER, TEXT

from regulus.evaluation.harness import ACTORS, ReviewRun, generation_result
from regulus.notifications import deliver_due
from regulus.observability.taxonomy import ErrorClass, Kind
from regulus.reliability.faults import Fault, Timeout
from regulus.reliability.guard import GuardedReviewStore, GuardedStore, IntegrityError
from regulus.reliability.invariants import (
    duplicate_decisions,
    state_safety,
    unaccounted_items,
    weaker_snapshots,
)
from regulus.reliability.wrappers import (
    FaultyChannel,
    FaultyPipeline,
    FaultyReviewStore,
    FaultyStore,
)
from regulus.review import Action, ActionRequest, ReviewConfig, StoreError, apply, claim
from regulus.workflow import (
    SYSTEM,
    InMemoryWorkflowStore,
    SnapshotInputs,
    Unavailable,
    submit_for_review,
)


def test_a_seeded_fault_plan_is_deterministic_bounded_and_fires_once_per_fault() -> None:
    pts = ["a", "b"]
    kinds = [FaultKind.UNAVAILABLE, FaultKind.CRASH]
    p1, p2 = FaultPlan.seeded(5, pts, kinds), FaultPlan.seeded(5, pts, kinds)
    assert p1.faults == p2.faults and 1 <= len(p1.faults) <= 3
    assert FaultPlan.seeded(5, pts, kinds, max_faults=1).faults.__len__() == 1
    plan = FaultPlan([Fault(kind=FaultKind.CRASH, point="x", call=2)])
    assert [plan.check("x"), plan.check("x"), plan.check("x")] == [
        None,
        FaultKind.CRASH,
        None,
    ] and plan.spent()


def test_wrappers_with_no_planned_fault_change_nothing() -> None:
    plain, wrapped = InMemoryWorkflowStore(), InMemoryWorkflowStore()
    go(plain, FakePipeline(3))
    plan = FaultPlan()
    go(FaultyStore(wrapped, plan), FaultyPipeline(FakePipeline(3), plan))  # type: ignore[arg-type]
    assert logical(plain) == logical(wrapped)
    chan_a, chan_b = FakeChannel(random.Random(0), 0.0), FakeChannel(random.Random(0), 0.0)
    deliver_due(plain, chan_a, SYSTEM, NOW, CFG)
    deliver_due(wrapped, FaultyChannel(chan_b, plan), SYSTEM, NOW, CFG)
    assert chan_a.keys == chan_b.keys and logical(plain) == logical(wrapped)
    run_a, run_b = ReviewRun("obl-rel", random.Random(3)), ReviewRun("obl-rel", random.Random(3))
    run_b.store = FaultyReviewStore(run_b.store, plan)  # type: ignore[assignment]
    for _ in range(15):
        run_a.step()
        run_b.step()
    assert run_a.store.get("obl-rel") == run_b.store._inner.get("obl-rel")


def test_timeouts_are_retryable_unavailable_and_store_errors() -> None:
    assert issubclass(Timeout, Unavailable) and issubclass(Timeout, StoreError)


def test_the_invariant_checkers_detect_injected_violations() -> None:
    s = InMemoryWorkflowStore()
    go(s, FakePipeline(2))
    assert state_safety(s) == [] and unaccounted_items(s, RUN) == 0
    ob = generation_result("obl-ghost").obligation
    from regulus.domain import ObligationStatus as S

    s.review.register(ob.model_copy(update={"status": S.PENDING_REVIEW}))
    found = state_safety(s)
    assert any("registered without a task" in f for f in found) and any(
        "without a submission record" in f for f in found
    )
    run = ReviewRun("obl-rel", random.Random(1))
    run.task = claim(run.task, ACTORS[0].id, run.clock, 900)
    from regulus.review import RejectCode, RejectReason

    req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=run.store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
    apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert duplicate_decisions(run.store, "obl-rel") == []
    rec = run.store.get("obl-rel")[1][0]
    run.store._log["obl-rel"] = (rec, rec)
    assert duplicate_decisions(run.store, "obl-rel") != []
    sub = submit_for_review(
        s,
        generation_result("obl-w"),
        SnapshotInputs(source_complete=True, permitted_source=TEXT),
        SYSTEM,
        NOW,
        {OWNER: TEXT},
    )
    assert sub.task is not None
    assert (
        weaker_snapshots([sub.task], {"obl-w": False}) == [sub.task.id]
        and weaker_snapshots([sub.task], {"obl-w": True}) == []
    )


def test_the_guards_are_transparent_on_intact_state_and_flag_integrity_refusals_for_observability() -> (
    None
):
    run = ReviewRun("obl-rel", random.Random(2))
    guarded = GuardedReviewStore(run.store)
    run.store = guarded  # type: ignore[assignment]
    for _ in range(15):
        run.step()
    assert run.store.get("obl-rel")[0] is not None
    obs = make_observer()
    with pytest.raises(IntegrityError):
        with obs.span(
            "run-g", __import__("regulus.observability.taxonomy", fromlist=["Stage"]).Stage.SUBMIT
        ):
            raise IntegrityError("chain failed")
    fin = obs.journal[-1]
    assert (
        fin.kind is Kind.SPAN_FINISHED
        and fin.error_class is ErrorClass.STORE
        and fin.attrs["store"] == "INTEGRITY"
    )
    assert GuardedStore and timedelta
