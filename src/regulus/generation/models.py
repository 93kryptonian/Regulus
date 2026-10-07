from enum import StrEnum
from typing import Protocol

from pydantic import AwareDatetime, Field

from regulus.documents import ProcessedDocument
from regulus.domain import Obligation, ObligationEvidence, Origin
from regulus.domain.base import Model
from regulus.obligations import ObligationCandidate


class Step(StrEnum):
    PRESERVE = "PRESERVE"
    WHITESPACE_COLLAPSE = "WHITESPACE_COLLAPSE"
    TRIM_PUNCTUATION = "TRIM_PUNCTUATION"
    JOIN = "JOIN"


class Disposition(StrEnum):
    PRESERVED = "PRESERVED"
    NORMALIZED = "NORMALIZED"
    ABSENT_NOT_STATED = "ABSENT_NOT_STATED"
    ABSENT_UNDETERMINED = "ABSENT_UNDETERMINED"
    DROPPED = "DROPPED"


class DropReason(StrEnum):
    DUPLICATE = "DUPLICATE"


class Violation(StrEnum):
    NEW_WORD = "NEW_WORD"
    FIELD_LOST = "FIELD_LOST"
    ORDER_CHANGED = "ORDER_CHANGED"
    MODALITY_CHANGED = "MODALITY_CHANGED"
    NUMBER_CHANGED = "NUMBER_CHANGED"
    FIELD_ALTERED = "FIELD_ALTERED"
    TRACE_INVALID = "TRACE_INVALID"
    CITATION_MISMATCH = "CITATION_MISMATCH"
    REQUIRED_MISSING = "REQUIRED_MISSING"
    LIFECYCLE_INVALID = "LIFECYCLE_INVALID"


class Status(StrEnum):
    GENERATED = "GENERATED"
    NOT_GENERABLE = "NOT_GENERABLE"
    GENERATOR_FAILED = "GENERATOR_FAILED"
    REJECTED_BY_VERIFICATION = "REJECTED_BY_VERIFICATION"


class FieldRef(Model):
    role: str
    index: int = 0


class CandidateTrace(Model):
    field: FieldRef
    disposition: Disposition
    steps: tuple[Step, ...] = ()
    target: str | None = None
    reason: str | None = None


class ContentTrace(Model):
    field: str
    sources: tuple[FieldRef, ...]
    steps: tuple[Step, ...] = ()


class TransformationTrace(Model):
    candidate: tuple[CandidateTrace, ...]
    content: tuple[ContentTrace, ...]
    open_questions: tuple[str, ...] = ()


class PermittedSource(Model):
    clause: str
    lead_in: str | None = None
    items: tuple[str, ...] = ()

    def all_text(self) -> str:
        return " ".join([*([self.lead_in] if self.lead_in else []), self.clause, *self.items])


class GenerationRequest(Model):
    candidate: ObligationCandidate
    source: PermittedSource
    config_version: str


class RawGenerated(Model):
    text: str
    content: dict[str, str | None]
    trace: TransformationTrace


class ObligationGenerator(Protocol):
    id: str
    version: str
    origin: Origin
    model: str | None
    prompt_version: str | None

    def generate(self, request: GenerationRequest) -> RawGenerated: ...


class GenerationConfig(Model):
    config_version: str = Field(min_length=1, default="1")


class GenerationRecord(Model):
    generator: str
    config_version: str
    candidate_id: str
    extractor: str
    model: str | None = None
    prompt_version: str | None = None
    generated_at: AwareDatetime
    source_complete: bool


class GenerationResult(Model):
    candidate_id: str
    status: Status
    obligation: Obligation | None = None
    evidence: tuple[ObligationEvidence, ...] = ()
    trace: TransformationTrace | None = None
    record: GenerationRecord | None = None
    open_questions: tuple[str, ...] = ()
    violations: tuple[Violation, ...] = ()
    reason: str | None = None
    raw: RawGenerated | None = None


class GenerationInput(Model):
    candidates: tuple[ObligationCandidate, ...] = ()
    documents: dict[str, ProcessedDocument] = {}
    extraction_complete: dict[str, bool] = {}


class GenerationOutput(Model):
    results: tuple[GenerationResult, ...] = ()
