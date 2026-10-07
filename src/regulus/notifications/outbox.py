from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from regulus.domain.base import Model
from regulus.review import StoreError
from regulus.workflow import (
    ClockRegression,
    Kind,
    Principal,
    ScheduleConfig,
    WorkflowRecord,
    WorkflowRole,
    WorkflowStore,
    next_attempt_at,
)

from .compose import compose
from .models import DeliveryStatus, Message, NotificationEvent
from .ports import Notifier, Recipients

ALLOWED = {WorkflowRole.SYSTEM, WorkflowRole.OPERATOR}
PREFIX = "notification:"


class State(StrEnum):
    QUEUED = "QUEUED"
    RETRYING = "RETRYING"
    DELIVERED = "DELIVERED"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    DEAD_LETTER = "DEAD_LETTER"


TERMINAL = {State.DELIVERED, State.FAILED_PERMANENT, State.DEAD_LETTER}


class NotificationState(Model):
    key: str
    state: State
    attempts: int = 0
    next_attempt_at: datetime | None = None
    recipients: tuple[str, ...] = ()
    message: Message | None = None
    error_class: str | None = None
    reroute_of: str | None = None
    window_start: int = 0
    requeues: int = 0


class QueueStatus(StrEnum):
    QUEUED = "QUEUED"
    DUPLICATE = "DUPLICATE"
    NO_RECIPIENT = "NO_RECIPIENT"
    REJECTED = "REJECTED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class QueueOutcome(Model):
    status: QueueStatus
    key: str | None = None
    reasons: tuple[str, ...] = ()


class Delivery(Model):
    key: str
    state: State
    unrecorded: bool = False


def stream_of(key: str) -> str:
    return PREFIX + key


def project(key: str, records: Sequence[WorkflowRecord]) -> NotificationState | None:
    st: NotificationState | None = None
    for r in records:
        d = r.details
        if r.kind is Kind.NOTIFICATION_QUEUED:
            st = NotificationState(
                key=key,
                state=State.QUEUED,
                next_attempt_at=r.at,
                recipients=tuple(d["recipients"]),
                message=Message.model_validate(d["message"]),
                reroute_of=d.get("reroute_of"),
            )
        elif st is None:
            continue
        elif r.kind is Kind.NOTIFICATION_DELIVERED:
            st = st.model_copy(
                update={"state": State.DELIVERED, "attempts": d["attempt"], "next_attempt_at": None}
            )
        elif r.kind is Kind.NOTIFICATION_FAILED:
            nxt = d.get("next_attempt_at")
            st = st.model_copy(
                update={
                    "state": State.RETRYING if d["retryable"] else State.FAILED_PERMANENT,
                    "attempts": d["attempt"],
                    "error_class": d["error_class"],
                    "next_attempt_at": datetime.fromisoformat(nxt) if nxt else None,
                }
            )
        elif r.kind is Kind.NOTIFICATION_REQUEUED:
            st = st.model_copy(
                update={
                    "state": State.QUEUED,
                    "next_attempt_at": r.at,
                    "window_start": st.attempts,
                    "requeues": st.requeues + 1,
                }
            )
        elif r.kind is Kind.NOTIFICATION_DEAD_LETTER:
            st = st.model_copy(
                update={
                    "state": State.DEAD_LETTER,
                    "attempts": d["attempt"],
                    "next_attempt_at": None,
                }
            )
    return st


def notification_state(store: WorkflowStore, key: str) -> NotificationState | None:
    return project(key, store.ledger(stream_of(key)))


def queue_notification(
    store: WorkflowStore,
    event: NotificationEvent,
    recipients: Recipients,
    principal: Principal,
    now: datetime,
    reroute_of: str | None = None,
    reason: str | None = None,
) -> QueueOutcome:
    if not ALLOWED & set(principal.roles):
        return QueueOutcome(status=QueueStatus.DENIED, reasons=("ROLE",))
    key = event.dedupe_key
    if store.ledger(stream_of(key)):
        return QueueOutcome(status=QueueStatus.DUPLICATE, key=key)
    try:
        message = compose(event)
    except ValueError as e:
        return QueueOutcome(status=QueueStatus.REJECTED, reasons=(str(e),))
    resolved = tuple(sorted(dict.fromkeys(recipients.resolve(event))))
    details: dict[str, Any] = {
        "event": event.model_dump(mode="json"),
        "recipients": list(resolved),
        "message": message.model_dump(mode="json"),
    }
    if reroute_of:
        details.update(reroute_of=reroute_of, reason=reason)
    try:
        store.append(stream_of(key), Kind.NOTIFICATION_QUEUED, principal, now, key, details)
        if not resolved:
            store.append(
                stream_of(key), Kind.NOTIFICATION_FAILED, principal, now, key,
                {"attempt": 0, "retryable": False, "error_class": "NO_RECIPIENT"},
            )  # fmt: skip
            return QueueOutcome(status=QueueStatus.NO_RECIPIENT, key=key)
    except (StoreError, ClockRegression) as e:
        return QueueOutcome(status=QueueStatus.FAILED, key=key, reasons=(type(e).__name__,))
    return QueueOutcome(status=QueueStatus.QUEUED, key=key)


