import hashlib

from regulus.documents import ProcessedDocument
from regulus.documents.models import Code, Provision
from regulus.ingestion.models import IngestionResult, IngestionStatus, Issue, IssueCode
from regulus.lineage.models import ChangedKind, ChangedProvision, TextRef
from regulus.obligations import ExtractionInput, ObligationExtractor, RulesExtractor, extract
from regulus.obligations.lexicon import Lexicon, load_lexicon
from regulus.obligations.models import ExtractionResult

from .crossrefs import build_graph
from .lexicon import SignalsLexicon, load_signals
from .models import (
    CrossReferenceGraph,
    ExtractionPackage,
    ExtractionUnit,
    HintCandidate,
    HintDiagnostic,
    HintStatus,
    PackageStatus,
    PackageVersions,
    Phase6Hint,
    Region,
    UnitKind,
)
from .signals import SignalMatcher

PHASE19_VERSION = "1"
SEP = "\x1f"
_REGIONS = (Code.PAGE_FAILED, Code.ANNEX_NOT_PROCESSED)


def _sha(*parts: str) -> str:
    return hashlib.sha256(SEP.join(parts).encode()).hexdigest()


def hint_from(result: ExtractionResult) -> Phase6Hint:
    diags = sorted(
        (
            HintDiagnostic(
                code=d.code.value,
                severity=d.severity,
                start=d.span[0] if d.span else None,
                end=d.span[1] if d.span else None,
                detail=d.detail,
            )
            for d in result.diagnostics
        ),
        key=lambda d: (d.start if d.start is not None else -1, d.end or 0, d.code, d.detail),
    )
    cands = tuple(
        HintCandidate(
            id=c.id,
            clause_start=c.clause.start,
            clause_end=c.clause.end,
            marker_start=c.marker.citation.start,
            marker_end=c.marker.citation.end,
            modality=c.modality.value,
        )
        for c in result.candidates
    )
    return Phase6Hint(
        status=HintStatus(result.status.value),
        candidates=cands,
        diagnostics=tuple(diags),
        dropped_ungrounded=result.dropped_ungrounded,
    )


def phase6_hint(
    doc: ProcessedDocument,
    regulation_id: str,
    owner_id: str,
    label: str,
    text: str,
    extractor: ObligationExtractor,
    lex: Lexicon,
) -> Phase6Hint:
    change = ChangedProvision(
        regulation_id=regulation_id,
        article_number=label,
        kind=ChangedKind.NEW_REGULATION_ARTICLE,
        text_ref=TextRef(owner_id=owner_id, start=0, end=len(text)),
    )
    try:
        out = extract(
            ExtractionInput(changes=(change,), documents={owner_id.split(":")[0]: doc}),
            extractor,
            lex,
        )
        return hint_from(out.results[0])
    except Exception:
        return Phase6Hint(status=HintStatus.PHASE6_FAILED)


def _missing(result: IngestionResult) -> tuple[str, ...]:
    names: set[str] = set()
    for i in result.issues:
        if i.code is IssueCode.ARTICLE_GAP:
            names.update(n for n in i.detail.replace("...", ",...").split(",") if n)
    return tuple(
        sorted(names, key=lambda n: (n == "...", not n.isdigit(), int(n) if n.isdigit() else 0, n))
    )


def _regions(doc: ProcessedDocument) -> tuple[Region, ...]:
    regs = {
        Region(kind=IssueCode(d.code.value), page=d.page, detail=d.detail)
        for d in doc.diagnostics
        if d.code in _REGIONS
    }
    return tuple(sorted(regs, key=lambda r: (r.kind.value, r.page or 0, r.detail)))


def _failed(result: IngestionResult, versions: PackageVersions, key: str) -> ExtractionPackage:
    return ExtractionPackage(
        package_key=key,
        identity=result.identity,
        status=PackageStatus.FAILED,
        inherited_issues=result.issues,
        versions=versions,
    )


