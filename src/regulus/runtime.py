import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum

from regulus.config import AuthMode, ConfigError, RegulusConfig
from regulus.governance import ChainLog, GovernedApp, IdentityMap, Retention, inventory, verify_all
from regulus.governance.resources import default_inventory, default_matrix, default_policy
from regulus.governance.retention import load_policy
from regulus.governance.verify import IntegrityReport
from regulus.observability.instrument import Observer
from regulus.observability.metrics import Registry
from regulus.observability.sinks import JsonlSink, ObservationBuffer
from regulus.observability.taxonomy import Stage
from regulus.review import Actor, Role
from regulus.review_ui import ReviewApp
from regulus.review_ui.app import Environ
from regulus.state import (
    LockHeld,
    Parts,
    SnapshotCorrupt,
    StateDir,
    apply,
    capture,
)
from regulus.workflow import SYSTEM, IntentWorkflowStore, Phase

Identity = Callable[[Environ], Actor | None]


class Exit(IntEnum):
    OK = 0
    CONFIG = 2
    STATE = 3
    RUNTIME = 4


class Refused(Exception):
    def __init__(self, code: Exit, reasons: list[str]) -> None:
        self.code = code
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class SystemClock:
    def __init__(self, source: Callable[[], datetime] | None = None) -> None:
        self._source = source or (lambda: datetime.now(UTC))
        self._last: datetime | None = None
        self.regressed = False

    def now(self) -> datetime:
        t = self._source()
        if self._last is not None and t < self._last:
            self.regressed = True
        else:
            self._last = t
        return t

    def monotonic_ms(self) -> int:
        return time.monotonic_ns() // 1_000_000


@dataclass
class Runtime:
    config: RegulusConfig
    state: StateDir
    parts: Parts
    app: GovernedApp
    observer: Observer
    clock: SystemClock
    run_id: str
    generation: int = 0
    clean: bool = True
    recovered: dict[str, int] = field(default_factory=dict)
    recovery_done: bool = False
    started: bool = False
    stopping: bool = False
    report: IntegrityReport | None = None
    notes: list[str] = field(default_factory=list)


def _dev_identity(environ: Environ) -> Actor | None:
    ident = environ.get("HTTP_X_REGULUS_ACTOR", "")
    if not ident:
        return None
    try:
        roles = tuple(
            Role(r) for r in environ.get("HTTP_X_REGULUS_ROLES", "").split(",") if r.strip()
        )
    except ValueError:
        return None
    return Actor(id=ident, roles=roles)


def _no_identity(environ: Environ) -> Actor | None:
    return None


def _csrf(secret: str, identify: Identity) -> Callable[[Environ], str]:
    def token(environ: Environ) -> str:
        actor = identify(environ)
        who = actor.id if actor else "anonymous"
        return hmac.new(secret.encode(), who.encode(), hashlib.sha256).hexdigest()

    return token


def packaged_problems() -> list[str]:
    try:
        default_matrix()
        default_policy()
        return list(inventory.check(default_inventory()))
    except Exception:
        return ["packaged data unreadable"]


def build(
    config: RegulusConfig,
    identity: Identity | None = None,
    clock: SystemClock | None = None,
) -> Runtime:
    problems = packaged_problems()
    if problems:
        raise Refused(Exit.CONFIG, ["packaged data failed validation"])
    if config.auth_mode is AuthMode.EXTERNAL and identity is None:
        raise ConfigError([("auth_mode", "external requires a host identity function")])
    identify: Identity = {
        AuthMode.NONE: _no_identity,
        AuthMode.DEV_HEADER: _dev_identity,
        AuthMode.EXTERNAL: identity or _no_identity,
    }[config.auth_mode]
    clk = clock or SystemClock()
    policy = load_policy(config.retention_policy) if config.retention_policy else default_policy()
    store = IntentWorkflowStore()
    texts: dict[str, str] = {}
    access, purge = ChainLog("access"), ChainLog("purge")
    retention = Retention(store, policy, purge, access)
    parts = Parts(store, texts, access, purge, retention, IdentityMap())
    inner = ReviewApp(
        store.review,
        store.tasks,
        identify,
        _csrf(config.csrf_secret, identify),
        texts,
        clk.now,
    )
    app = GovernedApp(inner, default_matrix(), access, clk.now)
    observer = Observer(clk, ObservationBuffer(config.observation_buffer), Registry())
    return Runtime(
        config=config,
        state=StateDir(config.state_dir),
        parts=parts,
        app=app,
        observer=observer,
        clock=clk,
        run_id=f"run-{secrets.token_hex(6)}",
    )


