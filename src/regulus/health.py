import json
from collections.abc import Callable, Iterable

from regulus.governance.resources import default_matrix, default_policy
from regulus.observability.taxonomy import ErrorClass, Outcome, Stage
from regulus.review_ui.app import SECURITY, Environ, StartResponse
from regulus.runtime import Runtime, integrity

Check = Callable[[Runtime], bool]


def _packaged(rt: Runtime) -> bool:
    try:
        default_matrix()
        default_policy()
    except Exception:
        return False
    return True


def _integrity(rt: Runtime) -> bool:
    try:
        r = integrity(rt)
    except Exception:
        return False
    return not r.broken and not r.unreceipted


def _audit(rt: Runtime) -> bool:
    a = rt.parts.access
    return a.fail_next == 0 and a.verified()


CHECKS: dict[str, Check] = {
    "configuration": lambda rt: rt.config is not None,
    "packaged_data": _packaged,
    "state_integrity": _integrity,
    "audit_appendable": _audit,
    "state_dir_writable": lambda rt: rt.state.writable(),
    "clock_monotonic": lambda rt: not rt.clock.regressed,
    "observation_buffer": lambda rt: rt.observer.buffer.buffered < rt.observer.buffer.capacity,
    "startup_recovery": lambda rt: rt.recovery_done and rt.started and not rt.stopping,
}
DEGRADED = {
    "audit_appendable": "audit_unavailable",
    "observation_buffer": "buffer_full",
}


def liveness() -> dict[str, object]:
    return {"alive": True}


def readiness(rt: Runtime) -> dict[str, object]:
    checks = {name: bool(fn(rt)) for name, fn in CHECKS.items()}
    degraded = [DEGRADED[n] for n, ok in checks.items() if not ok and n in DEGRADED]
    degraded += [n for n in rt.notes if n == "unclean_shutdown_recovered"]
    failing = [n for n, ok in checks.items() if not ok]
    return {
        "ready": not failing,
        "checks": checks,
        "failing": failing,
        "degraded": degraded,
        "generation": rt.generation,
        "run_id": rt.run_id,
    }


def _json(start: StartResponse, status: str, body: dict[str, object]) -> Iterable[bytes]:
    data = json.dumps(body, sort_keys=True).encode()
    start(
        status,
        [("Content-Type", "application/json"), ("Content-Length", str(len(data))), *SECURITY],
    )
    return [data]


class Served:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def __call__(self, environ: Environ, start: StartResponse) -> Iterable[bytes]:
        rt, path = self.rt, environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET")
        if path == "/healthz" and method == "GET":
            return _json(start, "200 OK", liveness())
        if path == "/readyz" and method == "GET":
            body = readiness(rt)
            return _json(start, "200 OK" if body["ready"] else "503 Service Unavailable", body)
        if rt.stopping or not rt.started:
            return _json(start, "503 Service Unavailable", {"stopping": True})
        seen: list[str] = []

        def record(status: str, headers: list[tuple[str, str]], exc: object = None) -> None:
            seen.append(status)
            start(status, headers)

        out = rt.app(environ, record)
        code = int(seen[0][:3]) if seen else 500
        rt.observer.point(rt.run_id, Stage.REVIEW_ACTION, *_classify(code))
        return out


def _classify(code: int) -> tuple[Outcome, ErrorClass | None]:
    if code < 400:
        return Outcome.OK, None
    if code in (401, 403):
        return Outcome.REFUSED, ErrorClass.DENIED
    if code < 500:
        return Outcome.REFUSED, ErrorClass.REJECTED_INPUT
    return (
        Outcome.FAILED_RETRYABLE,
        ErrorClass.UNAVAILABLE if code == 503 else ErrorClass.UNCLASSIFIED,
    )
