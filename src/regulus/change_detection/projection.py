from collections.abc import Iterable

from regulus.domain import EventType, RegulationStatus, RegulatoryEvent
from regulus.domain.base import Model

ACTING = {EventType.AMEND, EventType.REPEAL, EventType.PARTIAL_REPEAL}


class StatusProjection(Model):
    status: RegulationStatus
    anomalies: tuple[str, ...] = ()


def project_status(regulation_id: str, events: Iterable[RegulatoryEvent]) -> StatusProjection:
    own_new = False
    acts = []
    for e in events:
        if e.type is EventType.NEW and e.regulation_id == regulation_id:
            own_new = True
        elif e.type in ACTING and e.target_id == regulation_id:
            acts.append(e)
    repeals = [e.occurred_on for e in acts if e.type is EventType.REPEAL]
    if repeals:
        cutoff = min(repeals)
        late = sorted(
            (e for e in acts if e.occurred_on > cutoff), key=lambda e: (e.occurred_on, e.id)
        )
        return StatusProjection(
            status=RegulationStatus.REPEALED, anomalies=tuple(e.id for e in late)
        )
    if acts:
        return StatusProjection(status=RegulationStatus.AMENDED)
    return StatusProjection(
        status=RegulationStatus.IN_FORCE if own_new else RegulationStatus.UNKNOWN
    )
