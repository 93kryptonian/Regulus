import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qs

from regulus.review import Actor, ReviewTask
from regulus.review_ui import ReviewApp
from regulus.review_ui.app import SECURITY, Environ, StartResponse
from regulus.review_ui.render import _page, e, render_queue
from regulus.review_ui.view import build_queue

from .access import Facts, Matrix, Operation, authorize
from .chain import ChainLog, LogUnavailable
from .policy import FreeTextPolicy

TASK = re.compile(r"^/tasks/([A-Za-z0-9_-]+)(/claim|/action)?$")
ACTION_OPS = {
    "EDIT": Operation.EDIT,
    "APPROVE": Operation.APPROVE,
    "REJECT": Operation.REJECT,
    "PUBLISH": Operation.PUBLISH,
}
TERMINAL = {"PUBLISHED", "REJECTED"}


@dataclass
class AuditCounters:
    attempted: int = 0
    recorded: int = 0
    gap: int = 0


class GovernedApp:
    def __init__(
        self,
        inner: ReviewApp,
        matrix: Matrix,
        audit: ChainLog,
        clock: Callable[[], datetime],
        policy: FreeTextPolicy | None = None,
    ) -> None:
        self.inner, self.matrix, self.audit, self.clock = inner, matrix, audit, clock
        self.policy = policy or FreeTextPolicy()
        self.counters = AuditCounters()

    def facts(self, task: ReviewTask) -> Facts:
        ob, log = self.inner.store.get(task.obligation_id)
        return Facts(
            task_id=task.id,
            status=ob.status.value,
            terminal=ob.status.value in TERMINAL,
            participants=tuple(dict.fromkeys(r.actor_id for r in log)),
        )

    def _audit(
        self, kind: str, op: str, actor: str, resource: str, outcome: str, roles: str = "NONE"
    ) -> bool:
        self.counters.attempted += 1
        try:
            self.audit.append(
                kind,
                self.clock(),
                operation=op,
                actor=actor,
                resource=resource,
                outcome=outcome,
                roles=roles,
            )
        except LogUnavailable:
            self.counters.gap += 1
            return False
        self.counters.recorded += 1
        return True

    def _respond(
        self, start: StartResponse, status: str, body: str, ctype: str = "text/plain"
    ) -> Iterable[bytes]:
        data = body.encode()
        start(
            status,
            [
                ("Content-Type", f"{ctype}; charset=utf-8"),
                ("Content-Length", str(len(data))),
                *SECURITY,
            ],
        )
        return [data]

    def __call__(self, environ: Environ, start: StartResponse) -> Iterable[bytes]:
        path, method = environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "GET")
        if path == "/static/review.css":
            return self.inner(environ, start)
        actor: Actor | None = self.inner.identify(environ)
        m = TASK.match(path)
        if actor is None:
            self._audit("ACCESS_DENIED", "READ_TASK", "anonymous", "none", "UNAUTHENTICATED")
            return self._respond(start, "401 Unauthorized", "Authentication required")
        roles = {r.value for r in actor.roles}
        label = "-".join(sorted(roles)) or "NONE"
        body = b""
        post: dict[str, list[str]] = {}
        if method == "POST":
            size = min(int(environ.get("CONTENT_LENGTH") or 0), 65536)
            body = environ["wsgi.input"].read(size)
            post = parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
        if path == "/tasks" and method == "GET":
            return self._queue(start, environ, actor, roles, label)
        task = self.inner.tasks.get(m.group(1)) if m else None
        if m is None or task is None:
            self._audit("ACCESS_DENIED", "READ_TASK", actor.id, "unknown", "NOT_FOUND", label)
            return self._respond(start, "404 Not Found", "Not found")
        sub = m.group(2)
        op = Operation.READ_TASK if method == "GET" and sub is None else None
        if method == "POST" and sub == "/claim":
            op = Operation.CLAIM
        elif method == "POST" and sub == "/action":
            op = ACTION_OPS.get((post.get("action") or [""])[0])
        facts = self.facts(task)
        decision = authorize(self.matrix, actor.id, roles, op.value if op else "UNLISTED", facts)
        read_ok = authorize(self.matrix, actor.id, roles, Operation.READ_TASK.value, facts)
        allowed = decision.allowed and read_ok.allowed
        outcome = (
            "ALLOWED"
            if allowed
            else f"DENIED_{decision.reason if not decision.allowed else read_ok.reason}"
        )
        bad = None
        if allowed and method == "POST":
            for k, vals in post.items():
                if (
                    self.policy.covers(k)
                    and vals
                    and vals[0]
                    and (why := self.policy.check(k, vals[0]))
                ):
                    bad, allowed, outcome = k, False, f"FREE_TEXT_{why.upper()}"
                    break
        recorded = self._audit(
            "ACCESS_ALLOWED" if allowed else "ACCESS_DENIED",
            (op.value if op else "UNLISTED"),
            actor.id,
            task.id,
            outcome,
            label,
        )
        if not recorded:
            return self._respond(start, "503 Service Unavailable", "Audit unavailable")
        if bad is not None:
            return self._respond(
                start,
                "400 Bad Request",
                _page(
                    "Bad request",
                    f"<h1>Bad request</h1><p>Field <code>{e(bad)}</code> was rejected.</p>",
                ),
                "text/html",
            )
        if not allowed:
            return self._respond(start, "403 Forbidden", "Forbidden")
        if method == "POST":
            environ["wsgi.input"] = io.BytesIO(body)
        return self.inner(environ, start)

    def _queue(
        self, start: StartResponse, environ: Environ, actor: Actor, roles: set[str], label: str
    ) -> Iterable[bytes]:
        visible = [
            t
            for t in self.inner.tasks.values()
            if authorize(
                self.matrix, actor.id, roles, Operation.READ_TASK.value, self.facts(t)
            ).allowed
        ]
        coarse = authorize(
            self.matrix,
            actor.id,
            roles,
            Operation.READ_QUEUE.value,
            Facts(task_id="queue", status="NONE", terminal=False),
        )
        ok = coarse.allowed
        if not self._audit(
            "ACCESS_ALLOWED" if ok else "ACCESS_DENIED",
            "READ_QUEUE",
            actor.id,
            "queue",
            "ALLOWED" if ok else f"DENIED_{coarse.reason}",
            label,
        ):
            return self._respond(start, "503 Service Unavailable", "Audit unavailable")
        if not ok:
            return self._respond(start, "403 Forbidden", "Forbidden")
        return self._respond(
            start,
            "200 OK",
            render_queue(build_queue(self.inner.store, visible, self.clock())),
            "text/html",
        )