def integrity(rt: Runtime) -> IntegrityReport:
    p = rt.parts
    report = verify_all(p.store, p.access, p.purge, p.anchors)
    receipted = {str(r.fields.get("stream")) for r in p.purge.records}
    missing = tuple(
        s
        for s in sorted(p.anchors)
        if s not in p.store.streams and s.replace(":", "_") not in receipted
    )
    if not missing:
        return report
    return report.model_copy(update={"unreceipted": (*report.unreceipted, *missing)})


def _interrupted_submissions(rt: Runtime) -> list[str]:
    store = rt.parts.store
    out = []
    for s in store.streams_with("obligation:"):
        oid = s.split(":", 1)[1]
        if store.submission(oid).phase is Phase.INTENT:
            out.append(oid)
    return out


def _corruption(report: IntegrityReport) -> list[str]:
    return [f"broken: {s}" for s in report.broken] + [
        f"unreceipted: {s}" for s in report.unreceipted
    ]


def startup(rt: Runtime, serving: bool = True) -> None:
    try:
        rt.state.acquire(rt.run_id)
    except LockHeld:
        raise Refused(Exit.RUNTIME, ["state directory is in use"]) from None
    except OSError:
        raise Refused(Exit.RUNTIME, ["state directory is not writable"]) from None
    try:
        _recover(rt)
    except BaseException:
        rt.state.release()
        raise
    rt.started = True
    rt.recovery_done = True
    if serving:
        rt.parts.access.append("SERVER_STARTED", rt.clock.now(), run_id=rt.run_id, clean=rt.clean)
        rt.observer.point(rt.run_id, Stage.RUN)


def _recover(rt: Runtime) -> None:
    stray = rt.state.clean_stray()
    try:
        loaded = rt.state.read_snapshot()
        if loaded is not None:
            rt.generation, content = loaded
            apply(rt.parts, content)
    except SnapshotCorrupt:
        raise Refused(Exit.STATE, ["snapshot is partial, unreadable or inconsistent"]) from None
    first = integrity(rt)
    if bad := _corruption(first):
        raise Refused(Exit.STATE, bad)
    now = rt.clock.now()
    rt.recovered["purges"] = rt.parts.retention.recover(now)
    pending = _interrupted_submissions(rt)
    for oid in pending:
        rt.parts.store.complete_submission(oid, SYSTEM, now)
    rt.recovered["submissions"] = len(pending)
    rt.recovered["spans"] = rt.observer.recover(rt.run_id)
    rt.report = integrity(rt)
    if bad := _corruption(rt.report):
        raise Refused(Exit.STATE, bad)
    rt.clean = loaded is None or rt.state.was_clean(rt.generation)
    if stray:
        rt.notes.append("stray_temp_removed")
    if not rt.clean:
        rt.notes.append("unclean_shutdown_recovered")
    rt.state.delete_marker()


def drain(rt: Runtime) -> int:
    sink = JsonlSink(rt.state.path / "events.jsonl")
    total = 0
    while rt.observer.buffer.buffered:
        n = rt.observer.buffer.drain(sink, 1000)
        total += n
        if not n and not rt.observer.buffer.buffered:
            break
        if not n:
            break
    return total


def snapshot_now(rt: Runtime) -> int:
    rt.state.write_snapshot(rt.generation + 1, rt.run_id, capture(rt.parts))
    rt.generation += 1
    return rt.generation


def shutdown(rt: Runtime) -> None:
    rt.stopping = True
    try:
        drain(rt)
        (rt.state.path / "metrics.txt").write_text(rt.observer.registry.text(), encoding="utf-8")
        snapshot_now(rt)
    finally:
        rt.state.release()
        rt.started = False


def state_hash(rt: Runtime) -> str:
    raw = json.dumps(capture(rt.parts), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


__all__ = ["Exit", "Refused", "Runtime", "SystemClock", "build", "shutdown", "startup"]
