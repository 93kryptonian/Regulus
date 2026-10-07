import random
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from regulus.notifications import DeliveryResult, DeliveryStatus, Message
from regulus.review import ReviewRecord, StoreError
from regulus.review.store import InMemoryReviewStore
from regulus.workflow import (
    Crash,
    Permanent,
    PreparedSubmission,
    Principal,
    Unavailable,
    WorkflowRecord,
)

from .faults import FaultKind, FaultPlan, Timeout


class FaultyPipeline:
    def __init__(self, inner: Any, plan: FaultPlan) -> None:
        self.inner, self.plan = inner, plan

    def _call(self, point: str, fn: Any, *args: Any) -> Any:
        kind = self.plan.check(point)
        if kind is FaultKind.UNAVAILABLE:
            raise Unavailable()
        if kind is FaultKind.PERMANENT:
            raise Permanent()
        if kind is FaultKind.TIMEOUT_BEFORE:
            raise Timeout()
        if kind is FaultKind.CRASH:
            raise Crash(point)
        out = fn(*args)
        if kind is FaultKind.TIMEOUT_AFTER:
            raise Timeout()
        return out

    def process(self, event: Any) -> Any:
        return self._call("pipeline.process", self.inner.process, event)

    def generate(self, event: Any, ref: str) -> Any:
        return self._call("pipeline.generate", self.inner.generate, event, ref)

    def enrich(self, item_id: str) -> Any:
        return self._call("pipeline.enrich", self.inner.enrich, item_id)

    def result(self, item_id: str) -> Any:
        return self.inner.result(item_id)

    def owner_texts(self, ref: str) -> Any:
        return self.inner.owner_texts(ref)


class FaultyChannel:
    def __init__(self, inner: Any, plan: FaultPlan) -> None:
        self.inner, self.plan = inner, plan

    def send(
        self, message: Message, recipients: Sequence[str], idempotency_key: str
    ) -> DeliveryResult:
        kind = self.plan.check("channel.send")
        if kind is FaultKind.UNAVAILABLE:
            return DeliveryResult(status=DeliveryStatus.FAILED_RETRYABLE, error_class="Unavailable")
        if kind is FaultKind.PERMANENT:
            return DeliveryResult(status=DeliveryStatus.FAILED_PERMANENT, error_class="Rejected")
        if kind is FaultKind.TIMEOUT_BEFORE:
            raise Timeout()
        out: DeliveryResult = self.inner.send(message, recipients, idempotency_key)
        if kind is FaultKind.DUPLICATE:
            self.inner.send(message, recipients, idempotency_key)
        if kind is FaultKind.TIMEOUT_AFTER:
            raise Timeout()
        if kind is FaultKind.CRASH:
            raise Crash("channel.send")
        return out


class FaultyDirectory:
    def __init__(self, inner: Any, plan: FaultPlan) -> None:
        self.inner, self.plan = inner, plan

    def reviewers(self, now: datetime) -> Any:
        if self.plan.check("directory.reviewers") in (
            FaultKind.UNAVAILABLE,
            FaultKind.TIMEOUT_BEFORE,
        ):
            return []
        return self.inner.reviewers(now)


class FaultyStore:
    def __init__(self, inner: Any, plan: FaultPlan) -> None:
        self._inner, self._plan = inner, plan

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _guard(self, point: str, fn: Any, *args: Any) -> Any:
        kind = self._plan.check(point)
        if kind is FaultKind.UNAVAILABLE:
            raise StoreError("injected unavailable")
        if kind is FaultKind.TIMEOUT_BEFORE:
            raise Timeout()
        if kind is FaultKind.CRASH:
            raise Crash(point)
        out = fn(*args)
        if kind is FaultKind.TIMEOUT_AFTER:
            raise Timeout()
        return out

    def commit_submission(
        self, prepared: PreparedSubmission, principal: Principal, at: datetime
    ) -> None:
        self._guard(
            "store.commit_submission", self._inner.commit_submission, prepared, principal, at
        )

    def append(self, *args: Any, **kw: Any) -> WorkflowRecord:
        out: WorkflowRecord = self._guard("store.append", self._inner.append, *args)
        return out


class FaultyReviewStore:
    def __init__(self, inner: InMemoryReviewStore, plan: FaultPlan) -> None:
        self._inner, self._plan = inner, plan

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def commit(
        self, oid: str, after: Any, records: Sequence[ReviewRecord], expected_version: str
    ) -> None:
        kind = self._plan.check("review.commit")
        if kind is FaultKind.UNAVAILABLE:
            raise StoreError("injected unavailable")
        if kind is FaultKind.TIMEOUT_BEFORE:
            raise Timeout()
        if kind is FaultKind.CRASH:
            raise Crash("review.commit")
        self._inner.commit(oid, after, records, expected_version)
        if kind is FaultKind.TIMEOUT_AFTER:
            raise Timeout()


class Corruption(StrEnum):
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    REORDER = "REORDER"
    TRUNCATE = "TRUNCATE"
    SPLICE = "SPLICE"


def corrupt(
    records: tuple[Any, ...], mode: Corruption, rng: random.Random, foreign: Any = None
) -> tuple[Any, ...]:
    if len(records) < 2:
        raise ValueError("need at least two records to corrupt")
    i = rng.randrange(len(records) - 1)
    recs = list(records)
    if mode is Corruption.MODIFY:
        rec = recs[i]
        names = type(rec).model_fields
        field = (
            "principal_id"
            if "principal_id" in names
            else "actor_id"
            if "actor_id" in names
            else "kind"
        )
        recs[i] = rec.model_copy(update={field: "mallory"})
    elif mode is Corruption.DELETE:
        del recs[i]
    elif mode is Corruption.REORDER:
        recs[i], recs[i + 1] = recs[i + 1], recs[i]
    elif mode is Corruption.TRUNCATE:
        recs = recs[:-1]
    elif mode is Corruption.SPLICE:
        recs.insert(i + 1, foreign if foreign is not None else records[0])
    return tuple(recs)
