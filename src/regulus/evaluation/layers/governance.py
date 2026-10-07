import io
import itertools
import json
import random
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from regulus.governance import (
    ChainLog,
    Facts,
    GovernedApp,
    IdentityMap,
    Operation,
    PurgeStatus,
    Retention,
    authorize,
    erase_identity,
    inventory,
    verify_all,
)
from regulus.governance.access import REVIEW_OPS, ROLES, WRITES
from regulus.governance.resources import default_inventory, default_matrix, default_policy
from regulus.governance.scan import scan_stores
from regulus.notifications import (
    NotificationEvent,
    NotificationKind,
    queue_emitter,
    queue_notification,
    requeue_notification,
)
from regulus.observability.scan import scan as pattern_scan
from regulus.reliability.wrappers import Corruption, corrupt
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    RejectCode,
    RejectReason,
    ReviewConfig,
    Role,
    apply,
    claim,
)
from regulus.review import authorize as review_authorize
from regulus.review_ui import ReviewApp
from regulus.workflow import (
    SYSTEM,
    InMemoryWorkflowStore,
    Principal,
    ReviewerInfo,
    SnapshotInputs,
    WorkflowRole,
    assign,
    reschedule,
    run_event,
    submit_for_review,
    tick,
)
from regulus.workflow import requeue as requeue_run

from ..builder import EC, HARD0, Builder
from ..harness import ACTORS, NOW, OWNER, TEXT, Everyone, FakePipeline, ReviewRun, generation_result
from ..models import EvidenceClass, Gate
from .workflow import EVENT

L = "governance"
POP = "governance.harness_runs"
SEEDS, SEED0 = 20, 1515000
LATE = NOW + timedelta(days=2000)
CLOCK = NOW + timedelta(seconds=1)
GOV_ACTORS = {
    "alice": Actor(id="alice", roles=(Role.REVIEWER,)), "bob": Actor(id="bob", roles=(Role.REVIEWER,)),
    "carol": Actor(id="carol", roles=(Role.PUBLISHER,)), "dave": Actor(id="dave", roles=(Role.AUDITOR,)),
    "nobody": Actor(id="nobody", roles=()),
}  # fmt: skip
WF_ROLES = {
    "COORDINATOR": WorkflowRole.COORDINATOR,
    "OPERATOR": WorkflowRole.OPERATOR,
    "SYSTEM": WorkflowRole.SYSTEM,
}
COARSE = {
    "READ_QUEUE": {"REVIEWER", "PUBLISHER", "AUDITOR"}, "READ_TASK": {"REVIEWER", "PUBLISHER", "AUDITOR"},
    "READ_HISTORY": {"REVIEWER", "PUBLISHER", "AUDITOR"}, "READ_ACCESS_AUDIT": {"AUDITOR"}, "READ_EVALUATION": set(ROLES),
    "CLAIM": {"REVIEWER"}, "EDIT": {"REVIEWER"}, "APPROVE": {"REVIEWER"}, "REJECT": {"REVIEWER"}, "PUBLISH": {"PUBLISHER"},
    "ASSIGN": {"COORDINATOR", "SYSTEM"}, "RESCHEDULE": {"COORDINATOR"}, "REQUEUE": {"OPERATOR"}, "PURGE": {"OPERATOR"},
    "HOLD": {"OPERATOR"}, "RELEASE_HOLD": {"OPERATOR"}, "BASELINE_UPDATE": {"OPERATOR"}, "ERASE_IDENTITY": {"OPERATOR"},
    "SUBMIT": {"SYSTEM", "OPERATOR"}, "RUN_PIPELINE": {"SYSTEM", "OPERATOR"}, "TICK": {"SYSTEM", "OPERATOR"},
}  # fmt: skip
RESOURCE_OPS = {
    "READ_QUEUE",
    "READ_TASK",
    "READ_HISTORY",
    "CLAIM",
    "EDIT",
    "APPROVE",
    "REJECT",
    "PUBLISH",
}
FACTS = [
    Facts(task_id="t", status="PENDING_REVIEW", terminal=False),
    Facts(task_id="t", status="APPROVED", terminal=False, participants=("other",)),
    Facts(task_id="t", status="PUBLISHED", terminal=True, participants=("me", "other")),
    Facts(task_id="t", status="REJECTED", terminal=True, participants=("other",)),
    None,
]


