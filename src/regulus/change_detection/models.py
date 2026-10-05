from datetime import date
from enum import StrEnum

from pydantic import Field

from regulus.domain import EventType, RegulationKind, RegulatoryEvent
from regulus.domain.base import Model


class Action(StrEnum):
    MENGUBAH = "MENGUBAH"
    MENCABUT = "MENCABUT"
    MENCABUT_SEBAGIAN = "MENCABUT_SEBAGIAN"


ACTION_EVENT = {
    Action.MENGUBAH: EventType.AMEND,
    Action.MENCABUT: EventType.REPEAL,
    Action.MENCABUT_SEBAGIAN: EventType.PARTIAL_REPEAL,
}


class TargetRef(Model):
    raw: str = Field(min_length=1)
    kind: RegulationKind | None = None
    number: str | None = None
    year: int | None = None


class DeclaredRelation(Model):
    action: Action
    target: TargetRef


class SourceRecord(Model):
    source_id: str = Field(min_length=1)
    kind: RegulationKind | None = None
    number: str | None = None
    year: int | None = None
    title: str | None = None
    promulgated_on: date | None = None
    enacted_on: date | None = None
    issuer: str | None = None
    relations: tuple[DeclaredRelation, ...] = ()


class Outcome(StrEnum):
    PROCESSED_OK = "PROCESSED_OK"
    PROCESSED_EMPTY = "PROCESSED_EMPTY"
    FAILED = "FAILED"


class Conflict(Model):
    field: str
    indexed: str | None
    incoming: str | None


class DetectionResult(Model):
    source_id: str
    outcome: Outcome
    events: tuple[RegulatoryEvent, ...] = ()
    duplicates: int = 0
    errors: tuple[str, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
