import json
import os
import signal
import socket
import subprocess
import time
import urllib.request

import pytest
from dep_helpers import PY, SECRET, cli, env, seeded, snapshot_doc

from regulus.evaluation.harness import TEXT


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(tmp_path, port=None, **kw):
    port = port or free_port()
    e = {**os.environ, **env(tmp_path, REGULUS_PORT=str(port), **kw)}
    p = subprocess.Popen(
        [PY, "-m", "regulus", "serve"],
        env=e,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        line = p.stdout.readline()
        if line.startswith("ready"):
            return p, port
        if p.poll() is not None:
            break
    p.kill()
    raise AssertionError(p.stderr.read())


def get(port, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def stop(p):
    p.send_signal(signal.SIGTERM)
    return p.wait(timeout=30)


@pytest.mark.parametrize(
    "kw,field",
    [
        ({"REGULUS_PORT": "70000"}, "port"),
        ({"REGULUS_PORT": "notanumber"}, "port"),
        ({"REGULUS_AUTH_MODE": "wide-open"}, "auth_mode"),
        ({"REGULUS_HOST": "0.0.0.0"}, "host"),
        ({"REGULUS_HOST": "0.0.0.0", "REGULUS_AUTH_MODE": "dev_header"}, "host"),
        ({"REGULUS_CSRF_SECRET": "tiny-secret-9"}, "csrf_secret"),
        ({"REGULUS_CLAIM_TTL_SECONDS": "0"}, "claim_ttl_seconds"),
        ({"REGULUS_OBSERVATION_BUFFER": "0"}, "observation_buffer"),
    ],
)
def test_invalid_configuration_exits_2_naming_the_field_only(tmp_path, kw, field):
    for command in ("check", "serve", "verify", "seed-demo"):
        r = cli([command], tmp_path, **kw)
        assert r.returncode == 2 and field in r.stderr
        for v in kw.values():
            if v in ("tiny-secret-9", "wide-open", "notanumber"):
                assert v not in r.stdout + r.stderr
    assert not (tmp_path / "st").exists()


def test_missing_secret_and_secret_in_file_exit_2(tmp_path):
    e = {k: v for k, v in env(tmp_path).items() if k != "REGULUS_CSRF_SECRET"}
    r = subprocess.run(
        [PY, "-m", "regulus", "check"],
        capture_output=True,
        text=True,
        env={**{k: v for k, v in os.environ.items() if not k.startswith("REGULUS_")}, **e},
        cwd=tmp_path,
    )
    assert r.returncode == 2 and "csrf_secret" in r.stderr
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"api_token": "z" * 40}))
    r = subprocess.run(
        [PY, "-m", "regulus", "--config", str(f), "check"],
        capture_output=True,
        text=True,
        env={**os.environ, **env(tmp_path)},
        cwd=tmp_path,
    )
    assert r.returncode == 2 and "api_token" in r.stderr and "z" * 40 not in r.stdout + r.stderr


