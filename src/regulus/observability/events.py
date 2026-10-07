import hashlib
import re
from typing import Self

from pydantic import AwareDatetime, model_validator

from regulus.domain.base import Model

from .taxonomy import ATTR_KEYS, ATTR_VALUES, COUNT_KEYS, ErrorClass, Kind, Outcome, Stage

ID = re.compile(r"^[A-Za-z0-9:_.\-]{1,96}$")


def trace_id(run_id: str) -> str:
    return hashlib.sha256(run_id.encode()).hexdigest()[:16]


def span_id(trace: str, stage: Stage, item: str, attempt: int) -> str:
    return hashlib.sha256(f"{trace}|{stage.value}|{item}|{attempt}".encode()).hexdigest()[:12]


class ObsEvent(Model):
    seq: int
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    run_id: str
    item_id: str = ""
    stage: Stage
    kind: Kind
    outcome: Outcome | None = None
    error_class: ErrorClass | None = None
    attempt: int = 1
    started_at: AwareDatetime
    duration_ms: int | None = None
    counts: dict[str, int] = {}
    attrs: dict[str, str | bool | int] = {}

    @model_validator(mode="after")
    def _rules(self) -> Self:
        for name in (self.run_id, self.item_id):
            if name and not ID.match(name):
                raise ValueError("identifier outside the permitted grammar")
        if not set(self.counts) <= COUNT_KEYS:
            raise ValueError(
                f"count key outside the vocabulary: {sorted(set(self.counts) - COUNT_KEYS)}"
            )
        if not set(self.attrs) <= ATTR_KEYS:
            raise ValueError(
                f"attr key outside the vocabulary: {sorted(set(self.attrs) - ATTR_KEYS)}"
            )
        for k, v in self.attrs.items():
            if isinstance(v, str) and v not in ATTR_VALUES:
                raise ValueError(f"attr {k} value outside the closed set")
        if any(type(v) is not int or v < 0 for v in self.counts.values()):
            raise ValueError("counts are non-negative integers")
        if self.kind is Kind.SPAN_FINISHED:
            if self.outcome is None or self.duration_ms is None or self.duration_ms < 0:
                raise ValueError("a finished span needs an outcome and a non-negative duration")
        elif self.kind is Kind.SPAN_STARTED and (self.outcome or self.duration_ms is not None):
            raise ValueError("a started span has neither outcome nor duration")
        if self.outcome is not None and self.outcome is not Outcome.OK and self.error_class is None:
            raise ValueError("every non-OK outcome needs an error class")
        if self.outcome is Outcome.OK and self.error_class is not None:
            raise ValueError("an OK outcome has no error class")
        return self
