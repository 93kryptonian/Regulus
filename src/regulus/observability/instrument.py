from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any, cast

from regulus.domain import RegulatoryEvent
from regulus.generation import GenerationResult
from regulus.notifications import Delivery, Notifier, deliver_due
from regulus.review import (
    ActionRequest,
    ReviewConfig,
    ReviewOutcome,
    ReviewStore,
    ReviewTask,
    apply,
)
from regulus.workflow import (
    PreparedSubmission,
    Principal,
    RunReport,
    RunStatus,
    ScheduleConfig,
    SnapshotInputs,
    WorkflowStore,
    run_event,
    run_key,
    tick,
)

from .clock import Clock
from .cost import CallKind, CostLedger, Source, UsageRecord
from .events import ObsEvent, span_id, trace_id
from .metrics import InvalidMetric, Registry
from .sinks import ObservationBuffer
from .taxonomy import (
    FAULTS,
    ErrorClass,
    Kind,
    Outcome,
    Stage,
    classify_exception,
    classify_notification,
    classify_review,
)

_DEPTH = [0]


def in_wrapper() -> bool:
    return _DEPTH[0] > 0


class Handle:
    def __init__(self) -> None:
        self.outcome: Outcome = Outcome.OK
        self.error_class: ErrorClass | None = None
        self.counts: dict[str, int] = {}
        self.attrs: dict[str, str | bool | int] = {}

    def result(
        self, outcome: Outcome, error_class: ErrorClass | None = None, **attrs: str | bool | int
    ) -> None:
        self.outcome, self.error_class = outcome, error_class
        self.attrs.update(attrs)


