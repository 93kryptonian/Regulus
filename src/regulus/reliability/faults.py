import random
from enum import StrEnum

from regulus.domain.base import Model
from regulus.review import StoreError
from regulus.workflow import Unavailable


class FaultKind(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    PERMANENT = "PERMANENT"
    TIMEOUT_BEFORE = "TIMEOUT_BEFORE"
    TIMEOUT_AFTER = "TIMEOUT_AFTER"
    CRASH = "CRASH"
    DUPLICATE = "DUPLICATE"
    PARTIAL_PERSISTENCE = "PARTIAL_PERSISTENCE"
    CORRUPTION = "CORRUPTION"
    CLOCK_SKEW = "CLOCK_SKEW"


class Timeout(Unavailable, StoreError):
    pass


class Fault(Model):
    kind: FaultKind
    point: str
    call: int


class FaultPlan:
    def __init__(self, faults: list[Fault] | None = None) -> None:
        self.faults = list(faults or [])
        self.fired: list[Fault] = []
        self._calls: dict[str, int] = {}

    @classmethod
    def seeded(
        cls,
        seed: int,
        points: list[str],
        kinds: list[FaultKind],
        max_faults: int = 3,
        horizon: int = 6,
    ) -> "FaultPlan":
        rng = random.Random(seed)
        n = rng.randint(1, max_faults)
        return cls(
            [
                Fault(
                    kind=rng.choice(kinds), point=rng.choice(points), call=rng.randint(1, horizon)
                )
                for _ in range(n)
            ]
        )

    def check(self, point: str) -> FaultKind | None:
        self._calls[point] = self._calls.get(point, 0) + 1
        n = self._calls[point]
        for f in self.faults:
            if f.point == point and f.call == n and f not in self.fired:
                self.fired.append(f)
                return f.kind
        return None

    def spent(self) -> bool:
        return all(f in self.fired for f in self.faults)

    def clear(self) -> None:
        self.faults = []
