import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from . import corpus
from .baseline import compare, load, update
from .builder import Builder
from .layers import (
    detection,
    documents,
    extraction,
    generation,
    governance,
    lineage,
    observability,
    relevance,
    reliability,
    review,
    similarity,
    workflow,
)
from .models import ABSENT, Population, Report
from .report import LIMITATIONS, claim_problems, gate_failures, to_json, to_markdown

GOLD = {
    "detection": "change_detection/gold.v1.json",
    "documents": "documents/gold.v1.json",
    "relevance": "relevance/gold.v1.json",
    "lineage": "lineage/gold_ops.v1.json",
    "extraction": "obligations/gold.v1.json",
    "generation": "generation/contradictions.v1.json",
    "similarity": "similarity/gold.v1.json",
}
LAYERS: tuple[tuple[str, Callable[[Builder, Path], None]], ...] = (
    ("detection", lambda b, r: detection.evaluate(b, r)),
    ("documents", lambda b, r: documents.evaluate(b, r)),
    ("relevance", lambda b, r: relevance.evaluate(b, r)),
    ("lineage", lambda b, r: lineage.evaluate(b, r)),
    ("extraction", lambda b, r: extraction.evaluate(b, r)),
    ("generation", lambda b, r: generation.evaluate(b, r)),
    ("similarity", lambda b, r: similarity.evaluate_layer(b, r)),
    ("review", lambda b, r: review.evaluate(b)),
    ("workflow", lambda b, r: workflow.evaluate(b)),
    ("observability", lambda b, r: observability.evaluate(b)),
    ("reliability", lambda b, r: reliability.evaluate(b, r)),
    ("governance", lambda b, r: governance.evaluate(b, r)),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_report(root: Path, pdf: Path, code_ref: str = "unversioned") -> Report:
    b = Builder()
    inputs = {"code": code_ref}
    for name, rel in GOLD.items():
        inputs[f"gold:{name}"] = _sha(root / rel)
    for name, run in LAYERS:
        try:
            run(b, root)
        except Exception as e:
            b.errors.append(f"{name}: {type(e).__name__}: {e}")
    try:
        manifest = corpus.evaluate(b, pdf)
    except Exception as e:
        manifest = {}
        b.errors.append(f"corpus: {type(e).__name__}: {e}")
    for k, v in manifest.items():
        inputs[f"corpus:{k}"] = v
    pops = tuple(b.populations.values())
    return Report(
        inputs=inputs, populations=pops, definitions=tuple(b.definitions.values()),
        results=tuple(b.results.values()), known_gaps=tuple(b.known_gaps),
        classes_present=tuple(sorted(b.classes, key=lambda c: c.value)), classes_absent=ABSENT,
        limitations=LIMITATIONS, errors=tuple(b.errors),
    )  # fmt: skip


def check_registry(report: Report, path: Path) -> list[str]:
    reg = (
        {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
    )
    problems = []
    corpus_present = any(k.startswith("corpus:") for k in report.inputs)
    for p in report.populations:
        if p.id.startswith("corpus.") and not corpus_present:
            continue
        got = reg.get(p.id)
        if got is None:
            problems.append(f"{p.id}: not in the registry")
        elif got["n"] != p.n:
            problems.append(f"{p.id}: n {p.n} differs from the registry {got['n']}")
    return problems


def write_registry(populations: tuple[Population, ...], path: Path) -> None:
    rows = [p.model_dump() for p in populations if not p.id.startswith("corpus.") or p.n]
    path.write_text(
        json.dumps(sorted(rows, key=lambda r: r["id"]), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run(
    root: Path, pdf: Path, out: Path, code_ref: str = "unversioned", baseline: Path | None = None
) -> int:
    report = build_report(root, pdf, code_ref)
    problems: list[str] = []
    problems += [f"gate failed: {g}" for g in gate_failures(report)]
    problems += [f"error: {e}" for e in report.errors]
    problems += [f"claim: {c}" for c in claim_problems(report)]
    problems += [f"registry: {p}" for p in check_registry(report, root / "populations.v1.json")]
    base = load(baseline) if baseline else None
    if baseline and base is not None:
        v = compare(report, base)
        problems += [
            f"drift ({'defect: inputs unchanged' if v.defect else 'inputs changed'}): {d.metric}"
            for d in v.drift
        ]
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.v1.json").write_text(to_json(report), encoding="utf-8")
    (out / "report.v1.md").write_text(to_markdown(report), encoding="utf-8")
    for p in problems:
        print(p)
    return 1 if problems else 0


__all__ = ["build_report", "check_registry", "run", "update", "write_registry"]
