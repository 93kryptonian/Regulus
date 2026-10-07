from collections.abc import Sequence
from typing import Protocol

from regulus.domain import Obligation

from .log import obligation_version, replay, tip, verify_chain
from .models import ReviewRecord


class StoreError(Exception):
    pass


class StaleCommit(StoreError):
    pass


class ReviewStore(Protocol):
    def get(self, obligation_id: str) -> tuple[Obligation, tuple[ReviewRecord, ...]]: ...

    def commit(
        self,
        obligation_id: str,
        after: Obligation,
        records: Sequence[ReviewRecord],
        expected_version: str,
    ) -> None: ...


class InMemoryReviewStore:
    def __init__(self) -> None:
        self._initial: dict[str, Obligation] = {}
        self._state: dict[str, Obligation] = {}
        self._log: dict[str, tuple[ReviewRecord, ...]] = {}
        self.fail_next = 0

    def register(self, obligation: Obligation) -> None:
        self._initial[obligation.id] = obligation
        self._state[obligation.id] = obligation
        self._log[obligation.id] = ()

    def get(self, obligation_id: str) -> tuple[Obligation, tuple[ReviewRecord, ...]]:
        return self._state[obligation_id], self._log[obligation_id]

    def version(self, obligation_id: str) -> str:
        return obligation_version(self._state[obligation_id], len(self._log[obligation_id]))

    def commit(
        self,
        obligation_id: str,
        after: Obligation,
        records: Sequence[ReviewRecord],
        expected_version: str,
    ) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise StoreError("injected store failure")
        if self.version(obligation_id) != expected_version:
            raise StaleCommit(obligation_id)
        log = (*self._log[obligation_id], *records)
        if (
            not verify_chain(log)
            or records
            and records[0].prev_hash != tip(self._log[obligation_id])
        ):
            raise StoreError("record does not extend the durable log")
        if replay(self._initial[obligation_id], log) != after:
            raise StoreError("replay of the log does not equal the new state")
        self._state[obligation_id], self._log[obligation_id] = after, log
