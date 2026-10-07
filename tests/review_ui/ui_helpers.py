import io
from datetime import timedelta
from urllib.parse import urlencode

from rv_engine_helpers import ALICE, BOB, CAROL, DAVE, World
from rv_helpers import NOW

from regulus.review_ui import ReviewApp

ACTORS = {a.id: a for a in (ALICE, BOB, CAROL, DAVE)}
CLOCK = NOW + timedelta(seconds=1)
TOKEN = "tok-123"


def make_app(w: World) -> ReviewApp:
    return ReviewApp(
        w.store,
        {w.task.id: w.task},
        lambda env: ACTORS.get(env.get("HTTP_X_ACTOR", "")),
        lambda env: TOKEN,
        w.texts,
        lambda: CLOCK,
    )


def call(
    app: ReviewApp,
    method: str,
    path: str,
    actor: str = "bob",
    body: dict | list | None = None,
    raw: str | None = None,
):  # type: ignore[no-untyped-def,type-arg]
    data = (raw if raw is not None else urlencode(body or {}, doseq=True)).encode()
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "HTTP_X_ACTOR": actor,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
    }
    out: dict = {}  # type: ignore[type-arg]

    def start(status, headers):  # type: ignore[no-untyped-def]
        out["status"], out["headers"] = status, dict(headers)

    out["body"] = b"".join(app(env, start)).decode()
    return out


def form(w: World, app: ReviewApp, action: str, **extra: object) -> dict[str, object]:
    task = app.tasks[w.task.id]
    return {
        "csrf": TOKEN,
        "action": action,
        "base_version": w.store.version("obl-1"),
        "snapshot_hash": task.snapshot.hash,
        **extra,
    }