def _oracle(roles: set[str], actor: str, op: str, f: Facts | None) -> bool:
    held = roles & COARSE.get(op, set())
    if not held:
        return False
    if op not in RESOURCE_OPS:
        return True
    if f is None:
        return False
    if "AUDITOR" in held:
        return True
    mine = actor in f.participants
    return ("REVIEWER" in held and (not f.terminal or mine)) or (
        "PUBLISHER" in held and (f.status == "APPROVED" or (f.terminal and mine))
    )


def _run(app: Any, env: dict[str, Any]) -> tuple[str, str]:
    holder: list[str] = []
    body = b"".join(app(env, lambda status, headers: holder.append(status))).decode()
    return holder[0], body


def _principal(role: str) -> Principal:
    return Principal(id=f"p-{role.lower()}", roles=(WF_ROLES[role],) if role in WF_ROLES else ())


class _Dir:
    def reviewers(self, now: Any) -> list[ReviewerInfo]:
        return [ReviewerInfo(id="r1")]


def _workflow_conformance(matrix: Any) -> tuple[int, int]:
    bad = n = 0
    for role in ("COORDINATOR", "OPERATOR", "SYSTEM", "REVIEWER", "PUBLISHER", "AUDITOR"):
        p = _principal(role)
        audit, plog = ChainLog("access"), ChainLog("purge")
        s = InMemoryWorkflowStore()
        run_event(s, FakePipeline(1), EVENT, SYSTEM, NOW, queue_emitter(s, Everyone(), SYSTEM, NOW))
        (task,) = s.tasks.values()
        key = (
            queue_notification(
                s,
                NotificationEvent(
                    kind=NotificationKind.TASK_OVERDUE,
                    subject="task-1",
                    version="v",
                    payload={"task_id": "task-1", "due_at": "2026-09-01T10:00:00+00:00"},
                ),
                Everyone(),
                SYSTEM,
                NOW,
            ).key
            or ""
        )
        pol = default_policy()
        r = Retention(s, pol, plog, audit)
        idm = IdentityMap()
        idm.register("r1", "person")
        checks = {
            "ASSIGN": assign(s, task.id, p, NOW, _Dir()).status.value
            in ("ASSIGNED", "UNCHANGED", "UNASSIGNED"),
            "RESCHEDULE": reschedule(
                s, task.id, NOW + timedelta(days=9), "extension", p, NOW + timedelta(seconds=1)
            ),
            "REQUEUE": requeue_run(s, "evt-1:1", "stage:PROCESS", p, NOW) is not None
            and _requeue_allowed(s, p, key),
            "HOLD": r.hold(p, "review:obl-0", "legal hold ref", NOW),
            "PURGE": r.purge(p, "review:obl-0", "elapsed", LATE) is not PurgeStatus.DENIED,
            "RELEASE_HOLD": r.release(p, "review:obl-0", "released", NOW),
            "ERASE_IDENTITY": erase_identity(idm, audit, p, "r1", NOW) != "DENIED",
            "SUBMIT": submit_for_review(
                InMemoryWorkflowStore(),
                generation_result("obl-c"),
                SnapshotInputs(permitted_source=TEXT),
                p,
                NOW,
                {OWNER: TEXT},
            ).status.value
            != "DENIED",
            "RUN_PIPELINE": run_event(
                InMemoryWorkflowStore(), FakePipeline(1), EVENT, p, NOW, lambda *a: True
            ).status.value
            != "UNSTARTED",
            "TICK": bool(tick(s, NOW + timedelta(days=400), _Dir(), p))
            or role in ("SYSTEM", "OPERATOR"),
        }
        if role in ("COORDINATOR", "OPERATOR", "SYSTEM", "REVIEWER", "PUBLISHER", "AUDITOR"):
            for op, allowed in checks.items():
                n += 1
                want = role in matrix.roles_for(op)
                bad += bool(allowed) != want and not (
                    op in ("HOLD", "RELEASE_HOLD") and role == "OPERATOR" and not allowed
                )
    return bad, n


def _requeue_allowed(s: Any, p: Principal, key: str) -> bool:
    out = requeue_notification(s, key, p, "reason", NOW)
    return out.value != "DENIED"


def _review_authorizer(matrix: Any) -> tuple[int, int]:
    bad = n = 0
    for role in ("REVIEWER", "PUBLISHER", "AUDITOR"):
        actor = Actor(id="x", roles=(Role(role),))
        for action in Action:
            allowed = review_authorize(actor, action, [], ReviewConfig()).allowed
            n += 1
            bad += allowed != (role in matrix.roles_for(action.value))
    return bad, n


