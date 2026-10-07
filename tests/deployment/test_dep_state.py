import json
import random
import shutil

import pytest
from dep_helpers import LATE, R1, SECRET, boot, call, cfg, seeded, snapshot_doc

from regulus.evaluation.harness import NOW
from regulus.reliability.wrappers import Corruption, corrupt
from regulus.runtime import (
    Exit,
    Refused,
    build,
    integrity,
    shutdown,
    snapshot_now,
    startup,
    state_hash,
)
from regulus.state import (
    _GOV,
    _LOG,
    _STREAMS,
    CRASH_STEPS,
    MARKER,
    SNAPSHOT,
    TMP,
    SnapshotCrash,
    StateDir,
    _digest,
)
from regulus.workflow import SYSTEM, Principal, WorkflowRole


def test_restart_convergence_is_repeatable(tmp_path):
    seeded(tmp_path, extra=True)
    seen = []
    for _ in range(4):
        rt = boot(tmp_path)
        assert rt.clean and not integrity(rt).broken and not integrity(rt).unreceipted
        seen.append(state_hash(rt))
        shutdown(rt)
    assert len(set(seen)) == 1


def _crash_case(tmp_path, step):
    seeded(tmp_path)
    before = boot(tmp_path)
    gen = before.generation
    before.parts.retention.holds["review:demo-1"] = "marker for the new generation"
    before.state.crash_at = step
    with pytest.raises(SnapshotCrash):
        snapshot_now(before)
    before.state.release()
    return gen


@pytest.mark.parametrize("step", CRASH_STEPS)
def test_a_crash_at_each_snapshot_step_leaves_one_complete_snapshot_and_a_truthful_marker(
    tmp_path, step
):
    gen = _crash_case(tmp_path, step)
    doc = snapshot_doc(tmp_path)
    new = step in ("after_rename", "before_marker", "after_marker")
    assert doc["generation"] == (gen + 1 if new else gen)
    assert doc["digest"] == _digest(doc["state"])
    marker = StateDir(tmp_path / "st").read_marker()
    assert (marker is not None) == (step == "after_marker") or marker["generation"] == gen
    rt = boot(tmp_path)
    assert rt.generation == doc["generation"]
    clean = step == "after_marker"
    assert rt.clean is clean
    assert ("unclean_shutdown_recovered" in rt.notes) is (not clean)
    assert ("review:demo-1" in rt.parts.retention.holds) is new
    assert not (tmp_path / "st" / TMP).exists()
    assert not integrity(rt).broken and not integrity(rt).unreceipted
    shutdown(rt)


def test_marker_names_a_generation_only_after_that_snapshot_completed(tmp_path):
    gen = _crash_case(tmp_path, "before_marker")
    sd = StateDir(tmp_path / "st")
    snap_gen = snapshot_doc(tmp_path)["generation"]
    m = sd.read_marker()
    assert snap_gen == gen + 1 and (m is None or m["generation"] != snap_gen)


def test_a_stale_marker_never_makes_a_start_clean(tmp_path):
    seeded(tmp_path)
    rt = boot(tmp_path)
    rt.state.write_snapshot(
        rt.generation + 5, rt.run_id, json.loads(json.dumps(snapshot_doc(tmp_path)["state"]))
    )
    (tmp_path / "st" / MARKER).write_text(json.dumps({"generation": 1, "run_id": "old"}))
    rt.state.release()
    again = boot(tmp_path)
    assert again.generation == 6 and not again.clean and "unclean_shutdown_recovered" in again.notes


def test_startup_deletes_the_marker_before_serving(tmp_path):
    seeded(tmp_path)
    assert (tmp_path / "st" / MARKER).exists()
    rt = boot(tmp_path)
    assert not (tmp_path / "st" / MARKER).exists() and rt.clean
    rt.state.release()
    assert not boot(tmp_path).clean


def _rewrite(tmp_path, mutate):
    doc = snapshot_doc(tmp_path)
    mutate(doc["state"])
    doc["digest"] = _digest(doc["state"])
    (tmp_path / "st" / SNAPSHOT).write_text(json.dumps(doc, sort_keys=True, ensure_ascii=False))


