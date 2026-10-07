import hmac
import re
from collections.abc import Callable, Iterable, MutableMapping
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

from regulus.review import (
    Actor,
    ClaimError,
    ReviewConfig,
    ReviewStore,
    ReviewTask,
    Role,
    Status,
    apply,
    claim,
)

from .forms import FormError, check_keys, parse_action
from .render import CSS, render_outcome, render_queue, render_task
from .view import build_queue, build_view

Environ = dict[str, Any]
StartResponse = Callable[[str, list[tuple[str, str]]], Any]
HTTP = {
    Status.APPLIED: "200 OK",
    Status.DENIED: "403 Forbidden",
    Status.STALE: "409 Conflict",
    Status.NOT_RECORDED: "503 Service Unavailable",
}
SECURITY = [
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
]
TASK = re.compile(r"^/tasks/([A-Za-z0-9_-]+)(/claim|/action)?$")


class ReviewApp:
    def __init__(
        self,
        store: ReviewStore,
        tasks: MutableMapping[str, ReviewTask],
        identify: Callable[[Environ], Actor | None],
        csrf_token: Callable[[Environ], str],
        owner_texts: dict[str, str],
        clock: Callable[[], datetime],
        cfg: ReviewConfig | None = None,
    ) -> None:
        self.store, self.tasks, self.identify = store, tasks, identify
        self.csrf_token, self.texts, self.clock = csrf_token, owner_texts, clock
        self.cfg = cfg or ReviewConfig()

    def __call__(self, environ: Environ, start: StartResponse) -> Iterable[bytes]:
        try:
            status, ctype, body = self.route(environ)
        except Exception:
            status, ctype, body = "500 Internal Server Error", "text/plain", "Internal error"
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

    def route(self, environ: Environ) -> tuple[str, str, str]:
        method, path = environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "")
        if path == "/static/review.css" and method == "GET":
            return "200 OK", "text/css", CSS
        actor = self.identify(environ)
        if actor is None:
            return "401 Unauthorized", "text/plain", "Authentication required"
        now = self.clock()
        if path == "/tasks" and method == "GET":
            return (
                "200 OK",
                "text/html",
                render_queue(build_queue(self.store, list(self.tasks.values()), now)),
            )
        m = TASK.match(path)
        task = self.tasks.get(m.group(1)) if m else None
        if m is None or task is None:
            return "404 Not Found", "text/plain", "Not found"
        sub = m.group(2)
        if method == "GET" and sub is None:
            return self.page(environ, task, actor, now)
        if method == "POST" and sub in ("/claim", "/action"):
            return self.post(environ, task, actor, now, sub)
        return "405 Method Not Allowed", "text/plain", "Method not allowed"

    def page(
        self,
        environ: Environ,
        task: ReviewTask,
        actor: Actor,
        now: datetime,
        outcome: str = "",
        status: str = "200 OK",
    ) -> tuple[str, str, str]:
        view = build_view(self.store, task, actor, now, self.cfg, self.texts)
        return status, "text/html", render_task(view, self.csrf_token(environ), outcome)

    def post(
        self, environ: Environ, task: ReviewTask, actor: Actor, now: datetime, sub: str
    ) -> tuple[str, str, str]:
        size = min(int(environ.get("CONTENT_LENGTH") or 0), 65536)
        raw = environ["wsgi.input"].read(size).decode("utf-8", "replace")
        post = parse_qs(raw, keep_blank_values=True)
        sent = (post.get("csrf") or [""])[0]
        if not hmac.compare_digest(sent, self.csrf_token(environ)):
            return "403 Forbidden", "text/plain", "Invalid CSRF token"
        try:
            if sub == "/claim":
                return self.claim(environ, task, actor, now, post)
            check_keys(post)
            req = parse_action(post, task.id, actor, now)
            if (post.get("snapshot_hash") or [""])[0] != task.snapshot.hash:
                return self.page(environ, task, actor, now, render_outcome("STALE"), "409 Conflict")
        except FormError as ex:
            return "400 Bad Request", "text/html", render_queue_error(ex)
        out = apply(self.store, task, req, self.cfg, self.texts)
        if out.task is not None:
            self.tasks[task.id] = out.task
        http = HTTP.get(out.status, "422 Unprocessable Entity")
        return self.page(
            environ,
            self.tasks[task.id],
            actor,
            now,
            render_outcome(out.status.value, out.reasons),
            http,
        )

    def claim(
        self,
        environ: Environ,
        task: ReviewTask,
        actor: Actor,
        now: datetime,
        post: dict[str, list[str]],
    ) -> tuple[str, str, str]:
        if set(post) - {"csrf"}:
            raise FormError(sorted(set(post) - {"csrf"})[0], "unknown field")
        if Role.REVIEWER not in actor.roles:
            return self.page(
                environ, task, actor, now, render_outcome("DENIED", ("ROLE",)), "403 Forbidden"
            )
        try:
            self.tasks[task.id] = claim(task, actor.id, now, self.cfg.claim_ttl_seconds)
        except ClaimError:
            return self.page(
                environ, task, actor, now, render_outcome("DENIED", ("NO_CLAIM",)), "409 Conflict"
            )
        return self.page(environ, self.tasks[task.id], actor, now, render_outcome("APPLIED"))


def render_queue_error(ex: FormError) -> str:
    from .render import _page, e

    return _page(
        "Bad request",
        f"<h1>Bad request</h1><p>Field <code>{e(ex.field)}</code>: {e(ex.message)}</p>",
    )