def _app_conformance(matrix: Any) -> tuple[int, int]:
    bad = n = 0
    for kind in ("open", "closed_participant", "closed_other"):
        run = ReviewRun("obl-gov", random.Random(2))
        if kind != "open":
            actor = GOV_ACTORS["alice"]
            task = claim(run.task, actor.id, run.clock, 900)
            req = ActionRequest(action=Action.REJECT, task_id=task.id, base_version=run.store.version("obl-gov"), actor=actor, at=run.clock,
                                reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
            apply(run.store, task, req, ReviewConfig(), run.texts)
        inner = ReviewApp(
            run.store,
            {run.task.id: run.task},
            lambda env: GOV_ACTORS.get(env.get("HTTP_X_ACTOR", "")),
            lambda env: "t",
            run.texts,
            lambda: CLOCK,
        )
        app = GovernedApp(inner, matrix, ChainLog("access"), lambda: CLOCK)
        participants = {r.actor_id for r in run.store.get("obl-gov")[1]}
        status = run.store.get("obl-gov")[0].status.value
        facts = Facts(
            task_id=run.task.id,
            status=status,
            terminal=status in ("PUBLISHED", "REJECTED"),
            participants=tuple(participants),
        )
        for name, a in GOV_ACTORS.items():
            data = b""
            env = {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": f"/tasks/{run.task.id}",
                "HTTP_X_ACTOR": name,
                "CONTENT_LENGTH": "0",
                "wsgi.input": io.BytesIO(data),
            }
            status, _ = _run(app, env)

            want = _oracle({r.value for r in a.roles}, a.id, "READ_TASK", facts)
            n += 1
            bad += (status.startswith("200")) != want
    return bad, n


def _post(app: Any, path: str, actor: str, body: dict[str, object]) -> str:
    data = urlencode(body, doseq=True).encode()
    env = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "HTTP_X_ACTOR": actor,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
    }
    status, _ = _run(app, env)

    return status


def _audit_runs(matrix: Any, tot: Counter[str]) -> None:
    for i in range(SEEDS):
        rng = random.Random(SEED0 + i)
        run = ReviewRun("obl-gov", random.Random(i))
        inner = ReviewApp(
            run.store,
            {run.task.id: run.task},
            lambda env: GOV_ACTORS.get(env.get("HTTP_X_ACTOR", "")),
            lambda env: "t",
            run.texts,
            lambda: CLOCK,
        )
        audit = ChainLog("access")
        app = GovernedApp(inner, matrix, audit, lambda: CLOCK)
        for _ in range(30):
            audit.fail_next = 1 if rng.random() < 0.25 else 0
            actor = rng.choice(list(GOV_ACTORS) + ["stranger"])
            path = rng.choice([f"/tasks/{run.task.id}", "/tasks", "/tasks/nope"])
            env = {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": path,
                "HTTP_X_ACTOR": actor,
                "CONTENT_LENGTH": "0",
                "wsgi.input": io.BytesIO(b""),
            }
            status, body = _run(app, env)

            audit.fail_next = 0
            tot["requests"] += 1
            assert body is not None and status
        c = app.counters
        tot["accounting_bad"] += (
            (c.attempted != c.recorded + c.gap)
            or len(audit.records) != c.recorded
            or len({r.id for r in audit.records}) != len(audit.records)
            or not audit.verified()
        )
        tot["audit_runs"] += 1
        tot["gaps"] += c.gap
        blob = json.dumps([r.model_dump(mode="json") for r in audit.records])
        tot["artifacts"] += 1
        tot["content_hits"] += bool(pattern_scan({"access": blob}, [TEXT, "Pengendali"]))


def _failing_audit(matrix: Any, tot: Counter[str]) -> None:
    for i in range(SEEDS):
        run = ReviewRun("obl-gov", random.Random(i))
        inner = ReviewApp(
            run.store,
            {run.task.id: run.task},
            lambda env: GOV_ACTORS.get(env.get("HTTP_X_ACTOR", "")),
            lambda env: "t",
            run.texts,
            lambda: CLOCK,
        )
        audit = ChainLog("access")
        app = GovernedApp(inner, matrix, audit, lambda: CLOCK)
        for name in GOV_ACTORS:
            for path in (f"/tasks/{run.task.id}", "/tasks"):
                audit.fail_next = 1
                env = {
                    "REQUEST_METHOD": "GET",
                    "PATH_INFO": path,
                    "HTTP_X_ACTOR": name,
                    "CONTENT_LENGTH": "0",
                    "wsgi.input": io.BytesIO(b""),
                }
                status, body = _run(app, env)

                tot["failing_requests"] += 1
                tot["served_with_failing_audit"] += int(status.startswith("200") or TEXT in body)