class Observer:
    def __init__(self, clock: Clock, buffer: ObservationBuffer | None = None, registry: Registry | None = None,
                 ledger: CostLedger | None = None) -> None:  # fmt: skip
        self.clock = clock
        self.buffer = buffer or ObservationBuffer()
        self.registry = registry or Registry()
        self.ledger = ledger
        self.journal: list[ObsEvent] = []
        self.invalid = 0
        self._open: dict[str, ObsEvent] = {}
        self._stack: dict[str, list[str]] = {}
        self._attempts: dict[tuple[str, str, str], int] = {}
        self._seq: dict[str, int] = {}
        self._mono: dict[str, int] = {}

    def _next(self, run: str) -> int:
        self._seq[run] = self._seq.get(run, 0) + 1
        return self._seq[run]

    def _record(self, e: ObsEvent) -> None:
        self.journal.append(e)
        self.buffer.enqueue(e)

    def _metric(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except InvalidMetric:
            self.invalid += 1

    @contextmanager
    def span(self, run_id: str, stage: Stage, item: str = "") -> Iterator[Handle]:
        _DEPTH[0] += 1
        h = Handle()
        started: ObsEvent | None = None
        t0 = 0
        try:
            try:
                tid = trace_id(run_id)
                key = (run_id, stage.value, item)
                attempt = self._attempts.get(key, 0) + 1
                self._attempts[key] = attempt
                stack = self._stack.setdefault(run_id, [])
                started = ObsEvent(seq=self._next(run_id), trace_id=tid, span_id=span_id(tid, stage, item, attempt),
                                   parent_span_id=stack[-1] if stack else None, run_id=run_id, item_id=item, stage=stage,
                                   kind=Kind.SPAN_STARTED, attempt=attempt, started_at=self.clock.now())  # fmt: skip
                t0 = self.clock.monotonic_ms()
                self._open[started.span_id] = started
                stack.append(started.span_id)
                self._record(started)
            except Exception:
                self.invalid += 1
                started = None
            try:
                yield h
            except Exception as exc:
                if not h.error_class and h.outcome is Outcome.OK:
                    h.outcome, h.error_class = classify_exception(exc)
                    extra = getattr(exc, "obs_attr", None)
                    if extra:
                        h.attrs[extra[0]] = extra[1]
                self._finish(started, run_id, stage, item, h, t0)
                raise
            self._finish(started, run_id, stage, item, h, t0)
        finally:
            _DEPTH[0] -= 1

    def _finish(
        self, started: ObsEvent | None, run_id: str, stage: Stage, item: str, h: Handle, t0: int
    ) -> None:
        if started is None:
            return
        try:
            now = self.clock.monotonic_ms()
            flagged = now < t0
            dur = max(0, now - t0)
            attrs = dict(h.attrs)
            if flagged:
                attrs["clock_regression"] = True
            e = ObsEvent(seq=self._next(run_id), trace_id=started.trace_id, span_id=started.span_id,
                         parent_span_id=started.parent_span_id, run_id=run_id, item_id=item, stage=stage,
                         kind=Kind.SPAN_FINISHED, outcome=h.outcome, error_class=h.error_class, attempt=started.attempt,
                         started_at=started.started_at, duration_ms=dur, counts=h.counts, attrs=attrs)  # fmt: skip
        except Exception:
            self.invalid += 1
            self._close(started.span_id, run_id)
            return
        self._close(started.span_id, run_id)
        try:
            self._record(e)
        except Exception:
            self.invalid += 1
        st, oc = stage.value, h.outcome.value
        self._metric(lambda: self.registry.inc("regulus_stage_total", {"stage": st, "outcome": oc}))
        self._metric(
            lambda: self.registry.observe(
                "regulus_stage_duration_ms", {"stage": st, "outcome": oc}, dur
            )
        )
        if item:
            self._metric(
                lambda: self.registry.inc("regulus_items_total", {"stage": st, "outcome": oc})
            )
        if h.outcome in FAULTS and h.error_class:
            ec = h.error_class.value
            self._metric(
                lambda: self.registry.inc(
                    "regulus_failures_total", {"stage": st, "error_class": ec}
                )
            )
        if started.attempt > 1:
            self._metric(lambda: self.registry.inc("regulus_retries_total", {"stage": st}))

    def _close(self, sid: str, run_id: str) -> None:
        self._open.pop(sid, None)
        stack = self._stack.get(run_id, [])
        if sid in stack:
            stack.remove(sid)

    def point(self, run_id: str, stage: Stage, outcome: Outcome = Outcome.OK, error_class: ErrorClass | None = None,
              **attrs: str | bool | int) -> None:  # fmt: skip
        try:
            tid = trace_id(run_id)
            stack = self._stack.get(run_id, [])
            e = ObsEvent(seq=self._next(run_id), trace_id=tid, span_id=span_id(tid, stage, "point", self._seq[run_id]),
                         parent_span_id=stack[-1] if stack else None, run_id=run_id, stage=stage, kind=Kind.POINT,
                         outcome=outcome, error_class=error_class, started_at=self.clock.now(), attrs=attrs)  # fmt: skip
            self._record(e)
        except Exception:
            self.invalid += 1

    def recover(self, run_id: str) -> int:
        n = 0
        for sid, s in sorted(self._open.items(), key=lambda kv: -kv[1].seq):
            if s.run_id != run_id:
                continue
            e = ObsEvent(seq=self._next(run_id), trace_id=s.trace_id, span_id=sid, parent_span_id=s.parent_span_id,
                         run_id=run_id, item_id=s.item_id, stage=s.stage, kind=Kind.SPAN_ABANDONED,
                         outcome=Outcome.FAILED_RETRYABLE, error_class=ErrorClass.ABANDONED, attempt=s.attempt,
                         started_at=s.started_at, attrs={"recovered": True})  # fmt: skip
            self._record(e)
            n += 1
        for sid in [k for k, v in self._open.items() if v.run_id == run_id]:
            self._open.pop(sid)
        self._stack[run_id] = []
        return n

    def usage(self, u: UsageRecord) -> None:
        if self.ledger is None:
            return
        try:
            cost = self.ledger.add(u)
            priced = cost is not None
            cur = self.ledger.table.currency
            if cost is not None:
                self._metric(
                    lambda: self.registry.inc(
                        "regulus_ai_cost_micro_total",
                        {"provider": u.provider, "currency": cur},
                        cost,
                    )
                )
            self._metric(
                lambda: self.registry.inc(
                    "regulus_ai_calls_total",
                    {"provider": u.provider, "kind": u.kind.value, "priced": str(priced).lower()},
                )
            )
            self._metric(
                lambda: self.registry.inc(
                    "regulus_ai_tokens_total",
                    {"provider": u.provider, "kind": u.kind.value, "direction": "input"},
                    u.input_tokens,
                )
            )
            self._metric(
                lambda: self.registry.inc(
                    "regulus_ai_tokens_total",
                    {"provider": u.provider, "kind": u.kind.value, "direction": "output"},
                    u.output_tokens,
                )
            )
        except Exception:
            self.invalid += 1


def observe_ai_call[T](obs: Observer, run_id: str, provider: str, model: str, kind: CallKind,
                    fn: Callable[[], tuple[T, tuple[int, int] | None]], stage: Stage = Stage.GENERATE) -> T:  # fmt: skip
    t0 = obs.clock.monotonic_ms()
    result, usage = fn()
    if usage is not None:
        obs.usage(UsageRecord(run_id=run_id, span_id="ai", provider=provider, model=model, kind=kind,
                              input_tokens=usage[0], output_tokens=usage[1], source=Source.REPORTED,
                              latency_ms=max(0, obs.clock.monotonic_ms() - t0)))  # fmt: skip
    return result


class ObservedPipeline:
    def __init__(self, inner: Any, obs: Observer, run_id: str) -> None:
        self.inner, self.obs, self.run_id = inner, obs, run_id

    def process(self, event: RegulatoryEvent) -> str:
        with self.obs.span(self.run_id, Stage.PROCESS):
            return cast(str, self.inner.process(event))

    def generate(self, event: RegulatoryEvent, ref: str) -> Sequence[str]:
        with self.obs.span(self.run_id, Stage.GENERATE) as h:
            out = cast(Sequence[str], self.inner.generate(event, ref))
            h.counts["items"] = len(out)
            return out

    def result(self, item_id: str) -> GenerationResult:
        return cast(GenerationResult, self.inner.result(item_id))

    def enrich(self, item_id: str) -> SnapshotInputs:
        with self.obs.span(self.run_id, Stage.ENRICH, item_id):
            return cast(SnapshotInputs, self.inner.enrich(item_id))

    def owner_texts(self, ref: str) -> Mapping[str, str]:
        return cast(Mapping[str, str], self.inner.owner_texts(ref))


class ObservedStore:
    def __init__(self, inner: Any, obs: Observer, run_id: str) -> None:
        self._inner, self._obs, self._run = inner, obs, run_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None:
        with self._obs.span(self._run, Stage.SUBMIT, prepared.obligation.id):
            self._inner.commit_submission(prepared, principal, at)


_RUN_OUTCOME = {
    RunStatus.COMPLETE: (Outcome.OK, None),
    RunStatus.WAITING: (Outcome.FAILED_RETRYABLE, ErrorClass.UNAVAILABLE),
    RunStatus.IN_PROGRESS: (Outcome.FAILED_RETRYABLE, ErrorClass.UNAVAILABLE),
    RunStatus.PARTIAL_DEAD: (Outcome.FAILED_PERMANENT, ErrorClass.DEAD_LETTER),
    RunStatus.DEAD: (Outcome.FAILED_PERMANENT, ErrorClass.DEAD_LETTER),
    RunStatus.REJECTED: (Outcome.REFUSED, ErrorClass.REJECTED_INPUT),
    RunStatus.UNSTARTED: (Outcome.REFUSED, ErrorClass.DENIED),
}


def observed_run_event(obs: Observer, store: WorkflowStore, pipeline: Any, event: RegulatoryEvent, principal: Principal,
                       now: datetime, emit: Callable[[str, str, str, dict[str, str | int]], bool],
                       config_version: str = "1", cfg: ScheduleConfig | None = None) -> RunReport:  # fmt: skip
    run_id = run_key(event.id, config_version)
    obs.recover(run_id)

    def watched_emit(kind: str, subject: str, version: str, payload: dict[str, str | int]) -> bool:
        if kind in ("REGULATION_DETECTED", "AMENDMENT_DETECTED"):
            with obs.span(run_id, Stage.DETECTED_NOTIFY) as h:
                ok = emit(kind, subject, version, payload)
                if not ok:
                    h.result(Outcome.FAILED_RETRYABLE, ErrorClass.CHANNEL_UNAVAILABLE)
                return ok
        ok = emit(kind, subject, version, payload)
        obs.point(run_id, Stage.NOTIFY_DELIVER, Outcome.OK if ok else Outcome.FAILED_RETRYABLE,
                  None if ok else ErrorClass.CHANNEL_UNAVAILABLE)  # fmt: skip
        return ok

    with obs.span(run_id, Stage.RUN) as h:
        rep = run_event(cast(WorkflowStore, ObservedStore(store, obs, run_id)),
                        ObservedPipeline(pipeline, obs, run_id), event, principal, now, watched_emit,
                        config_version, cfg)  # fmt: skip
        outcome, ec = (
            (Outcome.FAILED_RETRYABLE, ErrorClass.STORE)
            if rep.store_unavailable
            else _RUN_OUTCOME[rep.status]
        )
        h.result(outcome, ec)
        h.counts["items"] = rep.submitted
    return rep


def observed_apply(obs: Observer, run_id: str, store: ReviewStore, task: ReviewTask, req: ActionRequest,
                   cfg: ReviewConfig | None = None, texts: Mapping[str, str] | None = None) -> ReviewOutcome:  # fmt: skip
    with obs.span(run_id, Stage.REVIEW_ACTION, task.obligation_id) as h:
        out = apply(store, task, req, cfg, texts)
        outcome, ec = classify_review(out.status.value)
        h.result(outcome, ec, status=out.status.value, action=req.action.value)
        return out


def observed_deliver(obs: Observer, run_id: str, store: WorkflowStore, notifier: Notifier, principal: Principal,
                     now: datetime, cfg: ScheduleConfig | None = None) -> list[Delivery]:  # fmt: skip
    with obs.span(run_id, Stage.NOTIFY_DELIVER) as h:
        out = deliver_due(store, notifier, principal, now, cfg)
        h.counts["items"] = len(out)
        bad = [d for d in out if d.state.value != "DELIVERED"]
        if bad:
            o, ec = classify_notification(bad[0].state.value)
            if any(d.unrecorded for d in out):
                o, ec = Outcome.FAILED_RETRYABLE, ErrorClass.STORE
            h.result(o, ec)
        return out


def observed_tick(obs: Observer, run_id: str, store: WorkflowStore, now: datetime, directory: Any, principal: Principal,
                  cfg: ScheduleConfig | None = None) -> Any:  # fmt: skip
    with obs.span(run_id, Stage.TICK) as h:
        out = tick(store, now, directory, principal, cfg)
        h.counts["items"] = len(out)
        return out


def lifecycle_violations(events: Sequence[ObsEvent]) -> list[str]:
    started: dict[str, ObsEvent] = {}
    closed: dict[str, int] = {}
    finish_seq: dict[str, int] = {}
    problems: list[str] = []
    by_span: dict[str, list[ObsEvent]] = {}
    for e in events:
        if e.kind is Kind.SPAN_STARTED:
            if e.span_id in started:
                problems.append(f"{e.span_id}: started twice")
            started[e.span_id] = e
        elif e.kind in (Kind.SPAN_FINISHED, Kind.SPAN_ABANDONED):
            closed[e.span_id] = closed.get(e.span_id, 0) + 1
            finish_seq[e.span_id] = e.seq
            if e.span_id not in started:
                problems.append(f"{e.span_id}: closed without start")
        by_span.setdefault(e.span_id, []).append(e)
    for sid, s in started.items():
        n = closed.get(sid, 0)
        if n == 0:
            problems.append(f"{sid}: never closed")
        if n > 1:
            problems.append(f"{sid}: closed {n} times")
        if s.parent_span_id is not None:
            p = started.get(s.parent_span_id)
            if p is None or p.seq > s.seq or p.trace_id != s.trace_id:
                problems.append(f"{sid}: parent does not resolve")
            elif finish_seq.get(s.parent_span_id, 10**9) < finish_seq.get(sid, 0):
                problems.append(f"{sid}: child outlived its parent")
    return problems
