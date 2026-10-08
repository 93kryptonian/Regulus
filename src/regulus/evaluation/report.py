import json

from .claims import violations
from .models import MetricDefinition, MetricResult, Report, Status

ORDER = (
    "detection",
    "documents",
    "relevance",
    "lineage",
    "extraction",
    "generation",
    "similarity",
    "review",
    "workflow",
    "observability",
    "reliability",
    "governance",
    "deployment",
    "reference",
    "ingestion",
    "corpus",
)
LIMITATIONS = (
    "Gold sets were authored by the system's author against the system's own contracts: they are regression evidence, not recall or precision on unseen regulations.",
    "Samples are small; intervals describe uncertainty for the evaluated population only and are not generalization evidence.",
    "One local corpus of Indonesian regulations without labels: corpus rows are counts and self-consistency checks, never correctness.",
    "No independent held-out data and no production data exist; those evidence classes are reported as none.",
    "Review and workflow rows come from scripted reviewers and fake infrastructure; they describe the logic, not reviewer or channel performance.",
)


def to_json(report: Report) -> str:
    return (
        json.dumps(report.model_dump(mode="json"), indent=1, sort_keys=True, ensure_ascii=False)
        + "\n"
    )


def _fmt(r: MetricResult) -> str:
    if r.value is None:
        return f"{r.status.value}"
    n, d = (f"{x:g}" for x in (r.numerator, r.denominator))
    pct = f"{r.value * 100:.1f}%" if d != "0" else ""
    ci = f" (Wilson 95% {r.interval[0] * 100:.0f}-{r.interval[1] * 100:.0f}%)" if r.interval else ""
    return f"{n}/{d} = {r.value:.3f} ({pct}){ci}"


def _gate(d: MetricDefinition, r: MetricResult) -> str:
    if d.gate is None:
        return ""
    if d.gate.kind.value == "REPORT_ONLY":
        return "report only"
    state = "met" if r.gate_passed else "NOT met" if r.gate_passed is not None else "n/a"
    return f"{d.gate.kind.value} (expect {d.gate.expect:g}): {state}"


def _layer(d: MetricDefinition) -> str:
    return "end-to-end" if d.id.startswith("corpus.funnel_") else d.layer


def to_markdown(report: Report) -> str:
    defs = {d.id: d for d in report.definitions}
    res = {r.definition_id: r for r in report.results}
    pops = {p.id: p for p in report.populations}
    out = ["# Regulus evaluation report", ""]
    out += [
        "Layered evaluation. There is no overall score: each row states its population, numerator and denominator.",
        "",
    ]
    out += [f"Evidence classes present: {', '.join(c.value for c in report.classes_present) or 'none'}.",
            f"Evidence classes absent: {', '.join(c.value for c in report.classes_absent)} (none exist yet).", ""]  # fmt: skip
    out += (
        ["## Inputs", ""]
        + [f"- `{k}`: `{v[:16]}`" for k, v in sorted(report.inputs.items())]
        + [""]
    )
    layers = [*ORDER, "end-to-end"]
    for layer in layers:
        ds = [d for d in report.definitions if _layer(d) == layer and d.id in res]
        if not ds:
            continue
        title = (
            "End-to-end funnel (separate denominator at every stage; no end-to-end precision or recall exists)"
            if layer == "end-to-end"
            else layer.capitalize()
        )
        out += [f"## {title}", ""]
        for pid in dict.fromkeys(d.population_id for d in ds):
            p = pops[pid]
            out.append(
                f"Population `{pid}`: {p.description}; n = {p.n}; built by {p.built_by}. Limits: {p.limitations}."
            )
        out += [
            "",
            "| Metric | Result | Class | Gate | Status | Note |",
            "|---|---|---|---|---|---|",
        ]
        for d in ds:
            r = res[d.id]
            q = (
                f" (with {defs[d.qualified_by].name}: {_fmt(res[d.qualified_by])})"
                if d.qualified_by
                else ""
            )
            out.append(
                f"| {d.name}{q}<br>{d.numerator_definition} / {d.denominator_definition} | {_fmt(r)} | {d.evidence_class.value} | {_gate(d, r)} | {r.status.value} | {r.note} |"
            )
        out.append("")
    out += (
        ["## Known gaps", ""]
        + ([f"- {g}" for g in report.known_gaps] or ["- none recorded"])
        + [""]
    )
    if report.errors:
        out += ["## Evaluation errors", ""] + [f"- {e}" for e in report.errors] + [""]
    out += ["## Limitations", ""] + [f"- {x}" for x in (report.limitations or LIMITATIONS)] + [""]
    return "\n".join(out)


def narrative(report: Report) -> str:
    notes = " ".join(r.note for r in report.results if r.note)
    return " ".join([notes, *report.known_gaps, *(report.limitations or LIMITATIONS)])


def claim_problems(report: Report) -> list[str]:
    return violations(narrative(report))


def gate_failures(report: Report) -> list[str]:
    return [r.definition_id for r in report.results if r.status is Status.GATE_FAILED]
