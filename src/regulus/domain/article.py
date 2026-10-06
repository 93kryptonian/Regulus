import hashlib
from typing import Self

from pydantic import Field, model_validator

from .base import Model


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Article(Model):
    id: str = Field(min_length=1)
    regulation_id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    parent: str | None = None
    text: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    text_hash: str

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("page_end < page_start")
        if self.text_hash != text_hash(self.text):
            raise ValueError("text_hash mismatch")
        return self

    @classmethod
    def of(
        cls,
        regulation_id: str,
        number: str,
        text: str,
        page_start: int,
        page_end: int,
        parent: str | None = None,
    ) -> Self:
        t = text
        return cls(
            id=f"{regulation_id}:{number}",
            regulation_id=regulation_id,
            number=number,
            parent=parent,
            text=t,
            page_start=page_start,
            page_end=page_end,
            text_hash=text_hash(t),
        )
