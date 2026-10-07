import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from regulus.documents import DocStatus, PdfPlumberReader, ProcessedDocument, process
from regulus.documents.evaluate import round_trip
from regulus.domain import EventType, RegulatoryEvent
from regulus.domain import ObligationStatus as S
from regulus.domain.base import Model
from regulus.generation import ExtractiveGenerator, GenerationInput, GenerationResult, generate
from regulus.generation.evaluate import run_generation
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import (
    ExtractionInput,
    ExtractionResult,
    RulesExtractor,
    extract,
    load_lexicon,
)
from regulus.obligations.lexicon import Lexicon
from regulus.obligations.models import ObligationCandidate, ResultStatus
from regulus.obligations.segment import find_markers
from regulus.review.gates import verified_evidence
from regulus.similarity import (
    Label,
    LexicalEmbedding,
    SearchConfig,
    SimilarityEntry,
    build_index,
    represent,
    search,
)
from regulus.similarity.representation import embedding_text
from regulus.workflow import (
    SYSTEM,
    InMemoryWorkflowStore,
    RunStatus,
    SnapshotInputs,
    run_event,
    run_state,
)
from regulus.workflow.engine import run_key

from .builder import EC, HARD0, Builder

NOW = datetime(2026, 9, 1, tzinfo=UTC)
L = "corpus"


class CorpusData(Model):
    manifest: dict[str, str]
    documents: int
    status_ok: int
    articles: int
    contiguous_docs: int
    round_trip_checked: int
    round_trip_violations: int
    regions: int
    candidates: int
    unresolved_regions: int
    unextracted_deontic: int
    citations_checked: int
    citation_violations: int
    markers: int
    silent_loss: int
    generated: int
    rejected: int
    gen_tokens: int
    gen_hallucinated: int
    gen_evidence: int
    gen_citation_failures: int
    gen_trace_refs: int
    gen_unaccounted: int
    sim_queries: int
    sim_with_duplicate: int
    sim_duplicate_suggestions: int
    sim_matches: int
    tasks: int
    reviewable: int
    funnel_events: int
    funnel_complete: int
    dead_items: int


def manifest_of(files: list[Path]) -> dict[str, str]:
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}


def standard_files(pdf: Path) -> list[Path]:
    return sorted(pdf.glob("lt*.pdf"))


class CorpusPipeline:
    def __init__(self) -> None:
        self.units: dict[str, tuple[str, GenerationResult]] = {}
        self.items: dict[str, list[str]] = {}
        self.texts: dict[str, dict[str, str]] = {}
        self.candidates: dict[str, ObligationCandidate] = {}
        self.sim: tuple = ()  # type: ignore[type-arg]

    def process(self, event: RegulatoryEvent) -> str:
        return event.regulation_id

    def generate(self, event: RegulatoryEvent, ref: str) -> list[str]:
        return list(self.items[ref])

    def result(self, item_id: str) -> GenerationResult:
        return self.units[item_id][1]

    def enrich(self, item_id: str) -> SnapshotInputs:
        reg, r = self.units[item_id]
        index, provider, cfg = self.sim
        assert r.obligation is not None
        q = SimilarityEntry(obligation=r.obligation, trace=r.trace, candidate_id=r.candidate_id)
        return SnapshotInputs(
            similarity=search(q, index, provider, cfg),
            candidate=self.candidates[r.candidate_id],
            permitted_source=self.texts[reg][r.obligation.source_owner_id],
        )

    def owner_texts(self, ref: str) -> dict[str, str]:
        return self.texts[ref]


def _cites(c: ObligationCandidate) -> list:  # type: ignore[type-arg]
    out = [c.clause, c.marker.citation, *c.items]
    for f in (c.actor, c.action, c.object, c.deadline, c.frequency):
        if f.value:
            out.append(f.value.citation)
    out += [v.citation for v in (*c.conditions, *c.exceptions)]
    return out


