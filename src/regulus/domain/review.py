from collections.abc import Sequence
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from .base import Model
from .enums import ObligationStatus as S
from .evidence import ObligationEvidence
from .obligation import Obligation, ObligationContent

TRANSITIONS: dict[S, frozenset[S]] = {
    S.GENERATED: frozenset(),
    S.PENDING_REVIEW: frozenset({S.APPROVED, S.REJECTED, S.EDITED}),
    S.EDITED: frozenset({S.PENDING_REVIEW}),
    S.APPROVED: frozenset({S.PUBLISHED}),
    S.REJECTED: frozenset(),
    S.PUBLISHED: frozenset(),
}


class TransitionError(ValueError):
    pass


class FieldChange(Model):
    field: str
    before: str | None
    after: str | None

    @model_validator(mode="after")
    def _valid(self) -> Self:
        if self.field not in ObligationContent.model_fields:
            raise ValueError(f"unknown field {self.field}")
        if self.before == self.after:
            raise ValueError("no-op change")
        return self


class ReviewDecision(Model):
    id: str = Field(min_length=1)
    obligation_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    at: AwareDatetime
    from_status: S
    to_status: S
    reason: str | None = None
    changes: tuple[FieldChange, ...] = ()

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.to_status not in TRANSITIONS[self.from_status]:
            raise ValueError(f"illegal transition {self.from_status} -> {self.to_status}")
        if self.to_status in (S.REJECTED, S.EDITED) and not self.reason:
            raise ValueError("reason required")
        if (self.to_status is S.EDITED) != bool(self.changes):
            raise ValueError("changes required iff EDITED")
        return self


def apply_decision(
    obligation: Obligation, decision: ReviewDecision, evidence: Sequence[ObligationEvidence]
) -> Obligation:
    if decision.obligation_id != obligation.id:
        raise TransitionError("decision targets another obligation")
    if decision.from_status != obligation.status:
        raise TransitionError("stale decision")
    if decision.to_status is S.APPROVED and not any(
        e.obligation_id == obligation.id and e.article_id == obligation.article_id for e in evidence
    ):
        raise TransitionError("approval requires evidence")
    current = obligation.current
    if decision.to_status is S.EDITED:
        data = current.model_dump()
        for c in decision.changes:
            if data[c.field] != c.before:
                raise TransitionError(f"stale edit on {c.field}")
            data[c.field] = c.after
        current = ObligationContent.model_validate(data)
    return obligation.model_copy(update={"status": decision.to_status, "current": current})


def submit(obligation: Obligation) -> Obligation:
    if obligation.status is not S.GENERATED:
        raise TransitionError("only GENERATED obligations can be submitted")
    return obligation.model_copy(update={"status": S.PENDING_REVIEW})
