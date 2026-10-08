from collections.abc import Mapping
from typing import Protocol

from .models import MatchKind, MatchResult, PredictedObligation, ReferenceObligation
from .normalize import norm


class Matcher(Protocol):
    version: str

    def match(
        self,
        predicted: PredictedObligation,
        candidates: tuple[ReferenceObligation, ...],
        articles: Mapping[str, frozenset[int]],
    ) -> MatchResult: ...


class BaselineMatcher:
    version = "baseline-1"

    def match(
        self,
        predicted: PredictedObligation,
        candidates: tuple[ReferenceObligation, ...],
        articles: Mapping[str, frozenset[int]],
    ) -> MatchResult:
        text = norm(predicted.text)
        exact = sorted(
            (o for o in candidates if o.normalized_text == text), key=lambda o: o.ordinal
        )
        if exact:
            ids = tuple(o.obligation_id for o in exact)
            return MatchResult(
                kind=MatchKind.EXACT_NORMALIZED, matched=ids, matcher_version=self.version
            )
        mine = frozenset(predicted.articles)
        near = tuple(
            sorted(
                o.obligation_id
                for o in candidates
                if mine & articles.get(o.obligation_id, frozenset())
            )
        )
        kind = MatchKind.ARTICLE_OVERLAP if near else MatchKind.NONE
        return MatchResult(kind=kind, overlapping=near, matcher_version=self.version)


BASELINE = BaselineMatcher()
