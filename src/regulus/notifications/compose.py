import re

from .models import Message, NotificationClass, NotificationEvent, NotificationKind

ID = re.compile(r"^[A-Za-z0-9:_.\-]{1,96}$")
K = NotificationKind
ALLOWED: dict[NotificationKind, dict[str, type]] = {
    K.REGULATION_DETECTED: {"regulation_id": str, "event_id": str},
    K.AMENDMENT_DETECTED: {"regulation_id": str, "target_id": str, "event_id": str},
    K.OBLIGATIONS_READY: {
        "event_id": str,
        "potential_obligations": int,
        "similarity_candidates": int,
    },
    K.TASK_ASSIGNED: {"task_id": str, "assignee": str},
    K.TASK_DUE_SOON: {"task_id": str, "due_at": str},
    K.TASK_OVERDUE: {"task_id": str, "due_at": str},
    K.SOURCE_CHANGED: {"task_id": str, "obligation_id": str},
    K.SOURCE_WITHDRAWN: {"task_id": str, "obligation_id": str},
    K.REVIEW_DECIDED: {"obligation_id": str, "status": str, "record_hash": str},
    K.PIPELINE_STAGE_FAILED: {"run_id": str, "stage": str, "error_class": str},
    K.DEAD_LETTER: {"run_id": str, "stage": str, "error_class": str},
}
TITLES = {
    K.REGULATION_DETECTED: "Regulation detected",
    K.AMENDMENT_DETECTED: "Amendment detected",
    K.OBLIGATIONS_READY: "Potential obligations ready for review (unreviewed, AI-enriched)",
    K.TASK_ASSIGNED: "Review task routed to you",
    K.TASK_DUE_SOON: "Review task due soon",
    K.TASK_OVERDUE: "Review task overdue",
    K.SOURCE_CHANGED: "Source changed for an open review task",
    K.SOURCE_WITHDRAWN: "Source withdrawn for an open review task",
    K.REVIEW_DECIDED: "Review decision recorded",
    K.PIPELINE_STAGE_FAILED: "Pipeline stage failed",
    K.DEAD_LETTER: "Work item needs operator attention",
}
BODIES = {
    K.REGULATION_DETECTED: "Regulation {regulation_id} was detected (event {event_id}).",
    K.AMENDMENT_DETECTED: "Regulation {target_id} is changed by {regulation_id} (event {event_id}).",
    K.OBLIGATIONS_READY: "Event {event_id}: {potential_obligations} potential obligation(s) and {similarity_candidates} similarity candidate(s) are unreviewed and await human review.",
    K.TASK_ASSIGNED: "Task {task_id} is routed to {assignee} as a routing hint only.",
    K.TASK_DUE_SOON: "Task {task_id} is due at {due_at}.",
    K.TASK_OVERDUE: "Task {task_id} passed its due time {due_at}.",
    K.SOURCE_CHANGED: "The source of obligation {obligation_id} (task {task_id}) changed after extraction.",
    K.SOURCE_WITHDRAWN: "The source of obligation {obligation_id} (task {task_id}) was withdrawn.",
    K.REVIEW_DECIDED: "Obligation {obligation_id} recorded status {status} (record {record_hash}).",
    K.PIPELINE_STAGE_FAILED: "Run {run_id}: stage {stage} failed ({error_class}).",
    K.DEAD_LETTER: "Run {run_id}: stage {stage} exhausted retries ({error_class}).",
}
AUTHORITY = re.compile(
    r"\b(approved?|approval|compliant|compliance|required|valid|validated|disetujui|patuh|sah)\b",
    re.IGNORECASE,
)
HEDGE = re.compile(r"\b(potential|candidate|unreviewed)\b", re.IGNORECASE)
LINK_KINDS = {
    K.TASK_ASSIGNED,
    K.TASK_DUE_SOON,
    K.TASK_OVERDUE,
    K.SOURCE_CHANGED,
    K.SOURCE_WITHDRAWN,
}


class MessageRejected(ValueError):
    pass


def compose(event: NotificationEvent) -> Message:
    spec = ALLOWED[event.kind]
    if set(event.payload) != set(spec):
        raise MessageRejected(f"payload keys for {event.kind.value}")
    for name, typ in spec.items():
        v = event.payload[name]
        if type(v) is not typ or (typ is str and not ID.match(str(v)) and name != "due_at"):
            raise MessageRejected(f"payload field {name}")
        if name == "due_at" and not re.match(r"^[0-9T:\-+.Z]{10,40}$", str(v)):
            raise MessageRejected("payload field due_at")
    msg = Message(
        cls=event.cls,
        title=TITLES[event.kind],
        body=BODIES[event.kind].format(**event.payload),
        link=f"/tasks/{event.payload['task_id']}" if event.kind in LINK_KINDS else None,
    )
    check_message(msg, event.kind)
    return msg


def check_message(msg: Message, kind: NotificationKind) -> None:
    text = f"{msg.title} {msg.body}"
    if kind is not NotificationKind.REVIEW_DECIDED and AUTHORITY.search(text):
        raise MessageRejected("authority language outside REVIEW_DECIDED")
    if msg.cls is NotificationClass.AI_ENRICHED and not HEDGE.search(text):
        raise MessageRejected("AI-enriched message must say potential, candidate or unreviewed")
    if msg.cls is NotificationClass.DETERMINISTIC and kind is NotificationKind.OBLIGATIONS_READY:
        raise MessageRejected("class mismatch")
    if re.search(r"@|https?://|token|secret|password", text, re.IGNORECASE):
        raise MessageRejected("forbidden content")
