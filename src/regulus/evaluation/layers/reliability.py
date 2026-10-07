import random
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from regulus.documents import DocStatus, process
from regulus.documents.evaluate import load_gold, reader_for
from regulus.notifications import (
    DeliveryResult,
    DeliveryStatus,
    NotificationEvent,
    NotificationKind,
    State,
    deliver_due,
    notification_state,
    queue_emitter,
    queue_notification,
    requeue_notification,
)
from regulus.reliability.faults import Fault, FaultKind, FaultPlan
from regulus.reliability.guard import GuardedReviewStore, GuardedStore, IntegrityError
from regulus.reliability.invariants import (
    corrupt_review_logs,
    corrupt_streams,
    duplicate_decisions,
    retry_bound_violations,
    state_safety,
    unaccounted_items,
)
from regulus.reliability.matrix import load, validate
from regulus.reliability.wrappers import (
    Corruption,
    FaultyChannel,
    FaultyPipeline,
    FaultyReviewStore,
    FaultyStore,
    corrupt,
)
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
from regulus.workflow import (
    SYSTEM,
    Crash,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Kind,
    SnapshotInputs,
    SubmitStatus,
    obligation_stream,
    requeue,
    run_event,
    run_state,
    source_complete_for,
    submit_for_review,
)
from regulus.workflow.runs import Status as UnitStatus

from ..builder import EC, HARD0, HARD1, Builder
from ..harness import (
    ACTORS,
    NOW,
    OWNER,
    TEXT,
    Everyone,
    FakeChannel,
    FakePipeline,
    ReviewRun,
    generation_result,
)
from .workflow import CFG, DRAIN, EVENT, OPERATOR, logical

from ..models import EvidenceClass, Gate  # isort: skip
from regulus.workflow import run_key  # isort: skip

L = "reliability"
POP = "reliability.harness_runs"
SEEDS, SEED0 = 20, 1414000
RUN = run_key(EVENT.id, "1")
POINTS = [
    "pipeline.process",
    "pipeline.generate",
    "pipeline.enrich",
    "store.commit_submission",
    "store.append",
    "channel.send",
]
KINDS = [
    FaultKind.UNAVAILABLE,
    FaultKind.TIMEOUT_BEFORE,
    FaultKind.TIMEOUT_AFTER,
    FaultKind.CRASH,
    FaultKind.PERMANENT,
]


class _Chan:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, message, recipients, idempotency_key):  # type: ignore[no-untyped-def]
        if idempotency_key not in self.sent:
            self.sent.append(idempotency_key)
        return DeliveryResult(status=DeliveryStatus.SENT)


def _recover(store, pipe) -> None:  # type: ignore[no-untyped-def]
    t = NOW + timedelta(days=1)
    for _ in range(12):
        st = run_state(store, RUN)
        for stage, u in st.stages.items():
            if u.status is UnitStatus.DEAD_LETTER:
                requeue(store, RUN, f"stage:{stage.value}", OPERATOR, t)
        for item, u in st.items.items():
            if u.status is UnitStatus.DEAD_LETTER:
                requeue(store, RUN, f"item:{item}", OPERATOR, t)
        t += timedelta(hours=2)
        run_event(
            store, pipe, EVENT, SYSTEM, t, queue_emitter(store, Everyone(), SYSTEM, t), "1", DRAIN
        )


def _settle(store) -> None:  # type: ignore[no-untyped-def]
    t = NOW + timedelta(days=3)
    for _ in range(4):
        for stream in store.streams_with("notification:"):
            key = stream[len("notification:") :]
            st = notification_state(store, key)
            if st is not None and st.state is State.DEAD_LETTER:
                requeue_notification(store, key, OPERATOR, "recovery after faults were removed", t)
        t += timedelta(hours=1)
        deliver_due(store, _Chan(), SYSTEM, t, DRAIN)


