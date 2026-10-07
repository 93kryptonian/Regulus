import io
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from rv_engine_helpers import ALICE, BOB, CAROL, DAVE, TEXT, World
from rv_helpers import NOW

from regulus.governance import ChainLog, GovernedApp, load_matrix
from regulus.review import Actor, Role
from regulus.review_ui import ReviewApp

ROOT = Path(__file__).parents[2]
MATRIX = load_matrix(ROOT / "governance" / "access_matrix.v1.json")
CLOCK = NOW + timedelta(seconds=1)
TOKEN = "tok"
NOBODY = Actor(id="nobody", roles=())
BOTH = Actor(id="both", roles=(Role.REVIEWER, Role.PUBLISHER))
ACTORS = {a.id: a for a in (ALICE, BOB, CAROL, DAVE, NOBODY, BOTH)}
__all__ = ["ACTORS", "CLOCK", "MATRIX", "ROOT", "TEXT", "TOKEN", "World", "call", "governed"]


def governed(w: World, audit: ChainLog | None = None) -> tuple[GovernedApp, ReviewApp, ChainLog]:
    inner = ReviewApp(
        w.store,
        {w.task.id: w.task},
        lambda env: ACTORS.get(env.get("HTTP_X_ACTOR", "")),
        lambda env: TOKEN,
        w.texts,
        lambda: CLOCK,
    )
    log = audit if audit is not None else ChainLog("access")
    return GovernedApp(inner, MATRIX, log, lambda: CLOCK), inner, log


def call(app, method: str, path: str, actor: str = "bob", body: dict | None = None):  # type: ignore[no-untyped-def,type-arg]
    data = urlencode(body or {}, doseq=True).encode()
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "HTTP_X_ACTOR": actor,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
    }
    out: dict = {}  # type: ignore[type-arg]
    out["body"] = b"".join(app(env, lambda s, h: out.update(status=s, headers=dict(h)))).decode()
    return out


def form(w: World, inner: ReviewApp, action: str, **extra: object) -> dict[str, object]:
    t = inner.tasks[w.task.id]
    return {
        "csrf": TOKEN,
        "action": action,
        "base_version": w.store.version("obl-1"),
        "snapshot_hash": t.snapshot.hash,
        **extra,
    }


__all__ += ["form", "datetime"]
