from collections.abc import Sequence
from typing import Protocol

from .models import DeliveryResult, Message, NotificationEvent


class Notifier(Protocol):
    def send(
        self, message: Message, recipients: Sequence[str], idempotency_key: str
    ) -> DeliveryResult: ...


class Recipients(Protocol):
    def resolve(self, event: NotificationEvent) -> Sequence[str]: ...
