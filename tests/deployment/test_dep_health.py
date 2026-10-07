import json
import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from dep_helpers import R1, SECRET, boot, call, cfg, seeded

from regulus.evaluation.harness import TEXT
from regulus.governance import GovernedApp
from regulus.health import CHECKS, Served, readiness
from regulus.observability.taxonomy import Stage
from regulus.runtime import SystemClock, build, shutdown
from regulus.workflow import WorkflowRecord


def served(tmp_path, **kw):
    rt = boot(tmp_path, serving=True, **kw)
    return rt, Served(rt)


def ready(app):
    r = call(app, "/readyz")
    return r["code"], json.loads(r["body"])


def test_served_app_is_always_the_governed_app(tmp_path):
    rt, app = served(tmp_path)
    assert isinstance(rt.app, GovernedApp) and app.rt.app is rt.app
    before = len(rt.parts.access.records)
    for path in ("/tasks", "/tasks/none", "/anything"):
        call(app, path)
    assert len(rt.parts.access.records) == before + 3


def test_auth_mode_none_serves_only_health(tmp_path):
    rt, app = served(tmp_path, REGULUS_AUTH_MODE="none")
    assert call(app, "/healthz")["code"] == 200 and call(app, "/readyz")["code"] == 200
    assert call(app, "/tasks", **R1)["code"] == 401
    tid = next(iter(rt.parts.store.tasks), "x")
    for path in (f"/tasks/{tid}", f"/tasks/{tid}/claim", f"/tasks/{tid}/action"):
        for method in ("GET", "POST"):
            assert call(app, path, method, {"csrf": "x"}, **R1)["code"] == 401


def test_health_bodies_are_content_free(tmp_path):
    seeded(tmp_path, extra=True)
    rt, app = served(tmp_path)
    bodies = [call(app, "/healthz")["body"], call(app, "/readyz")["body"]]
    for b in bodies:
        for forbidden in (SECRET, TEXT, str(tmp_path), "demo-0", "127.0.0.1", "8765", "dev_header"):
            assert forbidden not in b
        doc = json.loads(b)
        stack = [doc]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                stack += list(x.values())
            elif isinstance(x, list):
                stack += x
            else:
                assert isinstance(x, bool | int) or re.fullmatch(r"[a-z_0-9\-]+", x)


def test_health_works_without_identity_and_serves_no_review_content(tmp_path):
    _, app = served(tmp_path)
    r = call(app, "/readyz")
    assert r["code"] == 200 and "task" not in r["body"]


def test_ready_when_healthy_and_before_startup_not_ready(tmp_path):
    rt, app = served(tmp_path)
    code, body = ready(app)
    assert (
        code == 200
        and body["ready"]
        and body["failing"] == []
        and set(body["checks"]) == set(CHECKS)
    )
    cold = build(cfg(tmp_path / "other"))
    assert readiness(cold)["ready"] is False and "startup_recovery" in readiness(cold)["failing"]
    assert call(Served(cold), "/tasks", **R1)["code"] == 503
    shutdown(rt)


def flips(app, name, inject, restore, reason=None):
    inject()
    code, body = ready(app)
    assert code == 503 and body["failing"] == [name] and body["checks"][name] is False
    if reason:
        assert reason in body["degraded"]
    restore()
    code, body = ready(app)
    assert code == 200 and body["ready"] and body["failing"] == []


def test_readiness_flips_for_packaged_data(tmp_path, monkeypatch):
    rt, app = served(tmp_path)
    import regulus.health as h

    orig = h.default_matrix

    def boom():
        raise OSError

    flips(
        app,
        "packaged_data",
        lambda: monkeypatch.setattr(h, "default_matrix", boom),
        lambda: monkeypatch.setattr(h, "default_matrix", orig),
    )


def test_readiness_flips_for_state_integrity(tmp_path):
    seeded(tmp_path)
    rt, app = served(tmp_path)
    key = "obligation:demo-0"
    good = rt.parts.store.streams[key]
    bad = (good[0].model_copy(update={"principal_id": "mallory"}), *good[1:])
    flips(
        app,
        "state_integrity",
        lambda: rt.parts.store.streams.__setitem__(key, bad),
        lambda: rt.parts.store.streams.__setitem__(key, good),
    )
    assert isinstance(good[0], WorkflowRecord)