def _dir_bytes(tmp_path):
    return {p.name: p.read_bytes() for p in sorted((tmp_path / "st").iterdir())}


def _refused(tmp_path, code=Exit.STATE):
    before = _dir_bytes(tmp_path)
    rt = build(cfg(tmp_path))
    with pytest.raises(Refused) as e:
        startup(rt)
    assert e.value.code is code
    assert _dir_bytes(tmp_path) == before and not (tmp_path / "st" / "lock").exists()
    return e.value


def _corrupt_part(state, where, mode, rng):
    if where == "stream":
        streams = _STREAMS.validate_python(state["streams"])
        key = "obligation:demo-0"
        streams[key] = corrupt(streams[key], mode, rng, foreign=streams["obligation:demo-1"][0])
        state["streams"] = json.loads(_STREAMS.dump_json(streams))
    elif where == "review":
        logs = _LOG.validate_python(state["log"])
        logs["demo-0"] = corrupt(logs["demo-0"], mode, rng, foreign=logs["demo-0"][0])
        state["log"] = json.loads(_LOG.dump_json(logs))
    else:
        recs = tuple(_GOV.validate_python(state["access"]))
        state["access"] = json.loads(
            _GOV.dump_json(list(corrupt(recs, mode, rng, foreign=recs[0])))
        )


@pytest.mark.parametrize("where", ["stream", "review", "access"])
@pytest.mark.parametrize("mode", list(Corruption))
def test_each_corruption_class_in_a_snapshot_refuses_startup_and_changes_nothing(
    tmp_path, where, mode
):
    seeded(tmp_path, extra=True)
    _rewrite(tmp_path, lambda s: _corrupt_part(s, where, mode, random.Random(7)))
    err = _refused(tmp_path)
    assert err.reasons