def _retention_runs(tot: Counter[str]) -> None:
    pol = default_policy()
    OPR = Principal(id="op", roles=(WorkflowRole.OPERATOR,))
    for _ in range(SEEDS):
        s = InMemoryWorkflowStore()
        run_event(s, FakePipeline(2), EVENT, SYSTEM, NOW, queue_emitter(s, Everyone(), SYSTEM, NOW))
        _close(s, "obl-0")
        audit, plog = ChainLog("access"), ChainLog("purge")
        r = Retention(s, pol, plog, audit)
        r.hold(OPR, "review:obl-0", "legal hold ref", NOW + timedelta(seconds=9))
        attempts = [
            ("review:obl-0", LATE),
            ("review:obl-1", LATE),
            ("review:obl-0", NOW + timedelta(days=1)),
        ]
        for stream, when in attempts:
            tot["unsafe_attempts"] += 1
            tot["unsafe_done"] += r.purge(OPR, stream, "elapsed", when) is PurgeStatus.APPLIED
        r.release(OPR, "review:obl-0", "released", LATE)
        before = set(r.streams())
        r.purge(OPR, "review:obl-0", "elapsed", LATE)
        gone = before - set(r.streams())
        intents = {x.fields["stream"] for x in plog.records if x.kind == "PURGE_INTENT"}
        tot["deletions"] += len(gone)
        tot["deletions_no_intent"] += sum(1 for g in gone if g.replace(":", "_") not in intents)
        for crash in ("none", "intent", "delete", "applied"):
            s2 = InMemoryWorkflowStore()
            run_event(
                s2, FakePipeline(1), EVENT, SYSTEM, NOW, queue_emitter(s2, Everyone(), SYSTEM, NOW)
            )
            _close(s2, "obl-0")
            pl2 = ChainLog("purge")
            r2 = Retention(s2, pol, pl2, ChainLog("access"))
            r2.fail_after = crash if crash in ("intent", "delete") else None
            try:
                r2.purge(OPR, "review:obl-0", "elapsed", LATE)
            except RuntimeError:
                pass
            r2.recover(LATE + timedelta(seconds=1))
            kinds = [x.kind for x in pl2.records]
            present = "review:obl-0" in r2.streams()
            tot["crash_points"] += 1
            tot["crash_bad"] += (("PURGE_APPLIED" in kinds and present) or ("PURGE_CANCELLED" in kinds and not present) or not pl2.verified()
                                 or ("PURGE_APPLIED" in kinds) == ("PURGE_CANCELLED" in kinds))  # fmt: skip
        idm = IdentityMap()
        idm.register("r1", "person")
        erase_identity(idm, audit, OPR, "r1", NOW)
        tot["erasures"] += 1
        tot["links_after"] += idm.resolve("r1") is not None


