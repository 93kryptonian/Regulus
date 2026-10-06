from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from .base import Model
from .enums import ObligationStatus, Origin


class ObligationContent(Model):
    text: str = Field(min_length=1)
    actor: str | None = None
    action: str | None = None
    object: str | None = None
    condition: str | None = None
    deadline: str | None = None
    frequency: str | None = None
    exception: str | None = None


class GenerationMetadata(Model):
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    generated_at: AwareDatetime


class Generated(Model):
    content: ObligationContent
    meta: GenerationMetadata | None = None


class Obligation(Model):
    id: str = Field(min_length=1)
    article_id: str = Field(min_length=1)
    status: ObligationStatus = ObligationStatus.GENERATED
    origin: Origin
    sectors: tuple[str, ...] = ()
    generated: Generated
    current: ObligationContent

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.origin is Origin.AI and self.generated.meta is None:
            raise ValueError("AI origin requires generation metadata")
        if self.status is ObligationStatus.GENERATED and self.current != self.generated.content:
            raise ValueError("GENERATED obligation must have current == generated.content")
        if len(set(self.sectors)) != len(self.sectors):
            raise ValueError("duplicate sectors")
        return self
