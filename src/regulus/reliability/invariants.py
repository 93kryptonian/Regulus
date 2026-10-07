from collections.abc import Mapping, Sequence

from regulus.domain import ObligationStatus as S
from regulus.review import ReplayError, ReviewRecord, ReviewTask, replay, verify_chain
from regulus.review.store import InMemoryReviewStore
from regulus.workflow import Phase, WorkflowStore, run_state
from regulus.workflow import verify_chain as verify_workflow_chain
from regulus.workflow.runs import Status as UnitStatus


def state_safety(store: WorkflowStore) -> list[str]:
    out: list[str] = []
    for tid, task in sorted(store.tasks.items()):
        if (
            not store.registered(task.obligation_id)
            and store.submission(task.obligation_id).phase is not Phase.INTENT
        ):
            out.append(f"{tid}: task for an unregistered obligation")
    for oid in sorted(store.review._initial):
        if not any(t.obligation_id == oid for t in store.tasks.values()):
            out.append(f"{oid}: registered without a task")
        ob, log = store.review.get(oid)
        if ob.status is S.PENDING_REVIEW and not any(
            t.obligation_id == oid for t in store.tasks.values()
        ):
            out.append(f"{oid}: PENDING_REVIEW without a task")
        if store.submission(oid).phase is Phase.NONE:
            out.append(f"{oid}: registered without a submission record")
        try:
            if replay(store.review._initial[oid], log) != ob:
                out.append(f"{oid}: state differs from the replay of its log")
        except ReplayError:
            out.append(f"{oid}: log does not replay")
    for stream in store.streams_with("obligation:"):
        oid = stream.split(":", 1)[1]
        if store.submission(oid).phase is Phase.COMPLETE and not store.registered(oid):
            out.append(f"{oid}: complete submission without an obligation")
    return out


def unaccounted_items(store: WorkflowStore, run: str) -> int:
    st = run_state(store, run)
    if st.stage_done("GENERATE") is False:
        return 0
    return sum(1 for i in st.item_ids if i not in st.items)


def duplicate_decisions(store: InMemoryReviewStore, oid: str) -> list[str]:
    _, log = store.get(oid)
    out = []
    ids = [r.id for r in log]
    dec = [r.decision.id for r in log]
    if len(set(ids)) != len(ids):
        out.append("duplicate record ids")
    if len(set(dec)) != len(dec):
        out.append("duplicate decision ids")
    if not verify_chain(log):
        out.append("chain broken")
    terminal = [r for r in log if r.decision.to_status in (S.APPROVED, S.REJECTED)]
    if len({(r.base_version, r.decision.to_status) for r in terminal}) != len(terminal):
        out.append("the same decision recorded twice for one version")
    return out


def corrupt_streams(store: WorkflowStore) -> list[str]:
    streams = [
        *store.streams_with("obligation:"),
        *store.streams_with("notification:"),
        *store.streams_with("task:"),
        *store.streams_with("run:"),
    ]
    return [s for s in streams if not verify_workflow_chain(store.ledger(s))]


def corrupt_review_logs(store: InMemoryReviewStore) -> list[str]:
    bad = []
    for oid in sorted(store._initial):
        state, log = store.get(oid)
        try:
            ok = verify_chain(log) and replay(store._initial[oid], log) == state
        except ReplayError:
            ok = False
        if not ok:
            bad.append(oid)
    return bad


def retry_bound_violations(store: WorkflowStore, run: str, max_attempts: int) -> list[str]:
    st = run_state(store, run)
    out = []
    for stage, unit in st.stages.items():
        if unit.attempts > max_attempts:
            out.append(f"stage {stage.value}: {unit.attempts} attempts")
    for item, unit in st.items.items():
        if unit.status is UnitStatus.RETRYING and unit.next_attempt_at is None:
            out.append(f"item {item}: retrying without a next attempt")
    return out


def weaker_snapshots(
    tasks: Sequence[ReviewTask], complete_by_obligation: Mapping[str, bool]
) -> list[str]:
    return [
        t.id
        for t in tasks
        if not complete_by_obligation.get(t.obligation_id, True) and t.snapshot.source_complete
    ]


def decisions(store: InMemoryReviewStore, oid: str) -> Sequence[ReviewRecord]:
    return store.get(oid)[1]
