import re
from collections import Counter
from pathlib import Path

from regulus.documents import PdfPlumberReader, UnreadableDocument, process
from regulus.documents.models import PageSource, RawPage
from regulus.ingestion.headings import reverify
from regulus.ingestion.ingest import ingest
from regulus.ingestion.models import IngestionResult, IssueCode, RegistryOutcome
from regulus.ingestion.models import IngestionStatus as S
from regulus.ingestion.registry import InMemoryRegistry
from regulus.reference.load import available, load_corpus
from regulus.reference.normalize import norm

from ..builder import EC, HARD0, TARGET0, Builder
from ..models import EvidenceClass, Gate, Status

L = "ingestion"
POP = "ingestion.synthetic_documents"
REAL = "ingestion_real.benchmark"
HEAD = [
    "PERATURAN PEMERINTAH",
    "NOMOR 1 TAHUN 2026",
    "TENTANG CONTOH",
    "Menimbang : bahwa perlu diatur.",
    "MEMUTUSKAN:",
    "BAB I",
    "KETENTUAN UMUM",
]


class TextReader:
    ocr = None
    min_chars = 50
    dpi = 200

    def __call__(self, data: bytes) -> list[RawPage]:
        text = data.split(b"\x00")[0].decode("utf-8", "replace")
        if not text.strip():
            raise UnreadableDocument("empty")
        return [
            RawPage(number=i, source=PageSource.NATIVE, text=t)
            for i, t in enumerate(text.split("\f"), 1)
        ]


def doc(
    n: int = 6,
    glitch: dict[int, str] | None = None,
    extra: list[str] | None = None,
    tweak: str = "",
    meta: str = "",
    penjelasan: bool = True,
) -> bytes:
    lines = list(HEAD)
    for i in range(1, n + 1):
        lines += [
            (glitch or {}).get(i, f"Pasal {i}"),
            f"Setiap pelaku usaha wajib melaksanakan kewajiban nomor {i} dengan baik{tweak}.",
        ]
    lines += extra or []
    if penjelasan:
        lines += ["Ditetapkan di Jakarta", "PENJELASAN", "I. UMUM"]
        for i in range(1, n + 1):
            lines += [f"Pasal {i}", "Cukup jelas."]
    pages = ["\n".join(lines[i : i + 14]) for i in range(0, len(lines), 14)]
    return ("\f".join(pages) + ("\x00" + meta if meta else "")).encode()


def _run(
    data: bytes,
    rid: str = "r",
    reg: InMemoryRegistry | None = None,
    normalize: bool = True,
) -> IngestionResult:
    registry = reg if reg is not None else InMemoryRegistry()
    return ingest(data, rid, TextReader(), registry, normalize_headings=normalize)


def _identity_scenarios() -> tuple[int, int]:
    bad = 0
    reg = InMemoryRegistry()
    steps = [
        (doc(), "r", RegistryOutcome.NEW),
        (doc(), "r", RegistryOutcome.UNCHANGED),
        (doc(tweak=" baru"), "r", RegistryOutcome.NEW_VERSION),
        (doc(), "other", RegistryOutcome.DUPLICATE_CONTENT),
        (doc(meta="x"), "r", RegistryOutcome.RERENDERED),
    ]
    for data, rid, want in steps:
        bad += _run(data, rid, reg).registry is not want
    reg2 = InMemoryRegistry()
    _run(doc(), "r", reg2)
    again = ingest(doc(), "r", TextReader(), reg2, normalize_headings=False)
    bad += again.registry is not RegistryOutcome.REPROCESSED
    reg3 = InMemoryRegistry()
    r = _run(b"\x00junk", "r", reg3)
    bad += not (
        r.status is S.FAILED
        and reg3.versions("r") == ()
        and r.registry is RegistryOutcome.NOT_REGISTERED
    )
    first = _run(doc(), "r", reg).identity
    bad += reg.find("r", first.processing_key) is None
    return bad, len(steps) + 3


def _key_scenarios() -> tuple[int, int]:
    base = _run(doc()).identity.processing_key
    equal = [
        _run(doc(), "other").identity.processing_key == base,
        _run(doc()).identity.processing_key == base,
    ]
    differ = [
        _run(doc(tweak=" x")).identity.processing_key != base,
        _run(doc(), normalize=False).identity.processing_key != base,
    ]
    return (len(equal) - sum(equal)) + (len(differ) - sum(differ)), len(equal) + len(differ)


