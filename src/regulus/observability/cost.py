import re
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from regulus.domain.base import Model

NAME = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")


class CallKind(StrEnum):
    GENERATE = "GENERATE"
    CLASSIFY = "CLASSIFY"
    EMBED = "EMBED"


class Source(StrEnum):
    REPORTED = "REPORTED"
    ESTIMATED = "ESTIMATED"


class UsageRecord(Model):
    run_id: str
    span_id: str
    provider: str
    model: str
    kind: CallKind
    input_tokens: int
    output_tokens: int
    source: Source = Source.REPORTED
    latency_ms: int = 0

    @model_validator(mode="after")
    def _rules(self) -> Self:
        for v in (self.run_id, self.span_id, self.provider, self.model):
            if not NAME.match(v):
                raise ValueError("name outside the permitted grammar")
        if min(self.input_tokens, self.output_tokens, self.latency_ms) < 0:
            raise ValueError("usage values are non-negative")
        return self


class Price(Model):
    input_micro_per_mtok: int
    output_micro_per_mtok: int


class PriceTable(Model):
    version: str
    currency: str
    entries: dict[str, Price] = {}


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def cost_micro(u: UsageRecord, table: PriceTable) -> int | None:
    p = table.entries.get(u.model)
    if p is None:
        return None
    return _ceil_div(u.input_tokens * p.input_micro_per_mtok, 1_000_000) + _ceil_div(
        u.output_tokens * p.output_micro_per_mtok, 1_000_000
    )


class Totals(Model):
    calls: int = 0
    priced_calls: int = 0
    unpriced_calls: int = 0
    estimated_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micro: int = 0
    estimated_cost_micro: int = 0


class CostLedger:
    def __init__(self, table: PriceTable) -> None:
        self.table = table
        self.records: list[UsageRecord] = []

    def add(self, u: UsageRecord) -> int | None:
        self.records.append(u)
        return cost_micro(u, self.table)

    def totals(self, run_id: str | None = None, model: str | None = None) -> Totals:
        t = Totals()
        for u in self.records:
            if (run_id and u.run_id != run_id) or (model and u.model != model):
                continue
            c = cost_micro(u, self.table)
            est = u.source is Source.ESTIMATED
            t = t.model_copy(update={
                "calls": t.calls + 1,
                "priced_calls": t.priced_calls + (c is not None),
                "unpriced_calls": t.unpriced_calls + (c is None),
                "estimated_calls": t.estimated_calls + est,
                "input_tokens": t.input_tokens + u.input_tokens,
                "output_tokens": t.output_tokens + u.output_tokens,
                "cost_micro": t.cost_micro + (c or 0 if not est else 0),
                "estimated_cost_micro": t.estimated_cost_micro + (c or 0 if est else 0),
            })  # fmt: skip
        return t

    def summary(self) -> str:
        t = self.totals()
        if t.calls == 0:
            return "0 AI calls"
        return f"{t.calls} AI calls, {t.unpriced_calls} unpriced, {t.estimated_calls} estimated"
