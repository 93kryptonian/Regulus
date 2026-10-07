from datetime import datetime

from regulus.workflow import Principal, WorkflowRole

from .chain import ChainLog, LogUnavailable


class IdentityMap:
    def __init__(self) -> None:
        self._m: dict[str, str] = {}
        self.available = True

    def register(self, opaque_id: str, person: str) -> None:
        self._m[opaque_id] = person

    def resolve(self, opaque_id: str) -> str | None:
        return self._m.get(opaque_id)

    def links(self) -> int:
        return len(self._m)


def erase_identity(
    idmap: IdentityMap, audit: ChainLog, operator: Principal, opaque_id: str, at: datetime
) -> str:
    operator_id = operator.id
    if WorkflowRole.OPERATOR not in operator.roles:
        return "DENIED"
    if not idmap.available:
        try:
            audit.append(
                "ACCESS_DENIED",
                at,
                operation="ERASE_IDENTITY",
                actor=operator_id,
                outcome="MAP_UNAVAILABLE",
            )
        except LogUnavailable:
            pass
        return "REFUSED"
    if opaque_id not in idmap._m:
        return "UNKNOWN"
    audit.append(
        "IDENTITY_ERASED",
        at,
        operation="ERASE_IDENTITY",
        actor=operator_id,
        resource=opaque_id,
        outcome="OK",
    )
    del idmap._m[opaque_id]
    return "ERASED"
