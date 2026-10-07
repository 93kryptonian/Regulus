import io
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from regulus.config import RegulusConfig, load
from regulus.domain import FieldChange
from regulus.evaluation.harness import ACTORS, NOW
from regulus.review import (
    Action,
    ActionRequest,
    RejectCode,
    RejectReason,
    ReviewConfig,
    apply,
    claim,
)
from regulus.runtime import Runtime, SystemClock, build, shutdown, startup
from regulus.seed import seed_demo
from regulus.workflow import SYSTEM, Kind

SECRET = "k" * 40
LATE = NOW + timedelta(days=200)
ROOT = Path(__file__).parents[2]
PY = sys.executable
R1 = {"HTTP_X_REGULUS_ACTOR": "r1", "HTTP_X_REGULUS_ROLES": "REVIEWER"}


def env(tmp: Path, **kw: str) -> dict[str, str]:
    return {
        "REGULUS_CSRF_SECRET": SECRET,
        "REGULUS_STATE_DIR": str(tmp / "st"),
        "REGULUS_AUTH_MODE": "dev_header",
        **kw,
    }


def cfg(tmp: Path, **kw: str) -> RegulusConfig:
    return load(env=env(tmp, **kw))


def boot(tmp: Path, serving: bool = False, at=LATE, **kw: str) -> Runtime:  # type: ignore[no-untyped-def]
    rt = build(cfg(tmp, **kw), clock=SystemClock(lambda: at))
    startup(rt, serving)
    return rt


def seeded(tmp: Path, extra: bool = False) -> RegulusConfig:
    rt = boot(tmp)
    seed_demo(rt)
    if extra:
        enrich(rt)
    shutdown(rt)
    return cfg(tmp)


def enrich(rt: Runtime) -> None:
    store = rt.parts.store
    r1 = next(a for a in ACTORS if a.id == "r1")
    oid = "demo-0"
    task = next(t for t in store.tasks.values() if t.obligation_id == oid)
    t = claim(task, r1.id, NOW + timedelta(seconds=5), 900)
    ob = store.review.get(oid)[0]
    edit = ActionRequest(
        action=Action.EDIT,
        task_id=t.id,
        base_version=store.review.version(oid),
        actor=r1,
        at=NOW + timedelta(seconds=6),
        changes=(
            FieldChange(field="deadline", before=ob.current.deadline, after="paling lambat 3 hari"),
        ),
        reason="scripted edit",
    )
    out = apply(store.review, t, edit, ReviewConfig(), rt.parts.texts)
    t = out.task or t
    rej = ActionRequest(
        action=Action.REJECT,
        task_id=t.id,
        base_version=store.review.version(oid),
        actor=r1,
        at=NOW + timedelta(seconds=7),
        reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE),
    )
    out = apply(store.review, t, rej, ReviewConfig(), rt.parts.texts)
    store.tasks[t.id] = out.task or t
    for i, kind in enumerate((Kind.NOTIFICATION_QUEUED, Kind.NOTIFICATION_DELIVERED)):
        store.append("notification:n1", kind, SYSTEM, NOW + timedelta(seconds=10 + i), f"k{i}", {})
    for _ in range(3):
        call(rt.app, "/tasks", **R1)


def call(
    app: Any, path: str, method: str = "GET", body: dict[str, Any] | None = None, **headers: str
) -> dict[str, Any]:
    data = urlencode(body or {}, doseq=True).encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": io.BytesIO(data),
        **headers,
    }
    out: dict[str, Any] = {}
    out["body"] = b"".join(
        app(environ, lambda s, h, e=None: out.update(status=s, headers=dict(h)))
    ).decode()
    out["code"] = int(out["status"][:3])
    return out


def cli(args: list[str], tmp: Path, **kw: str) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, **env(tmp, **kw)}
    return subprocess.run(
        [PY, "-m", "regulus", *args], capture_output=True, text=True, env=e, cwd=tmp, timeout=120
    )


def snapshot_doc(tmp: Path) -> dict[str, Any]:
    return json.loads((tmp / "st" / "snapshot.json").read_text(encoding="utf-8"))
