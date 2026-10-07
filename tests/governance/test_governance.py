import itertools
import json
import random
from datetime import timedelta

import pytest
from gov_helpers import CLOCK, MATRIX, TEXT, TOKEN, World, call, form, governed
from rv_engine_helpers import ALICE, BOB, CAROL
from rv_helpers import NOW

from regulus.evaluation.claims import violations as claim_violations
from regulus.evaluation.harness import ACTORS as HARNESS_ACTORS
from regulus.evaluation.harness import OWNER, Everyone, FakePipeline, ReviewRun
from regulus.governance import (
    ChainLog,
    Facts,
    FreeTextPolicy,
    IdentityMap,
    LogUnavailable,
    Operation,
    PurgeStatus,
    Retention,
    authorize,
    erase_identity,
    inventory,
    load_policy,
    verify_all,
)
from regulus.governance.access import REVIEW_OPS, ROLES, WRITES
from regulus.governance.chain import GovRecord
from regulus.governance.resources import (
    default_controls,
    default_inventory,
    default_policy,
)
from regulus.governance.resources import text as res_text
from regulus.governance.scan import records_scanned, scan_stores
from regulus.notifications import queue_emitter
from regulus.reliability.wrappers import Corruption, corrupt
from regulus.review import Action, ActionRequest, ReviewConfig, apply, claim
from regulus.workflow import SYSTEM, InMemoryWorkflowStore, Principal, WorkflowRole, run_event

OP = Principal(id="op", roles=(WorkflowRole.OPERATOR,))
POLICY = default_policy()


def test_the_inventory_matches_the_code_and_every_defect_is_caught() -> None:
    entries = default_inventory()
    assert inventory.check(entries) == []
    first = json.loads(json.dumps(entries[0]))
    removed = json.loads(json.dumps(entries))
    removed[0]["fields"].pop(next(iter(first["fields"])))
    assert any("field not classified" in p for p in inventory.check(removed))
    stale = json.loads(json.dumps(entries))
    stale[0]["fields"]["ghost"] = "PUBLIC"
    assert any("stale entry" in p for p in inventory.check(stale))
    assert any("not in the inventory" in p for p in inventory.check(entries[1:]))
    bad = json.loads(json.dumps(entries))
    bad[0]["fields"][next(iter(first["fields"]))] = "TOP_SECRET"
    assert any("unknown class" in p for p in inventory.check(bad))
    ghost = [*entries, {**first, "model": "regulus.nowhere.Model"}]
    assert any("not stored" in p for p in inventory.check(ghost))
    secret = [e for e in entries if "SECRET" in json.dumps(e["fields"])]
    assert secret == []
    restricted = {str(e["model"]) for e in entries if e["class"] == "RESTRICTED"}
    assert (
        "regulus.review.models.ReviewRecord" in restricted
        and "regulus.workflow.models.WorkflowRecord" in restricted
    )


def oracle(role_set: set[str], actor: str, op: Operation, f: Facts | None) -> bool:
    coarse = {
        "READ_QUEUE": {"REVIEWER", "PUBLISHER", "AUDITOR"}, "READ_TASK": {"REVIEWER", "PUBLISHER", "AUDITOR"},
        "READ_HISTORY": {"REVIEWER", "PUBLISHER", "AUDITOR"}, "READ_ACCESS_AUDIT": {"AUDITOR"},
        "READ_EVALUATION": set(ROLES), "CLAIM": {"REVIEWER"}, "EDIT": {"REVIEWER"}, "APPROVE": {"REVIEWER"},
        "REJECT": {"REVIEWER"}, "PUBLISH": {"PUBLISHER"}, "ASSIGN": {"COORDINATOR", "SYSTEM"}, "RESCHEDULE": {"COORDINATOR"},
        "REQUEUE": {"OPERATOR"}, "PURGE": {"OPERATOR"}, "HOLD": {"OPERATOR"}, "RELEASE_HOLD": {"OPERATOR"},
        "BASELINE_UPDATE": {"OPERATOR"}, "ERASE_IDENTITY": {"OPERATOR"}, "SUBMIT": {"SYSTEM", "OPERATOR"},
        "RUN_PIPELINE": {"SYSTEM", "OPERATOR"}, "TICK": {"SYSTEM", "OPERATOR"},
    }  # fmt: skip
    held = role_set & coarse[op.value]
    if not held:
        return False
    if op.value not in {
        "READ_QUEUE",
        "READ_TASK",
        "READ_HISTORY",
        "CLAIM",
        "EDIT",
        "APPROVE",
        "REJECT",
        "PUBLISH",
    }:
        return True
    if f is None:
        return False
    if "AUDITOR" in held:
        return True
    mine = actor in f.participants
    return ("REVIEWER" in held and (not f.terminal or mine)) or (
        "PUBLISHER" in held and (f.status == "APPROVED" or (f.terminal and mine))
    )