def _clean(store_cls: type[InMemoryWorkflowStore] | type[IntentWorkflowStore]) -> tuple:  # type: ignore[type-arg]
    s = store_cls()
    run_event(
        s, FakePipeline(3), EVENT, SYSTEM, NOW, queue_emitter(s, Everyone(), SYSTEM, NOW), "1", CFG
    )
    _settle(s)
    return logical(s)


def _normalized(store: Any, plan: FaultPlan) -> tuple[tuple[Any, ...], bool]:
    # a PERMANENT channel rejection is a terminal, visible FAILED_PERMANENT (no requeue by design);
    # each such notification must be accounted for by a fired permanent channel fault
    rejected = [
        s for s in store.streams_with("notification:")
        if (n := notification_state(store, s[len("notification:") :])) is not None and n.state is State.FAILED_PERMANENT
    ]  # fmt: skip
    fired = sum(
        1 for f in plan.fired if f.kind is FaultKind.PERMANENT and f.point == "channel.send"
    )
    base = logical(store)
    notes = [(n, "DELIVERED" if n in {f"{r}" for r in rejected} else st) for n, st in base[2]]
    return (base[0], base[1], notes), len(rejected) > fired


def _fault_runs(tot: Counter[str]) -> None:
    for i in range(SEEDS):
        for store_cls in (InMemoryWorkflowStore, IntentWorkflowStore):
            plan = FaultPlan.seeded(SEED0 + i, POINTS, KINDS, 3)
            s = store_cls()
            pipe, store, chan = (
                FaultyPipeline(FakePipeline(3), plan),
                FaultyStore(s, plan),
                FaultyChannel(_Chan(), plan),
            )
            t = NOW
            unsafe = bound = False
            for _ in range(10):
                t += timedelta(seconds=30)
                aborted = False
                try:
                    rep = run_event(
                        store,
                        pipe,
                        EVENT,
                        SYSTEM,
                        t,
                        queue_emitter(store, Everyone(), SYSTEM, t),
                        "1",
                        CFG,
                    )
                    aborted = rep.store_unavailable
                    deliver_due(s, chan, SYSTEM, t, CFG)
                except Crash:
                    aborted = True
                unsafe |= bool(state_safety(s))
                bound |= bool(retry_bound_violations(s, RUN, CFG.max_attempts))
                if not aborted:
                    tot["observed"] += len(run_state(s, RUN).item_ids)
                    tot["lost"] += unaccounted_items(s, RUN)
            plan.clear()
            _recover(s, FakePipeline(3))
            _settle(s)
            tot["runs"] += 1
            tot["unsafe"] += unsafe or bool(state_safety(s))
            tot["bound"] += bound
            got, perm = _normalized(s, plan)
            tot["divergent"] += got != _clean(store_cls) or perm


def _duplicates(tot: Counter[str]) -> None:
    for i in range(SEEDS):
        s = InMemoryWorkflowStore()
        pipe = FakePipeline(2)
        for k in range(3):
            run_event(
                s,
                pipe,
                EVENT,
                SYSTEM,
                NOW + timedelta(hours=k),
                queue_emitter(s, Everyone(), SYSTEM, NOW),
                "1",
                CFG,
            )
        tot["dup_inputs"] += 2
        tot["dup_effects"] += max(0, len(s.tasks) - 2) + max(
            0, len(s.streams_with("notification:")) - 2
        )
        res = generation_result(f"obl-dup{i}")
        for k in range(3):
            submit_for_review(
                s,
                res,
                SnapshotInputs(permitted_source=TEXT),
                SYSTEM,
                NOW + timedelta(hours=k),
                {OWNER: TEXT},
            )
        tot["dup_inputs"] += 2
        tot["dup_effects"] += max(
            0, sum(1 for t in s.tasks.values() if t.obligation_id == f"obl-dup{i}") - 1
        )
        run = ReviewRun("obl-rel", random.Random(SEED0 + i))
        run.task = claim(run.task, ACTORS[0].id, run.clock, 900)
        req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=run.store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                            reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
        for _ in range(3):
            apply(run.store, run.task, req, ReviewConfig(), run.texts)
        tot["dup_inputs"] += 2
        tot["dup_effects"] += max(0, len(run.store.get("obl-rel")[1]) - 1) + len(
            duplicate_decisions(run.store, "obl-rel")
        )


