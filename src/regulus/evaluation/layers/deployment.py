import fnmatch
import importlib
import importlib.util
import json
import random
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from regulus.config import ConfigError, load
from regulus.governance import GovernedApp
from regulus.health import CHECKS, Served, readiness
from regulus.observability.taxonomy import Stage
from regulus.reliability.wrappers import Corruption, corrupt
from regulus.runtime import (
    Exit,
    Refused,
    Runtime,
    SystemClock,
    build,
    integrity,
    shutdown,
    snapshot_now,
    startup,
    state_hash,
)
from regulus.seed import seed_demo
from regulus.state import (
    _GOV,
    _LOG,
    _STREAMS,
    CRASH_STEPS,
    SNAPSHOT,
    TMP,
    SnapshotCorrupt,
    SnapshotCrash,
    StateDir,
    _digest,
)
from regulus.workflow import Kind, Principal, WorkflowRole

from ..builder import EC, HARD0, Builder
from ..harness import NOW, TEXT
from ..models import EvidenceClass, Status
from ..runbook import Runner, steps

L = "deployment"
POP = "deployment.reference_runs"
SEEDS, SEED0 = 10, 1616000
SECRET = "z" * 40
LATE = NOW + timedelta(days=200)
OP = Principal(id="op1", roles=(WorkflowRole.OPERATOR,))
R1 = {"HTTP_X_REGULUS_ACTOR": "r1", "HTTP_X_REGULUS_ROLES": "REVIEWER"}


def _env(d: Path, **kw: str) -> dict[str, str]:
    return {
        "REGULUS_CSRF_SECRET": SECRET,
        "REGULUS_STATE_DIR": str(d / "st"),
        "REGULUS_AUTH_MODE": "dev_header",
        **kw,
    }


def _boot(d: Path, serving: bool = False, **kw: str) -> Runtime:
    rt = build(load(env=_env(d, **kw)), clock=SystemClock(lambda: LATE))
    startup(rt, serving)
    return rt


def _call(app: Any, path: str, method: str = "GET", **headers: str) -> tuple[int, str]:
    import io

    out: dict[str, Any] = {}
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": "0",
        "wsgi.input": io.BytesIO(b""),
        **headers,
    }
    body = b"".join(app(environ, lambda s, h, e=None: out.update(status=s))).decode()
    return int(out["status"][:3]), body


def _vary(rt: Runtime, rng: random.Random) -> None:
    store = rt.parts.store
    for i in range(rng.randint(0, 3)):
        store.append(
            f"notification:n{i}",
            Kind.NOTIFICATION_QUEUED,
            Principal(id="system", roles=(WorkflowRole.SYSTEM,)),
            NOW + timedelta(seconds=10 + i),
            f"k{i}",
            {},
        )
    for _ in range(rng.randint(0, 4)):
        _call(rt.app, "/tasks", **R1)
    if rng.random() < 0.5:
        rt.parts.retention.holds["review:demo-1"] = "scripted"


def _seeded(d: Path, rng: random.Random) -> None:
    rt = _boot(d)
    seed_demo(rt)
    _vary(rt, rng)
    shutdown(rt)


def _refuses(d: Path) -> bool:
    rt = build(load(env=_env(d)), clock=SystemClock(lambda: LATE))
    try:
        startup(rt)
    except Refused as e:
        return e.code is Exit.STATE
    return False


