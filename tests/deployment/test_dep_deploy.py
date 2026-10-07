import json
import re
import shutil
import subprocess
import time

import pytest
from dep_helpers import ROOT, SECRET

from regulus.config import RegulusConfig, load

DEPLOY = ROOT / "deploy"


def docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def test_example_configuration_lists_every_setting_with_its_default_and_no_secret(tmp_path):
    doc = json.loads((DEPLOY / "regulus.example.json").read_text(encoding="utf-8"))
    fields = set(RegulusConfig.model_fields) - {"csrf_secret"}
    assert set(doc) == fields
    assert not any(re.search("secret|token|password|key", k, re.I) for k in doc)
    f = tmp_path / "c.json"
    f.write_text(json.dumps(doc))
    assert load(f, {"REGULUS_CSRF_SECRET": SECRET}) == load(
        env={"REGULUS_CSRF_SECRET": SECRET}, path=None
    )


def test_dockerfile_contract_properties():
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM python:3\.12-slim", text, re.M)
    assert re.search(r"^USER regulus", text, re.M) and "useradd" in text
    assert "requirements.lock" in text and "HEALTHCHECK" in text and "/healthz" in text
    assert "VOLUME /var/lib/regulus" in text
    assert not re.search(r"^(ENV|ARG).*(SECRET|TOKEN|PASSWORD|KEY)", text, re.M | re.I)
    assert "REGULUS_CSRF_SECRET" not in text and SECRET not in text
    assert not re.search(r"COPY .*(state|\.env|pdf|evaluation)", text)


def test_dockerignore_keeps_state_secrets_and_development_evidence_out_of_the_image():
    names = set((DEPLOY / "Dockerfile.dockerignore").read_text(encoding="utf-8").split())
    assert {".git", ".venv", "tests", "evaluation", "pdf", "regulus-state", ".env"} <= names


def test_the_lock_installs_before_the_package_so_the_build_is_reproducible():
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert text.index("-r requirements.lock") < text.index("--no-deps .")


@pytest.mark.skipif(
    not docker_ready(), reason="no container runtime: container evidence is NOT_MEASURABLE"
)
def test_container_builds_and_reports_healthy(tmp_path):
    tag = "regulus-ref-test"
    b = subprocess.run(
        ["docker", "build", "-f", str(DEPLOY / "Dockerfile"), "-t", tag, str(ROOT)],
        capture_output=True,
        text=True,
    )
    assert b.returncode == 0, b.stderr[-800:]
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-e",
            f"REGULUS_CSRF_SECRET={SECRET}",
            "-e",
            "REGULUS_AUTH_MODE=none",
            tag,
        ],
        capture_output=True,
        text=True,
    )
    cid = run.stdout.strip()
    try:
        status = ""
        for _ in range(30):
            status = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Health.Status}}", cid],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if status == "healthy":
                break
            time.sleep(2)
        assert status == "healthy"
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)
