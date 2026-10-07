from typing import Self

from pydantic import Field, model_validator

from .base import Model
from .enums import OwnerKind


class ObligationEvidence(Model):
    obligation_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_kind: OwnerKind
    span: tuple[int, int]
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _span(self) -> Self:
        s, e = self.span
        if s < 0 or e <= s or e - s != len(self.quote):
            raise ValueError("invalid span")
        return self

    def matches(self, owner_id: str, owner_text: str) -> bool:
        s, e = self.span
        return owner_id == self.owner_id and e <= len(owner_text) and owner_text[s:e] == self.quote
