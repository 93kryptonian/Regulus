from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime

from regulus.domain import Obligation
from regulus.domain.base import Model
from regulus.review import ReviewTask


class WorkflowRole(StrEnum):
    COORDINATOR = "COORDINATOR"
    OPERATOR = "OPERATOR"
    SYSTEM = "SYSTEM"


class Principal(Model):
    id: str
    roles: tuple[WorkflowRole, ...] = ()


SYSTEM = Principal(id="system", roles=(WorkflowRole.SYSTEM,))


class Kind(StrEnum):
    SUBMISSION_INTENT = "SUBMISSION_INTENT"
    SUBMITTED = "SUBMITTED"
    SUBMIT_FAILED = "SUBMIT_FAILED"
    SUBMIT_REFUSED = "SUBMIT_REFUSED"
    CLOCK_REGRESSION = "CLOCK_REGRESSION"
    ASSIGNED = "ASSIGNED"
    REASSIGNED = "REASSIGNED"
    UNASSIGNED = "UNASSIGNED"
    DUE_SET = "DUE_SET"
    RESCHEDULED = "RESCHEDULED"
    TICK_ACTION = "TICK_ACTION"
    NOTIFICATION_QUEUED = "NOTIFICATION_QUEUED"
    NOTIFICATION_DELIVERED = "NOTIFICATION_DELIVERED"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
    NOTIFICATION_DEAD_LETTER = "NOTIFICATION_DEAD_LETTER"


class WorkflowRecord(Model):
    id: str
    stream: str
    seq: int
    kind: Kind
    key: str | None = None
    principal_id: str
    at: AwareDatetime
    details: dict[str, Any] = {}
    prev_hash: str
    hash: str = ""


class PreparedSubmission(Model):
    key: str
    content_hash: str
    obligation: Obligation
    task: ReviewTask


class Phase(StrEnum):
    NONE = "NONE"
    INTENT = "INTENT"
    COMPLETE = "COMPLETE"


class SubmissionState(Model):
    phase: Phase = Phase.NONE
    key: str | None = None
    content_hash: str | None = None
    task_id: str | None = None
    prepared: PreparedSubmission | None = None


class SubmitStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ALREADY_SUBMITTED = "ALREADY_SUBMITTED"
    CONFLICT = "CONFLICT"
    NOT_SUBMITTABLE = "NOT_SUBMITTABLE"
    NOT_GENERATED = "NOT_GENERATED"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    DENIED = "DENIED"
    FAILED = "FAILED"


class SubmissionOutcome(Model):
    status: SubmitStatus
    task: ReviewTask | None = None
    reasons: tuple[str, ...] = ()
