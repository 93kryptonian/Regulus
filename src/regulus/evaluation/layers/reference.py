import random
import subprocess
from pathlib import Path

from regulus.reference.load import available, build_corpus, load_corpus
from regulus.reference.metrics import instrument_problems
from regulus.reference.models import DiscrepancyKind as K
from regulus.reference.scan import leaking_files, public_text, tracked_files
from regulus.reference.split import load_split, split_problems, structural_problems
from regulus.reference.synthetic import synthetic_corpus, synthetic_rows

from ..builder import EC, HARD0, Builder
from ..models import EvidenceClass, Gate, Status

L = "reference"
POP = "reference.synthetic_standin"
REAL = "reference_real.regulations"
SEEDS, SEED0 = 10, 1717000
INSTRUMENT_CHECKS = 8
UNLABELLED = (
    ("type_accuracy", "obligation type accuracy"),
    ("sanction_accuracy", "sanction category accuracy"),
    ("appendix_accuracy", "appendix-derived obligation accuracy"),
    ("pointer_accuracy", "reference pointer accuracy"),
)


def _tracked(root: Path) -> tuple[int, int]:
    files = (
        [p for p in (root / "reference").rglob("*") if p.is_file()]
        if (root / "reference").is_dir()
        else []
    )
    try:
        out = subprocess.run(
            ["git", "ls-files", "reference"], capture_output=True, text=True, cwd=root, check=True
        ).stdout
    except Exception:
        return 0, len(files)
    return len([x for x in out.splitlines() if x.strip()]), len(files)


def _nondeterministic() -> int:
    d, c, s = synthetic_rows()
    base = build_corpus(d, c, s)
    bad = 0
    for i in range(SEEDS):
        rows = d[:]
        random.Random(SEED0 + i).shuffle(rows)
        got = build_corpus(rows, c, s)
        bad += (got.obligations, got.links, got.discrepancies) != (
            base.obligations,
            base.links,
            base.discrepancies,
        )
    return bad


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    repo = root.resolve().parent
    syn = synthetic_corpus()
    split_file = root / "reference_split.v1.json"
    split = load_split(split_file)
    m = b.metric

    b.population(POP, "deterministic synthetic stand-in with the reference schema", "regulus.reference.synthetic", len(syn.obligations),
                 "evaluation harness", "synthetic rows built to exercise every reconciliation kind; says nothing about the expert reference")  # fmt: skip

    def add(
        pop: str,
        id: str,
        name: str,
        num: str,
        den: str,
        nv: float,
        dv: float,
        cls: EvidenceClass = EC.PROPERTY,
        gate: Gate | None = HARD0,
        note: str = "",
    ) -> None:
        b.record(m(f"{L}.{id}", L, name, pop, num, den, cls, gate), nv, dv, note)

    regs = len(syn.regulations)
    add(POP, "instrument_failures", "instrument failures on the stand-in", "failed oracle, null and mutation checks", "regulations times instrument checks",
        len(instrument_problems(syn)), regs * INSTRUMENT_CHECKS)  # fmt: skip
    add(
        POP,
        "nondeterministic_builds",
        "non-deterministic corpus builds",
        "builds from shuffled rows that differ",
        "shuffled builds",
        _nondeterministic(),
        SEEDS,
    )
    sp = structural_problems(split)
    add(
        POP,
        "split_structure_violations",
        "split structure violations",
        "violated structural rules",
        "structural rules",
        len(sp),
        3,
        EC.REGRESSION,
    )

    real_dir = repo / "reference"
    have = available(real_dir)
    corpus = load_corpus(real_dir) if have else None
    n_real = len(corpus.regulations) if corpus else 0
    b.population(REAL, "the six expert-reference regulations (local, uncommitted)", "reference/ folder", n_real,
                 "project expert", "expert reference, not held out, not generalization evidence; absent on machines without the local files")  # fmt: skip

    defs: dict[str, tuple[str, str, str, Gate | None, EvidenceClass]] = {
        "instrument_failures_real": ("instrument failures on the reference", "failed oracle, null and mutation checks", "regulations times instrument checks", HARD0, EC.PROPERTY),
        "split_violations": ("split violations against the reference", "violated split rules", "split rules checked", HARD0, EC.REGRESSION),
        "content_leaks": ("committed artifacts containing expert content", "files with expert-authored text", "text files scanned", HARD0, EC.PROPERTY),
        "tracked_reference_files": ("reference files tracked by git", "tracked files under reference/", "files under reference/", HARD0, EC.PROPERTY),
        "unknown_sector_links": ("rows with a sector outside the vocabulary", "unknown-sector rows", "rows read", HARD0, EC.PROPERTY),
        "parse_error_rows": ("rows with an unparseable article reference", "excluded rows", "rows read", HARD0, EC.PROPERTY),
        "count_unreconciled_regulations": ("regulations whose derived count differs from the declared count", "regulations with a count discrepancy", "regulations", None, EC.CORPUS_COVERAGE),
    }  # fmt: skip

    def real(id: str, nv: float, dv: float, note: str = "") -> None:
        name, num, den, gate, cls = defs[id]
        add(REAL, id, name, num, den, nv, dv, cls, gate, note)

    if corpus is None:
        for id, (name, num, den, gate, cls) in defs.items():
            b.unmeasurable(
                m(f"{L}.{id}", L, name, REAL, num, den, cls, gate),
                "the local expert reference is absent",
                Status.NOT_MEASURABLE,
            )
    else:
        kinds = [d.kind for d in corpus.discrepancies]
        rows = max(corpus.rows_read, 1)
        pdf = public_text(repo / "pdf", corpus)
        files = list(tracked_files(repo))
        tracked, present = _tracked(repo)
        flagged = (
            K.COUNT_EXCEEDS_DECLARED,
            K.COUNT_BELOW_DECLARED,
            K.COUNT_UNDECLARED,
            K.DECLARED_COUNT_CONFLICT,
        )
        real(
            "instrument_failures_real", len(instrument_problems(corpus)), n_real * INSTRUMENT_CHECKS
        )
        real("split_violations", len(split_problems(corpus, split)), 5)
        real(
            "content_leaks",
            len(leaking_files(repo, corpus, pdf)),
            max(len(files), 1),
            f"public statute wording is excluded; {len(pdf)} of {n_real} source PDFs available",
        )
        real("tracked_reference_files", tracked, max(present, 1))
        real(
            "unknown_sector_links",
            sum(
                d.detail.get("rows", 0) for d in corpus.discrepancies if d.kind is K.UNKNOWN_SECTOR
            ),
            rows,
        )
        real(
            "parse_error_rows",
            sum(d.detail.get("rows", 0) for d in corpus.discrepancies if d.kind is K.PARSE_ERROR),
            rows,
        )
        real(
            "count_unreconciled_regulations",
            sum(k in flagged for k in kinds),
            n_real,
            "reported, never forced; the pinned expectation is five matched and one over by one",
        )
    for id, name in UNLABELLED:
        b.unmeasurable(m(f"{L}.{id}", L, name, REAL, "reference obligations whose label agrees", "reference obligations with a label", EC.PROPERTY),
                       "the reference carries no labels for this dimension; the rules exist only in the instruction documents", Status.NOT_MEASURABLE)  # fmt: skip
