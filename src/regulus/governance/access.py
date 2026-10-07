import json
from enum import StrEnum
from pathlib import Path

from regulus.domain.base import Model


class Operation(StrEnum):
    READ_QUEUE = "READ_QUEUE"
    READ_TASK = "READ_TASK"
    READ_HISTORY = "READ_HISTORY"
    READ_ACCESS_AUDIT = "READ_ACCESS_AUDIT"
    READ_EVALUATION = "READ_EVALUATION"
    CLAIM = "CLAIM"
    EDIT = "EDIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    PUBLISH = "PUBLISH"
    ASSIGN = "ASSIGN"
    RESCHEDULE = "RESCHEDULE"
    REQUEUE = "REQUEUE"
    PURGE = "PURGE"
    HOLD = "HOLD"
    RELEASE_HOLD = "RELEASE_HOLD"
    BASELINE_UPDATE = "BASELINE_UPDATE"
    ERASE_IDENTITY = "ERASE_IDENTITY"
    SUBMIT = "SUBMIT"
    RUN_PIPELINE = "RUN_PIPELINE"
    TICK = "TICK"


ROLES = ("REVIEWER", "PUBLISHER", "AUDITOR", "COORDINATOR", "OPERATOR", "SYSTEM")
RESOURCE_OPS = {
    Operation.READ_QUEUE,
    Operation.READ_TASK,
    Operation.READ_HISTORY,
    Operation.CLAIM,
    Operation.EDIT,
    Operation.APPROVE,
    Operation.REJECT,
    Operation.PUBLISH,
}
WRITES = {Operation.CLAIM, Operation.EDIT, Operation.APPROVE, Operation.REJECT, Operation.PUBLISH, Operation.ASSIGN, Operation.RESCHEDULE, Operation.REQUEUE,
          Operation.PURGE, Operation.HOLD, Operation.RELEASE_HOLD, Operation.BASELINE_UPDATE, Operation.ERASE_IDENTITY, Operation.SUBMIT,
          Operation.RUN_PIPELINE, Operation.TICK}  # fmt: skip
REVIEW_OPS = {
    Operation.CLAIM,
    Operation.EDIT,
    Operation.APPROVE,
    Operation.REJECT,
    Operation.PUBLISH,
}


class Matrix(Model):
    allow: dict[str, tuple[str, ...]]

    def roles_for(self, op: str) -> tuple[str, ...]:
        return self.allow.get(op, ())


def load_matrix(path: Path) -> Matrix:
    return Matrix.model_validate(json.loads(path.read_text(encoding="utf-8")))


class Facts(Model):
    task_id: str
    status: str
    terminal: bool
    participants: tuple[str, ...] = ()


class Decision(Model):
    allowed: bool
    reason: str


def authorize(
    matrix: Matrix, actor_id: str, roles: set[str], op: str, facts: Facts | None = None
) -> Decision:
    try:
        operation = Operation(op)
    except ValueError:
        return Decision(allowed=False, reason="UNLISTED_OPERATION")
    permitted = set(matrix.roles_for(operation.value))
    if not permitted:
        return Decision(allowed=False, reason="UNLISTED_OPERATION")
    held = roles & permitted
    if not held:
        return Decision(allowed=False, reason="ROLE")
    if operation not in RESOURCE_OPS:
        return Decision(allowed=True, reason="OK")
    if facts is None:
        return Decision(allowed=False, reason="NO_RESOURCE")
    return _resource_rule(held, actor_id, facts)


def _resource_rule(held: set[str], actor_id: str, f: Facts) -> Decision:
    if "AUDITOR" in held:
        return Decision(allowed=True, reason="OK")
    mine = actor_id in f.participants
    if "REVIEWER" in held and (not f.terminal or mine):
        return Decision(allowed=True, reason="OK")
    if "PUBLISHER" in held and (f.status == "APPROVED" or (f.terminal and mine)):
        return Decision(allowed=True, reason="OK")
    return Decision(allowed=False, reason="RESOURCE")
