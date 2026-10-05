from typing import Self

from pydantic import Field, model_validator

from .article import Article
from .base import Model


class ObligationEvidence(Model):
    obligation_id: str = Field(min_length=1)
    article_id: str = Field(min_length=1)
    span: tuple[int, int]
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def _span(self) -> Self:
        s, e = self.span
        if s < 0 or e <= s or e - s != len(self.quote):
            raise ValueError("invalid span")
        return self

    def matches(self, article: Article) -> bool:
        s, e = self.span
        return (
            article.id == self.article_id
            and e <= len(article.text)
            and article.text[s:e] == self.quote
        )