def test_truncated_or_partial_snapshot_is_refused(tmp_path):
    seeded(tmp_path)
    f = tmp_path / "st" / SNAPSHOT
    raw = f.read_bytes()
    f.write_bytes(raw[: len(raw) // 2])
    _refused(tmp_path)
    f.write_bytes(raw)
    _rewrite(tmp_path, lambda s: s.pop("streams"))
    _refused(tmp_path)
    f.write_bytes(raw)
    doc = snapshot_doc(tmp_path)
    doc["state"]["texts"]["R:1"] = "altered"
    f.write_text(json.dumps(doc))
    _refused(tmp_path)


def test_a_stream_deleted_without_a_purge_intent_is_corruption(tmp_path):
    seeded(tmp_path, extra=True)
    _rewrite(tmp_path, lambda s: s["streams"].pop("notification:n1"))
    err = _refused(tmp_path)
    assert any("unreceipted" in r for r in err.reasons)


def test_a_purge_interrupted_after_the_delete_is_recovered_not_refused(tmp_path):
    seeded(tmp_path, extra=True)
    rt = boot(tmp_path)
    rt.parts.retention.fail_after = "delete"
    op = Principal(id="op1", roles=(WorkflowRole.OPERATOR,))
    with pytest.raises(RuntimeError):
        rt.parts.retention.purge(op, "notification:n1", "elapsed", LATE)
    assert "notification:n1" not in rt.parts.store.streams
    snapshot_now(rt)
    rt.state.release()
    (tmp_path / "st" / MARKER).unlink()
    again = boot(tmp_path)
    kinds = [r.kind for r in again.parts.purge.records]
    assert kinds == ["PURGE_INTENT", "PURGE_APPLIED"] and again.recovered["purges"] == 1
    assert not integrity(again).unreceipted and not integrity(again).broken


def test_an_interrupted_purge_intent_with_the_stream_still_present_is_recovered(tmp_path):
    seeded(tmp_path, extra=True)
    rt = boot(tmp_path)
    rt.parts.retention.fail_after = "intent"
    op = Principal(id="op1", roles=(WorkflowRole.OPERATOR,))
    with pytest.raises(RuntimeError):
        rt.parts.retention.purge(op, "notification:n1", "elapsed", LATE)
    snapshot_now(rt)
    rt.state.release()
    again = boot(tmp_path)
    assert [r.kind for r in again.parts.purge.records] == ["PURGE_INTENT", "PURGE_APPLIED"]
    assert "notification:n1" not in again.parts.store.streams
    assert not integrity(again).broken


def test_an_intent_phase_submission_is_completed_from_its_payload(tmp_path):
    from regulus.evaluation.harness import OWNER, TEXT, generation_result
    from regulus.workflow import SnapshotInputs, submit_for_review

    rt = boot(tmp_path)
    rt.parts.texts[OWNER] = TEXT
    rt.parts.store.fail_after = "intent"
    with pytest.raises(BaseException) as e:
        submit_for_review(
            rt.parts.store,
            generation_result("late-1"),
            SnapshotInputs(permitted_source=TEXT),
            SYSTEM,
            NOW,
            rt.parts.texts,
        )
    assert type(e.value).__name__ == "Crash"
    assert not rt.parts.store.registered("late-1")
    snapshot_now(rt)
    rt.state.release()
    again = boot(tmp_path)
    assert again.recovered["submissions"] == 1 and again.parts.store.registered("late-1")
    assert any(t.obligation_id == "late-1" for t in again.parts.store.tasks.values())
    assert not integrity(again).broken and not integrity(again).unreceipted


def test_recovery_is_rerunnable(tmp_path):
    seeded(tmp_path, extra=True)
    rt = boot(tmp_path)
    rt.parts.retention.fail_after = "delete"
    op = Principal(id="op1", roles=(WorkflowRole.OPERATOR,))
    with pytest.raises(RuntimeError):
        rt.parts.retention.purge(op, "notification:n1", "elapsed", LATE)
    snapshot_now(rt)
    rt.state.release()
    first = boot(tmp_path)
    assert first.recovered["purges"] == 1
    shutdown(first)
    second = boot(tmp_path)
    assert second.recovered == {"purges": 0, "submissions": 0, "spans": 0} and second.clean
    assert [r.kind for r in second.parts.purge.records] == ["PURGE_INTENT", "PURGE_APPLIED"]


def test_second_server_on_one_state_dir_is_refused(tmp_path):
    rt = boot(tmp_path)
    other = build(cfg(tmp_path))
    with pytest.raises(Refused) as e:
        startup(other)
    assert e.value.code is Exit.RUNTIME
    rt.state.release()
    startup(other)


def test_a_dead_process_lock_is_not_treated_as_live(tmp_path):
    rt = boot(tmp_path)
    (tmp_path / "st" / "lock").write_text(json.dumps({"pid": 2**22 + 12345, "run_id": "gone"}))
    assert StateDir(tmp_path / "st").is_free()
    rt.state.release()
    boot(tmp_path)


def test_backup_restore_serves_the_same_tasks(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    seeded(a, extra=True)
    rt = boot(a)
    tasks_a = sorted(rt.parts.store.tasks)
    h = state_hash(rt)
    shutdown(rt)
    shutil.copytree(a / "st", b / "st")
    restored = boot(b)
    assert sorted(restored.parts.store.tasks) == tasks_a and state_hash(restored) == h
    assert not integrity(restored).broken
    assert call(restored.app, "/tasks", **R1)["code"] == 200


def test_secret_never_reaches_the_state_directory(tmp_path):
    rt = boot(tmp_path, serving=True)
    call(rt.app, "/tasks", **R1)
    shutdown(rt)
    for p in (tmp_path / "st").iterdir():
        assert SECRET not in p.read_text(encoding="utf-8")


def test_access_log_survives_restart_with_its_chain(tmp_path):
    rt = boot(tmp_path, serving=True)
    call(rt.app, "/tasks", **R1)
    n = len(rt.parts.access.records)
    shutdown(rt)
    again = boot(tmp_path)
    assert len(again.parts.access.records) == n and again.parts.access.verified()
