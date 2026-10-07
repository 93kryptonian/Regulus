import copy
import random
from datetime import timedelta

import pytest
from rv_engine_helpers import ALICE, BOB, CAROL, CFG, DAVE, World, change
from rv_helpers import NOW, make_obligation

from regulus.domain import ObligationStatus as S
from regulus.obligations.models import ImpactKind
from regulus.review import (
    Action as A,
)
from regulus.review import (
    Actor,
    Disposition,
    MatchDisposition,
    OpenQuestionResolution,
    RejectCode,
    RejectReason,
    Resolution,
    Role,
    apply,
    preflight,
    replay,
    verify_chain,
)
from regulus.review import (
    Status as R,
)
from regulus.similarity import Label

SEEDS = range(60)
BOTH = Actor(id="erin", roles=(Role.REVIEWER, Role.PUBLISHER))
ACTORS = (ALICE, BOB, CAROL, DAVE, BOTH)
QUESTIONS = ("deadline:undelimited trigger", "actor:comma inside the actor phrase")


def world(rng: random.Random) -> World:
    labels = tuple(
        rng.choice((Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY, Label.RELATED))
        for _ in range(rng.randint(0, 3))
    )
    impacts = tuple(
        __import__("rv_engine_helpers").impact(k)
        for k in rng.sample((ImpactKind.MODIFIED, ImpactKind.WITHDRAWN), rng.randint(0, 1))
    )
    return World(
        questions=tuple(rng.sample(QUESTIONS, rng.randint(0, 2))),
        labels=labels,
        complete=rng.random() < 0.7,
        impacts=impacts,
        with_evidence=rng.random() < 0.9,
    )


def params(w: World, rng: random.Random, action: A) -> dict[str, object]:
    snap, ob = w.task.snapshot, w.store.get("obl-1")[0]
    kw: dict[str, object] = {}
    if action is A.APPROVE:
        kw["resolutions"] = tuple(
            OpenQuestionResolution(question=q, resolution=Resolution.ACCEPTED_AS_IS, note="n")
            for q in snap.open_questions
            if rng.random() < 0.6
        )
        if snap.similarity:
            kw["dispositions"] = tuple(
                MatchDisposition(match_id=m.obligation_id, disposition=Disposition.NOT_A_DUPLICATE)
                for m in snap.similarity.matches
                if rng.random() < 0.6
            )
        kw["acknowledged_flags"] = tuple(f for f in snap.source_flags if rng.random() < 0.6)
    elif action is A.REJECT and rng.random() < 0.9:
        code = rng.choice(
            [c for c in RejectCode if c not in (RejectCode.DUPLICATE_OF, RejectCode.OTHER)]
        )
        kw["reject_reason"] = RejectReason(code=code)
    elif action is A.EDIT:
        if rng.random() < 0.9:
            new = f"paling lambat {rng.randint(1, 9)} hari"
            if new == ob.current.deadline:
                new += " kerja"
            kw["changes"] = (change("deadline", ob.current.deadline, new),)
        if rng.random() < 0.9:
            kw["reason"] = "r"
    return kw


def step(w: World, rng: random.Random, history: list) -> tuple:  # type: ignore[type-arg]
    actor, action = rng.choice(ACTORS), rng.choice(list(A))
    before = w.store.get("obl-1")
    if rng.random() < 0.8 and action is not A.PUBLISH:
        w.task = w.task.model_copy(
            update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
        )
        w.claim(actor)
    req = w.req(actor, action, **params(w, rng, action))
    if history and rng.random() < 0.2:
        req = req.model_copy(update={"base_version": rng.choice(history)})
    history.append(w.store.version("obl-1"))
    w.store.fail_next = 1 if rng.random() < 0.05 else 0
    out = apply(w.store, w.task, req, CFG, w.texts)
    w.store.fail_next = 0
    if out.task is not None:
        w.task = out.task
    return req, out, before


def check(w: World, req, out, before, gen0) -> None:  # type: ignore[no-untyped-def]
    ob, log = w.store.get("obl-1")
    assert verify_chain(log) and replay(make_obligation(), log) == ob
    assert ob.generated == gen0
    if out.status is not R.APPLIED:
        assert (ob, log) == before
        return
    assert log[: len(before[1])] == before[1] and log[len(before[1]) :] == out.records
    snap, prior = w.task.snapshot, before[1]
    if req.action is A.APPROVE:
        assert "SOURCE_WITHDRAWN" not in snap.source_flags
        assert all(f in req.acknowledged_flags for f in snap.source_flags)
        last_edit = next(
            (r.actor_id for r in reversed(prior) if r.decision.to_status is S.EDITED), None
        )
        edited_by = next(
            (r.actor_id for r in reversed(prior) if r.decision.from_status is S.EDITED), None
        )
        assert req.actor.id not in (last_edit, edited_by)
    if req.action is A.PUBLISH:
        approver = next(r.actor_id for r in reversed(prior) if r.decision.to_status is S.APPROVED)
        assert req.actor.id != approver and "SOURCE_WITHDRAWN" not in snap.source_flags
    if req.action is A.EDIT:
        assert ob.status is S.PENDING_REVIEW and len(out.records) == 2


@pytest.mark.parametrize("seed", SEEDS)
def test_random_action_sequences_keep_every_invariant(seed: int) -> None:
    rng = random.Random(seed)
    w = world(rng)
    gen0, history = w.ob.generated, []  # type: ignore[var-annotated]
    for _ in range(30):
        req, out, before = step(w, rng, history)
        check(w, req, out, before, gen0)
        w.clock += timedelta(seconds=rng.choice((0, 1, 2000)))


