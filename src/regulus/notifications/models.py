import hashlib
from enum import StrEnum

from regulus.domain.base import Model


class NotificationClass(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    AI_ENRICHED = "AI_ENRICHED"


class NotificationKind(StrEnum):
    REGULATION_DETECTED = "REGULATION_DETECTED"
    AMENDMENT_DETECTED = "AMENDMENT_DETECTED"
    OBLIGATIONS_READY = "OBLIGATIONS_READY"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_DUE_SOON = "TASK_DUE_SOON"
    TASK_OVERDUE = "TASK_OVERDUE"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    SOURCE_WITHDRAWN = "SOURCE_WITHDRAWN"
    REVIEW_DECIDED = "REVIEW_DECIDED"
    PIPELINE_STAGE_FAILED = "PIPELINE_STAGE_FAILED"
    DEAD_LETTER = "DEAD_LETTER"


CLASS_OF = {
    NotificationKind.OBLIGATIONS_READY: NotificationClass.AI_ENRICHED,
}


class NotificationEvent(Model):
    kind: NotificationKind
    subject: str
    version: str
    payload: dict[str, str | int] = {}

    @property
    def cls(self) -> NotificationClass:
        return CLASS_OF.get(self.kind, NotificationClass.DETERMINISTIC)

    @property
    def dedupe_key(self) -> str:
        return (
            "ntf-"
            + hashlib.sha256(
                f"{self.kind.value}|{self.subject}|{self.version}".encode()
            ).hexdigest()[:24]
        )


class Message(Model):
    cls: NotificationClass
    title: str
    body: str
    link: str | None = None


class DeliveryStatus(StrEnum):
    SENT = "SENT"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"


class DeliveryResult(Model):
    status: DeliveryStatus
    error_class: str | None = None
