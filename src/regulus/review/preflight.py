from collections.abc import Mapping
from datetime import datetime

from regulus.domain.base import Model

from .authorize import ReviewConfig, authorize
from .gates import Gate, approval_items, claim_held, refusals, verified_evidence
from .log import obligation_version
from .models import Action, ActionRequest, Actor, ReviewTask
from .store import ReviewStore


class ActionVerdict(Model):
    available: bool
    reasons: tuple[str, ...] = ()


class Preflight(Model):
    actions: dict[Action, ActionVerdict]
    gates: tuple[Gate, ...]


def preflight(
    store: ReviewStore,
    task: ReviewTask,
    actor: Actor,
    now: datetime,
    cfg: ReviewConfig | None = None,
    owner_texts: Mapping[str, str] | None = None,
) -> Preflight:
    cfg = cfg or ReviewConfig()
    owner_texts = owner_texts or {}
    ob, log = store.get(task.obligation_id)
    version = obligation_version(ob, len(log))
    actions: dict[Action, ActionVerdict] = {}
    for action in Action:
        req = ActionRequest(
            action=action, task_id=task.id, base_version=version, actor=actor, at=now
        )
        reasons = tuple(
            r for f in refusals(task, req, ob, log, version, cfg, owner_texts) for r in f.reasons
        )
        actions[action] = ActionVerdict(available=not reasons, reasons=reasons)
    bare = ActionRequest(
        action=Action.APPROVE, task_id=task.id, base_version=version, actor=actor, at=now
    )
    auth = authorize(actor, Action.APPROVE, log, cfg)
    gates = [
        Gate(id="EVIDENCE", ok=bool(verified_evidence(task.snapshot, ob, owner_texts))),
        Gate(id="CLAIM", ok=claim_held(task, actor.id, now)),
        Gate(id="AUTHORIZATION", ok=auth.allowed, detail=auth.reason),
        *approval_items(task, log, bare),
    ]
    return Preflight(actions=actions, gates=tuple(gates))
