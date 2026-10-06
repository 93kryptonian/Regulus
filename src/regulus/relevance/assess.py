import hashlib
from datetime import datetime

from pydantic import ConfigDict

from regulus.domain import EventType
from regulus.domain.base import Model

from .classifier import (
    MAX_EXCERPT,
    ClassificationRequest,
    ClassificationResult,
    ClassifierError,
    Decision,
    RelevanceClassifier,
)
from .models import (
    AssessmentContext,
    AssessmentResult,
    AssessStatus,
    Basis,
    Confidence,
    Effect,
    Evidence,
    Kind,
    Method,
    Relevance,
    RelevanceAssessment,
    SectorStatus,
    SemanticInfo,
    SemanticStatus,
    Strength,
    TextSource,
    title_source,
)
from .rules import RuleSet, signals
from .taxonomy import ScopeProfile, SectorTaxonomy


class AssessmentConfig(Model):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    taxonomy: SectorTaxonomy
    scope: ScopeProfile
    rules: RuleSet


def _not_assessable(reason: str) -> AssessmentResult:
    return AssessmentResult(status=AssessStatus.NOT_ASSESSABLE, reason=reason)


def _check(ctx: AssessmentContext) -> str | None:
    e = ctx.event
    if e.type is EventType.NEEDS_REVIEW:
        return "NEEDS_REVIEW events are not assessable"
    if ctx.regulation.id != e.regulation_id:
        return "regulation does not match event.regulation_id"
    if e.target_id and (ctx.target is None or ctx.target.id != e.target_id):
        return "target missing or does not match event.target_id"
    if not e.target_id and ctx.target is not None:
        return "target supplied for an event without target_id"
    return None


def _texts(ctx: AssessmentContext) -> dict[str, str]:
    out = {title_source(ctx.regulation.id): ctx.regulation.title}
    if ctx.target:
        out[title_source(ctx.target.id)] = ctx.target.title
    out.update({t.owner_id: t.text for t in ctx.texts})
    return out


def _ground(
    res: ClassificationResult, texts: dict[str, str], taxonomy: SectorTaxonomy, rule_id: str
) -> tuple[list[Evidence], int]:
    good, dropped = [], 0
    for se in res.evidence:
        text = texts.get(se.source_id)
        s, e = se.span
        ok = (
            text is not None
            and 0 <= s < e <= len(text)
            and text[s:e] == se.quote
            and (se.sector is None or se.sector in taxonomy.codes)
        )
        if not ok:
            dropped += 1
            continue
        effect = (
            Effect.SECTOR_ONLY
            if se.sector
            else Effect.SUPPORTS_RELEVANCE
            if res.decision is Decision.RELEVANT
            else Effect.CONTRADICTS_RELEVANCE
        )
        good.append(
            Evidence(
                kind=Kind.SEMANTIC,
                rule_id=rule_id,
                strength=Strength.WEAK,
                effect=effect,
                sector=se.sector,
                source_id=se.source_id,
                span=se.span,
                quote=se.quote,
                detail=se.detail,
            )
        )
    return sorted(good, key=lambda x: (x.source_id, x.span or (0, 0), x.sector or "")), dropped


def _sectors(evidence: list[Evidence]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                e.sector
                for e in evidence
                if e.sector
                and (e.kind is Kind.SEMANTIC or e.strength in (Strength.STRONG, Strength.MODERATE))
            }
        )
    )


