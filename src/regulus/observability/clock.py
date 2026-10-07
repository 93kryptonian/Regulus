from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def monotonic_ms(self) -> int: ...

    def now(self) -> datetime: ...


class FakeClock:
    def __init__(self, step_ms: int = 5, start: datetime | None = None) -> None:
        self.t = 0
        self.step = step_ms
        self.start = start or datetime(2026, 9, 1, tzinfo=UTC)
        self.backwards = False

    def monotonic_ms(self) -> int:
        if self.backwards:
            self.backwards = False
            self.t -= 3 * self.step
        self.t += self.step
        return self.t

    def now(self) -> datetime:
        return self.start + timedelta(milliseconds=self.t)
