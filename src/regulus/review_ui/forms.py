from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import ValidationError

from regulus.domain import FieldChange
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    Disposition,
    MatchDisposition,
    OpenQuestionResolution,
    RejectCode,
    RejectReason,
    Resolution,
)

SINGLE = {
    "csrf", "action", "base_version", "snapshot_hash", "reason", "reject_code", "reject_text",
    "reject_match",
}  # fmt: skip
MULTI = {"ack"}
PREFIXES = ("res:", "note:", "disp:", "edit:", "before:")
ACTOR_KEYS = {"actor", "actor_id", "roles", "actor_roles", "reviewer"}


class FormError(Exception):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


def _one(post: Mapping[str, Sequence[str]], key: str) -> str | None:
    vals = post.get(key)
    return vals[0] if vals and vals[0] != "" else None


def _enum(cls, value: str, field: str):  # type: ignore[no-untyped-def]
    try:
        return cls(value)
    except ValueError:
        raise FormError(field, "not an allowed value") from None


def check_keys(post: Mapping[str, Sequence[str]]) -> None:
    for key, vals in post.items():
        if key in ACTOR_KEYS:
            raise FormError(key, "the actor is not accepted from the client")
        known = key in SINGLE or key in MULTI or key.startswith(PREFIXES)
        if not known:
            raise FormError(key, "unknown field")
        if key not in MULTI and len(vals) != 1:
            raise FormError(key, "duplicate field")


def parse_action(
    post: Mapping[str, Sequence[str]], task_id: str, actor: Actor, now: datetime
) -> ActionRequest:
    check_keys(post)
    action_raw, base = _one(post, "action"), _one(post, "base_version")
    if action_raw is None:
        raise FormError("action", "required")
    if base is None:
        raise FormError("base_version", "required")
    action = _enum(Action, action_raw, "action")
    try:
        resolutions = tuple(
            OpenQuestionResolution(
                question=k[4:],
                resolution=_enum(Resolution, v[0], k),
                note=_one(post, f"note:{k[4:]}") or "",
            )
            for k, v in post.items()
            if k.startswith("res:") and v[0] != ""
        )
        dispositions = tuple(
            MatchDisposition(match_id=k[5:], disposition=_enum(Disposition, v[0], k))
            for k, v in post.items()
            if k.startswith("disp:") and v[0] != ""
        )
        changes = []
        for k, v in post.items():
            if k.startswith("edit:"):
                name = k[5:]
                before = _one(post, f"before:{name}")
                if f"before:{name}" not in post:
                    raise FormError(k, "the previous value is required")
                after = v[0] or None
                if after != before:
                    changes.append(FieldChange(field=name, before=before, after=after))
        reject = None
        code = _one(post, "reject_code")
        if code is not None:
            reject = RejectReason(
                code=_enum(RejectCode, code, "reject_code"),
                text=_one(post, "reject_text"),
                match_id=_one(post, "reject_match"),
            )
        return ActionRequest(
            action=action,
            task_id=task_id,
            base_version=base,
            actor=actor,
            at=now,
            reason=_one(post, "reason"),
            changes=tuple(changes),
            reject_reason=reject,
            resolutions=resolutions,
            dispositions=dispositions,
            acknowledged_flags=tuple(post.get("ack", ())),
        )
    except ValidationError as ex:
        loc = ".".join(str(p) for p in ex.errors()[0]["loc"]) or "request"
        raise FormError(loc, ex.errors()[0]["msg"]) from None
    except ValueError as ex:
        raise FormError("request", str(ex)[:120]) from None