def _determinism() -> tuple[int, int]:
    docs = [
        doc(),
        doc(glitch={3: "Pasa13"}),
        doc(glitch={2: "Pasa12", 5: "Pasa15"}),
        doc(extra=["Pasa13"]),
        doc(n=3),
    ]
    return sum(_run(d).model_dump_json() != _run(d).model_dump_json() for d in docs), len(docs)


def _phase3_equivalence() -> tuple[int, int]:
    docs = [doc(), doc(glitch={3: "Pasa13"}), doc(n=3)]
    bad = sum(_run(d, normalize=False).processed != process(d, "r", TextReader()) for d in docs)
    return bad, len(docs)


def _normalization_checks() -> tuple[int, int, int, int]:
    positives = [
        doc(glitch={3: "Pasa13"}),
        doc(glitch={4: "Pasa14"}),
        doc(glitch={2: "Pasa12", 5: "Pasa15"}),
    ]
    made = failing = 0
    for d in positives:
        r = _run(d)
        arts = r.processed.articles if r.processed else ()
        present = {int(a.number): (a.page_start, a.page_end) for a in arts if a.number.isdigit()}
        made += len(r.normalizations)
        failing += sum(bool(reverify(n, present)) for n in r.normalizations)
        failing += not r.normalizations
    negatives = [
        doc(glitch={1: "Pasa11"}),
        doc(glitch={3: "Pasa19"}),
        doc(extra=["Pasa13"]),
        doc(glitch={3: "Pass3"}, extra=["Pasa13"], penjelasan=False),
        doc(glitch={3: "Pass3"}, extra=["sebagaimana dimaksud dalam Pasa13 dan seterusnya"]),
        doc(glitch={3: "Pasa13", 4: "Pasa13"}),
    ]
    false = sum(bool(_run(d).normalizations) for d in negatives)
    return failing, made + len(positives), false, len(negatives)


def _unreadable() -> tuple[int, int]:
    junk = [b"", b"\x00", b"   ", b"\x00meta only"]
    return sum(_run(j).status is not S.FAILED for j in junk), len(junk)


def _reported(r: IngestionResult, n: int) -> bool:
    if r.status in (S.FAILED, S.REFUSED):
        return True
    for i in r.issues:
        if i.code is IssueCode.ARTICLE_GAP and str(n) in [x.strip() for x in i.detail.split(",")]:
            return True
    return False


def _tokens(s: str) -> Counter[str]:
    return Counter(re.findall(r"\w+", norm(s)))


