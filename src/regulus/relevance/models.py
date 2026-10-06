from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from regulus.domain import Regulation, RegulatoryEvent
from regulus.domain.base import Model


class Relevance(StrEnum):
    RELEVANT = "RELEVANT"
    NOT_RELEVANT = "NOT_RELEVANT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class Kind(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC = "SEMANTIC"


class Strength(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class Effect(StrEnum):
    SUPPORTS_RELEVANCE = "SUPPORTS_RELEVANCE"
    CONTRADICTS_RELEVANCE = "CONTRADICTS_RELEVANCE"
    SECTOR_ONLY = "SECTOR_ONLY"


class Method(StrEnum):
    RULES = "RULES"
    SEMANTIC = "SEMANTIC"
    HYBRID = "HYBRID"


class SectorStatus(StrEnum):
    DETERMINED = "DETERMINED"
    UNDETERMINED = "UNDETERMINED"


class SemanticStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


class ScoreKind(StrEnum):
    UNCALIBRATED = "UNCALIBRATED"
    CALIBRATED_PROBABILITY = "CALIBRATED_PROBABILITY"


class AssessStatus(StrEnum):
    ASSESSED = "ASSESSED"
    NOT_ASSESSABLE = "NOT_ASSESSABLE"


class TextSource(Model):
    owner_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


def title_source(regulation_id: str) -> str:
    return f"{regulation_id}#title"


class Evidence(Model):
    kind: Kind
    rule_id: str = Field(min_length=1)
    strength: Strength
    effect: Effect
    sector: str | None = None
    source_id: str = Field(min_length=1)
    span: tuple[int, int] | None = None
    quote: str | None = None
    detail: str = ""

    @model_validator(mode="after")
    def _grounded(self) -> Self:
        if (self.span is None) != (self.quote is None):
            raise ValueError("span and quote go together")
        if self.span and (self.span[0] < 0 or self.span[1] - self.span[0] != len(self.quote or "")):
            raise ValueError("invalid span")
        return self


class SemanticInfo(Model):
    classifier_id: str
    classifier_version: str
    status: SemanticStatus
    score: float | None = None
    score_kind: ScoreKind | None = None
    dropped_ungrounded: int = 0


class Basis(Model):
    scope_id: str
    scope_version: str
    ruleset_version: str
    taxonomy_version: str


class RelevanceAssessment(Model):
    id: str
    event_id: str
    regulation_id: str
    target_id: str | None = None
    relevance: Relevance
    confidence: Confidence
    sectors: tuple[str, ...] = ()
    sector_status: SectorStatus
    evidence: tuple[Evidence, ...] = ()
    method: Method
    semantic: SemanticInfo | None = None
    conflict: bool = False
    summary: str
    basis: Basis
    assessed_at: AwareDatetime

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if list(self.sectors) != sorted(set(self.sectors)):
            raise ValueError("sectors must be sorted and unique")
        if (self.sector_status is SectorStatus.UNDETERMINED) != (not self.sectors):
            raise ValueError("sector_status UNDETERMINED iff no sectors")
        insufficient = self.relevance is Relevance.INSUFFICIENT_EVIDENCE
        if insufficient != (self.confidence is Confidence.NONE):
            raise ValueError("confidence NONE iff INSUFFICIENT_EVIDENCE")
        if self.conflict and not insufficient:
            raise ValueError("conflict implies INSUFFICIENT_EVIDENCE")
        if self.method is Method.SEMANTIC and self.confidence not in (
            Confidence.LOW,
            Confidence.NONE,
        ):
            raise ValueError("semantic-only decisions are LOW confidence")
        if not insufficient and not self.evidence:
            raise ValueError("a decided assessment needs evidence")
        return self


class AssessmentContext(Model):
    event: RegulatoryEvent
    regulation: Regulation
    target: Regulation | None = None
    texts: tuple[TextSource, ...] = ()


class AssessmentResult(Model):
    status: AssessStatus
    assessment: RelevanceAssessment | None = None
    reason: str | None = None