def gather(pdf: Path) -> CorpusData | None:
    files = standard_files(pdf)
    if not files:
        return None
    lex = load_lexicon()
    pipe = CorpusPipeline()
    docs: dict[str, ProcessedDocument] = {}
    d: dict[str, int] = dict.fromkeys(CorpusData.model_fields, 0)
    d["manifest"] = manifest_of(
        files + [p for p in (pdf / "pp20_1980.pdf", pdf / "uu21_1982.pdf") if p.exists()]
    )  # type: ignore[assignment]
    pairs = []
    entries: list[SimilarityEntry] = []
    for f in files:
        reg = "R" + f.stem[-6:]
        doc = process(f.read_bytes(), reg, PdfPlumberReader())
        docs[reg] = doc
        pipe.texts[reg] = {a.id: a.text for a in doc.articles}
        d["documents"] += 1
        d["status_ok"] += doc.status is DocStatus.PROCESSED_OK
        d["articles"] += len(doc.articles)
        nums = [a.number for a in doc.articles]
        d["contiguous_docs"] += nums == [str(i) for i in range(1, len(nums) + 1)]
        rt = round_trip(doc)
        d["round_trip_checked"] += rt.checked
        d["round_trip_violations"] += rt.violations
        changes = tuple(
            ChangedProvision(regulation_id=reg, article_number=a.number, kind=ChangedKind.NEW_REGULATION_ARTICLE,
                             text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)))
            for a in doc.articles
        )  # fmt: skip
        ex = extract(ExtractionInput(changes=changes, documents={reg: doc}), RulesExtractor())
        cands = tuple(c for r in ex.results for c in r.candidates)
        pipe.candidates.update({c.id: c for c in cands})
        pairs += [(c, doc) for c in cands]
        _tally_extraction(d, ex.results, pipe.texts[reg], lex)
        gen = generate(
            GenerationInput(candidates=cands, documents={reg: doc}), ExtractiveGenerator()
        )
        pipe.items[reg] = []
        for r in gen.results:
            if r.obligation is not None:
                d["generated"] += 1
                pipe.units[r.obligation.id] = (reg, r)
                pipe.items[reg].append(r.obligation.id)
                entries.append(SimilarityEntry(obligation=r.obligation.model_copy(update={"status": S.APPROVED}),
                                               trace=r.trace, candidate_id=r.candidate_id))  # fmt: skip
            else:
                d["rejected"] += 1
    g = run_generation(pairs)
    d["gen_tokens"], d["gen_hallucinated"] = g.tokens_checked, g.hallucinated_tokens
    d["gen_evidence"], d["gen_citation_failures"] = g.evidence_checked, g.citation_failures
    d["gen_trace_refs"], d["gen_unaccounted"] = g.trace_refs, g.unaccounted_fields
    cfg = SearchConfig()
    provider = LexicalEmbedding.fit(
        [embedding_text(represent(e.obligation, e.trace)) for e in entries]
    )
    index = build_index(entries, provider, cfg)
    pipe.sim = (index, provider, cfg)
    for e in entries:
        q = e.model_copy(update={"obligation": pipe.units[e.obligation.id][1].obligation})
        res = search(q, index, provider, cfg)
        d["sim_queries"] += 1
        dups = sum(m.verdict.label is Label.POSSIBLE_DUPLICATE for m in res.matches)
        d["sim_with_duplicate"] += dups > 0
        d["sim_duplicate_suggestions"] += dups
        d["sim_matches"] += len(res.matches)
    store = InMemoryWorkflowStore()
    for i, reg in enumerate(sorted(pipe.items)):
        ev = RegulatoryEvent(id=f"evt-{i}", type=EventType.NEW, regulation_id=reg, occurred_on=date(2026, 8, 1),
                             detected_on=date(2026, 8, 2), basis="local corpus")  # fmt: skip
        d["funnel_events"] += 1
        rep = run_event(store, pipe, ev, SYSTEM, NOW, lambda *a: True)
        d["funnel_complete"] += rep.status is RunStatus.COMPLETE
        st = run_state(store, run_key(ev.id, "1"))
        d["dead_items"] += sum(1 for u in st.items.values() if u.status.value == "DEAD_LETTER")
    d["tasks"] = len(store.tasks)
    for t in store.tasks.values():
        ob = store.review.get(t.obligation_id)[0]
        texts = pipe.texts[pipe.units[t.obligation_id][0]]
        d["reviewable"] += ob.status is S.PENDING_REVIEW and bool(
            verified_evidence(t.snapshot, ob, texts)
        )
    return CorpusData.model_validate(d)