def _rewrite(d: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    f = d / "st" / SNAPSHOT
    doc = json.loads(f.read_text(encoding="utf-8"))
    mutate(doc["state"])
    doc["digest"] = _digest(doc["state"])
    f.write_text(json.dumps(doc, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _corrupt_part(state: dict[str, Any], where: str, mode: Corruption, rng: random.Random) -> None:
    if where == "stream":
        streams = _STREAMS.validate_python(state["streams"])
        key = "obligation:demo-0"
        streams[key] = corrupt(streams[key], mode, rng, foreign=streams["obligation:demo-1"][0])
        state["streams"] = json.loads(_STREAMS.dump_json(streams))
    elif where == "review":
        logs = _LOG.validate_python(state["log"])
        logs["demo-0"] = corrupt(logs["demo-0"], mode, rng, foreign=logs["demo-1"][0])
        state["log"] = json.loads(_LOG.dump_json(logs))
    else:
        recs = tuple(_GOV.validate_python(state["access"]))
        state["access"] = json.loads(
            _GOV.dump_json(list(corrupt(recs, mode, rng, foreign=recs[0])))
        )


def _data_files(root: Path) -> tuple[int, int]:
    src = root.parent / "src"
    cfg = tomllib.loads((root.parent / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = cfg["tool"]["setuptools"]["package-data"]
    files = sorted((src / "regulus").rglob("data/*.json"))
    missing = 0
    for f in files:
        rel = f.relative_to(src)
        pkg = ".".join(rel.parts[:-2])
        missing += not any(
            fnmatch.fnmatch("/".join(rel.parts[-2:]), p) for p in patterns.get(pkg, [])
        )
    return missing, len(files)


def _lock(root: Path) -> tuple[int, int]:
    script = root.parent / "scripts" / "lock.py"
    spec = importlib.util.spec_from_file_location("lockscript", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    want = mod.closure(mod.declared())
    have = mod.parse((root.parent / "requirements.lock").read_text(encoding="utf-8"))
    bad = len(set(want) ^ set(have)) + sum(want[k] != have[k] for k in set(want) & set(have))
    return bad, len(want)


INVALID: list[dict[str, str]] = [
    {"REGULUS_PORT": "0"},
    {"REGULUS_PORT": "65536"},
    {"REGULUS_PORT": "x"},
    {"REGULUS_PORT": ""},
    {"REGULUS_AUTH_MODE": "open"},
    {"REGULUS_AUTH_MODE": ""},
    {"REGULUS_HOST": "0.0.0.0"},
    {"REGULUS_HOST": "0.0.0.0", "REGULUS_AUTH_MODE": "dev_header"},
    {"REGULUS_HOST": "example.invalid"},
    {"REGULUS_CSRF_SECRET": ""},
    {"REGULUS_CSRF_SECRET": "tiny"},
    {"REGULUS_CSRF_SECRET": "s" * 31},
    {"REGULUS_CLAIM_TTL_SECONDS": "0"},
    {"REGULUS_CLAIM_TTL_SECONDS": "-5"},
    {"REGULUS_CLAIM_TTL_SECONDS": "abc"},
    {"REGULUS_OBSERVATION_BUFFER": "0"},
    {"REGULUS_OBSERVATION_BUFFER": "-1"},
    {"REGULUS_OBSERVATION_BUFFER": "1.5"},
]


def _invalid_configs(d: Path) -> tuple[int, int, list[str]]:
    accepted, outputs = 0, []
    for kw in INVALID:
        env = _env(d, **kw)
        try:
            load(env=env)
            accepted += 1
        except ConfigError as e:
            outputs.append(str(e))
    files: list[dict[str, Any]] = [
        {"surprise": 1},
        {"port": "8000"},
        {"api_token": SECRET},
        {"state_dir": 5},
        {"schedule": {"nope": 1}},
    ]
    for i, doc in enumerate(files):
        f = d / f"c{i}.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        try:
            load(f, _env(d))
            accepted += 1
        except ConfigError as e:
            outputs.append(str(e))
    try:
        load(env={})
        accepted += 1
    except ConfigError as e:
        outputs.append(str(e))
    return accepted, len(INVALID) + len(files) + 1, outputs


def _scan_secret(texts: list[str]) -> int:
    return sum(SECRET in t for t in texts)


def _governed_probes(d: Path) -> tuple[int, int]:
    rt = _boot(d, True)
    app = Served(rt)
    assert isinstance(rt.app, GovernedApp)
    tid = next(iter(rt.parts.store.tasks), "t")
    bad = n = 0
    for headers in ({}, R1, {"HTTP_X_REGULUS_ACTOR": "nobody", "HTTP_X_REGULUS_ROLES": ""}):
        for path in (
            "/tasks",
            f"/tasks/{tid}",
            f"/tasks/{tid}/claim",
            f"/tasks/{tid}/action",
            "/tasks/nope",
        ):
            for method in ("GET", "POST"):
                before = len(rt.parts.access.records)
                code, _ = _call(app, path, method, **headers)
                n += 1
                bad += len(rt.parts.access.records) != before + 1 and code != 503
    shutdown(rt)
    return bad, n


def _snapshot_outcomes(d: Path) -> tuple[int, int]:
    bad = 0
    for step in CRASH_STEPS:
        sub = d / step
        sub.mkdir()
        _seeded(sub, random.Random(SEED0))
        rt = _boot(sub)
        gen = rt.generation
        rt.parts.retention.holds["probe:new-generation"] = "new generation"
        rt.state.crash_at = step
        try:
            snapshot_now(rt)
        except SnapshotCrash:
            pass
        rt.state.release()
        sd = StateDir(sub / "st")
        try:
            loaded = sd.read_snapshot()
        except SnapshotCorrupt:
            bad += 1
            continue
        marker = sd.read_marker()
        assert loaded is not None
        snap_gen = loaded[0]
        if snap_gen not in (gen, gen + 1) or (
            marker is not None and marker["generation"] != snap_gen
        ):
            bad += 1
            continue
        again = _boot(sub)
        clean_expected = marker is not None
        has_new = "probe:new-generation" in again.parts.retention.holds
        rep = integrity(again)
        bad += bool(
            again.clean is not clean_expected
            or has_new is not (snap_gen == gen + 1)
            or rep.broken
            or rep.unreceipted
            or (sub / "st" / TMP).exists()
        )
    return bad, len(CRASH_STEPS)


def _classification(d: Path) -> tuple[int, int]:
    bad = n = 0

    def fresh(name: str) -> Path:
        p = d / name
        p.mkdir()
        _seeded(p, random.Random(SEED0 + 1))
        rt = _boot(p)
        rt.parts.store.append("notification:n9", Kind.NOTIFICATION_QUEUED, OP, NOW, "k9", {})
        rt.parts.store.append(
            "notification:n9",
            Kind.NOTIFICATION_DELIVERED,
            OP,
            NOW + timedelta(seconds=1),
            "k10",
            {},
        )
        shutdown(rt)
        return p

    for crash in ("intent", "delete"):
        p = fresh(f"purge_{crash}")
        rt = _boot(p)
        rt.parts.retention.fail_after = crash
        try:
            rt.parts.retention.purge(OP, "notification:n9", "elapsed", LATE)
        except RuntimeError:
            pass
        snapshot_now(rt)
        rt.state.release()
        n += 1
        try:
            again = _boot(p)
            rep = integrity(again)
            bad += bool(rep.broken or rep.unreceipted)
        except Refused:
            bad += 1
    p = fresh("intent_submission")
    rt = _boot(p)
    from regulus.workflow import SnapshotInputs, submit_for_review

    from ..harness import OWNER, generation_result

    rt.parts.texts[OWNER] = TEXT
    rt.parts.store.fail_after = "intent"
    try:
        submit_for_review(
            rt.parts.store, generation_result("late-1"), SnapshotInputs(permitted_source=TEXT),
            OP, NOW, rt.parts.texts,
        )  # fmt: skip
    except BaseException:
        pass
    snapshot_now(rt)
    rt.state.release()
    n += 1
    try:
        again = _boot(p)
        bad += not (again.parts.store.registered("late-1") and not integrity(again).broken)
    except Refused:
        bad += 1
    p = fresh("stray_tmp")
    (p / "st" / TMP).write_text("partial", encoding="utf-8")
    n += 1
    try:
        _boot(p)
        bad += (p / "st" / TMP).exists()
    except Refused:
        bad += 1
    p = fresh("deleted_without_intent")
    _rewrite(p, lambda s: s["streams"].pop("notification:n9"))
    n += 1
    bad += not _refuses(p)
    p = fresh("modified")
    _rewrite(p, lambda s: s["streams"]["obligation:demo-0"][0].update(principal_id="mallory"))
    n += 1
    bad += not _refuses(p)
    return bad, n


def _readiness(d: Path) -> tuple[int, int]:
    import os

    bad = n = 0
    rt = _boot(d, True)
    seed_demo(rt)
    app = Served(rt)

    def state() -> dict[str, Any]:
        _, body = _call(app, "/readyz")
        return json.loads(body)  # type: ignore[no-any-return]

    def probe(name: str, inject: Callable[[], None], restore: Callable[[], None]) -> None:
        nonlocal bad, n
        n += 1
        inject()
        s = state()
        flipped = s["ready"] is False and s["failing"] == [name]
        restore()
        s2 = state()
        bad += not (flipped and s2["ready"] is True)

    streams = rt.parts.store.streams
    key = next(iter(streams))
    good = streams[key]
    probe("state_integrity",
          lambda: streams.__setitem__(key, (good[0].model_copy(update={"principal_id": "x"}), *good[1:])),
          lambda: streams.__setitem__(key, good))  # fmt: skip
    probe(
        "audit_appendable",
        lambda: setattr(rt.parts.access, "fail_next", 99),
        lambda: setattr(rt.parts.access, "fail_next", 0),
    )
    probe(
        "clock_monotonic",
        lambda: setattr(rt.clock, "regressed", True),
        lambda: setattr(rt.clock, "regressed", False),
    )
    probe(
        "startup_recovery",
        lambda: setattr(rt, "draining", True),
        lambda: setattr(rt, "draining", False),
    )
    cap = rt.observer.buffer.capacity

    def fill() -> None:
        while rt.observer.buffer.buffered < cap:
            rt.observer.point(rt.run_id, Stage.RUN)

    def drain() -> None:
        rt.observer.buffer.drain(_Null(), cap)

    probe("observation_buffer", fill, drain)
    st = d / "st"
    if os.geteuid() != 0:
        probe("state_dir_writable", lambda: st.chmod(0o500), lambda: st.chmod(0o700))
    else:
        n += 1
        bad += 1
    h: Any = importlib.import_module("regulus.health")
    orig = h.default_matrix

    def boom() -> Any:
        raise OSError

    probe(
        "packaged_data",
        lambda: setattr(h, "default_matrix", boom),
        lambda: setattr(h, "default_matrix", orig),
    )
    pol = d / "pol.json"
    pol.write_text(json.dumps({"illustrative": True, "days": {"WORKFLOW": 90}}), encoding="utf-8")
    rt.config = rt.config.model_copy(update={"retention_policy": pol})
    bak = d / "pol.bak"

    def hide() -> None:
        pol.rename(bak)

    def show() -> None:
        bak.rename(pol)

    probe("configuration", hide, show)
    assert set(CHECKS) >= {"configuration", "packaged_data"}
    shutdown(rt)
    return bad, n


class _Null:
    def emit(self, event: object) -> None:
        return


def _content_free(d: Path) -> tuple[int, int]:
    _seeded(d, random.Random(SEED0 + 2))
    rt = _boot(d, True)
    app = Served(rt)
    forbidden = (SECRET, TEXT, str(d), "demo-0", "dev_header", "127.0.0.1")
    bodies = [_call(app, "/healthz")[1], _call(app, "/readyz")[1]]
    rt.parts.access.fail_next = 5
    bodies.append(_call(app, "/readyz")[1])
    rt.parts.access.fail_next = 0
    rt.draining = True
    bodies.append(_call(app, "/readyz")[1])
    bodies.append(json.dumps(readiness(rt)))
    shutdown(rt)
    return sum(any(f in b for f in forbidden) for b in bodies), len(bodies)


def _determinism(d: Path) -> tuple[int, int]:
    bad = 0
    for i in range(SEEDS):
        hashes = []
        for j in range(2):
            sub = d / f"{i}-{j}"
            sub.mkdir()
            rt = _boot(sub)
            seed_demo(rt)
            reports = integrity(rt).model_dump_json()
            hashes.append((state_hash(rt), reports))
            shutdown(rt)
        bad += hashes[0] != hashes[1]
    return bad, SEEDS


def _restart(d: Path) -> tuple[int, int]:
    bad = 0
    for i in range(SEEDS):
        sub = d / f"r{i}"
        sub.mkdir()
        rng = random.Random(SEED0 + 10 + i)
        _seeded(sub, rng)
        first = None
        for _ in range(2):
            rt = _boot(sub)
            h = state_hash(rt)
            rep = integrity(rt)
            shutdown(rt)
            first = first or h
            bad += bool(h != first or rep.broken or rep.unreceipted)
    return bad, SEEDS * 2


def _corruptions(d: Path) -> tuple[int, int]:
    accepted = n = 0
    for where in ("stream", "review", "access"):
        for mode in Corruption:
            sub = d / f"{where}-{mode.value}"
            sub.mkdir()
            rt = _boot(sub, True)
            seed_demo(rt)
            _enrich_review(rt)
            for _ in range(3):
                _call(rt.app, "/tasks", **R1)
            shutdown(rt)
            _rewrite(sub, lambda s, w=where, m=mode: _corrupt_part(s, w, m, random.Random(7)))  # type: ignore[misc]
            n += 1
            accepted += not _refuses(sub)
    for i, cut in enumerate((0.5, 0.9)):
        sub = d / f"cut{i}"
        sub.mkdir()
        _seeded(sub, random.Random(1))
        f = sub / "st" / SNAPSHOT
        raw = f.read_bytes()
        f.write_bytes(raw[: int(len(raw) * cut)])
        n += 1
        accepted += not _refuses(sub)
    return accepted, n


def _enrich_review(rt: Runtime) -> None:
    from regulus.domain import FieldChange
    from regulus.review import (
        Action,
        ActionRequest,
        RejectCode,
        RejectReason,
        ReviewConfig,
        apply,
        claim,
    )

    from ..harness import ACTORS

    store = rt.parts.store
    for oid in ("demo-0", "demo-1"):
        r1 = next(a for a in ACTORS if a.id == "r1")
        task = next(t for t in store.tasks.values() if t.obligation_id == oid)
        t = claim(task, r1.id, NOW + timedelta(seconds=5), 900)
        ob = store.review.get(oid)[0]
        change = FieldChange(
            field="deadline", before=ob.current.deadline, after="paling lambat 3 hari"
        )
        edit = ActionRequest(action=Action.EDIT, task_id=t.id, base_version=store.review.version(oid),
                             actor=r1, at=NOW + timedelta(seconds=6), changes=(change,), reason="scripted edit")  # fmt: skip
        t = apply(store.review, t, edit, ReviewConfig(), rt.parts.texts).task or t
        rej = ActionRequest(action=Action.REJECT, task_id=t.id, base_version=store.review.version(oid),
                            actor=r1, at=NOW + timedelta(seconds=7),
                            reject_reason=RejectReason(code=RejectCode.OUT_OF_SCOPE))  # fmt: skip
        store.tasks[t.id] = apply(store.review, t, rej, ReviewConfig(), rt.parts.texts).task or t


def _secrets(d: Path) -> tuple[int, int]:
    arts: list[str] = []
    _, _, errors = _invalid_configs(d)
    arts += errors
    rt = _boot(d, True)
    app = Served(rt)
    seed_demo(rt)
    for path in ("/healthz", "/readyz", "/tasks"):
        arts.append(_call(app, path, **R1)[1])
    arts.append(json.dumps(rt.config.effective()))
    arts.append(repr(rt.config))
    shutdown(rt)
    for p in sorted((d / "st").iterdir()):
        arts.append(p.read_text(encoding="utf-8"))
    return _scan_secret(arts), len(arts)


def _runbook(root: Path) -> tuple[int, int] | None:
    book = root.parent / "docs" / "16_runbook.md"
    if not book.exists():
        return None
    plan = steps(book.read_text(encoding="utf-8"))
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        runner = Runner(Path(tmp), root.parent)
        try:
            for step in plan:
                try:
                    runner.run(step[0])
                    for e in step[1:]:
                        runner.expect(e)
                except (AssertionError, KeyError, OSError, subprocess.SubprocessError):
                    failed += 1
        finally:
            if runner.proc is not None:
                runner.proc.kill()
    return failed, len(plan)


def _container(root: Path) -> str | None:
    if shutil.which("docker") is None:
        return "no container runtime on the evaluation host"
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return "the container client is present but no daemon is reachable"
    return "a container runtime is present; the build and probe run in the deployment tests"


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        def sub(name: str) -> Path:
            p = base / name
            p.mkdir()
            return p

        missing, nfiles = _data_files(root)
        locked, closure = _lock(root)
        acc, ninvalid, _ = _invalid_configs(sub("cfg"))
        leaked, nart = _secrets(sub("sec"))
        ungov, nprobe = _governed_probes(sub("gov"))
        diverged, ncycles = _restart(sub("restart"))
        corrupted, ncorr = _corruptions(sub("corrupt"))
        nonatomic, ncrash = _snapshot_outcomes(sub("crash"))
        mis, ncls = _classification(sub("class"))
        untruthful, ninj = _readiness(sub("ready"))
        nonfree, nbod = _content_free(sub("probe"))
        nondet, npair = _determinism(sub("det"))
    book = _runbook(root)
    b.population(
        POP,
        "seeded reference deployments over temporary state directories",
        f"seeds {SEED0}..{SEED0 + SEEDS - 1} and the committed deploy files",
        SEEDS,
        "evaluation harness",
        "one host, in-memory stores with snapshot persistence, fault injection in process; "
        "no availability, capacity or production evidence",
    )
    m = b.metric

    def add(
        id: str,
        name: str,
        num: str,
        den: str,
        nv: float,
        dv: float,
        cls: EvidenceClass = EC.PROPERTY,
        note: str = "",
    ) -> None:
        b.record(m(f"{L}.{id}", L, name, POP, num, den, cls, HARD0), nv, dv, note)

    add("data_files_missing_from_package", "runtime data files missing from the package",
        "data files without a package-data pattern", "data files in the tree", missing, nfiles, EC.REGRESSION,
        "matched against pyproject package-data; the wheel build is tested separately")  # fmt: skip
    add("lock_mismatches", "runtime dependencies missing or mismatched in the lock",
        "closure packages missing, extra or at another version", "runtime closure packages", locked, closure,
        EC.REGRESSION)  # fmt: skip
    add("invalid_configurations_accepted", "invalid configurations accepted",
        "accepted", "invalid configurations tried", acc, ninvalid)  # fmt: skip
    add("secrets_in_artifacts", "secrets found in outputs, logs, state or errors",
        "artifacts containing the secret", "artifacts scanned", leaked, nart)  # fmt: skip
    add("non_governed_routes", "review routes served without the governed app",
        "probes without exactly one access-audit record (or a fail-closed 503)", "routes probed", ungov, nprobe)  # fmt: skip
    add("restart_divergence", "restart divergence",
        "restores whose verified content differs from the snapshot", "restore cycles", diverged, ncycles)  # fmt: skip
    add("corrupted_snapshots_accepted", "corrupted snapshots accepted at startup",
        "accepted", "injected corruptions", corrupted, ncorr)  # fmt: skip
    add("non_atomic_snapshot_outcomes", "non-atomic snapshot outcomes",
        "crash points leaving a mixed or unverifiable state or a marker naming an incomplete generation",
        "crash points tried", nonatomic, ncrash,
        note="controlled in-process fault injection; not power loss")  # fmt: skip
    add("misclassified_startup_state", "misclassified startup state",
        "recoverable states refused, or corruption recovered or accepted", "classified cases", mis, ncls)  # fmt: skip
    add("untruthful_readiness", "untruthful readiness",
        "injected failures not reflected or not recovered", "injected failures", untruthful, ninj)  # fmt: skip
    add("non_content_free_probe_bodies", "non-content-free probe bodies",
        "bodies with content, a secret or a configuration value", "bodies scanned", nonfree, nbod)  # fmt: skip
    add("nondeterministic_seeded_runs", "non-deterministic seeded runs",
        "differing state hashes or verify reports", "paired seed runs", nondet, npair)  # fmt: skip
    if book is None:
        b.unmeasurable(
            m(f"{L}.runbook_failures", L, "runbook commands that fail or drift", POP,
              "failing steps", "runbook steps executed", EC.REGRESSION, HARD0),
            "the runbook is not present on this host", Status.NOT_MEASURABLE)  # fmt: skip
    else:
        add("runbook_failures", "runbook commands that fail or drift", "failing steps",
            "runbook steps executed", book[0], book[1], EC.REGRESSION)  # fmt: skip
    b.unmeasurable(
        m(f"{L}.container_build_and_probe", L, "container build and probe", POP,
          "built and healthy", "attempts", EC.REGRESSION),
        _container(root) or "", Status.NOT_MEASURABLE)  # fmt: skip
