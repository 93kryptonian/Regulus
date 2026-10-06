import hashlib
from typing import Protocol

from regulus.documents import DocStatus, ProcessedDocument
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind

from .ground import _Counter, ground
from .impact import impacts
from .lexicon import Lexicon, load_lexicon
from .models import (
    ChangeRef,
    DiagCode,
    Diagnostic,
    ExtractionInput,
    ExtractionOutput,
    ExtractionRequest,
    ExtractionResult,
    FieldStatus,
    ObligationCandidate,
    RawCandidate,
    ResultStatus,
)
from .segment import find_markers, prepare_region


class ObligationExtractor(Protocol):
    id: str
    version: str

    def extract(self, request: ExtractionRequest) -> tuple[RawCandidate, ...]: ...


def _owner_text(doc: ProcessedDocument, owner_id: str) -> str | None:
    for a in doc.articles:
        if a.id == owner_id:
            return a.text
    for u in doc.amendment_units:
        if u.id == owner_id:
            return u.text
    return None


def _cand_id(owner: str, raw: RawCandidate, extractor: str) -> str:
    key = "|".join(
        [owner, str(raw.clause), f"{raw.marker.start}-{raw.marker.end}", raw.modality, extractor]
    )
    return "cand-" + hashlib.sha256(key.encode()).hexdigest()[:16]


def _extract_change(
    change: ChangedProvision, inp: ExtractionInput, extractor: ObligationExtractor, lex: Lexicon
) -> ExtractionResult:
    owner = change.text_ref.owner_id
    ref = ChangeRef(
        regulation_id=change.regulation_id,
        article_number=change.article_number,
        owner_id=owner,
        impact_id=change.impact_id,
    )
    if change.kind is ChangedKind.TERM_REPLACED:
        return ExtractionResult(change=ref, status=ResultStatus.NO_OBLIGATION)
    doc = inp.documents.get(owner.split(":")[0])
    text = _owner_text(doc, owner) if doc else None
    if doc is None or text is None:
        diag = Diagnostic(
            code=DiagCode.INCOMPLETE_SOURCE,
            severity="error",
            owner_id=owner,
            detail="owner text missing",
        )
        return ExtractionResult(
            change=ref, status=ResultStatus.NOT_EXTRACTABLE, diagnostics=(diag,), complete=False
        )
    diags: list[Diagnostic] = []
    complete = doc.status is DocStatus.PROCESSED_OK
    if not complete:
        diags.append(
            Diagnostic(
                code=DiagCode.INCOMPLETE_SOURCE,
                severity="error",
                owner_id=owner,
                detail=str(doc.status),
            )
        )
    region = prepare_region(text, (change.text_ref.start, change.text_ref.end))
    provs = tuple(
        p
        for p in doc.provisions
        if p.owner_id == owner and p.span[0] >= region[0] and p.span[1] <= region[1]
    )
    req = ExtractionRequest(owner_id=owner, text=text, region=region, provisions=provs)
    try:
        raws = extractor.extract(req)
    except Exception:
        return ExtractionResult(
            change=ref, status=ResultStatus.FAILED, diagnostics=tuple(diags), complete=complete
        )
    counter = _Counter()
    name = f"{extractor.id}@{extractor.version}"
    found: dict[str, ObligationCandidate] = {}
    for raw in raws:
        cid = _cand_id(owner, raw, name)
        cand = ground(raw, req, lex, ref, name, cid, counter)
        if cand is not None:
            found[cand.id] = cand
    cands = tuple(sorted(found.values(), key=lambda c: (c.clause.start, c.marker.citation.start)))
    covered = {c.marker.citation.start for c in cands}
    unextracted = 0
    for m in find_markers(text, region, lex):
        span = (m.start, m.end)
        if m.negated:
            diags.append(
                Diagnostic(
                    code=DiagCode.NEGATED_MARKER,
                    severity="info",
                    owner_id=owner,
                    span=span,
                    detail=m.word,
                )
            )
        elif m.start not in covered:
            unextracted += 1
            diags.append(
                Diagnostic(
                    code=DiagCode.UNEXTRACTED_DEONTIC,
                    severity="error",
                    owner_id=owner,
                    span=span,
                    detail=m.word,
                )
            )
    for c in cands:
        for name_, st in (
            ("actor", c.actor),
            ("action", c.action),
            ("object", c.object),
            ("deadline", c.deadline),
            ("frequency", c.frequency),
        ):
            if st.status is FieldStatus.UNDETERMINED:
                diags.append(
                    Diagnostic(
                        code=DiagCode.UNDETERMINED_FIELD,
                        severity="warning",
                        owner_id=owner,
                        span=(c.clause.start, c.clause.end),
                        detail=f"{name_}: {st.reason}",
                    )
                )
        for n in c.undetermined:
            diags.append(
                Diagnostic(
                    code=DiagCode.UNDETERMINED_FIELD,
                    severity="warning",
                    owner_id=owner,
                    span=(c.clause.start, c.clause.end),
                    detail=f"{n}: undelimited trigger",
                )
            )
        if c.items and any(
            o.marker.citation.start != c.marker.citation.start
            and any(i.start <= o.marker.citation.start < i.end for i in c.items)
            for o in cands
        ):
            diags.append(
                Diagnostic(
                    code=DiagCode.ENUMERATION_ITEM_MARKER,
                    severity="info",
                    owner_id=owner,
                    span=(c.clause.start, c.clause.end),
                )
            )
    if cands:
        status = ResultStatus.EXTRACTED
    elif unextracted:
        status = ResultStatus.UNRESOLVED
    else:
        status = ResultStatus.NO_OBLIGATION
    return ExtractionResult(
        change=ref,
        status=status,
        candidates=cands,
        diagnostics=tuple(diags),
        dropped_ungrounded=counter.dropped,
        complete=complete,
    )


def extract(
    inp: ExtractionInput, extractor: ObligationExtractor, lexicon: Lexicon | None = None
) -> ExtractionOutput:
    lex = lexicon or load_lexicon()
    changes = sorted(
        inp.changes, key=lambda c: (c.text_ref.owner_id, c.text_ref.start, c.article_number, c.kind)
    )
    results = tuple(_extract_change(c, inp, extractor, lex) for c in changes)
    return ExtractionOutput(
        results=results,
        impacts=tuple(
            impacts(inp.withdrawn, inp.changes, inp.obligations, inp.obligations_complete)
        ),
    )
