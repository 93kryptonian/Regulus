from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from regulus.domain import EventType, RegulatoryEvent
from regulus.domain.base import Model
from regulus.generation import GenerationResult
from regulus.review import StoreError

from .intake import SnapshotInputs, submit_for_review
from .models import Kind, Principal, SubmitStatus, WorkflowRole
from .runs import RunState, RunStatus, Stage, Status, project_run
from .schedule import ScheduleConfig, next_attempt_at
from .store import ClockRegression, WorkflowStore

Emit = Callable[[str, str, str, dict[str, str | int]], bool]
PROCESSABLE = {EventType.NEW, EventType.AMEND, EventType.REPEAL, EventType.PARTIAL_REPEAL}
PERMANENT_SUBMIT = {
    SubmitStatus.CONFLICT,
    SubmitStatus.NOT_GENERATED,
    SubmitStatus.NOT_SUBMITTABLE,
    SubmitStatus.EVIDENCE_INVALID,
}


class Unavailable(Exception):
    pass


class Permanent(Exception):
    pass


class Pipeline(Protocol):
    def process(self, event: RegulatoryEvent) -> str: ...

    def generate(self, event: RegulatoryEvent, ref: str) -> Sequence[str]: ...

    def result(self, item_id: str) -> GenerationResult: ...

    def enrich(self, item_id: str) -> SnapshotInputs: ...

    def owner_texts(self, ref: str) -> Mapping[str, str]: ...


class RunReport(Model):
    run_key: str
    status: RunStatus
    submitted: int = 0
    store_unavailable: bool = False


def run_key(event_id: str, config_version: str) -> str:
    return f"{event_id}:{config_version}"


def run_stream(key: str) -> str:
    return f"run:{key}"


def run_state(store: WorkflowStore, key: str) -> RunState:
    return project_run(store.ledger(run_stream(key)))


def _due(unit_next: datetime | None, now: datetime) -> bool:
    return unit_next is None or unit_next <= now


def run_event(
    store: WorkflowStore,
    pipeline: Pipeline,
    event: RegulatoryEvent,
    principal: Principal,
    now: datetime,
    emit: Emit,
    config_version: str = "1",
    cfg: ScheduleConfig | None = None,
) -> RunReport:
    cfg = cfg or ScheduleConfig()
    key = run_key(event.id, config_version)
    stream = run_stream(key)
    if not {WorkflowRole.SYSTEM, WorkflowRole.OPERATOR} & set(principal.roles):
        return RunReport(run_key=key, status=run_state(store, key).status)
    try:
        return _run(store, pipeline, event, principal, now, emit, key, stream, cfg)
    except (StoreError, ClockRegression):
        return RunReport(run_key=key, status=run_state(store, key).status, store_unavailable=True)


def _fail(
    store: WorkflowStore,
    stream: str,
    principal: Principal,
    now: datetime,
    cfg: ScheduleConfig,
    key: str,
    attempts: int,
    err: str,
    emit: Emit,
    run: str,
    stage_label: str,
    retry_kind: Kind,
    dead_kind: Kind,
    retryable: bool,
) -> None:
    attempt = attempts + 1
    nxt = next_attempt_at(now, attempts, cfg) if retryable else None
    if nxt is None:
        store.append(
            stream, dead_kind, principal, now, key, {"attempt": attempt, "error_class": err}
        )
        emit(
            "DEAD_LETTER",
            run,
            f"{key}:{attempt}",
            {"run_id": run, "stage": stage_label, "error_class": err},
        )
    else:
        store.append(
            stream, retry_kind, principal, now, key,
            {"attempt": attempt, "error_class": err, "next_attempt_at": nxt.isoformat()},
        )  # fmt: skip
        emit(
            "PIPELINE_STAGE_FAILED", run, f"{key}:{attempt}",
            {"run_id": run, "stage": stage_label, "error_class": err},
        )  # fmt: skip