FACTS = [
    Facts(task_id="t", status="PENDING_REVIEW", terminal=False),
    Facts(task_id="t", status="EDITED", terminal=False, participants=("me",)),
    Facts(task_id="t", status="APPROVED", terminal=False, participants=("other",)),
    Facts(task_id="t", status="PUBLISHED", terminal=True, participants=("me", "other")),
    Facts(task_id="t", status="REJECTED", terminal=True, participants=("other",)),
    None,
]


def test_the_matrix_and_resource_rules_match_an_independent_oracle_for_every_combination() -> None:
    n = 0
    role_sets = [set(c) for r in range(0, 3) for c in itertools.combinations(ROLES, r)]
    for roles, op, facts in itertools.product(role_sets, Operation, FACTS):
        got = authorize(MATRIX, "me", roles, op.value, facts).allowed
        assert got == oracle(roles, "me", op, facts), (roles, op, facts)
        n += 1
    assert n > 1000


def test_unlisted_operations_and_unnamed_resources_are_denied() -> None:
    assert (
        authorize(MATRIX, "me", {"REVIEWER"}, "DELETE_EVERYTHING", FACTS[0]).reason
        == "UNLISTED_OPERATION"
    )
    assert (
        authorize(MATRIX, "me", set(ROLES), Operation.READ_TASK.value, None).reason == "NO_RESOURCE"
    )
    assert not authorize(MATRIX, "me", {"COORDINATOR"}, Operation.READ_TASK.value, FACTS[0]).allowed


def test_separation_properties_hold_over_the_matrix() -> None:
    for op in WRITES:
        assert "AUDITOR" not in MATRIX.roles_for(op.value)
    for role in ("OPERATOR", "COORDINATOR", "SYSTEM"):
        assert not any(role in MATRIX.roles_for(op.value) for op in REVIEW_OPS)
    assert set(MATRIX.allow) == {o.value for o in Operation}
    assert "assignee" not in Facts.model_fields and "assignment" not in "".join(Facts.model_fields)


def test_governed_pages_follow_the_resource_rules_and_every_request_is_audited_once() -> None:
    w = World()
    app, inner, audit = governed(w)
    path = f"/tasks/{w.task.id}"
    assert call(app, "GET", path, "bob")["status"].startswith("200") and call(
        app, "GET", path, "dave"
    )["status"].startswith("200")
    assert call(app, "GET", path, "nobody")["status"].startswith("403") and call(
        app, "GET", "/tasks", "nobody"
    )["status"].startswith("403")
    assert call(app, "GET", path, "carol")["status"].startswith("403")
    assert call(app, "GET", "/tasks/nope", "bob")["status"].startswith("404")
    assert call(app, "GET", path, "stranger")["status"].startswith("401")
    assert call(app, "GET", "/tasks", "bob")["body"].count("/tasks/") >= 1
    c = app.counters
    assert c.attempted == c.recorded + c.gap == len(audit.records) == 8 and c.gap == 0
    assert len({r.id for r in audit.records}) == 8 and audit.verified()
    assert {r.kind for r in audit.records} == {"ACCESS_ALLOWED", "ACCESS_DENIED"}