def _timeouts(tot: Counter[str]) -> None:
    ev = NotificationEvent(
        kind=NotificationKind.TASK_OVERDUE,
        subject="task-1",
        version="v",
        payload={"task_id": "task-1", "due_at": "2026-09-01T10:00:00+00:00"},
    )
    for phase, kind in (("before", FaultKind.TIMEOUT_BEFORE), ("after", FaultKind.TIMEOUT_AFTER)):
        for i in range(SEEDS):
            s = InMemoryWorkflowStore()
            key = queue_notification(s, ev, Everyone(), SYSTEM, NOW).key or ""
            inner = _Chan()
            chan = FaultyChannel(inner, FaultPlan([Fault(kind=kind, point="channel.send", call=1)]))
            deliver_due(s, chan, SYSTEM, NOW, CFG)
            deliver_due(s, chan, SYSTEM, NOW + timedelta(minutes=5), CFG)
            tot[f"to_{phase}_cases"] += 1
            tot[f"to_{phase}_second"] += max(0, inner.sent.count(key) - 1)
            st = IntentWorkflowStore()
            plan = FaultPlan([Fault(kind=kind, point="store.commit_submission", call=1)])
            res = generation_result(f"obl-to{i}")
            submit_for_review(
                FaultyStore(st, plan),
                res,
                SnapshotInputs(permitted_source=TEXT),
                SYSTEM,
                NOW,
                {OWNER: TEXT},
            )
            again = submit_for_review(
                st,
                res,
                SnapshotInputs(permitted_source=TEXT),
                SYSTEM,
                NOW + timedelta(seconds=1),
                {OWNER: TEXT},
            )
            tot[f"to_{phase}_cases"] += 1
            tot[f"to_{phase}_second"] += max(0, len(st.tasks) - 1) + (
                again.status not in (SubmitStatus.SUBMITTED, SubmitStatus.ALREADY_SUBMITTED)
            )
            run = ReviewRun("obl-rel", random.Random(SEED0 + i))
            inner_store = run.store
            run.store = FaultyReviewStore(
                inner_store, FaultPlan([Fault(kind=kind, point="review.commit", call=1)])
            )  # type: ignore[assignment]
            run.task = claim(run.task, ACTORS[0].id, run.clock, 900)
            req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=inner_store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                                reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
            apply(run.store, run.task, req, ReviewConfig(), run.texts)
            out = apply(run.store, run.task, req, ReviewConfig(), run.texts)
            tot[f"to_{phase}_cases"] += 1
            tot[f"to_{phase}_second"] += max(0, len(inner_store.get("obl-rel")[1]) - 1) + (
                out.status is Status.APPLIED and phase == "after"
            )


