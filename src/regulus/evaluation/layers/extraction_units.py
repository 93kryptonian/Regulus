import ast
import hashlib
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import regulus.extraction as pkg
from regulus.documents import PdfPlumberReader
from regulus.extraction import ExtractionPackage, PackageStatus, SignalKind, UnitKind, build_package
from regulus.extraction.package import hint_from
from regulus.extraction.signals import selects_term
from regulus.ingestion.ingest import ingest
from regulus.ingestion.models import IngestionResult
from regulus.ingestion.registry import InMemoryRegistry
from regulus.lineage.models import ChangedKind, ChangedProvision, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract
from regulus.reference.load import available, load_corpus
from regulus.reference.split import load_split

from ..builder import EC, HARD0, Builder
from ..models import EvidenceClass, Gate, Status
from .ingestion import HEAD, TextReader

L = "extraction_units"
POP = "extraction_units.synthetic_documents"
REAL = "extraction_units_real.regulations"
FORBIDDEN = (
    "openai",
    "httpx",
    "requests",
    "urllib",
    "socket",
    "http",
    "psycopg",
    "psycopg2",
    "supabase",
    "sqlite3",
    "regulus.reference",
)
BODIES = (
    "Pelaku usaha wajib menyampaikan laporan setiap bulan.",
    "Uraian umum tanpa kata kunci.",
    "Pelaku usaha dilarang menyimpan data; pelaku usaha dapat mengajukan keberatan.",
    "Pelanggaran dikenakan sanksi administratif dan laporan disampaikan paling lama 7 hari.",
    "Pelaku usaha tidak wajib melapor, dalam hal tidak ada perubahan.",
)


def _body(i: int, refs: tuple[int, ...] = ()) -> str:
    text = BODIES[i % len(BODIES)]
    return text + "".join(f" Lihat Pasal {t}." for t in refs)


def _doc(
    n: int, glitch: dict[int, str] | None = None, refs: dict[int, tuple[int, ...]] | None = None
) -> bytes:
    lines = list(HEAD)
    for i in range(1, n + 1):
        lines += [(glitch or {}).get(i, f"Pasal {i}"), _body(i, (refs or {}).get(i, ()))]
    lines += ["Ditetapkan di Jakarta", "PENJELASAN", "I. UMUM"]
    for i in range(1, n + 1):
        lines += [f"Pasal {i}", "Cukup jelas."]
    return ("\f".join("\n".join(lines[i : i + 14]) for i in range(0, len(lines), 14))).encode()


def _run(data: bytes, rid: str = "r") -> IngestionResult:
    return ingest(data, rid, TextReader(), InMemoryRegistry())


