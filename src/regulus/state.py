import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from regulus.domain import Obligation
from regulus.governance import ChainLog, GovRecord, IdentityMap, Retention
from regulus.review import ReviewRecord, ReviewTask
from regulus.workflow import InMemoryWorkflowStore, IntentWorkflowStore, WorkflowRecord

SNAPSHOT, MARKER, LOCK, TMP = "snapshot.json", "marker.json", "lock", "snapshot.json.tmp"
CRASH_STEPS = (
    "before_tmp",
    "during_tmp",
    "after_tmp",
    "after_flush",
    "after_rename",
    "before_marker",
    "after_marker",
)

_OBL = TypeAdapter(dict[str, Obligation])
_LOG = TypeAdapter(dict[str, tuple[ReviewRecord, ...]])
_TASKS = TypeAdapter(dict[str, ReviewTask])
_STREAMS = TypeAdapter(dict[str, tuple[WorkflowRecord, ...]])
_GOV = TypeAdapter(list[GovRecord])


class SnapshotCorrupt(Exception):
    pass


class LockHeld(Exception):
    pass


class SnapshotCrash(BaseException):
    pass


@dataclass
class Parts:
    store: IntentWorkflowStore | InMemoryWorkflowStore
    texts: dict[str, str]
    access: ChainLog
    purge: ChainLog
    retention: Retention
    idmap: IdentityMap


def _digest(state: dict[str, Any]) -> str:
    raw = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def capture(p: Parts) -> dict[str, Any]:
    r = p.store.review
    return {
        "initial": json.loads(_OBL.dump_json(r._initial)),
        "current": json.loads(_OBL.dump_json(r._state)),
        "log": json.loads(_LOG.dump_json(r._log)),
        "tasks": json.loads(_TASKS.dump_json(p.store.tasks)),
        "streams": json.loads(_STREAMS.dump_json(p.store.streams)),
        "texts": dict(p.texts),
        "access": json.loads(_GOV.dump_json(p.access.records)),
        "purge": json.loads(_GOV.dump_json(p.purge.records)),
        "holds": dict(p.retention.holds),
        "identity": dict(p.idmap._m),
    }


def apply(p: Parts, state: dict[str, Any]) -> None:
    try:
        r = p.store.review
        r._initial = _OBL.validate_python(state["initial"])
        r._state = _OBL.validate_python(state["current"])
        r._log = _LOG.validate_python(state["log"])
        p.store.tasks.clear()
        p.store.tasks.update(_TASKS.validate_python(state["tasks"]))
        p.store.streams = _STREAMS.validate_python(state["streams"])
        p.texts.clear()
        p.texts.update({str(k): str(v) for k, v in state["texts"].items()})
        for log, key in ((p.access, "access"), (p.purge, "purge")):
            log.records = _GOV.validate_python(state[key])
            log.anchor = (log.records[-1].seq, log.records[-1].hash) if log.records else None
        p.retention.holds = {str(k): str(v) for k, v in state["holds"].items()}
        p.idmap._m = {str(k): str(v) for k, v in state["identity"].items()}
    except (KeyError, ValidationError, AttributeError, TypeError):
        raise SnapshotCorrupt("snapshot content is partial or inconsistent") from None


class StateDir:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.crash_at: str | None = None

    def _p(self, name: str) -> Path:
        return self.path / name

    def _crash(self, step: str) -> None:
        if self.crash_at == step:
            self.crash_at = None
            raise SnapshotCrash(step)

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        probe = self._p(".write-probe")
        probe.write_bytes(b"")
        probe.unlink()

    def writable(self) -> bool:
        try:
            self.prepare()
        except OSError:
            return False
        return True

    def holder(self) -> int | None:
        try:
            pid = int(json.loads(self._p(LOCK).read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        except PermissionError:
            return pid
        return pid

    def is_free(self) -> bool:
        return not self._p(LOCK).exists() or self.holder() is None

    def acquire(self, run_id: str) -> None:
        self.prepare()
        body = json.dumps({"pid": os.getpid(), "run_id": run_id}).encode()
        for _ in range(2):
            try:
                fd = os.open(self._p(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self.holder() is not None:
                    raise LockHeld("state directory is in use") from None
                self._p(LOCK).unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "wb") as f:
                f.write(body)
            return
        raise LockHeld("state directory is in use")

    def release(self) -> None:
        self._p(LOCK).unlink(missing_ok=True)

    def clean_stray(self) -> bool:
        stray = self._p(TMP)
        found = stray.exists()
        stray.unlink(missing_ok=True)
        return found

    def read_marker(self) -> dict[str, Any] | None:
        try:
            m = json.loads(self._p(MARKER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return m if isinstance(m, dict) else None

    def delete_marker(self) -> None:
        self._p(MARKER).unlink(missing_ok=True)

    def read_snapshot(self) -> tuple[int, dict[str, Any]] | None:
        f = self._p(SNAPSHOT)
        if not f.exists():
            return None
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
            gen, state, dig = doc["generation"], doc["state"], doc["digest"]
        except (OSError, ValueError, KeyError, TypeError):
            raise SnapshotCorrupt("snapshot unreadable or incomplete") from None
        if not isinstance(gen, int) or not isinstance(state, dict) or dig != _digest(state):
            raise SnapshotCorrupt("snapshot digest mismatch")
        return gen, state

    def was_clean(self, generation: int) -> bool:
        m = self.read_marker()
        return m is not None and m.get("generation") == generation

    def write_snapshot(self, generation: int, run_id: str, state: dict[str, Any]) -> None:
        data = json.dumps(
            {"generation": generation, "digest": _digest(state), "state": state},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
        self.prepare()
        self._crash("before_tmp")
        tmp = self._p(TMP)
        half = len(data) // 2
        with open(tmp, "wb") as f:
            f.write(data[:half])
            f.flush()
            self._crash("during_tmp")
            f.write(data[half:])
            f.flush()
            self._crash("after_tmp")
            os.fsync(f.fileno())
        self._crash("after_flush")
        os.replace(tmp, self._p(SNAPSHOT))
        self._crash("after_rename")
        self._crash("before_marker")
        mtmp = self._p(MARKER + ".tmp")
        mtmp.write_text(json.dumps({"generation": generation, "run_id": run_id}), encoding="utf-8")
        os.replace(mtmp, self._p(MARKER))
        self._crash("after_marker")
