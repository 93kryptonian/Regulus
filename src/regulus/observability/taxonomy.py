from enum import StrEnum

from regulus.generation import Status as GenStatus
from regulus.review import Status as ReviewStatus
from regulus.workflow import Permanent, SubmitStatus, Unavailable


class Stage(StrEnum):
    RUN = "RUN"
    DETECTED_NOTIFY = "DETECTED_NOTIFY"
    PROCESS = "PROCESS"
    GENERATE = "GENERATE"
    ENRICH = "ENRICH"
    SUBMIT = "SUBMIT"
    REVIEW_ACTION = "REVIEW_ACTION"
    NOTIFY_DELIVER = "NOTIFY_DELIVER"
    TICK = "TICK"


class Kind(StrEnum):
    SPAN_STARTED = "SPAN_STARTED"
    SPAN_FINISHED = "SPAN_FINISHED"
    SPAN_ABANDONED = "SPAN_ABANDONED"
    POINT = "POINT"


class Outcome(StrEnum):
    OK = "OK"
    ABSTAINED = "ABSTAINED"
    REFUSED = "REFUSED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    SKIPPED = "SKIPPED"


FAULTS = (Outcome.FAILED_RETRYABLE, Outcome.FAILED_PERMANENT)


class ErrorClass(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    PERMANENT = "PERMANENT"
    REJECTED_INPUT = "REJECTED_INPUT"
    STORE = "STORE"
    CHANNEL_UNAVAILABLE = "CHANNEL_UNAVAILABLE"
    CHANNEL_REJECTED = "CHANNEL_REJECTED"
    DEAD_LETTER = "DEAD_LETTER"
    DENIED = "DENIED"
    STALE = "STALE"
    INCOMPLETE_REVIEW = "INCOMPLETE_REVIEW"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ALREADY_DONE = "ALREADY_DONE"
    ABANDONED = "ABANDONED"
    UNCLASSIFIED = "UNCLASSIFIED"


COUNT_KEYS = frozenset(
    {"items", "retries", "candidates", "tokens_in", "tokens_out", "events", "dropped"}
)
ATTR_KEYS = frozenset(
    {"status", "action", "store", "recovered", "clock_regression", "attempt_kind"}
)
ATTR_VALUES = frozenset(
    {*(s.value for s in ReviewStatus), *(s.value for s in SubmitStatus), *(s.value for s in GenStatus),
     "APPROVE", "REJECT", "EDIT", "PUBLISH", "memory", "intent", "INTEGRITY", "FIRST", "RETRY", "DELIVERED", "RETRYING",
     "FAILED_PERMANENT", "DEAD_LETTER", "QUEUED"}
)  # fmt: skip

REFUSALS = {
    ReviewStatus.DENIED.value: ErrorClass.DENIED,
    ReviewStatus.STALE.value: ErrorClass.STALE,
    ReviewStatus.INCOMPLETE_REVIEW.value: ErrorClass.INCOMPLETE_REVIEW,
    ReviewStatus.INVALID_TRANSITION.value: ErrorClass.INVALID_TRANSITION,
    ReviewStatus.EVIDENCE_INVALID.value: ErrorClass.EVIDENCE_INVALID,
}


def classify_review(status: str) -> tuple[Outcome, ErrorClass | None]:
    if status == ReviewStatus.APPLIED.value:
        return Outcome.OK, None
    if status == ReviewStatus.NOT_RECORDED.value:
        return Outcome.FAILED_RETRYABLE, ErrorClass.STORE
    if status in REFUSALS:
        return Outcome.REFUSED, REFUSALS[status]
    return Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED


def classify_submit(status: str) -> tuple[Outcome, ErrorClass | None]:
    if status in (SubmitStatus.SUBMITTED.value,):
        return Outcome.OK, None
    if status == SubmitStatus.ALREADY_SUBMITTED.value:
        return Outcome.SKIPPED, ErrorClass.ALREADY_DONE
    if status == SubmitStatus.FAILED.value:
        return Outcome.FAILED_RETRYABLE, ErrorClass.STORE
    if status == SubmitStatus.DENIED.value:
        return Outcome.REFUSED, ErrorClass.DENIED
    if status in (SubmitStatus.CONFLICT.value, SubmitStatus.NOT_SUBMITTABLE.value, SubmitStatus.NOT_GENERATED.value,
                  SubmitStatus.EVIDENCE_INVALID.value):  # fmt: skip
        return Outcome.FAILED_PERMANENT, ErrorClass.REJECTED_INPUT
    return Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED


def classify_exception(exc: BaseException) -> tuple[Outcome, ErrorClass]:
    if isinstance(exc, Unavailable):
        return Outcome.FAILED_RETRYABLE, ErrorClass.UNAVAILABLE
    if isinstance(exc, Permanent):
        return Outcome.FAILED_PERMANENT, ErrorClass.PERMANENT
    from regulus.review import StoreError

    if isinstance(exc, StoreError):
        return Outcome.FAILED_RETRYABLE, ErrorClass.STORE
    return Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED


def classify_notification(state: str) -> tuple[Outcome, ErrorClass | None]:
    return {
        "DELIVERED": (Outcome.OK, None),
        "RETRYING": (Outcome.FAILED_RETRYABLE, ErrorClass.CHANNEL_UNAVAILABLE),
        "QUEUED": (Outcome.SKIPPED, ErrorClass.ALREADY_DONE),
        "FAILED_PERMANENT": (Outcome.FAILED_PERMANENT, ErrorClass.CHANNEL_REJECTED),
        "DEAD_LETTER": (Outcome.FAILED_PERMANENT, ErrorClass.DEAD_LETTER),
    }.get(state, (Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED))


def classify_generation(status: str) -> tuple[Outcome, ErrorClass | None]:
    if status == GenStatus.GENERATED.value:
        return Outcome.OK, None
    if status == GenStatus.NOT_GENERABLE.value:
        return Outcome.ABSTAINED, ErrorClass.INSUFFICIENT_EVIDENCE
    if status == GenStatus.GENERATOR_FAILED.value:
        return Outcome.FAILED_RETRYABLE, ErrorClass.UNAVAILABLE
    if status == GenStatus.REJECTED_BY_VERIFICATION.value:
        return Outcome.REFUSED, ErrorClass.EVIDENCE_INVALID
    return Outcome.FAILED_PERMANENT, ErrorClass.UNCLASSIFIED
