from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from regulus.documents import ProcessedDocument
from regulus.documents.models import Provision
from regulus.domain import Obligation
from regulus.domain.base import Model
from regulus.lineage import ChangedProvision, WithdrawnProvision


class Modality(StrEnum):
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"


class FieldStatus(StrEnum):
    PRESENT = "PRESENT"
    NOT_STATED = "NOT_STATED"
    UNDETERMINED = "UNDETERMINED"


class ResultStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    NO_OBLIGATION = "NO_OBLIGATION"
    UNRESOLVED = "UNRESOLVED"
    FAILED = "FAILED"
    NOT_EXTRACTABLE = "NOT_EXTRACTABLE"


class DiagCode(StrEnum):
    UNEXTRACTED_DEONTIC = "UNEXTRACTED_DEONTIC"
    NEGATED_MARKER = "NEGATED_MARKER"
    UNDETERMINED_FIELD = "UNDETERMINED_FIELD"
    ENUMERATION_ITEM_MARKER = "ENUMERATION_ITEM_MARKER"
    INCOMPLETE_SOURCE = "INCOMPLETE_SOURCE"


class ImpactKind(StrEnum):
    WITHDRAWN = "WITHDRAWN"
    MODIFIED = "MODIFIED"
    TERM_REPLACED = "TERM_REPLACED"


class Citation(Model):
    owner_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _span(self) -> Self:
        if self.end - self.start != len(self.quote):
            raise ValueError("citation span does not match its quote")
        return self

    def within(self, other: "Citation") -> bool:
        return (
            self.owner_id == other.owner_id and other.start <= self.start and self.end <= other.end
        )


class FieldValue(Model):
    value: str = Field(min_length=1)
    citation: Citation

    @model_validator(mode="after")
    def _verbatim(self) -> Self:
        if self.value != self.citation.quote:
            raise ValueError("value must equal its citation quote")
        return self


class FieldState(Model):
    status: FieldStatus
    value: FieldValue | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.status is FieldStatus.PRESENT) != (self.value is not None):
            raise ValueError("value iff PRESENT")
        if (self.status is FieldStatus.UNDETERMINED) != (self.reason is not None):
            raise ValueError("reason iff UNDETERMINED")
        return self


class ChangeRef(Model):
    regulation_id: str
    article_number: str
    owner_id: str
    impact_id: str | None = None


class ObligationCandidate(Model):
    id: str
    change_ref: ChangeRef
    clause: Citation
    modality: Modality
    marker: FieldValue
    actor: FieldState
    action: FieldState
    object: FieldState
    deadline: FieldState
    frequency: FieldState
    conditions: tuple[FieldValue, ...] = ()
    exceptions: tuple[FieldValue, ...] = ()
    undetermined: tuple[str, ...] = ()
    items: tuple[Citation, ...] = ()
    lead_in: Citation | None = None
    extractor: str

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.action.status is not FieldStatus.PRESENT:
            raise ValueError("a candidate needs a present action")
        if not self.marker.citation.within(self.clause):
            raise ValueError("marker outside clause")
        lead = {"actor", "conditions"}
        singles = {
            "actor": self.actor,
            "action": self.action,
            "object": self.object,
            "deadline": self.deadline,
            "frequency": self.frequency,
        }
        for name, st in singles.items():
            if st.value is not None:
                self._check(name, st.value.citation, name in lead)
        for name, values in (("conditions", self.conditions), ("exceptions", self.exceptions)):
            for v in values:
                self._check(name, v.citation, name in lead)
        return self

    def _check(self, name: str, c: Citation, may_lead: bool) -> None:
        if c.within(self.clause) or (
            may_lead and self.lead_in is not None and c.within(self.lead_in)
        ):
            return
        raise ValueError(f"{name} cites text outside the clause")


class RawField(Model):
    value: str
    start: int
    end: int


class RawFieldState(Model):
    status: FieldStatus
    value: RawField | None = None
    reason: str | None = None


class RawCandidate(Model):
    clause: tuple[int, int]
    modality: Modality
    marker: RawField
    actor: RawFieldState
    action: RawFieldState
    object: RawFieldState
    deadline: RawFieldState
    frequency: RawFieldState
    conditions: tuple[RawField, ...] = ()
    exceptions: tuple[RawField, ...] = ()
    undetermined: tuple[str, ...] = ()
    items: tuple[tuple[int, int], ...] = ()
    lead_in: tuple[int, int] | None = None


class ExtractionRequest(Model):
    owner_id: str
    text: str
    region: tuple[int, int]
    provisions: tuple[Provision, ...] = ()


class Diagnostic(Model):
    code: DiagCode
    severity: str
    owner_id: str
    span: tuple[int, int] | None = None
    detail: str = ""


class ExtractionResult(Model):
    change: ChangeRef
    status: ResultStatus
    candidates: tuple[ObligationCandidate, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    dropped_ungrounded: int = 0
    complete: bool = True


class ObligationImpact(Model):
    id: str
    kind: ImpactKind
    regulation_id: str
    article_number: str
    article_id: str
    affected_obligation_ids: tuple[str, ...] = ()
    review_required: bool
    store_complete: bool
    impact_id: str | None = None


class ExtractionInput(Model):
    changes: tuple[ChangedProvision, ...] = ()
    withdrawn: tuple[WithdrawnProvision, ...] = ()
    documents: dict[str, ProcessedDocument] = {}
    obligations: tuple[Obligation, ...] = ()
    obligations_complete: bool = True


class ExtractionOutput(Model):
    results: tuple[ExtractionResult, ...] = ()
    impacts: tuple[ObligationImpact, ...] = ()
