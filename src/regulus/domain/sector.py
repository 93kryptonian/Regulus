from pydantic import Field

from .base import Model


class Sector(Model):
    code: str = Field(min_length=1)
    label: str = Field(min_length=1)