def test_check_output_is_content_free_and_masks_the_secret(tmp_path):
    seeded(tmp_path, extra=True)
    r = cli(["check"], tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert (
        out["config"]["csrf_secret"] == "<set>" and out["packaged_data"] and out["state_readable"]
    )
    assert (
        out["evaluation_assets_packaged"] is False
        and out["lock_free"]
        and out["valid_backup_source"]
    )
    for text in (r.stdout, r.stderr):
        assert SECRET not in text and TEXT not in text and "demo-0" not in text


def test_version_runs_without_configuration(tmp_path):
    r = subprocess.run(
        [PY, "-m", "regulus", "version"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={k: v for k, v in os.environ.items() if not k.startswith("REGULUS_")},
    )
    assert r.returncode == 0 and json.loads(r.stdout)["version"]


def test_seed_demo_twice_is_deterministic_and_refuses_a_non_empty_directory(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ra, rb = cli(["seed-demo"], a), cli(["seed-demo"], b)
    assert ra.returncode == rb.returncode == 0 and ra.stdout == rb.stdout
    sa, sb = snapshot_doc(a), snapshot_doc(b)
    assert sa["digest"] == sb["digest"] and sa["state"] == sb["state"]
    va, vb = cli(["verify"], a), cli(["verify"], b)
    assert va.returncode == vb.returncode == 0 and va.stdout == vb.stdout
    again = cli(["seed-demo"], a)
    assert again.returncode == 4 and "not empty" in again.stderr
    assert snapshot_doc(a)["digest"] == sa["digest"]


def test_verify_reports_corruption_with_exit_3(tmp_path):
    seeded(tmp_path)
    doc = snapshot_doc(tmp_path)
    from regulus.state import _digest

    doc["state"]["streams"]["obligation:demo-0"][0]["principal_id"] = "mallory"
    doc["digest"] = _digest(doc["state"])
    (tmp_path / "st" / "snapshot.json").write_text(json.dumps(doc))
    r = cli(["verify"], tmp_path)
    assert r.returncode == 3 and "obligation:demo-0" in r.stdout
    assert cli(["serve"], tmp_path).returncode == 3


def test_operator_commands_hold_release_purge_and_recover(tmp_path):
    seeded(tmp_path, extra=True)
    base = ["--operator", "op1", "--stream", "notification:n1", "--reason", "legal"]
    held = cli(["hold", *base], tmp_path)
    assert held.returncode == 0 and json.loads(held.stdout)["result"] is True
    refused = cli(["purge", *base], tmp_path)
    assert json.loads(refused.stdout)["result"] == "REFUSED"
    assert json.loads(cli(["release", *base], tmp_path).stdout)["result"] is True
    done = cli(["purge", *base], tmp_path)
    assert json.loads(done.stdout)["result"] in ("APPLIED", "REFUSED")
    denied = cli(
        ["hold", "--operator", "op1", "--stream", "obligation:demo-1", "--reason", "x"], tmp_path
    )
    assert denied.returncode == 0
    assert json.loads(cli(["recover-purges", "--operator", "op1"], tmp_path).stdout)["result"] == 0
    v = cli(["verify"], tmp_path)
    assert v.returncode == 0


def test_a_running_server_blocks_a_second_server_and_operator_commands(tmp_path):
    seeded(tmp_path)
    p, port = start_server(tmp_path)
    try:
        assert get(port, "/healthz")[0] == 200
        assert cli(["serve"], tmp_path, REGULUS_PORT=str(free_port())).returncode == 4
        assert cli(["snapshot"], tmp_path).returncode == 4
        assert cli(["verify"], tmp_path).returncode == 4
        chk = json.loads(cli(["check"], tmp_path).stdout)
        assert chk["lock_free"] is False and chk["valid_backup_source"] is False
    finally:
        assert stop(p) == 0
    after = json.loads(cli(["check"], tmp_path).stdout)
    assert after["lock_free"] and after["valid_backup_source"]


def test_serve_end_to_end_with_sigterm_snapshot_and_content_free_logs(tmp_path):
    seeded(tmp_path)
    gen = snapshot_doc(tmp_path)["generation"]
    p, port = start_server(tmp_path)
    assert get(port, "/readyz")[0] == 200
    assert get(port, "/tasks")[0] == 401
    status, body = get(port, "/tasks", {"X-Regulus-Actor": "r1", "X-Regulus-Roles": "REVIEWER"})
    assert status == 200 and TEXT not in get(port, "/healthz")[1]
    assert stop(p) == 0
    out, err = p.stdout.read(), p.stderr.read()
    assert snapshot_doc(tmp_path)["generation"] == gen + 1
    for text in (out, err):
        assert SECRET not in text and TEXT not in text
    assert "dev_header" in err and "insecure" in err
    assert cli(["verify"], tmp_path).returncode == 0


def test_sigterm_with_a_request_in_flight_completes_it_first(tmp_path):
    seeded(tmp_path)
    gen = snapshot_doc(tmp_path)["generation"]
    p, port = start_server(tmp_path)
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(b"GET /tasks HTTP/1.0\r\nX-Regulus-Actor: r1\r\nX-Regulus-Roles: REVIEWER\r\n")
    time.sleep(0.5)
    p.send_signal(signal.SIGTERM)
    time.sleep(0.8)
    assert p.poll() is None
    s.sendall(b"\r\n")
    data = b""
    while chunk := s.recv(65536):
        data += chunk
    assert data.startswith(b"HTTP/1.0 200")
    assert p.wait(timeout=30) == 0
    assert snapshot_doc(tmp_path)["generation"] == gen + 1


def test_port_in_use_exits_4_before_ready_and_leaves_the_state_clean(tmp_path):
    seeded(tmp_path)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        r = cli(["serve"], tmp_path, REGULUS_PORT=str(port))
    assert r.returncode == 4 and "ready" not in r.stdout
    assert cli(["verify"], tmp_path).returncode == 0
    assert not (tmp_path / "st" / "lock").exists()


def test_a_killed_server_restarts_unclean_and_recovers(tmp_path):
    seeded(tmp_path)
    p, port = start_server(tmp_path)
    p.kill()
    p.wait()
    assert cli(["check"], tmp_path).returncode == 0
    q, port = start_server(tmp_path)
    try:
        status, body = get(port, "/readyz")
        assert status == 200 and "unclean_shutdown_recovered" in json.loads(body)["degraded"]
    finally:
        assert stop(q) == 0


def test_auth_none_server_refuses_review_routes_but_answers_health(tmp_path):
    seeded(tmp_path)
    p, port = start_server(tmp_path, REGULUS_AUTH_MODE="none")
    try:
        assert get(port, "/healthz")[0] == 200 and get(port, "/readyz")[0] == 200
        assert (
            get(port, "/tasks", {"X-Regulus-Actor": "r1", "X-Regulus-Roles": "REVIEWER"})[0] == 401
        )
    finally:
        assert stop(p) == 0