def _tally_extraction(
    d: dict[str, int], results: tuple[ExtractionResult, ...], texts: dict[str, str], lex: Lexicon
) -> None:
    for r in results:
        d["regions"] += 1
        d["candidates"] += len(r.candidates)
        d["unresolved_regions"] += r.status is ResultStatus.UNRESOLVED
        d["unextracted_deontic"] += sum(
            1 for g in r.diagnostics if g.code.value == "UNEXTRACTED_DEONTIC"
        )
        text = texts.get(r.change.owner_id, "")
        for c in r.candidates:
            for ct in _cites(c):
                d["citations_checked"] += 1
                d["citation_violations"] += text[ct.start : ct.end] != ct.quote
        markers = [m for m in find_markers(text, (0, len(text)), lex) if not m.negated]
        d["markers"] += len(markers)
        if r.status not in (ResultStatus.FAILED, ResultStatus.NOT_EXTRACTABLE):
            covered = {c.marker.citation.start for c in r.candidates} | {
                g.span[0] for g in r.diagnostics if g.code.value == "UNEXTRACTED_DEONTIC" and g.span
            }
            d["silent_loss"] += len({m.start for m in markers} - covered)


def evaluate(b: Builder, pdf: Path) -> dict[str, str]:
    data = gather(pdf)
    n = data.documents if data else 0
    pops = {
        "corpus.documents": ("standard regulation PDFs", n),
        "corpus.articles": ("articles recovered from the corpus", data.articles if data else 0),
        "corpus.regions": ("extraction regions (articles)", data.regions if data else 0),
        "corpus.candidates": ("extracted candidates", data.candidates if data else 0),
        "corpus.generated": ("generated obligations", data.generated if data else 0),
        "corpus.tasks": ("submitted review tasks", data.tasks if data else 0),
    }
    for pid, (desc, size) in pops.items():
        b.population(pid, desc, "local pdf/ corpus (uncommitted, identified by manifest hash)", size, "n/a: real regulations, no labels",
                     "no ground truth; one local set of Indonesian regulations; counts and invariants only")  # fmt: skip
    m = b.metric
    defs = {
        "status_ok": m(
            f"{L}.documents_processed_ok",
            L,
            "documents processed without issues",
            "corpus.documents",
            "documents with status PROCESSED_OK",
            "corpus documents",
            EC.CORPUS_COVERAGE,
        ),
        "contiguous": m(
            f"{L}.documents_with_contiguous_numbering",
            L,
            "documents with contiguous article numbering",
            "corpus.documents",
            "documents whose articles are numbered 1..n without gaps",
            "corpus documents",
            EC.CORPUS_COVERAGE,
        ),
        "round_trip": m(
            f"{L}.provenance_round_trip",
            L,
            "provenance round-trip violation rate",
            "corpus.articles",
            "articles whose text is not reconstructible from its source spans",
            "articles checked",
            EC.PROPERTY,
            HARD0,
        ),
        "citations": m(
            f"{L}.citation_self_consistency",
            L,
            "citation self-consistency violation rate",
            "corpus.candidates",
            "cited spans whose quote is not at the span",
            "citations checked",
            EC.PROPERTY,
            HARD0,
        ),
        "silent": m(
            f"{L}.marker_accounting",
            L,
            "marker accounting violation rate",
            "corpus.regions",
            "marker occurrences with neither candidate nor diagnostic",
            "marker occurrences",
            EC.PROPERTY,
            HARD0,
        ),
        "unresolved": m(
            f"{L}.unresolved_regions",
            L,
            "regions left unresolved",
            "corpus.regions",
            "regions with status UNRESOLVED",
            "extraction regions",
            EC.CORPUS_COVERAGE,
        ),
        "candidates": m(
            f"{L}.regions_with_candidates",
            L,
            "candidates per region",
            "corpus.regions",
            "candidates produced",
            "extraction regions",
            EC.CORPUS_COVERAGE,
        ),
        "generated": m(
            f"{L}.candidates_generated",
            L,
            "candidates turned into obligations",
            "corpus.candidates",
            "obligations generated and verified",
            "candidates",
            EC.CORPUS_COVERAGE,
        ),
        "halluc": m(
            f"{L}.generation_new_token_rate",
            L,
            "generated-token violation rate",
            "corpus.generated",
            "tokens of generated text absent from the permitted source",
            "tokens of generated text",
            EC.PROPERTY,
            HARD0,
        ),
        "evidence": m(
            f"{L}.generation_evidence_citation",
            L,
            "generation evidence citation violation rate",
            "corpus.generated",
            "evidence items whose quote is not at its span",
            "evidence items",
            EC.PROPERTY,
            HARD0,
        ),
        "accounting": m(
            f"{L}.generation_field_accounting",
            L,
            "generation field accounting violation rate",
            "corpus.generated",
            "trace references duplicated or untraced",
            "trace references",
            EC.PROPERTY,
            HARD0,
        ),
        "dup": m(
            f"{L}.queries_with_duplicate_suggestion",
            L,
            "queries with a duplicate suggestion",
            "corpus.generated",
            "queries with at least one POSSIBLE_DUPLICATE suggestion (a suggestion, not a confirmed duplicate)",
            "similarity queries",
            EC.CORPUS_COVERAGE,
        ),
        "submitted": m(
            f"{L}.funnel_tasks_per_generated",
            L,
            "generated obligations submitted for review",
            "corpus.generated",
            "review tasks created",
            "generated obligations",
            EC.CORPUS_COVERAGE,
        ),
        "reviewable": m(
            f"{L}.funnel_reviewable_tasks",
            L,
            "tasks reviewable with verified evidence",
            "corpus.tasks",
            "tasks pending review with verified evidence",
            "review tasks",
            EC.CORPUS_COVERAGE,
        ),
        "runs": m(
            f"{L}.funnel_runs_complete",
            L,
            "event runs completed",
            "corpus.documents",
            "runs with status COMPLETE",
            "event runs",
            EC.CORPUS_COVERAGE,
        ),
        "dead": m(
            f"{L}.funnel_dead_lettered_items",
            L,
            "items dead-lettered",
            "corpus.generated",
            "items dead-lettered",
            "generated obligations",
            EC.CORPUS_COVERAGE,
        ),
    }
    if data is None:
        for df in defs.values():
            b.unmeasurable(df, "the local corpus is absent")
        return {}
    r = b.record
    r(defs["status_ok"], data.status_ok, data.documents)
    r(defs["contiguous"], data.contiguous_docs, data.documents)
    r(
        defs["round_trip"],
        data.round_trip_violations,
        data.round_trip_checked,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(
        defs["citations"],
        data.citation_violations,
        data.citations_checked,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(
        defs["silent"],
        data.silent_loss,
        data.markers,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(defs["unresolved"], data.unresolved_regions, data.regions)
    r(defs["candidates"], data.candidates, data.regions)
    r(
        defs["generated"],
        data.generated,
        data.candidates,
        f"{data.rejected} candidates rejected by verification",
    )
    r(
        defs["halluc"],
        data.gen_hallucinated,
        data.gen_tokens,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(
        defs["evidence"],
        data.gen_citation_failures,
        data.gen_evidence,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(
        defs["accounting"],
        data.gen_unaccounted,
        data.gen_trace_refs,
        "0 violations in N items checked: self-consistency, not correctness",
    )
    r(
        defs["dup"],
        data.sim_with_duplicate,
        data.sim_queries,
        f"{data.sim_duplicate_suggestions} duplicate suggestions over {data.sim_matches} returned matches",
    )
    r(defs["submitted"], data.tasks, data.generated)
    r(defs["reviewable"], data.reviewable, data.tasks)
    r(defs["runs"], data.funnel_complete, data.funnel_events)
    r(defs["dead"], data.dead_items, data.generated)
    return data.manifest
