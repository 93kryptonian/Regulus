from datetime import date
from typing import Self

from pydantic import Field, HttpUrl, model_validator

from .base import Model
from .enums import RegulationKind, RegulationStatus


def regulation_id(kind: RegulationKind, number: str, year: int) -> str:
    return f"{kind}-{number}-{year}".replace("/", "_").replace(" ", "")


class Regulation(Model):
    id: str
    kind: RegulationKind
    number: str = Field(min_length=1)
    year: int = Field(ge=1945, le=2100)
    title: str = Field(min_length=1)
    issuer: str | None = None
    enacted_on: date | None = None
    promulgated_on: date | None = None
    source_url: HttpUrl | None = None
    status: RegulationStatus = RegulationStatus.UNKNOWN

    @model_validator(mode="after")
    def _id_is_derived(self) -> Self:
        if self.id != regulation_id(self.kind, self.number, self.year):
            raise ValueError("id must derive from (kind, number, year)")
        return self

    @classmethod
    def of(cls, kind: RegulationKind, number: str, year: int, **kw: object) -> Self:
        return cls(id=regulation_id(kind, number, year), kind=kind, number=number, year=year, **kw)
