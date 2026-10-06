from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from regulus.documents import DocStatus, ProcessedDocument
from regulus.documents.models import SourceSpan
from regulus.domain import Article, Regulation, RegulatoryEvent
from regulus.domain.base import Model


class RelationType(StrEnum):
    AMENDS = "AMENDS"
    REPEALS = "REPEALS"
    PARTIALLY_REPEALS = "PARTIALLY_REPEALS"
    IMPLEMENTS = "IMPLEMENTS"


class EvidenceKind(StrEnum):
    EVENT = "EVENT"
    DECLARATION = "DECLARATION"
    UNIT = "UNIT"


class Integrity(StrEnum):
    OK = "OK"
    CONFLICT = "CONFLICT"


class IssueCode(StrEnum):
    SELF_RELATION = "SELF_RELATION"
    ANACHRONISM = "ANACHRONISM"
    MUTUAL_REPEAL = "MUTUAL_REPEAL"
    HIERARCHY_CYCLE = "HIERARCHY_CYCLE"
    HIERARCHY_INVERSION = "HIERARCHY_INVERSION"
    UNIT_TARGET_MISMATCH = "UNIT_TARGET_MISMATCH"
    CONFLICTING_OPERATIONS = "CONFLICTING_OPERATIONS"
    CONFLICTING_DECLARATIONS = "CONFLICTING_DECLARATIONS"
    DUPLICATE_RELATION = "DUPLICATE_RELATION"


class Effect(StrEnum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    REPEALED = "REPEALED"
    PARTIALLY_REPEALED = "PARTIALLY_REPEALED"
    UNKNOWN = "UNKNOWN"


class TargetCheck(StrEnum):
    CONFIRMED = "CONFIRMED"
    MISSING = "MISSING"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    NOT_CHECKED = "NOT_CHECKED"


class ImpactStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class ChangedKind(StrEnum):
    NEW_REGULATION_ARTICLE = "NEW_REGULATION_ARTICLE"
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    TERM_REPLACED = "TERM_REPLACED"


class ArticleStatus(StrEnum):
    IN_FORCE = "IN_FORCE"
    AMENDED = "AMENDED"
    WITHDRAWN = "WITHDRAWN"


class SourceRef(Model):
    kind: EvidenceKind
    ref: str = Field(min_length=1)
    spans: tuple[SourceSpan, ...] = ()


class RelationEvidence(Model):
    kind: EvidenceKind
    ref: str = Field(min_length=1)
    occurred_on: date
    spans: tuple[SourceSpan, ...] = ()


class LineageRelation(Model):
    id: str
    type: RelationType
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    evidence: tuple[RelationEvidence, ...]
    integrity: Integrity = Integrity.OK

    @model_validator(mode="after")
    def _evidence(self) -> "LineageRelation":
        if not self.evidence:
            raise ValueError("a relation needs evidence")
        return self


class IntegrityIssue(Model):
    id: str
    code: IssueCode
    relation_ids: tuple[str, ...] = ()
    detail: str = ""


class UnresolvedRelation(Model):
    event_id: str
    reason: str
    declared_ref: str | None = None


class UnresolvedOperation(Model):
    event_id: str
    owner_id: str
    reason: str
    detail: str = ""
    spans: tuple[SourceSpan, ...] = ()


class TextRef(Model):
    owner_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> "TextRef":
        if self.end < self.start:
            raise ValueError("end < start")
        return self


class ImpactItem(Model):
    id: str
    relation_id: str
    event_id: str
    occurred_on: date
    target_regulation_id: str
    article_number: str | None = None
    provision_path: tuple[str, ...] = ()
    effect: Effect
    source: SourceRef
    new_text: TextRef | None = None
    target_check: TargetCheck = TargetCheck.NOT_CHECKED
    status: ImpactStatus = ImpactStatus.RESOLVED
    unresolved_reason: str | None = None
    derived: bool = False
    source_status: str | None = None


class ChangedProvision(Model):
    regulation_id: str
    article_number: str
    kind: ChangedKind
    text_ref: TextRef
    supersedes: str | None = None
    impact_id: str | None = None


class WithdrawnProvision(Model):
    regulation_id: str
    article_number: str
    effect: Effect
    impact_id: str


class IncompleteSource(Model):
    ref: str
    status: str


class Declaration(Model):
    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    raw: str = ""
    occurred_on: date


class TargetArticles(Model):
    status: DocStatus
    articles: tuple[Article, ...] = ()


class LineageInput(Model):
    events: tuple[RegulatoryEvent, ...] = ()
    regulations: tuple[Regulation, ...] = ()
    declarations: tuple[Declaration, ...] = ()
    documents: dict[str, ProcessedDocument] = {}
    target_articles: dict[str, TargetArticles] = {}


class LineageResult(Model):
    relations: tuple[LineageRelation, ...] = ()
    impacts: tuple[ImpactItem, ...] = ()
    changed: tuple[ChangedProvision, ...] = ()
    withdrawn: tuple[WithdrawnProvision, ...] = ()
    unresolved_relations: tuple[UnresolvedRelation, ...] = ()
    unresolved_operations: tuple[UnresolvedOperation, ...] = ()
    issues: tuple[IntegrityIssue, ...] = ()
    complete: bool = True
    incomplete_sources: tuple[IncompleteSource, ...] = ()


class ArticleProjection(Model):
    status: ArticleStatus
    anomalies: tuple[str, ...] = ()
