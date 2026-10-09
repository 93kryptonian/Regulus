from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from regulus.domain.base import Model
from regulus.ingestion.models import DocumentIdentity, Issue, IssueCode


class UnitKind(StrEnum):
    ARTICLE = "ARTICLE"
    AMENDMENT_UNIT = "AMENDMENT_UNIT"


class SignalKind(StrEnum):
    EXPLICIT_OBLIGATION = "EXPLICIT_OBLIGATION"
    EXPLICIT_PROHIBITION = "EXPLICIT_PROHIBITION"
    PERMISSION = "PERMISSION"
    SANCTION = "SANCTION"
    RESPONSIBILITY = "RESPONSIBILITY"
    DUTY_VERB = "DUTY_VERB"
    PASSIVE_DUTY = "PASSIVE_DUTY"
    CONDITION = "CONDITION"
    DEADLINE = "DEADLINE"
    FREQUENCY = "FREQUENCY"
    ENUMERATION = "ENUMERATION"
    DEFINITION = "DEFINITION"
    CROSS_REFERENCE = "CROSS_REFERENCE"
    NO_SIGNAL = "NO_SIGNAL"


class Signal(Model):
    kind: SignalKind
    term: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    signals_version: str

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("end < start")
        return self


class HintStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    NO_OBLIGATION = "NO_OBLIGATION"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"
    NOT_EXTRACTABLE = "NOT_EXTRACTABLE"
    PHASE6_FAILED = "PHASE6_FAILED"


class HintCandidate(Model):
    id: str
    clause_start: int
    clause_end: int
    marker_start: int
    marker_end: int
    modality: str


class HintDiagnostic(Model):
    code: str
    severity: str
    start: int | None = None
    end: int | None = None
    detail: str = ""


class Phase6Hint(Model):
    status: HintStatus
    candidates: tuple[HintCandidate, ...] = ()
    diagnostics: tuple[HintDiagnostic, ...] = ()
    dropped_ungrounded: int = 0


class ExtractionUnit(Model):
    unit_id: str
    kind: UnitKind
    label: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    article_id: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    text_hash: str
    provision_ids: tuple[str, ...] = ()
    heading_normalized: bool = False
    signals: tuple[Signal, ...]
    phase6: Phase6Hint

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.kind is UnitKind.ARTICLE) != (self.article_id is not None):
            raise ValueError("article_id is required for ARTICLE and absent for AMENDMENT_UNIT")
        if self.page_end < self.page_start:
            raise ValueError("page_end < page_start")
        none = any(s.kind is SignalKind.NO_SIGNAL for s in self.signals)
        if none and len(self.signals) != 1:
            raise ValueError("NO_SIGNAL cannot accompany another signal")
        if not self.signals:
            raise ValueError("a unit carries its signals or NO_SIGNAL")
        return self


class Edge(Model):
    from_unit: str
    to_unit: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class UnresolvedReference(Model):
    from_unit: str
    label: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    external: bool = False


class CrossReferenceGraph(Model):
    edges: tuple[Edge, ...] = ()
    unresolved: tuple[UnresolvedReference, ...] = ()


class PackageStatus(StrEnum):
    PACKAGED = "PACKAGED"
    PACKAGED_WITH_ISSUES = "PACKAGED_WITH_ISSUES"
    FAILED = "FAILED"


class Region(Model):
    kind: IssueCode
    page: int | None = None
    detail: str = ""


class PackageVersions(Model):
    ingestion: str
    signals: str
    phase6_extractor: str
    phase6_lexicon: str
    phase19: str


class ExtractionPackage(Model):
    package_key: str
    identity: DocumentIdentity
    status: PackageStatus
    units: tuple[ExtractionUnit, ...] = ()
    graph: CrossReferenceGraph = CrossReferenceGraph()
    missing_articles: tuple[str, ...] = ()
    unprocessed_regions: tuple[Region, ...] = ()
    inherited_issues: tuple[Issue, ...] = ()
    versions: PackageVersions

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        ids = [u.unit_id for u in self.units]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate unit_id")
        arts = [u.article_id for u in self.units if u.article_id is not None]
        if len(set(arts)) != len(arts):
            raise ValueError("duplicate article_id")
        if [u.ordinal for u in self.units] != list(range(len(self.units))):
            raise ValueError("ordinals must follow document order")
        if self.status is PackageStatus.FAILED and (self.units or self.graph.edges):
            raise ValueError("a FAILED package carries no units")
        if self.status is PackageStatus.PACKAGED and not self.units:
            raise ValueError("PACKAGED needs units; report the loss as PACKAGED_WITH_ISSUES")
        known = set(ids)
        for e in self.graph.edges:
            if e.from_unit not in known or e.to_unit not in known:
                raise ValueError("edge endpoint is not a unit")
        for r in self.graph.unresolved:
            if r.from_unit not in known:
                raise ValueError("unresolved reference from an unknown unit")
        return self