def _run(
    store: WorkflowStore,
    pipeline: Pipeline,
    event: RegulatoryEvent,
    principal: Principal,
    now: datetime,
    emit: Emit,
    key: str,
    stream: str,
    cfg: ScheduleConfig,
) -> RunReport:
    state = project_run(store.ledger(stream))
    if state.rejected:
        return RunReport(run_key=key, status=RunStatus.REJECTED)
    if event.type not in PROCESSABLE:
        store.append(
            stream, Kind.RUN_REJECTED, principal, now, details={"reason": event.type.value}
        )
        return RunReport(run_key=key, status=RunStatus.REJECTED)
    if not state.started:
        store.append(stream, Kind.RUN_STARTED, principal, now, details={"event": event.id})
    if state.stage(Stage.DETECTED).status is not Status.DONE:
        kind = "REGULATION_DETECTED" if event.type is EventType.NEW else "AMENDMENT_DETECTED"
        payload: dict[str, str | int] = {"regulation_id": event.regulation_id, "event_id": event.id}
        if kind == "AMENDMENT_DETECTED":
            payload["target_id"] = event.target_id or ""
        if emit(kind, event.id, key, payload):
            store.append(stream, Kind.STAGE_DONE, principal, now, Stage.DETECTED.value, {})
    state = project_run(store.ledger(stream))
    run = key
    for stage in (Stage.PROCESS, Stage.GENERATE):
        unit = state.stage(stage)
        if unit.status is Status.DONE:
            continue
        if unit.status is Status.DEAD_LETTER or not _due(unit.next_attempt_at, now):
            return RunReport(run_key=key, status=state.status)
        try:
            if stage is Stage.PROCESS:
                ref = pipeline.process(event)
                store.append(stream, Kind.STAGE_DONE, principal, now, stage.value, {"ref": ref})
            else:
                items = list(pipeline.generate(event, state.ref or ""))
                store.append(stream, Kind.STAGE_DONE, principal, now, stage.value, {"items": items})
        except (Unavailable, Permanent) as e:
            _fail(store, stream, principal, now, cfg, stage.value, unit.attempts,
                  type(e).__name__, emit, run, stage.value, Kind.STAGE_FAILED,
                  Kind.STAGE_DEAD_LETTER, isinstance(e, Unavailable))  # fmt: skip
            return RunReport(run_key=key, status=run_state(store, key).status)
        state = project_run(store.ledger(stream))
    texts = pipeline.owner_texts(state.ref or "")
    submitted = 0
    for item in state.item_ids:
        prior = state.items.get(item)
        if prior is not None and prior.status in (Status.DONE, Status.DEAD_LETTER):
            continue
        if prior is not None and not _due(prior.next_attempt_at, now):
            continue
        attempts = prior.attempts if prior else 0
        try:
            inputs = pipeline.enrich(item)
            out = submit_for_review(store, pipeline.result(item), inputs, principal, now, texts)
        except (Unavailable, Permanent) as e:
            _fail(store, stream, principal, now, cfg, item, attempts, type(e).__name__, emit,
                  run, "SIMILARITY", Kind.ITEM_FAILED, Kind.ITEM_DEAD_LETTER,
                  isinstance(e, Unavailable))  # fmt: skip
            continue
        if out.status in (SubmitStatus.SUBMITTED, SubmitStatus.ALREADY_SUBMITTED):
            store.append(
                stream, Kind.ITEM_DONE, principal, now, item, {"outcome": out.status.value}
            )
            submitted += out.status is SubmitStatus.SUBMITTED
        elif out.status in PERMANENT_SUBMIT:
            store.append(
                stream, Kind.ITEM_DEAD_LETTER, principal, now, item,
                {"error_class": out.status.value, "reason": ",".join(out.reasons)},
            )  # fmt: skip
            emit("DEAD_LETTER", run, f"{item}:{out.status.value}",
                 {"run_id": run, "stage": "SUBMIT", "error_class": out.status.value})  # fmt: skip
        else:
            _fail(store, stream, principal, now, cfg, item, attempts, out.status.value, emit,
                  run, "SUBMIT", Kind.ITEM_FAILED, Kind.ITEM_DEAD_LETTER, True)  # fmt: skip
    state = project_run(store.ledger(stream))
    if state.status in (RunStatus.COMPLETE, RunStatus.PARTIAL_DEAD) and not state.ready_emitted:
        done = [i for i, u in state.items.items() if u.detail in ("SUBMITTED", "ALREADY_SUBMITTED")]
        cands = sum(
            len(t.snapshot.similarity.matches) if t.snapshot.similarity else 0
            for t in store.tasks.values()
            if t.obligation_id in done
        )
        ready: dict[str, str | int] = {
            "event_id": event.id,
            "potential_obligations": len(done),
            "similarity_candidates": cands,
        }
        if emit("OBLIGATIONS_READY", event.id, key, ready):
            store.append(stream, Kind.TICK_ACTION, principal, now, "ready-emitted", {})
        state = project_run(store.ledger(stream))
    return RunReport(run_key=key, status=state.status, submitted=submitted)


def requeue(
    store: WorkflowStore, key: str, target: str, principal: Principal, now: datetime
) -> bool:
    if WorkflowRole.OPERATOR not in principal.roles:
        return False
    state = run_state(store, key)
    unit = (
        state.stage(Stage(target[6:]))
        if target.startswith("stage:")
        else state.items.get(target[5:])
    )
    if unit is None or unit.status is not Status.DEAD_LETTER:
        return False
    store.append(run_stream(key), Kind.RUN_REQUEUED, principal, now, target,
                 {"target": target, "by": principal.id})  # fmt: skip
    return True


def unaccounted(store: WorkflowStore) -> list[str]:
    bad = []
    for s in store.streams_with("run:"):
        state = project_run(store.ledger(s))
        if state.status in (RunStatus.IN_PROGRESS,) and not state.stages:
            bad.append(s)
    return bad