def test_a_reviewer_cannot_read_a_closed_task_they_did_not_take_part_in_but_a_participant_and_the_auditor_can() -> (
    None
):
    w = World()
    app, inner, audit = governed(w)
    claimed = claim(w.task, "alice", CLOCK, 900)
    inner.tasks[w.task.id] = claimed
    from regulus.review import RejectCode, RejectReason

    req = ActionRequest(
        action=Action.REJECT,
        task_id=claimed.id,
        base_version=w.store.version("obl-1"),
        actor=ALICE,
        at=CLOCK,
        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE),
    )
    assert apply(w.store, claimed, req, ReviewConfig(), w.texts).status.value == "APPLIED"
    path = f"/tasks/{w.task.id}"
    assert call(app, "GET", path, "bob")["status"].startswith("403")
    assert call(app, "GET", path, "alice")["status"].startswith("200") and call(
        app, "GET", path, "dave"
    )["status"].startswith("200")
    assert "task" not in call(app, "GET", "/tasks", "bob")["body"].split("<tbody>")[1].split(
        "</tbody>"
    )[0].replace("tasks/", "")


def test_read_access_does_not_depend_on_assignment() -> None:
    store = InMemoryWorkflowStore()
    run_event(
        store,
        FakePipeline(1),
        __import__("regulus.evaluation.layers.workflow", fromlist=["EVENT"]).EVENT,
        SYSTEM,
        NOW,
        queue_emitter(store, Everyone(), SYSTEM, NOW),
    )
    from gov_helpers import ACTORS as GA

    from regulus.review_ui import ReviewApp

    inner = ReviewApp(
        store.review,
        dict(store.tasks),
        lambda env: GA.get(env.get("HTTP_X_ACTOR", "")),
        lambda env: TOKEN,
        {OWNER: TEXT},
        lambda: CLOCK,
    )
    app = __import__("regulus.governance", fromlist=["GovernedApp"]).GovernedApp(
        inner, MATRIX, ChainLog("access"), lambda: CLOCK
    )
    (tid,) = inner.tasks
    before = [
        call(app, "GET", f"/tasks/{tid}", a)["status"][:3]
        for a in ("alice", "bob", "carol", "dave", "nobody")
    ]
    from regulus.workflow import ReviewerInfo, assign

    class Dir:
        def reviewers(self, now):  # type: ignore[no-untyped-def]
            return [ReviewerInfo(id="alice")]

    assign(store, tid, SYSTEM, NOW, Dir())
    after = [
        call(app, "GET", f"/tasks/{tid}", a)["status"][:3]
        for a in ("alice", "bob", "carol", "dave", "nobody")
    ]
    assert before == after == ["200", "200", "403", "200", "403"]


def test_a_write_requires_the_role_and_the_ability_to_read_the_task_and_the_app_leaves_phase_10_alone() -> (
    None
):
    w = World()
    app, inner, audit = governed(w)
    assert call(app, "POST", f"/tasks/{w.task.id}/claim", "carol", {"csrf": TOKEN})[
        "status"
    ].startswith("403")
    assert call(app, "POST", f"/tasks/{w.task.id}/claim", "bob", {"csrf": TOKEN})[
        "status"
    ].startswith("200")
    assert call(app, "POST", f"/tasks/{w.task.id}/action", "dave", form(w, inner, "APPROVE"))[
        "status"
    ].startswith("403")
    assert call(app, "POST", f"/tasks/{w.task.id}/action", "bob", form(w, inner, "NUKE"))[
        "status"
    ].startswith("403")
    plain = call(inner, "GET", f"/tasks/{w.task.id}", "nobody")
    assert plain["status"].startswith("200")