def reroute(
    store: WorkflowStore,
    original_key: str,
    event: NotificationEvent,
    recipients: Recipients,
    reason: str,
    principal: Principal,
    now: datetime,
) -> QueueOutcome:
    if not reason or not store.ledger(stream_of(original_key)):
        return QueueOutcome(status=QueueStatus.REJECTED, reasons=("REASON_AND_ORIGINAL_REQUIRED",))
    return queue_notification(store, event, recipients, principal, now, original_key, reason)


def deliver_due(
    store: WorkflowStore,
    notifier: Notifier,
    principal: Principal,
    now: datetime,
    cfg: ScheduleConfig | None = None,
) -> list[Delivery]:
    cfg = cfg or ScheduleConfig()
    out: list[Delivery] = []
    for stream in store.streams_with(PREFIX):
        key = stream[len(PREFIX) :]
        st = project(key, store.ledger(stream))
        if st is None or st.state in TERMINAL or st.message is None:
            continue
        if st.next_attempt_at is not None and st.next_attempt_at > now:
            continue
        attempt = st.attempts + 1
        try:
            result = notifier.send(st.message, st.recipients, key)
            status, err = result.status, result.error_class
        except Exception as e:
            status, err = DeliveryStatus.FAILED_RETRYABLE, type(e).__name__
        try:
            if status is DeliveryStatus.SENT:
                store.append(
                    stream, Kind.NOTIFICATION_DELIVERED, principal, now, key, {"attempt": attempt}
                )
            elif status is DeliveryStatus.FAILED_PERMANENT:
                store.append(
                    stream, Kind.NOTIFICATION_FAILED, principal, now, key,
                    {"attempt": attempt, "retryable": False, "error_class": err or "PERMANENT"},
                )  # fmt: skip
            else:
                nxt = next_attempt_at(now, st.attempts - st.window_start, cfg)
                if nxt is None:
                    store.append(
                        stream, Kind.NOTIFICATION_DEAD_LETTER, principal, now, key,
                        {"attempt": attempt, "error_class": err or "RETRYABLE"},
                    )  # fmt: skip
                else:
                    store.append(
                        stream, Kind.NOTIFICATION_FAILED, principal, now, key,
                        {"attempt": attempt, "retryable": True, "error_class": err or "RETRYABLE",
                         "next_attempt_at": nxt.isoformat()},
                    )  # fmt: skip
        except (StoreError, ClockRegression):
            out.append(Delivery(key=key, state=st.state, unrecorded=True))
            continue
        after = project(key, store.ledger(stream))
        out.append(Delivery(key=key, state=after.state if after else st.state))
    return out


class RequeueStatus(StrEnum):
    REQUEUED = "REQUEUED"
    DENIED = "DENIED"
    NOT_DEAD_LETTERED = "NOT_DEAD_LETTERED"
    UNKNOWN = "UNKNOWN"
    REASON_REQUIRED = "REASON_REQUIRED"
    FAILED = "FAILED"


def requeue_notification(
    store: WorkflowStore, key: str, principal: Principal, reason: str, now: datetime
) -> RequeueStatus:
    if WorkflowRole.OPERATOR not in principal.roles:
        return RequeueStatus.DENIED
    if not reason.strip():
        return RequeueStatus.REASON_REQUIRED
    st = notification_state(store, key)
    if st is None:
        return RequeueStatus.UNKNOWN
    if st.state is not State.DEAD_LETTER:
        return RequeueStatus.NOT_DEAD_LETTERED
    try:
        store.append(
            stream_of(key), Kind.NOTIFICATION_REQUEUED, principal, now, key,
            {"reason": reason, "by": principal.id, "attempt_window": st.requeues + 1},
        )  # fmt: skip
    except (StoreError, ClockRegression):
        return RequeueStatus.FAILED
    return RequeueStatus.REQUEUED