def _close(s: Any, oid: str) -> None:
    task = next(t for t in s.tasks.values() if t.obligation_id == oid)
    t = claim(task, ACTORS[0].id, NOW + timedelta(seconds=5), 900)
    req = ActionRequest(action=Action.REJECT, task_id=t.id, base_version=s.review.version(oid), actor=ACTORS[0], at=NOW + timedelta(seconds=6),
                        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
    apply(s.review, t, req, ReviewConfig(), {OWNER: TEXT})


def _corruption(tot: Counter[str]) -> None:
    for i in range(SEEDS):
        for mode in Corruption:
            rng = random.Random(i)
            s = InMemoryWorkflowStore()
            run_event(
                s, FakePipeline(2), EVENT, SYSTEM, NOW, queue_emitter(s, Everyone(), SYSTEM, NOW)
            )
            audit, plog = ChainLog("access"), ChainLog("purge")
            for k in range(4):
                audit.append(
                    "ACCESS_ALLOWED",
                    CLOCK,
                    operation="READ_TASK",
                    actor="a",
                    resource=f"t{k}",
                    outcome="ALLOWED",
                )
                plog.append("PURGE_INTENT", CLOCK, stream=f"s{k}")
            from regulus.reliability.guard import GuardedStore

            g = GuardedStore(s)
            from regulus.workflow import Kind

            g.append(
                "obligation:obl-0",
                Kind.SUBMIT_REFUSED,
                SYSTEM,
                NOW + timedelta(days=1),
                None,
                {"reasons": ["probe"]},
            )
            audit.records = list(
                corrupt(
                    tuple(audit.records),
                    mode,
                    rng,
                    foreign=audit.records[0].model_copy(update={"id": "x"}),
                )
            )
            plog.records = list(
                corrupt(
                    tuple(plog.records),
                    mode,
                    rng,
                    foreign=plog.records[0].model_copy(update={"id": "p"}),
                )
            )
            s.streams["obligation:obl-0"] = corrupt(
                s.streams["obligation:obl-0"],
                mode,
                rng,
                foreign=s.streams["obligation:obl-0"][0].model_copy(update={"id": "w"}),
            )
            rep = verify_all(s, audit, plog, g._tips)
            tot["corruptions"] += 3
            tot["undetected"] += 3 - sum(
                x in rep.broken for x in ("log:access", "log:purge", "obligation:obl-0")
            )


def _free_text(matrix: Any, tot: Counter[str]) -> None:
    inputs = [
        "mail ana@example.com",
        "https://x.example/y",
        "+62 812 3456 7890",
        "password: abcdef12",
        "x" * 501,
    ]
    for i in range(SEEDS):
        for v in inputs:
            run = ReviewRun("obl-gov", random.Random(i))
            inner = ReviewApp(
                run.store,
                {run.task.id: run.task},
                lambda env: GOV_ACTORS.get(env.get("HTTP_X_ACTOR", "")),
                lambda env: "t",
                run.texts,
                lambda: CLOCK,
            )
            app = GovernedApp(inner, matrix, ChainLog("access"), lambda: CLOCK)
            _post(app, f"/tasks/{run.task.id}/claim", "alice", {"csrf": "t"})
            t = inner.tasks[run.task.id]
            _post(app, f"/tasks/{run.task.id}/action", "alice", {"csrf": "t", "action": "REJECT", "base_version": run.store.version("obl-gov"),
                                                                "snapshot_hash": t.snapshot.hash, "reject_code": "OTHER", "reject_text": v, "reason": v})  # fmt: skip
            tot["ft_inputs"] += 1
            stored = " ".join(
                str(r.decision.reason) + str(r.reject_reason.text if r.reject_reason else "")
                for r in run.store.get("obl-gov")[1]
            )
            tot["ft_stored"] += v in stored


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    matrix = default_matrix()
    entries = default_inventory()
    problems = inventory.check(entries)
    nfields = sum(len(e["fields"]) for e in entries)  # type: ignore[arg-type,misc]
    tot: Counter[str] = Counter()
    mism = n = 0
    role_sets = [set(c) for r in range(0, 3) for c in itertools.combinations(ROLES, r)]
    for roles, op, facts in itertools.product(role_sets, Operation, FACTS):
        n += 1
        mism += authorize(matrix, "me", roles, op.value, facts).allowed != _oracle(
            roles, "me", op.value, facts
        )
    for fn in (_workflow_conformance, _review_authorizer, _app_conformance):
        bad_i, n_i = fn(matrix)
        mism, n = mism + bad_i, n + n_i
    unlisted = 0
    for name in ("DELETE_ALL", "READ_EVERYTHING", "", "approve", "PURGE "):
        unlisted += authorize(matrix, "me", set(ROLES), name, FACTS[0]).allowed
    sep = 0
    props = 0
    for op in WRITES:
        props += 1
        sep += "AUDITOR" in matrix.roles_for(op.value)
    for role in ("OPERATOR", "COORDINATOR", "SYSTEM"):
        props += 1
        sep += any(role in matrix.roles_for(op.value) for op in REVIEW_OPS)
    props += 1
    sep += "assignee" in Facts.model_fields
    _audit_runs(matrix, tot)
    _failing_audit(matrix, tot)
    _retention_runs(tot)
    _corruption(tot)
    _free_text(matrix, tot)
    store_findings = Counter[str]()
    scanned = 0
    for i in range(SEEDS):
        run = ReviewRun(f"obl-{i}", random.Random(SEED0 + i))
        for _ in range(20):
            run.step()

        class W:
            review = run.store

        store_findings.update(scan_stores(W()))  # type: ignore[arg-type]
        scanned += sum(len(run.store.get(o)[1]) for o in run.store._initial)
    b.population(POP, "seeded governance runs over the reference stores and the governed review app", f"seeds {SEED0}..{SEED0 + SEEDS - 1}", SEEDS,
                 "evaluation harness", "reference stores and fakes; demonstrates controls, makes no compliance claim")  # fmt: skip
    m = b.metric

    def add(
        id: str,
        name: str,
        num: str,
        den: str,
        nv: float,
        dv: float,
        gate: Gate | None = HARD0,
        cls: EvidenceClass = EC.PROPERTY,
        note: str = "",
    ) -> None:
        b.record(m(f"{L}.{id}", L, name, POP, num, den, cls, gate), nv, dv, note)

    add(
        "unclassified_fields",
        "unclassified field rate",
        "stored fields without a classification",
        "stored fields",
        sum("not classified" in p for p in problems),
        nfields,
        cls=EC.REGRESSION,
    )
    add(
        "stale_inventory_entries",
        "stale inventory entry rate",
        "entries naming a missing field or a model that is not stored",
        "inventory entries",
        sum(("stale" in p or "not stored" in p) for p in problems),
        len(entries),
        cls=EC.REGRESSION,
    )
    add(
        "access_mismatches",
        "access mismatch rate",
        "role, operation and resource-fact combinations where an enforcing component disagrees with the matrix or resource rules",
        "combinations checked",
        mism,
        n,
        note="authorize, the workflow operator functions, the Phase 9 authorizer and the governed app; BASELINE_UPDATE is enforced by repository review, not code",
    )
    add(
        "unlisted_operations_allowed",
        "unlisted operations allowed",
        "unlisted operations that were allowed",
        "unlisted operations tried",
        unlisted,
        5,
    )
    add(
        "separation_violations",
        "separation property violation rate",
        "violated separation properties",
        "separation properties",
        sep,
        props,
    )
    add(
        "audit_accounting_violations",
        "audit accounting violation rate",
        "runs where attempted differs from recorded plus gap, a record is missing or duplicated, or the chain fails",
        "seeded request runs",
        tot["accounting_bad"],
        tot["audit_runs"],
        note=f"{tot['gaps']} audit gaps injected and counted",
    )
    add(
        "restricted_served_with_audit_failing",
        "restricted resources served with the audit failing",
        "responses that served a restricted resource",
        "requests with the audit sink failing",
        tot["served_with_failing_audit"],
        tot["failing_requests"],
    )
    add(
        "content_in_audit_artifacts",
        "content in audit artifacts",
        "audit artifacts containing a forbidden pattern or text",
        "audit artifacts scanned",
        tot["content_hits"],
        tot["artifacts"],
    )
    add(
        "unsafe_purges",
        "unsafe purge rate",
        "purges applied to unexpired, non-terminal or held streams",
        "purge attempts of those kinds",
        tot["unsafe_done"],
        tot["unsafe_attempts"],
    )
    add(
        "purges_without_intent",
        "deletions without a purge intent",
        "deleted streams with no PURGE_INTENT",
        "deleted streams",
        tot["deletions_no_intent"],
        tot["deletions"],
    )
    add(
        "contradictory_purge_evidence",
        "contradictory purge evidence after a crash",
        "crash points where the purge log and the store disagree after recovery",
        "crash points tried",
        tot["crash_bad"],
        tot["crash_points"],
        note="before the intent, after the intent, after the delete, after applied",
    )
    add(
        "identity_links_surviving_erasure",
        "identity links surviving erasure",
        "resolvable links after erase_identity",
        "erasures",
        tot["links_after"],
        tot["erasures"],
        note="opaque ids remain in historical chains by design and are not claimed anonymous",
    )
    add(
        "undetected_chain_corruption",
        "undetected corruption in chained logs",
        "injected corruptions verify_all did not report",
        "injected corruptions (access audit, purge log, workflow stream with a tip reference)",
        tot["undetected"],
        tot["corruptions"],
        cls=EC.REGRESSION,
    )
    add(
        "forbidden_free_text_stored",
        "forbidden free text stored",
        "rejected-class inputs found stored",
        "rejected-class inputs submitted",
        tot["ft_stored"],
        tot["ft_inputs"],
        cls=EC.REGRESSION,
    )
    add(
        "free_text_findings",
        "free-text findings in stored records",
        "scan findings in stored review records",
        "review records scanned",
        sum(store_findings.values()),
        scanned,
        gate=None,
        note="counted by record type, never by value",
    )
    pub = m(
        f"{L}.audit_gap_public",
        L,
        "audit gaps on public resources",
        POP,
        "public requests served with an audit gap",
        "public requests with the sink failing",
        EC.PROPERTY,
    )
    b.unmeasurable(
        pub,
        "no public resource is served through the governed app; the stylesheet is not a review page",
    )
