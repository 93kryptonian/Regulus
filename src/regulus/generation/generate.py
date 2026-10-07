import hashlib
from datetime import datetime

from regulus.documents import ProcessedDocument
from regulus.domain import (
    Generated,
    GenerationMetadata,
    Obligation,
    ObligationContent,
    ObligationEvidence,
    Origin,
    OwnerKind,
)
from regulus.obligations import Lexicon, ObligationCandidate, load_lexicon
from regulus.obligations.models import Citation

from .models import (
    GenerationConfig,
    GenerationInput,
    GenerationOutput,
    GenerationRecord,
    GenerationRequest,
    GenerationResult,
    ObligationGenerator,
    PermittedSource,
    RawGenerated,
    Status,
    Violation,
)
from .verify import verify_evidence, verify_obligation, verify_raw


def _citations(c: ObligationCandidate) -> list[Citation]:
    out = [c.clause, c.marker.citation]
    if c.lead_in:
        out.append(c.lead_in)
    out += list(c.items)
    for role in ("actor", "action", "object", "deadline", "frequency"):
        v = getattr(c, role).value
        if v:
            out.append(v.citation)
    out += [v.citation for v in (*c.conditions, *c.exceptions)]
    return out


def _owner(doc: ProcessedDocument, owner_id: str) -> tuple[str, OwnerKind] | None:
    for a in doc.articles:
        if a.id == owner_id:
            return a.text, OwnerKind.ARTICLE
    for u in doc.amendment_units:
        if u.id == owner_id:
            return u.text, OwnerKind.AMENDMENT_UNIT
    return None


def _fail(
    c: ObligationCandidate,
    status: Status,
    reason: str | None = None,
    violations: tuple[Violation, ...] = (),
    raw: RawGenerated | None = None,
) -> GenerationResult:
    return GenerationResult(
        candidate_id=c.id, status=status, reason=reason, violations=violations, raw=raw
    )


def _one(
    c: ObligationCandidate,
    inp: GenerationInput,
    generator: ObligationGenerator,
    config: GenerationConfig,
    lex: Lexicon,
    generated_at: datetime,
) -> GenerationResult:
    doc = inp.documents.get(c.clause.owner_id.split(":")[0])
    owner = _owner(doc, c.clause.owner_id) if doc else None
    if owner is None:
        return _fail(c, Status.NOT_GENERABLE, "SOURCE_MISSING")
    text, kind = owner
    for cite in _citations(c):
        if cite.owner_id != c.clause.owner_id or text[cite.start : cite.end] != cite.quote:
            return _fail(c, Status.NOT_GENERABLE, "CITATION_MISMATCH")
    source = PermittedSource(
        clause=text[c.clause.start : c.clause.end],
        lead_in=text[c.lead_in.start : c.lead_in.end] if c.lead_in else None,
        items=tuple(text[i.start : i.end] for i in c.items),
    )
    try:
        raw = generator.generate(
            GenerationRequest(candidate=c, source=source, config_version=config.config_version)
        )
        raw = RawGenerated.model_validate(raw.model_dump())
    except Exception as e:
        return _fail(c, Status.GENERATOR_FAILED, type(e).__name__)
    raw = raw.model_copy(update={"text": " ".join(raw.text.split())})
    violations = verify_raw(c, source, raw, lex)
    gen_id = f"{generator.id}@{generator.version}"
    oid = (
        "obl-"
        + hashlib.sha256("|".join([c.id, gen_id, config.config_version]).encode()).hexdigest()[:16]
    )
    seen: set[tuple[int, int]] = set()
    evidence = []
    for cite in _citations(c):
        if (cite.start, cite.end) not in seen:
            seen.add((cite.start, cite.end))
            evidence.append(
                ObligationEvidence(
                    obligation_id=oid,
                    owner_id=cite.owner_id,
                    owner_kind=kind,
                    span=(cite.start, cite.end),
                    quote=cite.quote,
                )
            )
    violations += verify_evidence(evidence, c, text, oid)
    if generator.origin is Origin.AI and (not generator.model or not generator.prompt_version):
        violations.append(Violation.LIFECYCLE_INVALID)
    if violations:
        return _fail(
            c, Status.REJECTED_BY_VERIFICATION, violations=tuple(dict.fromkeys(violations)), raw=raw
        )
    content = ObligationContent(
        text=raw.text, **{k: v for k, v in raw.content.items() if v is not None}
    )
    meta = (
        GenerationMetadata(
            model=generator.model or "",
            prompt_version=generator.prompt_version or "",
            generated_at=generated_at,
        )
        if generator.origin is Origin.AI
        else None
    )
    obligation = Obligation(
        id=oid,
        article_id=f"{c.change_ref.regulation_id}:{c.change_ref.article_number}",
        source_owner_id=c.clause.owner_id,
        origin=generator.origin,
        generated=Generated(content=content, meta=meta),
        current=content,
    )
    violations += verify_obligation(obligation, c, generator.origin)
    if violations:
        return _fail(
            c, Status.REJECTED_BY_VERIFICATION, violations=tuple(dict.fromkeys(violations)), raw=raw
        )
    complete = inp.extraction_complete.get(c.id, True)
    record = GenerationRecord(
        generator=gen_id,
        config_version=config.config_version,
        candidate_id=c.id,
        extractor=c.extractor,
        model=generator.model,
        prompt_version=generator.prompt_version,
        generated_at=generated_at,
        source_complete=complete,
    )
    return GenerationResult(
        candidate_id=c.id,
        status=Status.GENERATED,
        obligation=obligation,
        evidence=tuple(evidence),
        trace=raw.trace,
        record=record,
        open_questions=raw.trace.open_questions,
        raw=None,
    )


def generate(
    inp: GenerationInput,
    generator: ObligationGenerator,
    config: GenerationConfig | None = None,
    generated_at: datetime | None = None,
    lexicon: Lexicon | None = None,
) -> GenerationOutput:
    config = config or GenerationConfig()
    lex = lexicon or load_lexicon()
    when = generated_at or datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    results = tuple(
        _one(c, inp, generator, config, lex, when)
        for c in sorted(inp.candidates, key=lambda c: (c.clause.owner_id, c.clause.start, c.id))
    )
    return GenerationOutput(results=results)
