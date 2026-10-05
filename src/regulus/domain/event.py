from datetime import date
from typing import Self

from pydantic import Field, model_validator

from .base import Model
from .enums import EventType

NEEDS_TARGET = {EventType.AMEND, EventType.REPEAL, EventType.PARTIAL_REPEAL}


class RegulatoryEvent(Model):
    id: str = Field(min_length=1)
    type: EventType
    regulation_id: str = Field(min_length=1)
    target_id: str | None = None
    occurred_on: date
    detected_on: date
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def _target_rules(self) -> Self:
        if self.type in NEEDS_TARGET and not self.target_id:
            raise ValueError(f"{self.type} requires target_id")
        if self.type is EventType.NEW and self.target_id:
            raise ValueError("NEW forbids target_id")
        if self.target_id == self.regulation_id:
            raise ValueError("target_id must differ from regulation_id")
        return self
