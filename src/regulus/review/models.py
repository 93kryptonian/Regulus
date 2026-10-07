from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from regulus.domain import FieldChange, Obligation, ObligationEvidence, ReviewDecision
from regulus.domain.base import Model
from regulus.similarity import SimilarityResult


class Role(StrEnum):
    REVIEWER = "REVIEWER"
    PUBLISHER = "PUBLISHER"
    AUDITOR = "AUDITOR"


class Action(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT = "EDIT"
    PUBLISH = "PUBLISH"


class RejectCode(StrEnum):
    DUPLICATE_OF = "DUPLICATE_OF"
    NOT_AN_OBLIGATION = "NOT_AN_OBLIGATION"
    INCORRECT_EXTRACTION = "INCORRECT_EXTRACTION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SOURCE_UNCLEAR = "SOURCE_UNCLEAR"
    OTHER = "OTHER"


class Resolution(StrEnum):
    RESOLVED_BY_EDIT = "RESOLVED_BY_EDIT"
    ACCEPTED_AS_IS = "ACCEPTED_AS_IS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Disposition(StrEnum):
    NOT_A_DUPLICATE = "NOT_A_DUPLICATE"
    CONFIRMED_RELATED = "CONFIRMED_RELATED"
    CONFIRMED_VARIANT = "CONFIRMED_VARIANT"
    CONTRADICTION_NOTED = "CONTRADICTION_NOTED"
    NOT_REVIEWED = "NOT_REVIEWED"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    CLAIMED = "CLAIMED"
    DONE = "DONE"
    SUPERSEDED = "SUPERSEDED"


class Status(StrEnum):
    APPLIED = "APPLIED"
    DENIED = "DENIED"
    STALE = "STALE"
    INCOMPLETE_REVIEW = "INCOMPLETE_REVIEW"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    NOT_RECORDED = "NOT_RECORDED"


SOURCE_INCOMPLETE, SOURCE_CHANGED, SOURCE_WITHDRAWN = (
    "SOURCE_INCOMPLETE",
    "SOURCE_CHANGED",
    "SOURCE_WITHDRAWN",
)


class Actor(Model):
    id: str = Field(min_length=1)
    roles: tuple[Role, ...]


class RejectReason(Model):
    code: RejectCode
    match_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.code is RejectCode.DUPLICATE_OF) != bool(self.match_id):
            raise ValueError("DUPLICATE_OF requires exactly a match_id")
        if self.code is RejectCode.OTHER and not self.text:
            raise ValueError("OTHER requires text")
        return self


class OpenQuestionResolution(Model):
    question: str
    resolution: Resolution
    note: str = ""


class MatchDisposition(Model):
    match_id: str
    disposition: Disposition


class ReviewSnapshot(Model):
    obligation: Obligation
    evidence: tuple[ObligationEvidence, ...] = ()
    open_questions: tuple[str, ...] = ()
    source_complete: bool = True
    source_flags: tuple[str, ...] = ()
    similarity: SimilarityResult | None = None
    permitted_source: str = ""
    carried_questions: tuple[str, ...] = ()
    hash: str = ""


class ReviewTask(Model):
    id: str
    obligation_id: str
    status: TaskStatus = TaskStatus.OPEN
    claimed_by: str | None = None
    claim_expires_at: AwareDatetime | None = None
    snapshots: tuple[ReviewSnapshot, ...]
    created_at: AwareDatetime

    @property
    def snapshot(self) -> ReviewSnapshot:
        return self.snapshots[-1]


class ReviewRecord(Model):
    id: str
    decision: ReviewDecision
    task_id: str
    base_version: str
    snapshot_hash: str
    actor_id: str
    actor_roles: tuple[Role, ...]
    open_question_resolutions: tuple[OpenQuestionResolution, ...] = ()
    match_dispositions: tuple[MatchDisposition, ...] = ()
    acknowledged_flags: tuple[str, ...] = ()
    divergence: tuple[str, ...] = ()
    reject_reason: RejectReason | None = None
    prev_hash: str
    hash: str = ""


class ActionRequest(Model):
    action: Action
    task_id: str
    base_version: str
    actor: Actor
    at: AwareDatetime
    reason: str | None = None
    changes: tuple[FieldChange, ...] = ()
    reject_reason: RejectReason | None = None
    resolutions: tuple[OpenQuestionResolution, ...] = ()
    dispositions: tuple[MatchDisposition, ...] = ()
    acknowledged_flags: tuple[str, ...] = ()


class ReviewOutcome(Model):
    status: Status
    obligation: Obligation | None = None
    records: tuple[ReviewRecord, ...] = ()
    reasons: tuple[str, ...] = ()
