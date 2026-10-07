import ast
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from regulus.domain.base import Model

from .faults import FaultKind

F = TypeVar("F", bound=Callable[..., Any])
GUARANTEES = {f"G{i}" for i in range(1, 11)}
FAULT_NAMES = {k.value for k in FaultKind} | {"COMBINED", "NONE"}


def covers(*rows: str) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        fn._covers = rows  # type: ignore[attr-defined]
        return fn

    return deco


class Row(Model):
    id: str
    domain: str
    fault: str
    guarantees: tuple[str, ...]
    recovery: str
    degraded: str
    tests: tuple[str, ...]


def load(path: Path) -> list[Row]:
    return [Row.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def _functions(path: Path) -> dict[str, tuple[str, ...]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            claims: list[str] = []
            for d in node.decorator_list:
                if (
                    isinstance(d, ast.Call)
                    and getattr(d.func, "id", getattr(d.func, "attr", "")) == "covers"
                ):
                    claims += [
                        a.value
                        for a in d.args
                        if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
            out[node.name] = tuple(claims)
    return out


def validate(rows: list[Row], root: Path) -> list[str]:
    problems: list[str] = []
    ids = [r.id for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate row ids")
    claimed: dict[str, set[str]] = {}
    files: dict[str, dict[str, tuple[str, ...]]] = {}
    for p in sorted((root / "tests" / "reliability").glob("test_*.py")):
        files[f"tests/reliability/{p.name}"] = _functions(p)
        for fn, claims in files[f"tests/reliability/{p.name}"].items():
            for c in claims:
                claimed.setdefault(c, set()).add(f"tests/reliability/{p.name}::{fn}")
    for r in rows:
        if not re.fullmatch(r"R\d{2}[a-z]?", r.id):
            problems.append(f"{r.id}: id format")
        if r.fault not in FAULT_NAMES:
            problems.append(f"{r.id}: unknown fault {r.fault}")
        if not r.guarantees or not set(r.guarantees) <= GUARANTEES:
            problems.append(f"{r.id}: guarantee ids")
        if not r.recovery.strip() or not r.degraded.strip():
            problems.append(f"{r.id}: recovery and degraded behaviour must be declared")
        if not r.tests:
            problems.append(f"{r.id}: no test")
        for t in r.tests:
            path, _, fn = t.partition("::")
            if fn not in files.get(path, {}):
                problems.append(f"{r.id}: test {t} does not exist")
            elif r.id not in files[path][fn]:
                problems.append(f"{r.id}: test {t} does not claim the row")
        if not claimed.get(r.id):
            problems.append(f"{r.id}: nothing claims this row")
    for claim in claimed:
        if claim not in set(ids):
            problems.append(f"claim for an unknown row {claim}")
    return problems