def versions_for(
    result: IngestionResult, sig: SignalsLexicon, extractor: ObligationExtractor, lex: Lexicon
) -> tuple[PackageVersions, str]:
    v = PackageVersions(
        ingestion=result.identity.ingestion_version,
        signals=sig.version,
        phase6_extractor=extractor.version,
        phase6_lexicon=lex.version,
        phase19=PHASE19_VERSION,
    )
    key = _sha(
        result.identity.processing_key, v.signals, v.phase6_extractor, v.phase6_lexicon, v.phase19
    )
    return v, key


def build_package(
    result: IngestionResult,
    extractor: ObligationExtractor | None = None,
    signals: SignalsLexicon | None = None,
) -> ExtractionPackage:
    sig = signals or load_signals()
    ex = extractor or RulesExtractor()
    lex: Lexicon = getattr(ex, "lex", None) or load_lexicon()
    versions, key = versions_for(result, sig, ex, lex)
    doc = result.processed
    if result.status in (IngestionStatus.FAILED, IngestionStatus.REFUSED) or doc is None:
        return _failed(result, versions, key)
    matcher = SignalMatcher(sig, lex)
    by_owner: dict[str, list[Provision]] = {}
    for p in doc.provisions:
        by_owner.setdefault(p.owner_id, []).append(p)
    normalized = {str(n.article_number) for n in result.normalizations}
    rid = result.identity.regulation_id
    items: list[tuple[UnitKind, str, str | None, str, str, int, int, str]] = [
        (UnitKind.ARTICLE, a.number, a.id, a.id, a.text, a.page_start, a.page_end, a.text_hash)
        for a in doc.articles
    ] + [
        (
            UnitKind.AMENDMENT_UNIT,
            u.label,
            None,
            u.id,
            u.text,
            u.page_start,
            u.page_end,
            u.text_hash,
        )
        for u in doc.amendment_units
    ]
    units: list[ExtractionUnit] = []
    texts: list[tuple[str, UnitKind, str, str]] = []
    for ordinal, (kind, label, art_id, owner, text, p0, p1, h) in enumerate(items):
        provs = tuple(by_owner.get(owner, ()))
        uid = _sha(rid, kind.value, label, str(ordinal))[:16]
        units.append(
            ExtractionUnit(
                unit_id=uid,
                kind=kind,
                label=label,
                ordinal=ordinal,
                article_id=art_id,
                page_start=p0,
                page_end=p1,
                text_hash=h,
                provision_ids=tuple(f"{owner}#{i}:{'.'.join(p.path)}" for i, p in enumerate(provs)),
                heading_normalized=kind is UnitKind.ARTICLE and label in normalized,
                signals=matcher.signals(text, provs, label if kind is UnitKind.ARTICLE else None),
                phase6=phase6_hint(doc, rid, owner, label, text, ex, lex),
            )
        )
        texts.append((uid, kind, label, text))
    missing = _missing(result)
    regions = _regions(doc)
    indexed = {a.article_id for a in result.article_index.values()}
    present = {a.id for a in doc.articles}
    extra: list[Issue] = [
        Issue(
            code=IssueCode.OTHER_ERROR,
            article_number=r.number,
            detail="indexed article is absent from the processed document",
        )
        for r in result.article_index.values()
        if r.article_id not in present
    ] + [
        Issue(
            code=IssueCode.OTHER_ERROR,
            article_number=a.number,
            detail="processed article is absent from the article index",
        )
        for a in doc.articles
        if a.id not in indexed
    ]
    issues = result.issues + tuple(extra)
    clean = (
        result.status is IngestionStatus.INGESTED
        and units
        and not missing
        and not regions
        and not extra
        and all(u.phase6.status is not HintStatus.PHASE6_FAILED for u in units)
    )
    return ExtractionPackage(
        package_key=key,
        identity=result.identity,
        status=PackageStatus.PACKAGED if clean else PackageStatus.PACKAGED_WITH_ISSUES,
        units=tuple(units),
        graph=build_graph(texts),
        missing_articles=missing,
        unprocessed_regions=regions,
        inherited_issues=issues,
        versions=versions,
    )


__all__ = ["CrossReferenceGraph", "build_package", "hint_from", "phase6_hint", "versions_for"]
