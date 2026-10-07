import time

import pytest
from dep_helpers import ROOT, SECRET

from regulus.evaluation.runbook import Runner, steps

RUNBOOK = ROOT / "docs" / "16_runbook.md"


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
    runner = Runner(tmp_path, ROOT)
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
    runner = Runner(tmp_path, ROOT)
    runner.run("$ regulus version")
    with pytest.raises(AssertionError):
        runner.expect("=> exit 2")
    with pytest.raises(AssertionError):
        runner.expect('=> contains "no-such-output"')
    with pytest.raises(AssertionError):
        runner.run("FROB")