def test_readiness_and_review_pages_fail_closed_when_the_audit_log_fails(tmp_path):
    seeded(tmp_path)
    rt, app = served(tmp_path)

    def inject():
        rt.parts.access.fail_next = 1000

    flips(
        app,
        "audit_appendable",
        inject,
        lambda: setattr(rt.parts.access, "fail_next", 0),
        "audit_unavailable",
    )
    rt.parts.access.fail_next = 1000
    assert call(app, "/tasks", **R1)["code"] == 503
    rt.parts.access.fail_next = 0
    assert call(app, "/tasks", **R1)["code"] == 200


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_readiness_flips_for_a_read_only_state_directory(tmp_path):
    rt, app = served(tmp_path)
    d = tmp_path / "st"
    flips(app, "state_dir_writable", lambda: d.chmod(0o500), lambda: d.chmod(0o700))


def test_readiness_flips_for_a_clock_regression(tmp_path):
    seq = iter([datetime(2026, 10, 1, tzinfo=UTC)] * 50)
    cur = {"t": datetime(2026, 10, 1, tzinfo=UTC)}
    rt = build(cfg(tmp_path), clock=SystemClock(lambda: cur["t"]))
    from regulus.runtime import startup

    startup(rt)
    app = Served(rt)
    assert ready(app)[0] == 200 and seq
    cur["t"] -= timedelta(hours=1)
    rt.clock.now()
    code, body = ready(app)
    assert code == 503 and body["failing"] == ["clock_monotonic"]
    rt.clock.regressed = False
    assert ready(app)[0] == 200


def test_readiness_flips_for_a_full_observation_buffer(tmp_path):
    rt, app = served(tmp_path, REGULUS_OBSERVATION_BUFFER="3")
    rt.observer.buffer.drain(
        __import__("regulus.observability.sinks", fromlist=["x"]).InMemorySink(), 100
    )
    cap = rt.observer.buffer.capacity

    def fill():
        while rt.observer.buffer.buffered < cap:
            rt.observer.point(rt.run_id, Stage.RUN)

    def drain():
        rt.observer.buffer.drain(
            __import__("regulus.observability.sinks", fromlist=["x"]).InMemorySink(), 100
        )

    flips(app, "observation_buffer", fill, drain, "buffer_full")
    fill()
    rt.observer.point(rt.run_id, Stage.RUN)
    assert rt.observer.buffer.dropped_total >= 1 and rt.observer.buffer.balanced()
    assert call(app, "/tasks", **R1)["code"] == 200
    assert call(app, "/healthz")["code"] == 200


def test_readiness_flips_for_a_missing_configured_file(tmp_path):
    pol = tmp_path / "pol.json"
    pol.write_text(json.dumps({"illustrative": True, "days": {"WORKFLOW": 90}}))
    rt, app = served(tmp_path, REGULUS_RETENTION_POLICY=str(pol))
    bak = tmp_path / "pol.bak"
    flips(app, "configuration", lambda: pol.rename(bak), lambda: bak.rename(pol))


def test_readiness_flips_while_draining(tmp_path):
    rt, app = served(tmp_path)
    flips(
        app,
        "startup_recovery",
        lambda: setattr(rt, "draining", True),
        lambda: setattr(rt, "draining", False),
    )


def test_an_unclean_start_is_reported_as_degraded_not_hidden(tmp_path):
    seeded(tmp_path)
    boot(tmp_path).state.release()
    rt, app = served(tmp_path)
    code, body = ready(app)
    assert code == 200 and "unclean_shutdown_recovered" in body["degraded"]


def test_requests_are_observed_without_invalid_events(tmp_path):
    rt, app = served(tmp_path)
    call(app, "/tasks", **R1)
    call(app, "/tasks")
    call(app, "/nope", **R1)
    assert rt.observer.invalid == 0 and rt.observer.buffer.emitted >= 1
    shutdown(rt)
    lines = (tmp_path / "st" / "events.jsonl").read_text().splitlines()
    assert lines and all(SECRET not in line and TEXT not in line for line in lines)
