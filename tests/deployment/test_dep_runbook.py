import json
import os
import re
import shlex
import signal
import subprocess
import time
import urllib.request
from pathlib import Path
from string import Template

import pytest
from dep_helpers import PY, ROOT, SECRET
from test_dep_cli import free_port

RUNBOOK = ROOT / "docs" / "16_runbook.md"
BLOCK = re.compile(r"```runbook\n(.*?)```", re.S)


def steps(text: str) -> list[list[str]]:
    out: list[list[str]] = []
    for block in BLOCK.findall(text):
        for line in block.splitlines():
            if not line.strip():
                continue
            if line.startswith("=> "):
                out[-1].append(line)
            else:
                out.append([line])
    return out


class Runner:
    def __init__(self, work: Path) -> None:
        self.vars = {
            "WORK": str(work),
            "STATE": str(work / "state"),
            "BACKUP": str(work / "backup"),
            "RESTORED": str(work / "restored"),
            "PORT": str(free_port()),
            "SECRET": SECRET,
        }
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("REGULUS_")}
        self.proc: subprocess.Popen[str] | None = None
        self.result: dict[str, object] = {}
        self.work = work

    def sub(self, s: str) -> str:
        return Template(s).safe_substitute(self.vars)

    def argv(self, cmd: str) -> tuple[list[str], dict[str, str]]:
        parts = shlex.split(self.sub(cmd))
        env = dict(self.env)
        while parts and re.fullmatch(r"[A-Z_]+=.*", parts[0]):
            k, v = parts.pop(0).split("=", 1)
            env[k] = v
        head = {"regulus": [PY, "-m", "regulus"], "pip": [PY, "-m", "pip"]}.get(parts[0])
        return (head + parts[1:] if head else parts), env

    def run(self, line: str) -> None:
        if line.startswith("ENV "):
            k, v = self.sub(line[4:]).split("=", 1)
            self.env[k] = v
            self.result = {}
        elif line.startswith("$ "):
            argv, env = self.argv(line[2:])
            r = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=ROOT, timeout=300)
            self.result = {"exit": r.returncode, "out": r.stdout + r.stderr}
        elif line.startswith("& "):
            argv, env = self.argv(line[2:])
            self.proc = subprocess.Popen(
                argv, env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            assert self.proc.stdout is not None
            while True:
                got = self.proc.stdout.readline()
                if got.startswith("ready"):
                    break
                assert self.proc.poll() is None, "server exited before ready"
            self.result = {}
        elif line.startswith("GET "):
            m = re.fullmatch(r"GET (\S+)(?: as (\S+) (\S+))?", line)
            assert m, line
            headers = {"X-Regulus-Actor": m[2], "X-Regulus-Roles": m[3]} if m[2] else {}
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.vars['PORT']}{m[1]}", headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    self.result = {"status": r.status, "out": r.read().decode()}
            except urllib.error.HTTPError as e:
                self.result = {"status": e.code, "out": e.read().decode()}
        elif line in ("STOP", "KILL"):
            assert self.proc is not None
            self.proc.send_signal(signal.SIGTERM if line == "STOP" else signal.SIGKILL)
            self.result = {"exit": self.proc.wait(timeout=60) if line == "STOP" else 0}
            if line == "KILL":
                self.proc.wait()
            self.proc = None
        else:
            raise AssertionError(f"unknown runbook directive: {line}")

    def expect(self, line: str) -> None:
        kind, _, arg = line[3:].partition(" ")
        if kind == "exit":
            assert self.result["exit"] == int(arg), self.result
        elif kind == "status":
            assert self.result["status"] == int(arg), self.result
        elif kind == "contains":
            assert self.sub(json.loads(arg)) in str(self.result["out"]), self.result
        elif kind == "absent":
            assert self.sub(json.loads(arg)) not in str(self.result["out"]), self.result
        else:
            raise AssertionError(line)


def test_runbook_has_the_required_sections():
    text = RUNBOOK.read_text(encoding="utf-8")
    for title in (
        "Build and install",
        "Configure and check",
        "Seed a demo state",
        "Start, probe",
        "Stop gracefully",
        "Holds, purges",
        "Snapshot, back up, restore",
        "Recover from an unclean stop",
    ):
        assert title in text
    assert SECRET not in text


def test_every_runbook_command_executes_and_produces_the_documented_output(tmp_path):
    runner = Runner(tmp_path)
    plan = steps(RUNBOOK.read_text(encoding="utf-8"))
    assert len(plan) > 40
    try:
        for step in plan:
            runner.run(step[0])
            for expectation in step[1:]:
                try:
                    runner.expect(expectation)
                except AssertionError as e:
                    pytest.fail(f"{step[0]} / {expectation}: {str(e)[:400]}")
    finally:
        if runner.proc is not None:
            runner.proc.kill()
            time.sleep(0.1)


def test_a_drifted_expectation_is_detected(tmp_path):
    runner = Runner(tmp_path)
    runner.run("$ regulus version")
    with pytest.raises(AssertionError):
        runner.expect("=> exit 2")
    with pytest.raises(AssertionError):
        runner.expect('=> contains "no-such-output"')
    with pytest.raises(AssertionError):
        runner.run("FROB")