def _direct(r: IngestionResult) -> dict[str, object]:
    doc = r.processed
    if doc is None:
        return {}
    changes = tuple(
        ChangedProvision(
            regulation_id=r.identity.regulation_id,
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )
    out = extract(
        ExtractionInput(changes=changes, documents={r.identity.regulation_id: doc}),
        RulesExtractor(),
    )
    return {x.change.owner_id: hint_from(x) for x in out.results}


def structural(pairs: Iterable[tuple[IngestionResult, ExtractionPackage]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for r, p in pairs:
        c["packages"] += 1
        if p.status is PackageStatus.FAILED or r.processed is None:
            continue
        doc = r.processed
        have = {u.article_id for u in p.units}
        c["index"] += len(r.article_index)
        c["dropped"] += sum(a.article_id not in have for a in r.article_index.values())
        c["count_bad"] += len(p.units) != len(doc.articles) + len(doc.amendment_units)
        by_id = {a.id: a for a in doc.articles}
        direct = _direct(r)
        normalized = {str(n.article_number) for n in r.normalizations}
        c["normalized"] += len(normalized)
        c["normalized_lost"] += sum(
            not u.heading_normalized
            for u in p.units
            if u.kind is UnitKind.ARTICLE and u.label in normalized
        ) + len(normalized - {u.label for u in p.units})
        for u in p.units:
            c["units"] += 1
            if u.kind is UnitKind.ARTICLE:
                a = by_id.get(u.article_id or "")
                text = a.text if a else ""
                c["prov_bad"] += not (
                    a
                    and (u.page_start, u.page_end, u.text_hash)
                    == (a.page_start, a.page_end, a.text_hash)
                    and hashlib.sha256(text.encode()).hexdigest() == u.text_hash
                )
                c["hint_bad"] += direct.get(u.article_id or "") != u.phase6
                for s in u.signals:
                    c["signals"] += 1
                    c["span_bad"] += not selects_term(text, s)
            else:
                c["prov_bad"] += u.article_id is not None
                c["signals"] += len(u.signals)
    return c


def _graph_errors() -> tuple[int, int]:
    refs = {1: (2, 1, 9), 2: (3, 3), 3: (1,), 4: (), 5: (2, 99)}
    p = build_package(_run(_doc(5, refs=refs)))
    ids = {u.label: u.unit_id for u in p.units}
    want_e = sorted(
        (ids[str(a)], ids[str(t)]) for a, ts in refs.items() for t in ts if t != a and t <= 5
    )
    want_u = sorted((ids[str(a)], str(t)) for a, ts in refs.items() for t in ts if t > 5)
    got_e = sorted((e.from_unit, e.to_unit) for e in p.graph.edges)
    got_u = sorted((u.from_unit, u.label) for u in p.graph.unresolved)
    mentions = sum(len(v) for v in refs.values())
    bad = (
        len(set(want_e) ^ set(got_e))
        + abs(len(want_e) - len(got_e))
        + len(set(want_u) ^ set(got_u))
    )
    selfm = sum(a in ts for a, ts in refs.items())
    return bad, mentions + selfm


def _imports() -> tuple[int, int]:
    files = sorted(Path(pkg.__file__).parent.glob("*.py"))
    bad = 0
    for f in files:
        for node in ast.walk(ast.parse(f.read_text())):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            bad += sum(any(n == b or n.startswith(b + ".") for b in FORBIDDEN) for n in names)
    return bad, len(files)


def _docs() -> list[bytes]:
    return [
        _doc(6),
        _doc(8, refs={1: (2,), 3: (3, 99)}),
        _doc(6, glitch={3: "Pasa13"}),
        _doc(6, glitch={2: "Pasa12", 5: "Pasa15"}),
        _doc(6, glitch={3: "Pasal 3x"}),
        _doc(3),
        b"\x00junk",
    ]


def _synthetic() -> list[tuple[IngestionResult, ExtractionPackage]]:
    out = []
    for d in _docs():
        r = _run(d)
        out.append((r, build_package(r)))
    return out


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    repo = root.resolve().parent
    m = b.metric
    pairs = _synthetic()
    b.population(POP, "generated documents exercising coverage, signals, hints, graph, normalization and failure", "regulus.evaluation.layers.extraction_units", len(pairs),
                 "evaluation harness", "synthetic text pages through a text reader; says nothing about the expert reference or obligation quality")  # fmt: skip

    def add(pop: str, id: str, name: str, num: str, den: str, nv: float, dv: float,
            cls: EvidenceClass = EC.PROPERTY, gate: Gate | None = HARD0, note: str = "") -> None:  # fmt: skip
        b.record(m(f"{L}.{id}", L, name, pop, num, den, cls, gate), nv, max(dv, 1), note)

    c = structural(pairs)
    repeat = sum(build_package(r).model_dump_json() != p.model_dump_json() for r, p in pairs)
    reingested = sum(
        build_package(_run(d)).model_dump_json() != p.model_dump_json()
        for d, (_, p) in zip(_docs(), pairs, strict=True)
    )
    ge, gm = _graph_errors()
    ib, im = _imports()
    add(
        POP,
        "silent_unit_drop",
        "silent unit drop",
        "indexed articles without a unit",
        "indexed articles",
        c["dropped"],
        c["index"],
    )
    add(
        POP,
        "unit_count_mismatch",
        "unit count differs from articles plus amendment units",
        "packages violating",
        "packages",
        c["count_bad"],
        c["packages"],
    )
    add(
        POP,
        "provenance_loss",
        "units whose provenance does not reconstruct the Phase 3 text",
        "such units",
        "units",
        c["prov_bad"],
        c["units"],
    )
    add(
        POP,
        "signal_span_errors",
        "signals whose offsets do not select their term",
        "such signals",
        "signals",
        c["span_bad"],
        c["signals"],
    )
    add(
        POP,
        "heading_flag_lost",
        "heading normalizations missing from the units",
        "normalized articles without the flag",
        "normalized articles",
        c["normalized_lost"],
        c["normalized"],
    )
    add(
        POP,
        "phase6_divergence",
        "hints differing from a direct Phase 6 run",
        "units whose hint differs",
        "article units",
        c["hint_bad"],
        c["units"],
        EC.REGRESSION,
    )
    add(
        POP,
        "nondeterministic_packages",
        "non-deterministic packages",
        "repeat builds with differing bytes",
        "repeat builds",
        repeat + reingested,
        2 * len(pairs),
    )
    add(
        POP,
        "cross_reference_errors",
        "cross-reference edges or unresolved references violating the contract",
        "mismatches against the planted references",
        "planted mentions",
        ge,
        gm,
    )
    add(
        POP,
        "forbidden_imports",
        "model, network, database or reference imports",
        "detected imports",
        "modules scanned",
        ib,
        im,
    )

    have = available(repo / "reference") and (repo / "pdf").is_dir()
    corpus = load_corpus(repo / "reference") if have else None
    n = len(corpus.regulations) if corpus else 0
    b.population(REAL, "the six expert-reference regulations, packaged from the local PDFs", "pdf/ and reference/", n, "project expert, system ingestion",
                 "structural coverage and exploratory signal association only; the signal lists were chosen while viewing the reference, so these figures are not held-out evidence and say nothing about obligation quality; absent without the local files")  # fmt: skip
    gates = (
        "silent_unit_drop",
        "provenance_loss",
        "signal_span_errors",
        "phase6_divergence",
        "mapped_reference_articles_without_unit",
    )
    names = {
        "silent_unit_drop": (
            "silent unit drop on the real documents",
            "indexed articles without a unit",
            "indexed articles",
        ),
        "provenance_loss": ("provenance loss on the real documents", "such units", "units"),
        "signal_span_errors": (
            "signal span errors on the real documents",
            "such signals",
            "signals",
        ),
        "phase6_divergence": (
            "hints differing from a direct Phase 6 run on the real documents",
            "units whose hint differs",
            "article units",
        ),
        "mapped_reference_articles_without_unit": (
            "mapped reference articles without a unit",
            "mapped reference articles lacking a unit",
            "mapped reference articles",
        ),
    }
    if corpus is None:
        for id in gates:
            name, num, den = names[id]
            b.unmeasurable(
                m(f"{L}.real_{id}", L, name, REAL, num, den, EC.REGRESSION, HARD0),
                "the local reference or PDFs are absent",
                Status.NOT_MEASURABLE,
            )
        b.unmeasurable(
            m(
                f"{L}.real_phase6_article_coverage",
                L,
                "reference articles carrying a Phase 6 candidate",
                REAL,
                "mapped reference articles with a candidate",
                "mapped reference articles",
                EC.CORPUS_COVERAGE,
                None,
            ),
            "the local reference or PDFs are absent",
            Status.NOT_MEASURABLE,
        )
        return
    split = load_split(root / "reference_split.v1.json")
    reader = PdfPlumberReader()
    real: list[tuple[IngestionResult, ExtractionPackage]] = []
    mapped = missing_unit = reported = unmapped = 0
    scopes: dict[str, Counter[str]] = {s: Counter() for s in ("pooled", "dev", "test")}
    types = Counter[str]()
    for reg in corpus.regulations:
        rid = reg.regulation_id
        r = ingest((repo / "pdf" / f"{rid}.pdf").read_bytes(), rid, reader, InMemoryRegistry())
        p = build_package(r)
        real.append((r, p))
        role = split.role_of(rid)
        keys = ("pooled", role.value.lower() if role else "pooled")
        by_label = {u.label: u for u in p.units if u.kind is UnitKind.ARTICLE}
        ref_articles = sorted(corpus.articles_of(rid))
        with_cand = 0
        mp = 0
        for a in ref_articles:
            u = by_label.get(str(a))
            if str(a) in r.article_index:
                mp += 1
                missing_unit += u is None
            elif str(a) in p.missing_articles or p.status is PackageStatus.FAILED:
                reported += 1
            else:
                unmapped += 1
            if u is not None:
                with_cand += bool(u.phase6.candidates)
        mapped += mp
        for k in keys:
            s = scopes[k]
            s["ref_mapped"] += mp
            s["ref_cand"] += with_cand
            s["articles"] += len(by_label)
            for u in by_label.values():
                kinds = {x.kind for x in u.signals}
                for kind in SignalKind:
                    s[f"all:{kind.value}"] += kind in kinds
                    if int(u.label) in ref_articles if u.label.isdigit() else False:
                        s[f"ref:{kind.value}"] += kind in kinds
            s["ref_articles"] += sum(str(a) in by_label for a in ref_articles)
        for u in p.units:
            types[u.phase6.status.value] += 1
        add(REAL, f"phase6_article_coverage_{rid[:10]}", f"reference articles carrying a Phase 6 candidate, {rid[:10]} ({role.value if role else 'unassigned'})", "mapped reference articles with a candidate", "mapped reference articles", with_cand, mp, EC.CORPUS_COVERAGE, None, "descriptive; a Phase 6 candidate is a hint, never a target")  # fmt: skip
        multi = [o for o in corpus.obligations_of(rid)]
        arts_of: dict[str, set[int]] = {}
        for link in corpus.links:
            if link.regulation_id == rid:
                arts_of.setdefault(link.obligation_id, set()).add(link.article)
        ids = {u.unit_id: u.label for u in p.units}
        adj: dict[str, set[str]] = {}
        for e in p.graph.edges:
            adj.setdefault(ids[e.from_unit], set()).add(ids[e.to_unit])
            adj.setdefault(ids[e.to_unit], set()).add(ids[e.from_unit])
        for o in multi:
            arts = {str(a) for a in arts_of.get(o.obligation_id, ())}
            if len(arts) < 2:
                continue
            seen, stack = set(), [next(iter(sorted(arts)))]
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                stack += [y for y in adj.get(x, ()) if y in arts and y not in seen]
            for k in keys:
                scopes[k]["multi"] += 1
                scopes[k]["connected"] += seen == arts
    pc = structural(real)
    for id, (nv, dv) in {
        "silent_unit_drop": (pc["dropped"], pc["index"]),
        "provenance_loss": (pc["prov_bad"], pc["units"]),
        "signal_span_errors": (pc["span_bad"], pc["signals"]),
        "phase6_divergence": (pc["hint_bad"], pc["units"]),
        "mapped_reference_articles_without_unit": (missing_unit, mapped),
    }.items():
        name, nd, dd = names[id]
        add(REAL, f"real_{id}", name, nd, dd, nv, dv, EC.REGRESSION, HARD0)
    note_c = "exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence"
    for k, s in scopes.items():
        add(REAL, f"phase6_article_coverage_{k}", f"reference articles carrying a Phase 6 candidate, {k}", "mapped reference articles with a candidate", "mapped reference articles", s["ref_cand"], s["ref_mapped"], EC.CORPUS_COVERAGE, None, "descriptive, never a target")  # fmt: skip
        add(REAL, f"cross_reference_connectivity_{k}", f"multi-article reference obligations connected by cross-references, {k}", "obligations whose articles form one connected group", "obligations spanning two or more articles", s["connected"], s["multi"], EC.CORPUS_COVERAGE, None, "the graph is a structural signal, not an obligation graph")  # fmt: skip
        for kind in SignalKind:
            add(REAL, f"association_{kind.value.lower()}_reference_{k}", f"{kind.value} among reference-linked articles, {k}", "reference-linked articles carrying the signal", "reference-linked articles", s[f"ref:{kind.value}"], s["ref_articles"], EC.CORPUS_COVERAGE, None, note_c)  # fmt: skip
            add(REAL, f"association_{kind.value.lower()}_all_{k}", f"{kind.value} among all articles, {k}", "articles carrying the signal", "articles", s[f"all:{kind.value}"], s["articles"], EC.CORPUS_COVERAGE, None, note_c)  # fmt: skip
    total = pc["units"]
    for st, cnt in sorted(types.items()):
        add(REAL, f"hint_status_{st.lower()}", f"units with Phase 6 status {st}", "units with this status", "units", cnt, total, EC.CORPUS_COVERAGE, None, "NO_OBLIGATION means no explicit marker, never no obligation")  # fmt: skip
    chars = sum(len(a.text) for r, _ in real if r.processed for a in r.processed.articles)
    add(REAL, "reference_mapping_mapped", "reference articles that map to a Phase 18 article", "mapped", "reference articles", mapped, mapped + reported + unmapped, EC.CORPUS_COVERAGE, None, "structural mapping only")  # fmt: skip
    add(REAL, "reference_mapping_reported_missing", "reference articles absent with a reported cause", "absent with a reported cause", "reference articles", reported, mapped + reported + unmapped, EC.CORPUS_COVERAGE, None, "")  # fmt: skip
    add(REAL, "reference_mapping_unmapped_number", "reference articles with no matching article number and no reported cause", "unmapped numbers", "reference articles", unmapped, mapped + reported + unmapped, EC.CORPUS_COVERAGE, None, "a numbering or source-alignment mismatch, not a missing unit")  # fmt: skip
    add(REAL, "units_carrying_a_signal", "units carrying at least one signal", "units with a lexical or structural signal", "units", total - sum(any(x.kind is SignalKind.NO_SIGNAL for x in u.signals) for _, p in real for u in p.units), total, EC.CORPUS_COVERAGE, None, f"totals for cost projection: {total} units, {pc['signals']} signals, {chars} characters")  # fmt: skip