def test_with_the_audit_failing_restricted_pages_are_not_served_and_the_gap_is_counted() -> None:
    w = World()
    app, inner, audit = governed(w)
    path = f"/tasks/{w.task.id}"
    audit.fail_next = 1
    out = call(app, "GET", path, "bob")
    assert (
        out["status"].startswith("503")
        and "Pengendali" not in out["body"]
        and TEXT not in out["body"]
    )
    ok = call(app, "GET", path, "bob")
    assert ok["status"].startswith("200")
    audit.fail_next = 1
    assert call(app, "GET", path, "nobody")["status"].startswith("503")
    audit.fail_next = 1
    assert call(app, "GET", "/tasks", "bob")["status"].startswith("503")
    c = app.counters
    assert (
        (c.attempted, c.recorded, c.gap) == (4, 1, 3)
        and c.attempted == c.recorded + c.gap
        and len(audit.records) == c.recorded
    )
    assert (
        call(app, "GET", "/static/review.css", "bob")["status"].startswith("200")
        and app.counters.attempted == 4
    )


def test_audit_and_purge_records_are_content_free_and_free_text_is_policed() -> None:
    log = ChainLog("access")
    with pytest.raises(ValueError):
        log.append("ACCESS_ALLOWED", CLOCK, resource="a free text value with spaces")
    with pytest.raises(ValueError):
        log.append("HOLD", CLOCK, reason="ana@example.com")
    log.append("HOLD", CLOCK, reason="legal hold per ticket 123")
    with pytest.raises(ValueError):
        GovRecord(
            id="x",
            seq=0,
            log="a",
            kind="K",
            fields={"reason": "x" * 600},
            at=CLOCK,
            prev_hash="GENESIS",
        )
    pol = FreeTextPolicy()
    assert (
        pol.check("reason", "fine") is None
        and pol.check("reason", "mail ana@example.com") == "email"
    )
    assert (
        pol.check("note:q", "see https://x.example") == "url"
        and pol.check("reason", "+62 812 3456 7890") == "phone"
    )
    assert (
        pol.check("reason", "password: hunter2xx") == "credential"
        and pol.check("reason", "x" * 501) == "too_long"
    )
    assert pol.check("reason", "due 2026-09-01T10:00:00+00:00") is None and not pol.covers(
        "deadline"
    )


@pytest.mark.parametrize(
    "value,why",
    [
        ("write to ana@example.com", "EMAIL"),
        ("see https://x.example/y", "URL"),
        ("call +62 812 3456 7890", "PHONE"),
        ("password: abcdef12", "CREDENTIAL"),
        ("x" * 501, "TOO_LONG"),
    ],
)
def test_forbidden_free_text_is_rejected_at_the_boundary_never_echoed_and_never_stored(
    value: str, why: str
) -> None:
    w = World()
    app, inner, audit = governed(w)
    call(app, "POST", f"/tasks/{w.task.id}/claim", "bob", {"csrf": TOKEN})
    before = w.store.get("obl-1")
    out = call(
        app,
        "POST",
        f"/tasks/{w.task.id}/action",
        "bob",
        form(w, inner, "REJECT", reject_code="OTHER", reject_text=value, reason=value),
    )
    assert (
        out["status"].startswith("400")
        and value not in out["body"]
        and ("reason" in out["body"] or "reject_text" in out["body"])
    )
    assert w.store.get("obl-1") == before
    last = audit.records[-1]
    assert (
        last.kind == "ACCESS_DENIED"
        and last.fields["outcome"] == f"FREE_TEXT_{why}"
        and value not in json.dumps(last.model_dump(mode="json"))
    )
    ok = call(
        app,
        "POST",
        f"/tasks/{w.task.id}/action",
        "bob",
        form(w, inner, "REJECT", reject_code="OUT_OF_SCOPE", reason="clean reason"),
    )
    assert ok["status"].startswith("200") and w.store.get("obl-1")[0].status.value == "REJECTED"


def store_with_closed_obligations(n: int = 2):  # type: ignore[no-untyped-def]
    s = InMemoryWorkflowStore()
    run_event(
        s,
        FakePipeline(n),
        __import__("regulus.evaluation.layers.workflow", fromlist=["EVENT"]).EVENT,
        SYSTEM,
        NOW,
        queue_emitter(s, Everyone(), SYSTEM, NOW),
    )
    return s


