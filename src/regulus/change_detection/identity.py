import hashlib
from collections.abc import Iterable

from regulus.domain import EventType, ReviewReason

from .matcher import norm_text
from .models import Action


def _h(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def event_id(
    type: EventType, regulation_id: str, target_id: str | None = None, discriminator: str = ""
) -> str:
    return "evt-" + _h(type, regulation_id, target_id or "", discriminator)[:16]


def target_discriminator(reason: ReviewReason, action: Action, raw: str) -> str:
    return f"{reason}:{action}:{norm_text(raw)}"


def conflict_discriminator(reason: ReviewReason, items: Iterable[str]) -> str:
    return f"{reason}:{_h(*sorted(items))}"