def evaluate(b: Builder, root: Path = Path("evaluation")) -> None:
    repo = root.resolve().parent
    m = b.metric
    b.population(
        POP,
        "generated documents exercising identity, registry, normalization and failure",
        "regulus.evaluation.layers.ingestion",
        12,
        "evaluation harness",
        "synthetic text pages through a text reader; PDF byte parsing is covered by the unit tests, not here",
    )

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

    v, d = _identity_scenarios()
    add(
        POP,
        "identity_errors",
        "identity errors",
        "wrong registry outcome",
        "registry scenarios",
        v,
        d,
    )
    v, d = _key_scenarios()
    add(
        POP,
        "processing_key_instability",
        "processing-key instability",
        "keys equal for different inputs or different for equal inputs",
        "key scenarios",
        v,
        d,
    )
    v, d = _determinism()
    add(
        POP,
        "nondeterministic_ingestion",
        "non-deterministic ingestion",
        "documents with differing results on repeat",
        "documents repeated",
        v,
        d,
    )
    v, d = _phase3_equivalence()
    add(
        POP,
        "phase3_divergence",
        "divergence from Phase 3 with normalization off",
        "documents whose result differs from the Phase 3 output",
        "documents compared",
        v,
        d,
        EC.REGRESSION,
    )
    v, d = _unreadable()
    add(
        POP,
        "unreadable_reported_as_ingested",
        "unreadable inputs reported as ingested",
        "such inputs",
        "unreadable inputs tried",
        v,
        d,
    )
    failing, made, false, neg = _normalization_checks()
    add(
        POP,
        "normalization_violations",
        "normalizations violating a condition",
        "normalizations failing re-verification or missing",
        "normalizations expected",
        failing,
        made,
    )
    add(
        POP,
        "false_normalizations",
        "false normalizations",
        "negative cases that were normalized",
        "negative cases tried",
        false,
        neg,
    )

    have = available(repo / "reference") and (repo / "pdf").is_dir()
    corpus = load_corpus(repo / "reference") if have else None
    n = len(corpus.regulations) if corpus else 0
    b.population(
        REAL,
        "the six expert-reference regulations, ingested from the local PDFs",
        "pdf/ and reference/",
        n,
        "project expert, system ingestion",
        "article-number recovery only; the reference article text is not a source copy; "
        "not generalization evidence; absent without the local files",
    )
    defs: dict[str, tuple[str, str, str, Gate | None]] = {
        "reference_articles_not_recovered": (
            "reference articles not recovered",
            "reference articles absent from the result",
            "reference articles",
            TARGET0,
        ),
        "silent_article_loss": (
            "silent article loss",
            "absent reference articles with no ARTICLE_GAP or failure issue",
            "reference articles",
            HARD0,
        ),
        "benchmark_gaps_unresolved": (
            "benchmark documents with an unresolved ARTICLE_GAP",
            "such documents",
            "benchmark documents",
            TARGET0,
        ),
        "reference_text_agreement": (
            "reference text agreement (not an oracle)",
            "reference texts with at least 95 percent token containment in the extracted article",
            "reference texts",
            None,
        ),
        "non_benchmark_ingested": (
            "non-benchmark PDFs ingested without failure",
            "PDFs ingested",
            "non-benchmark PDFs",
            None,
        ),
    }
    if corpus is None:
        for id, (name, num, den, gate) in defs.items():
            b.unmeasurable(
                m(f"{L}.{id}", L, name, REAL, num, den, EC.CORPUS_COVERAGE, gate),
                "the local reference or PDFs are absent",
                Status.NOT_MEASURABLE,
            )
        return
    reader = PdfPlumberReader()
    lost = silent = gaps = text_ok = texts = total = 0
    for reg in corpus.regulations:
        rid = reg.regulation_id
        r = ingest((repo / "pdf" / f"{rid}.pdf").read_bytes(), rid, reader, InMemoryRegistry())
        want = sorted(corpus.articles_of(rid))
        absent = [a for a in want if str(a) not in r.article_index]
        lost += len(absent)
        silent += sum(not _reported(r, a) for a in absent)
        gaps += any(i.code is IssueCode.ARTICLE_GAP for i in r.issues)
        total += len(want)
        arts = {
            int(a.number): a
            for a in (r.processed.articles if r.processed else ())
            if a.number.isdigit()
        }
        for link in corpus.links:
            if link.regulation_id != rid or link.article not in arts:
                continue
            have_t = _tokens(arts[link.article].text)
            for t in link.article_texts:
                want_t = _tokens(t)
                if want_t:
                    texts += 1
                    share = sum(min(c, have_t[w]) for w, c in want_t.items()) / sum(want_t.values())
                    text_ok += share >= 0.95
        add(
            REAL,
            f"recovery_{rid[:10]}",
            f"reference articles recovered, {rid[:10]}",
            "reference articles present in the result",
            "reference articles of this regulation",
            len(want) - len(absent),
            len(want),
            EC.CORPUS_COVERAGE,
            None,
        )
    name, num, den, gate = defs["reference_articles_not_recovered"]
    add(
        REAL,
        "reference_articles_not_recovered",
        name,
        num,
        den,
        lost,
        total,
        EC.REGRESSION,
        gate,
        "pooled; per-regulation rows are listed beside it",
    )
    name, num, den, gate = defs["silent_article_loss"]
    add(REAL, "silent_article_loss", name, num, den, silent, total, EC.PROPERTY, gate)
    name, num, den, gate = defs["benchmark_gaps_unresolved"]
    add(REAL, "benchmark_gaps_unresolved", name, num, den, gaps, n, EC.REGRESSION, gate)
    name, num, den, gate = defs["reference_text_agreement"]
    add(
        REAL,
        "reference_text_agreement",
        name,
        num,
        den,
        text_ok,
        max(texts, 1),
        EC.CORPUS_COVERAGE,
        gate,
        "the reference text is not a verbatim source copy; reported, never an oracle",
    )
    bench = {r.regulation_id for r in corpus.regulations}
    others = [f for f in sorted((repo / "pdf").glob("*.pdf")) if f.stem not in bench]
    ok = sum(
        ingest(f.read_bytes(), f.stem, reader, InMemoryRegistry()).status
        in (S.INGESTED, S.INGESTED_WITH_ISSUES)
        for f in others
    )
    name, num, den, gate = defs["non_benchmark_ingested"]
    add(
        REAL,
        "non_benchmark_ingested",
        name,
        num,
        den,
        ok,
        max(len(others), 1),
        EC.CORPUS_COVERAGE,
        gate,
        "robustness only; no quality claim",
    )