def close(s, oid: str, actor_i: int = 0) -> None:  # type: ignore[no-untyped-def]
    from regulus.review import RejectCode, RejectReason

    task = next(t for t in s.tasks.values() if t.obligation_id == oid)
    t = claim(task, HARNESS_ACTORS[actor_i].id, NOW + timedelta(seconds=5), 900)
    req = ActionRequest(
        action=Action.REJECT,
        task_id=t.id,
        base_version=s.review.version(oid),
        actor=HARNESS_ACTORS[actor_i],
        at=NOW + timedelta(seconds=6),
        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE),
    )
    assert apply(s.review, t, req, ReviewConfig(), {OWNER: TEXT}).status.value == "APPLIED"


LATE = NOW + timedelta(days=2000)


def test_a_purge_runs_intent_then_delete_then_applied_and_leaves_a_verifiable_receipt() -> None:
    s = store_with_closed_obligations()
    close(s, "obl-0")
    audit, plog = ChainLog("access"), ChainLog("purge")
    r = Retention(s, POLICY, plog, audit)
    assert r.purge(OP, "review:obl-0", "retention period elapsed", LATE) is PurgeStatus.APPLIED
    assert [x.kind for x in plog.records] == ["PURGE_INTENT", "PURGE_APPLIED"] and plog.verified()
    intent, applied = plog.records
    assert (
        applied.fields["intent"] == intent.id
        and intent.fields["records"] == 1
        and "tip" in intent.fields
    )
    assert "review:obl-0" not in r.streams() and not s.registered("obl-0")
    rep = verify_all(s, audit, plog)
    assert "obl-0" not in str(rep.broken)
    assert r.purge(OP, "review:obl-0", "again", LATE) is PurgeStatus.REFUSED


def test_a_purge_is_refused_for_unexpired_non_terminal_held_unknown_or_unauthorised_requests() -> (
    None
):
    s = store_with_closed_obligations()
    close(s, "obl-0")
    audit, plog = ChainLog("access"), ChainLog("purge")
    r = Retention(s, POLICY, plog, audit)
    assert r.purge(OP, "review:obl-0", "too early", NOW + timedelta(days=1)) is PurgeStatus.REFUSED
    assert r.purge(OP, "review:obl-1", "still open", LATE) is PurgeStatus.REFUSED
    assert (
        r.purge(Principal(id="x", roles=(WorkflowRole.COORDINATOR,)), "review:obl-0", "no", LATE)
        is PurgeStatus.DENIED
    )
    assert r.purge(OP, "review:obl-nope", "no", LATE) is PurgeStatus.REFUSED
    assert r.hold(OP, "review:obl-0", "legal hold ref 7", LATE)
    assert r.purge(OP, "review:obl-0", "held", LATE) is PurgeStatus.REFUSED
    assert not r.hold(Principal(id="x"), "review:obl-0", "no", LATE) and not r.release(
        Principal(id="x"), "review:obl-0", "no", LATE
    )
    assert plog.records == []
    assert (
        r.release(OP, "review:obl-0", "hold lifted", LATE)
        and r.purge(OP, "review:obl-0", "now", LATE) is PurgeStatus.APPLIED
    )
    kinds = [x.kind for x in audit.records]
    assert "HOLD" in kinds and "RELEASE_HOLD" in kinds and kinds.count("ACCESS_DENIED") >= 4
    unset = Retention(s, type(POLICY)(days={}), ChainLog("purge"), ChainLog("access"))
    assert unset.purge(OP, "notification:x", "no class", LATE) is PurgeStatus.REFUSED


@pytest.mark.parametrize("crash", [None, "intent", "delete"])
def test_a_crash_at_any_purge_step_leaves_no_contradictory_evidence_and_recovery_is_rerunnable(
    crash: str | None,
) -> None:
    s = store_with_closed_obligations()
    close(s, "obl-0")
    audit, plog = ChainLog("access"), ChainLog("purge")
    r = Retention(s, POLICY, plog, audit)
    r.fail_after = crash
    if crash:
        with pytest.raises(RuntimeError):
            r.purge(OP, "review:obl-0", "elapsed", LATE)
    else:
        r.purge(OP, "review:obl-0", "elapsed", LATE)
    for _ in range(2):
        r.recover(LATE + timedelta(seconds=1))
    kinds = [x.kind for x in plog.records]
    stream_present = "review:obl-0" in r.streams()
    assert plog.verified() and kinds.count("PURGE_INTENT") == (0 if crash is None and False else 1)
    if "PURGE_APPLIED" in kinds:
        assert not stream_present
    if "PURGE_CANCELLED" in kinds:
        assert stream_present
    assert ("PURGE_APPLIED" in kinds) != ("PURGE_CANCELLED" in kinds)
    again = r.recover(LATE + timedelta(seconds=2))
    assert again == 0 and [x.kind for x in plog.records] == kinds


