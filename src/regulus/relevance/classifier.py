from enum import StrEnum
from typing import Protocol

from pydantic import Field

from regulus.domain import Regulation, RegulatoryEvent
from regulus.domain.base import Model

from .models import ScoreKind, TextSource
from .taxonomy import ScopeProfile, SectorTaxonomy

MAX_EXCERPT = 2000


class Decision(StrEnum):
    RELEVANT = "RELEVANT"
    NOT_RELEVANT = "NOT_RELEVANT"
    ABSTAIN = "ABSTAIN"


class ClassifierError(Exception):
    pass


class ClassificationRequest(Model):
    event: RegulatoryEvent
    regulation: Regulation
    target: Regulation | None = None
    texts: tuple[TextSource, ...] = ()
    taxonomy: SectorTaxonomy
    scope: ScopeProfile


class SemanticEvidence(Model):
    source_id: str = Field(min_length=1)
    span: tuple[int, int]
    quote: str = Field(min_length=1)
    sector: str | None = None
    detail: str = ""


class ClassificationResult(Model):
    decision: Decision
    evidence: tuple[SemanticEvidence, ...] = ()
    score: float | None = None
    score_kind: ScoreKind | None = None


class RelevanceClassifier(Protocol):
    id: str
    version: str

    def classify(self, request: ClassificationRequest) -> ClassificationResult: ...