def test_the_sequences_exercise_every_outcome_and_action() -> None:
    seen: set[tuple[A, R]] = set()
    for seed in SEEDS:
        rng = random.Random(seed)
        w, history = world(rng), []  # type: ignore[var-annotated]
        for _ in range(30):
            req, out, _ = step(w, rng, history)
            seen.add((req.action, out.status))
    applied = {a for a, s in seen if s is R.APPLIED}
    assert applied == set(A)
    assert {s for _, s in seen} >= {
        R.APPLIED,
        R.DENIED,
        R.STALE,
        R.INCOMPLETE_REVIEW,
        R.INVALID_TRANSITION,
        R.EVIDENCE_INVALID,
        R.NOT_RECORDED,
    }


@pytest.mark.parametrize("seed", range(20))
def test_competing_actions_on_one_version_only_the_first_is_applied(seed: int) -> None:
    rng = random.Random(seed)
    w = World()
    w.claim(BOB)
    a = w.req(BOB, A.APPROVE)
    b = w.req(BOB, A.REJECT, reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))
    first, second = (a, b) if rng.random() < 0.5 else (b, a)
    assert apply(w.store, w.task, first, CFG, w.texts).status is R.APPLIED
    snapshot = w.store.get("obl-1")
    w.task = w.task.model_copy(
        update={"claimed_by": "bob", "claim_expires_at": NOW + timedelta(hours=1)}
    )
    assert apply(w.store, w.task, second, CFG, w.texts).status is R.STALE
    assert w.store.get("obl-1") == snapshot


def logged_world(seed: int) -> list:  # type: ignore[type-arg]
    rng = random.Random(seed)
    w, history = world(rng), []  # type: ignore[var-annotated]
    for _ in range(40):
        step(w, rng, history)
    return list(w.store.get("obl-1")[1])


def test_any_tampering_with_a_non_empty_log_is_detected() -> None:
    tampered = 0
    for seed in range(40):
        log = logged_world(seed)
        if len(log) < 2:
            continue
        i = random.Random(seed).randrange(len(log) - 1)
        forged = log.copy()
        forged[i] = forged[i].model_copy(update={"actor_id": "mallory"})
        assert not verify_chain(forged)
        assert not verify_chain(log[:i] + log[i + 1 :])
        swapped = log.copy()
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        assert not verify_chain(swapped)
        assert not verify_chain([*log, log[0]])
        assert not verify_chain(log[1:])
        tampered += 1
    assert tampered >= 20


BASE_ONLY = {"REJECT_REASON", "EDIT_CHANGES_AND_REASON"}


def check_preflight(w: World, rng: random.Random) -> None:
    actor = rng.choice(ACTORS)
    if rng.random() < 0.7:
        w.task = w.task.model_copy(
            update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
        )
        w.claim(actor)
    now = w.clock + timedelta(seconds=1)
    state = (w.store.get("obl-1"), w.store.version("obl-1"), w.task.model_copy(deep=True))
    pf = preflight(w.store, w.task, actor, now, CFG, w.texts)
    assert (w.store.get("obl-1"), w.store.version("obl-1"), w.task) == state
    assert (
        w.task.claimed_by == state[2].claimed_by
        and w.task.claim_expires_at == state[2].claim_expires_at
    )
    for action in A:
        probe = copy.deepcopy(w.store)
        out = apply(probe, w.task, w.req(actor, action), CFG, w.texts)
        verdict = pf.actions[action]
        if verdict.available:
            assert out.status is R.APPLIED or set(out.reasons) <= BASE_ONLY, (action, out)
        else:
            assert out.status not in (R.APPLIED,) and set(out.reasons) <= set(verdict.reasons), (
                action,
                out,
                verdict,
            )


@pytest.mark.parametrize("seed", range(40))
def test_preflight_never_mutates_and_agrees_with_apply(seed: int) -> None:
    rng = random.Random(1000 + seed)
    w, history = world(rng), []  # type: ignore[var-annotated]
    for _ in range(25):
        check_preflight(w, rng)
        step(w, rng, history)
        w.clock += timedelta(seconds=rng.choice((0, 1, 2000)))


def test_preflight_lists_every_failing_reason_not_just_the_first() -> None:
    w = World(
        questions=QUESTIONS,
        labels=(Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY),
        complete=False,
    )
    pf = preflight(w.store, w.task, DAVE, w.clock, CFG, w.texts)
    assert pf.actions[A.APPROVE].reasons[:2] == ("ROLE", "NO_CLAIM")
    pf = preflight(w.store, w.task, BOB, w.clock, CFG, w.texts)
    failing = {g.id for g in pf.gates if not g.ok}
    assert failing >= {
        "CLAIM",
        "DISPOSITION:m0",
        "DISPOSITION:m1",
        "ACKNOWLEDGE:SOURCE_INCOMPLETE",
        f"OPEN_QUESTION:{QUESTIONS[0]}",
        f"OPEN_QUESTION:{QUESTIONS[1]}",
    }
    assert not pf.actions[A.APPROVE].available and pf.gates[0].id == "EVIDENCE" and pf.gates[0].ok


def test_a_clean_task_shows_approve_available_and_publish_unavailable_until_approved() -> None:
    w = World()
    w.claim(BOB)
    pf = preflight(w.store, w.task, BOB, w.clock + timedelta(seconds=1), CFG, w.texts)
    assert (
        pf.actions[A.APPROVE].available
        and pf.actions[A.REJECT].available
        and pf.actions[A.EDIT].available
    )
    assert not pf.actions[A.PUBLISH].available and all(g.ok for g in pf.gates)