def _corruption(tot: Counter[str]) -> None:
    for i in range(SEEDS):
        for mode in Corruption:
            s = IntentWorkflowStore() if i % 2 else InMemoryWorkflowStore()
            run_event(
                s,
                FakePipeline(2),
                EVENT,
                SYSTEM,
                NOW,
                queue_emitter(s, Everyone(), SYSTEM, NOW),
                "1",
                CFG,
            )
            stream = obligation_stream("obl-0")
            guarded = GuardedStore(s)
            guarded.append(
                stream,
                Kind.SUBMIT_REFUSED,
                SYSTEM,
                NOW + timedelta(days=1),
                None,
                {"reasons": ["probe"]},
            )
            foreign = s.streams[stream][0].model_copy(update={"id": "wrec-foreign"})
            s.streams[stream] = corrupt(s.streams[stream], mode, random.Random(i), foreign=foreign)
            tot["injected"] += 1
            detected = stream in corrupt_streams(s)
            try:
                guarded.append(
                    stream,
                    Kind.SUBMIT_REFUSED,
                    SYSTEM,
                    NOW + timedelta(days=2),
                    None,
                    {"reasons": ["x"]},
                )
                accepted = True
            except IntegrityError:
                accepted = False
            tot["undetected"] += not (detected or not accepted)
            tot["attempts"] += 1
            tot["accepted"] += accepted
            run = ReviewRun("obl-rel", random.Random(SEED0 + i))
            for _ in range(80):
                run.step()
                if len(run.store.get("obl-rel")[1]) >= 3:
                    break
            log = run.store.get("obl-rel")[1]
            if len(log) < 3:
                continue
            run.store._log["obl-rel"] = corrupt(
                log, mode, random.Random(i), foreign=log[0].model_copy(update={"id": "rrec-x"})
            )
            tot["injected"] += 1
            tot["undetected"] += "obl-rel" not in corrupt_review_logs(run.store)
            guard = GuardedReviewStore(run.store)
            req = ActionRequest(action=Action.REJECT, task_id=run.task.id, base_version=run.store.version("obl-rel"), actor=ACTORS[0], at=run.clock,
                                reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
            claimed = claim(
                run.task.model_copy(
                    update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
                ),
                ACTORS[0].id,
                run.clock,
                900,
            )
            tot["attempts"] += 1
            tot["accepted"] += (
                apply(guard, claimed, req, ReviewConfig(), run.texts).status is Status.APPLIED
            )


def _weaker(tot: Counter[str], root: Path) -> None:
    for case in load_gold(root / "documents" / "gold.v1.json"):
        doc = process(f"rel:{case.case_id}".encode(), "PP-1-2026", reader_for(case))
        if doc.status in (DocStatus.PARTIAL, DocStatus.PROCESSED_WITH_ISSUES) and doc.articles:
            s = InMemoryWorkflowStore()
            out = submit_for_review(
                s,
                generation_result(f"obl-{len(case.case_id)}{case.case_id[:3]}"),
                SnapshotInputs(
                    source_complete=source_complete_for(doc.status.value), permitted_source=TEXT
                ),
                SYSTEM,
                NOW,
                {OWNER: TEXT},
            )
            tot["issue_tasks"] += 1
            tot["weaker"] += bool(out.task and out.task.snapshot.source_complete)


def _transparency(tot: Counter[str]) -> None:
    for i in range(SEEDS):
        plain, wrapped = InMemoryWorkflowStore(), InMemoryWorkflowStore()
        rng = random.Random(SEED0 + i)
        run_event(
            plain,
            FakePipeline(3, rng, 0.0),
            EVENT,
            SYSTEM,
            NOW,
            queue_emitter(plain, Everyone(), SYSTEM, NOW),
            "1",
            CFG,
        )
        plan = FaultPlan()
        w = FaultyStore(wrapped, plan)
        run_event(
            w,
            FaultyPipeline(FakePipeline(3), plan),
            EVENT,
            SYSTEM,
            NOW,
            queue_emitter(w, Everyone(), SYSTEM, NOW),
            "1",
            CFG,
        )
        chan_a, chan_b = FakeChannel(random.Random(i), 0.0), FakeChannel(random.Random(i), 0.0)
        deliver_due(plain, chan_a, SYSTEM, NOW, CFG)
        deliver_due(wrapped, FaultyChannel(chan_b, plan), SYSTEM, NOW, CFG)
        tot["transp_runs"] += 1
        tot["transp_diff"] += logical(plain) != logical(wrapped) or chan_a.keys != chan_b.keys


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    tot: Counter[str] = Counter()
    _fault_runs(tot)
    _duplicates(tot)
    _timeouts(tot)
    _corruption(tot)
    _weaker(tot, root)
    _transparency(tot)
    rows = load(root / "reliability" / "matrix.v1.json")
    problems = validate(rows, root.resolve().parent)
    covered = sum(
        1
        for r in rows
        if not any(
            p.startswith(f"{r.id}:")
            and ("does not exist" in p or "no test" in p or "nothing claims" in p)
            for p in problems
        )
    )
    b.population(POP, "seeded fault, duplicate, timeout and corruption runs over fake infrastructure", f"seeds {SEED0}..{SEED0 + SEEDS - 1}, both stores", SEEDS,
                 "evaluation harness", "in-memory stores and fakes; describes failure semantics, not any real system's availability or durability")  # fmt: skip
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
        "state_safety_violations",
        "state-safety violation rate (G1, G2)",
        "fault runs with any state-safety violation after a run round or after recovery",
        "seeded fault runs",
        tot["unsafe"],
        tot["runs"],
        note="1 to 3 faults per run, both stores",
    )
    add(
        "lost_items",
        "lost item rate (G3)",
        "items with no state after a run returned normally",
        "items observed after normal runs",
        tot["lost"],
        tot["observed"],
    )
    add(
        "duplicate_effects",
        "duplicate logical effect rate (G4, G7)",
        "extra tasks, notifications or decisions after re-delivery",
        "re-delivered inputs",
        tot["dup_effects"],
        tot["dup_inputs"],
    )
    add(
        "undetected_corruption",
        "undetected corruption rate (G5)",
        "injected corruptions neither detected by verification nor refused by a guarded write",
        "injected corruptions",
        tot["undetected"],
        tot["injected"],
        cls=EC.REGRESSION,
        note="modification, deletion, reordering, truncation, splicing on ledger streams and review logs",
    )
    add(
        "writes_on_corrupted_streams",
        "writes accepted on corrupted streams (G5)",
        "guarded writes accepted on a corrupted stream or log",
        "guarded writes attempted on corrupted streams",
        tot["accepted"],
        tot["attempts"],
        cls=EC.REGRESSION,
    )
    add(
        "recovery_divergence",
        "recovery divergence rate (G6)",
        "fault runs whose final logical state differs from the uninterrupted run once faults are removed",
        "seeded fault runs",
        tot["divergent"],
        tot["runs"],
    )
    add(
        "retry_bound_violations",
        "unbounded or silent retry rate (G8)",
        "runs exceeding the attempt bound or retrying without a next attempt",
        "seeded fault runs",
        tot["bound"],
        tot["runs"],
    )
    add(
        "weaker_snapshots",
        "weaker-than-shown snapshot rate (G9)",
        "tasks from a partial or issue-bearing document built without the incomplete flag",
        "tasks from partial or issue-bearing documents",
        tot["weaker"],
        tot["issue_tasks"],
        cls=EC.REGRESSION,
    )
    add(
        "second_effects_after_timeout_before",
        "second effects after a timeout before the effect (G10)",
        "second effects",
        "timeout-before-effect cases (channel, submission, review)",
        tot["to_before_second"],
        tot["to_before_cases"],
    )
    add(
        "second_effects_after_timeout_after",
        "second effects after a timeout after the effect (G10)",
        "second effects",
        "timeout-after-effect cases (channel, submission, review)",
        tot["to_after_second"],
        tot["to_after_cases"],
    )
    add(
        "matrix_coverage",
        "failure matrix coverage",
        "matrix rows with at least one existing claiming test",
        "matrix rows",
        covered,
        len(rows),
        HARD1,
        EC.REGRESSION,
    )
    add(
        "matrix_integrity",
        "failure matrix integrity violation rate",
        "matrix defects (unknown fault, bad guarantee id, missing test, unknown claim)",
        "matrix rows",
        len(problems),
        len(rows),
        HARD0,
        EC.REGRESSION,
    )
    add(
        "wrapper_transparency",
        "fault-wrapper transparency violation rate",
        "runs whose results differ with the wrappers present and no fault planned",
        "seeded runs",
        tot["transp_diff"],
        tot["transp_runs"],
    )