def test_a_hold_placed_between_the_intent_and_the_delete_cancels_the_purge() -> None:
    s = store_with_closed_obligations()
    close(s, "obl-0")
    audit, plog = ChainLog("access"), ChainLog("purge")
    r = Retention(s, POLICY, plog, audit)
    r.fail_after = "intent"
    with pytest.raises(RuntimeError):
        r.purge(OP, "review:obl-0", "elapsed", LATE)
    r.holds["review:obl-0"] = "hold placed meanwhile"
    assert r.recover(LATE) == 1
    assert [x.kind for x in plog.records] == [
        "PURGE_INTENT",
        "PURGE_CANCELLED",
    ] and "review:obl-0" in r.streams()


def test_workflow_streams_are_purged_whole_and_a_missing_stream_without_receipt_is_reported() -> (
    None
):
    s = store_with_closed_obligations()
    audit, plog = ChainLog("access"), ChainLog("purge")
    r = Retention(s, POLICY, plog, audit)
    note = s.streams_with("notification:")[0]
    assert (
        r.purge(OP, note, "notification retention elapsed", LATE) is PurgeStatus.APPLIED
        and note not in s.streams
    )
    close(s, "obl-0")
    del s.streams["obligation:obl-0"]  # type: ignore[attr-defined]
    rep = verify_all(s, audit, plog)
    assert "obligation:obl-0" in rep.unreceipted


def test_identity_erasure_removes_the_link_only_and_is_audited() -> None:
    assert (
        erase_identity(
            IdentityMap(),
            ChainLog("a"),
            Principal(id="x", roles=(WorkflowRole.COORDINATOR,)),
            "r1",
            NOW,
        )
        == "DENIED"
    )
    s = store_with_closed_obligations()
    close(s, "obl-0")
    audit, plog = ChainLog("access"), ChainLog("purge")
    idm = IdentityMap()
    idm.register("r1", "A Person")
    assert idm.resolve("r1") == "A Person"
    ids_before = {x.actor_id for x in s.review.get("obl-0")[1]}
    assert erase_identity(idm, audit, OP, "r1", NOW) == "ERASED"
    assert idm.resolve("r1") is None and idm.links() == 0
    assert {x.actor_id for x in s.review.get("obl-0")[1]} == ids_before and "r1" in ids_before
    assert verify_all(s, audit, plog).broken == () and audit.records[-1].kind == "IDENTITY_ERASED"
    assert erase_identity(idm, audit, OP, "r1", NOW) == "UNKNOWN"
    idm.register("r2", "B")
    idm.available = False
    assert erase_identity(idm, audit, OP, "r2", NOW) == "REFUSED" and idm.resolve("r2") == "B"


def _chain(name: str) -> ChainLog:
    log = ChainLog(name)
    for i in range(4):
        log.append(
            "ACCESS_ALLOWED",
            CLOCK,
            operation="READ_TASK",
            actor="a",
            resource=f"t{i}",
            outcome="ALLOWED",
        )
    return log


@pytest.mark.parametrize("mode", list(Corruption))
def test_verify_all_detects_every_corruption_class_in_the_governance_logs(mode: Corruption) -> None:
    rng = random.Random(3)
    s = store_with_closed_obligations()
    audit, plog = _chain("access"), _chain("purge")
    assert verify_all(s, audit, plog).broken == ()
    audit.records = list(
        corrupt(
            tuple(audit.records),
            mode,
            rng,
            foreign=audit.records[0].model_copy(update={"id": "x-foreign"}),
        )
    )
    rep = verify_all(s, audit, plog)
    assert "log:access" in rep.broken and "log:purge" in rep.intact
    plog.records = list(
        corrupt(
            tuple(plog.records),
            mode,
            rng,
            foreign=plog.records[0].model_copy(update={"id": "p-foreign"}),
        )
    )
    assert "log:purge" in verify_all(s, audit, plog).broken