def assess(
    ctx: AssessmentContext,
    config: AssessmentConfig,
    classifier: RelevanceClassifier | None,
    assessed_at: datetime,
) -> AssessmentResult:
    if reason := _check(ctx):
        return _not_assessable(reason)
    det = signals(ctx, config.scope, config.rules)
    strong_sup = any(
        e.strength is Strength.STRONG and e.effect is Effect.SUPPORTS_RELEVANCE for e in det
    )
    strong_con = any(
        e.strength is Strength.STRONG and e.effect is Effect.CONTRADICTS_RELEVANCE for e in det
    )
    mod_sup = any(
        e.strength is Strength.MODERATE and e.effect is Effect.SUPPORTS_RELEVANCE for e in det
    )
    any_sup = any(e.effect is Effect.SUPPORTS_RELEVANCE for e in det)

    relevance: Relevance | None = None
    confidence, conflict = Confidence.NONE, False
    if strong_sup and strong_con:
        relevance, conflict = Relevance.INSUFFICIENT_EVIDENCE, True
    elif strong_sup:
        relevance, confidence = Relevance.RELEVANT, Confidence.HIGH
    elif strong_con:
        relevance, confidence = Relevance.NOT_RELEVANT, Confidence.HIGH
    elif mod_sup:
        relevance, confidence = Relevance.RELEVANT, Confidence.MEDIUM

    sectors = _sectors(det)
    undecided = relevance is None
    needs_sectors = relevance is Relevance.RELEVANT and not sectors
    semantic_ev: list[Evidence] = []
    info: SemanticInfo | None = None
    semantic_decided = False
    if classifier is not None and (undecided or needs_sectors):
        texts = _texts(ctx)
        request = ClassificationRequest(
            event=ctx.event,
            regulation=ctx.regulation,
            target=ctx.target,
            texts=tuple(
                TextSource(owner_id=t.owner_id, text=t.text[:MAX_EXCERPT]) for t in ctx.texts
            ),
            taxonomy=config.taxonomy,
            scope=config.scope,
        )
        cid, cver = classifier.id, classifier.version
        try:
            res = classifier.classify(request)
        except (ClassifierError, TimeoutError, OSError, ValueError, RuntimeError):
            info = SemanticInfo(
                classifier_id=cid, classifier_version=cver, status=SemanticStatus.FAILED
            )
        else:
            semantic_ev, dropped = _ground(res, texts, config.taxonomy, f"{cid}@{cver}")
            if needs_sectors:
                semantic_ev = [e for e in semantic_ev if e.sector]
            decided = res.decision is not Decision.ABSTAIN and bool(semantic_ev)
            useful = decided if undecided else bool(semantic_ev)
            info = SemanticInfo(
                classifier_id=cid,
                classifier_version=cver,
                status=SemanticStatus.OK if useful else SemanticStatus.ABSTAINED,
                score=res.score,
                score_kind=res.score_kind,
                dropped_ungrounded=dropped,
            )
            if undecided and decided:
                if res.decision is Decision.RELEVANT:
                    relevance, confidence, semantic_decided = (
                        Relevance.RELEVANT,
                        Confidence.LOW,
                        True,
                    )
                elif any_sup:
                    relevance, conflict = Relevance.INSUFFICIENT_EVIDENCE, True
                else:
                    relevance, confidence, semantic_decided = (
                        Relevance.NOT_RELEVANT,
                        Confidence.LOW,
                        True,
                    )
    if relevance is None:
        relevance = Relevance.INSUFFICIENT_EVIDENCE
    used_semantic = bool(semantic_ev) and relevance is not Relevance.INSUFFICIENT_EVIDENCE
    if used_semantic:
        sectors = _sectors(det + semantic_ev)
    method = (
        Method.SEMANTIC if semantic_decided else Method.HYBRID if used_semantic else Method.RULES
    )
    evidence = det + (semantic_ev if used_semantic else [])
    basis = Basis(
        scope_id=config.scope.id,
        scope_version=config.scope.version,
        ruleset_version=config.rules.version,
        taxonomy_version=config.taxonomy.version,
    )
    cl = f"{classifier.id}@{classifier.version}" if classifier else "none"
    key = "|".join(
        [
            ctx.event.id,
            f"{basis.scope_id}@{basis.scope_version}",
            basis.ruleset_version,
            basis.taxonomy_version,
            cl,
        ]
    )
    codes = ",".join(dict.fromkeys(e.rule_id for e in evidence)) or "no evidence"
    summary = f"{relevance} ({confidence}): {codes}; sectors: {','.join(sectors) or 'none'}"
    a = RelevanceAssessment(
        id="rel-" + hashlib.sha256(key.encode()).hexdigest()[:16],
        event_id=ctx.event.id,
        regulation_id=ctx.regulation.id,
        target_id=ctx.event.target_id,
        relevance=relevance,
        confidence=confidence,
        sectors=sectors,
        sector_status=SectorStatus.DETERMINED if sectors else SectorStatus.UNDETERMINED,
        evidence=tuple(evidence),
        method=method,
        semantic=info,
        conflict=conflict,
        summary=summary,
        basis=basis,
        assessed_at=assessed_at,
    )
    return AssessmentResult(status=AssessStatus.ASSESSED, assessment=a)
