import json
from pathlib import Path
from typing import Any

from regulus.domain.base import Model

from .models import GateKind, Report, Status


class Drift(Model):
    metric: str
    kind: str
    before: str | None
    after: str | None


class Verdict(Model):
    drift: tuple[Drift, ...]
    defect: bool
    changed_inputs: tuple[str, ...]


def snapshot(report: Report) -> dict[str, dict[str, object]]:
    return {
        r.definition_id: {
            "numerator": r.numerator,
            "denominator": r.denominator,
            "status": r.status.value,
        }
        for r in report.results
    }


def _corpus(name: str) -> bool:
    return name.startswith("corpus.")


def compare(report: Report, baseline: dict[str, Any]) -> Verdict:
    old, new = baseline["metrics"], snapshot(report)
    changed = sorted(
        k
        for k in set(baseline["inputs"]) | set(report.inputs)
        if baseline["inputs"].get(k) != report.inputs.get(k)
    )
    corpus_changed = any(k.startswith("corpus:") for k in changed)
    drift: list[Drift] = []
    for k in sorted(set(old) | set(new)):
        if corpus_changed and _corpus(k):
            continue
        a, b = old.get(k), new.get(k)
        if a != b:
            drift.append(Drift(metric=k, kind="added" if a is None else "removed" if b is None else "changed",
                               before=json.dumps(a, sort_keys=True) if a else None, after=json.dumps(b, sort_keys=True) if b else None))  # fmt: skip
    return Verdict(
        drift=tuple(drift), defect=bool(drift) and not changed, changed_inputs=tuple(changed)
    )


class BaselineRefused(Exception):
    pass


def update(
    report: Report, path: Path, reason: str, changed_input: str, previous: dict[str, Any] | None
) -> None:
    if not reason.strip() or not changed_input.strip():
        raise BaselineRefused("a baseline update must name the changed input and the reason")
    if any(r.status is Status.GATE_FAILED for r in report.results) or report.errors:
        raise BaselineRefused("a hard-gate failure or an evaluation error cannot be baselined")
    if previous is not None:
        v = compare(report, previous)
        if v.drift and not v.changed_inputs:
            raise BaselineRefused(
                "metrics changed with unchanged inputs: a defect, not a baseline update"
            )
        if v.drift and changed_input not in v.changed_inputs:
            raise BaselineRefused(
                f"{changed_input} did not change; changed inputs: {list(v.changed_inputs)}"
            )
        worse = _hard_worse(report, previous)
        if worse:
            raise BaselineRefused(f"a hard-gate metric got worse: {worse}")
    history = list(previous.get("history", [])) if previous else []
    history.append({"reason": reason, "changed_input": changed_input})
    path.write_text(json.dumps({"inputs": dict(sorted(report.inputs.items())), "metrics": snapshot(report), "history": history},
                               indent=1, sort_keys=True) + "\n", encoding="utf-8")  # fmt: skip


def _hard_worse(report: Report, previous: dict[str, Any]) -> list[str]:
    defs = {d.id: d for d in report.definitions}
    out = []
    for r in report.results:
        d = defs[r.definition_id]
        old = previous["metrics"].get(r.definition_id)
        if (
            d.gate
            and d.gate.kind is GateKind.HARD
            and old
            and r.value is not None
            and old["denominator"]
        ):
            before = old["numerator"] / old["denominator"]
            if abs(r.value - d.gate.expect) > abs(before - d.gate.expect) + 1e-12:
                out.append(r.definition_id)
    return out


def load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
