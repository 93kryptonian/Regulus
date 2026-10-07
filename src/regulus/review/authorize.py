from collections.abc import Sequence

from pydantic import Field

from regulus.domain import ObligationStatus
from regulus.domain.base import Model

from .models import Action, Actor, ReviewRecord, Role


class ReviewConfig(Model):
    four_eyes: bool = True
    claim_ttl_seconds: int = Field(default=900, gt=0)


class Authorization(Model):
    allowed: bool
    reason: str | None = None


def _last_actor(records: Sequence[ReviewRecord], to: ObligationStatus) -> str | None:
    for r in reversed(records):
        if r.decision.to_status is to:
            return r.actor_id
    return None


def authorize(
    actor: Actor, action: Action, records: Sequence[ReviewRecord], cfg: ReviewConfig
) -> Authorization:
    needed = Role.PUBLISHER if action is Action.PUBLISH else Role.REVIEWER
    if needed not in actor.roles:
        return Authorization(allowed=False, reason="ROLE")
    if cfg.four_eyes:
        if action is Action.APPROVE and _last_actor(records, ObligationStatus.EDITED) == actor.id:
            return Authorization(allowed=False, reason="FOUR_EYES")
        if action is Action.PUBLISH and _last_actor(records, ObligationStatus.APPROVED) == actor.id:
            return Authorization(allowed=False, reason="FOUR_EYES")
    return Authorization(allowed=True)
