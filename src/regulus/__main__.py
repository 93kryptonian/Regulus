import argparse
import json
import os
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path

from regulus.config import ConfigError, RegulusConfig, load
from regulus.governance import erase_identity
from regulus.runtime import (
    Exit,
    Refused,
    Runtime,
    build,
    integrity,
    packaged_problems,
    shutdown,
    startup,
)
from regulus.seed import seed_demo
from regulus.serve import serve
from regulus.state import LOCK, SnapshotCorrupt, StateDir, apply
from regulus.workflow import Principal, WorkflowRole


def _out(obj: object) -> None:
    print(json.dumps(obj, sort_keys=True))


def _version() -> dict[str, object]:
    out: dict[str, object] = {"version": metadata.version("regulus")}
    root = Path(__file__).resolve().parents[2]
    head = root / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        out["commit"] = (
            (root / ".git" / ref[5:]).read_text(encoding="utf-8").strip()[:12]
            if ref.startswith("ref: ")
            else ref[:12]
        )
    except OSError:
        pass
    return out


def _operator(name: str) -> Principal:
    return Principal(id=name, roles=(WorkflowRole.OPERATOR,))


def _open_readonly(rt: Runtime) -> None:
    try:
        rt.state.acquire(rt.run_id)
    except Exception:
        raise Refused(Exit.RUNTIME, ["state directory is in use or not writable"]) from None
    try:
        loaded = rt.state.read_snapshot()
        if loaded is not None:
            rt.generation, content = loaded
            apply(rt.parts, content)
    except SnapshotCorrupt:
        rt.state.release()
        raise Refused(Exit.STATE, ["snapshot is partial, unreadable or inconsistent"]) from None


def _check(cfg: RegulusConfig) -> int:
    sd = StateDir(cfg.state_dir)
    problems = packaged_problems()
    state_ok = True
    if (cfg.state_dir / "snapshot.json").exists():
        try:
            sd.read_snapshot()
        except SnapshotCorrupt:
            state_ok = False
    _out(
        {
            "config": cfg.effective(),
            "packaged_data": not problems,
            "state_readable": state_ok,
            "state_dir_exists": cfg.state_dir.exists(),
            "lock_free": sd.is_free() if (cfg.state_dir / LOCK).exists() else True,
            "evaluation_assets_packaged": False,
        }
    )
    return (
        int(Exit.OK)
        if not problems and state_ok
        else int(Exit.STATE if not state_ok else Exit.CONFIG)
    )


def _operate(rt: Runtime, args: argparse.Namespace) -> int:
    startup(rt, serving=False)
    now = rt.clock.now()
    try:
        ret = rt.parts.retention
        if args.command == "hold":
            ok: object = ret.hold(_operator(args.operator), args.stream, args.reason, now)
        elif args.command == "release":
            ok = ret.release(_operator(args.operator), args.stream, args.reason, now)
        elif args.command == "purge":
            ok = ret.purge(_operator(args.operator), args.stream, args.reason, now).value
        elif args.command == "recover-purges":
            ok = ret.recover(now)
        elif args.command == "erase-identity":
            ok = erase_identity(
                rt.parts.idmap, rt.parts.access, _operator(args.operator), args.opaque_id, now
            )
        else:
            ok = True
        _out({"command": args.command, "result": ok, "generation": rt.generation + 1})
    finally:
        shutdown(rt)
    return int(Exit.OK)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="regulus")
    p.add_argument("--config", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("version", "check", "verify", "seed-demo", "serve", "snapshot", "recover-purges"):
        sub.add_parser(name)
    for name in ("hold", "release", "purge"):
        s = sub.add_parser(name)
        s.add_argument("--operator", required=True)
        s.add_argument("--stream", required=True)
        s.add_argument("--reason", required=True)
    e = sub.add_parser("erase-identity")
    e.add_argument("--operator", required=True)
    e.add_argument("--opaque-id", required=True)
    sub.choices["recover-purges"].add_argument("--operator", required=True)
    return p


def main(argv: Sequence[str] | None = None, env: dict[str, str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "version":
        _out(_version())
        return int(Exit.OK)
    try:
        cfg = load(args.config, dict(os.environ) if env is None else env)
        if args.command == "check":
            return _check(cfg)
        rt = build(cfg)
        if args.command == "serve":
            return serve(rt)
        if args.command == "verify":
            _open_readonly(rt)
            try:
                r = integrity(rt)
            finally:
                rt.state.release()
            _out(
                {
                    "intact": len(r.intact),
                    "broken": list(r.broken),
                    "unreceipted": list(r.unreceipted),
                }
            )
            return int(Exit.OK) if not r.broken and not r.unreceipted else int(Exit.STATE)
        if args.command == "seed-demo":
            if (cfg.state_dir / "snapshot.json").exists():
                raise Refused(Exit.RUNTIME, ["state directory is not empty"])
            startup(rt, serving=False)
            try:
                n = seed_demo(rt)
            finally:
                shutdown(rt)
            _out({"seeded": n})
            return int(Exit.OK)
        return _operate(rt, args)
    except ConfigError as e:
        print(
            "configuration error: " + "; ".join(f"{f} ({r})" for f, r in e.problems),
            file=sys.stderr,
        )
        return int(Exit.CONFIG)
    except Refused as e:
        print("refused: " + "; ".join(e.reasons), file=sys.stderr)
        return int(e.code)


if __name__ == "__main__":
    sys.exit(main())