@pytest.mark.parametrize("mode", list(Corruption))
def test_verify_all_detects_every_corruption_class_in_workflow_streams_with_a_tip_reference(
    mode: Corruption,
) -> None:
    from regulus.reliability.guard import GuardedStore

    s = store_with_closed_obligations()
    guarded = GuardedStore(s)
    stream = "obligation:obl-0"
    guarded.append(
        stream,
        __import__("regulus.workflow", fromlist=["Kind"]).Kind.SUBMIT_REFUSED,
        SYSTEM,
        NOW + timedelta(days=1),
        None,
        {"reasons": ["probe"]},
    )
    audit, plog = ChainLog("access"), ChainLog("purge")
    assert verify_all(s, audit, plog, guarded._tips).broken == ()
    s.streams[stream] = corrupt(
        s.streams[stream],
        mode,
        random.Random(1),
        foreign=s.streams[stream][0].model_copy(update={"id": "w-foreign"}),
    )  # type: ignore[attr-defined]
    assert stream in verify_all(s, audit, plog, guarded._tips).broken


@pytest.mark.parametrize("mode", list(Corruption))
def test_verify_all_detects_every_corruption_class_in_review_logs(mode: Corruption) -> None:
    run = ReviewRun("obl-rel", random.Random(7))
    for _ in range(80):
        run.step()
        if len(run.store.get("obl-rel")[1]) >= 3:
            break
    log = run.store.get("obl-rel")[1]
    if len(log) < 3:
        pytest.skip("scripted run produced too short a log")

    class W:
        review = run.store

        def streams_with(self, prefix: str) -> list[str]:
            return []

    assert verify_all(W(), ChainLog("a"), ChainLog("p")).broken == ()  # type: ignore[arg-type]
    run.store._log["obl-rel"] = corrupt(
        log, mode, random.Random(2), foreign=log[0].model_copy(update={"id": "r-foreign"})
    )
    assert "review:obl-rel" in verify_all(W(), ChainLog("a"), ChainLog("p")).broken  # type: ignore[arg-type]


def test_the_store_scan_finds_seeded_free_text_without_revealing_it() -> None:
    run = ReviewRun("obl-rel", random.Random(1))
    run.task = claim(run.task, ALICE.id, run.clock, 900)
    from regulus.domain import FieldChange

    req = ActionRequest(action=Action.EDIT, task_id=run.task.id, base_version=run.store.version("obl-rel"), actor=ALICE, at=run.clock,
                        reason="contact ana@example.com for details", changes=(FieldChange(field="deadline", before=None, after="paling lambat 3 hari"),))  # fmt: skip

    class W:
        review = run.store

    out = apply(run.store, run.task, req, ReviewConfig(), run.texts)
    assert out.status.value == "APPLIED"
    found = scan_stores(W())  # type: ignore[arg-type]
    assert found["review_record.reason:email"] == 1 and records_scanned(W()) == 2  # type: ignore[arg-type]
    assert "ana@example.com" not in json.dumps(dict(found))


def test_the_controls_map_makes_no_compliance_claim_and_points_at_real_invariants() -> None:
    data = default_controls()
    assert "not an assertion of conformance" in data["note"] and "confirmed" in data["note"]
    assert {c["invariant"] for c in data["controls"]} <= set(range(1, 11)) and len(
        data["controls"]
    ) == len({c["id"] for c in data["controls"]})
    text = json.dumps(data)
    assert (
        claim_violations(text) == []
        and "compliant" not in text.lower()
        and "certified" not in text.lower()
    )
    pol = json.loads(res_text("retention_policy.v1.json"))
    assert pol["illustrative"] is True and BOB and CAROL and LogUnavailable and load_policy
