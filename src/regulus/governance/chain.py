import hashlib
import json
import re
from datetime import datetime
from typing import Self

from pydantic import AwareDatetime, model_validator

from regulus.domain.base import Model

from .policy import FreeTextPolicy

GENESIS = "GENESIS"
ID = re.compile(r"^[A-Za-z0-9:_.\-]{1,96}$")
REASON_KEYS = {"reason"}


class LogUnavailable(Exception):
    pass


class GovRecord(Model):
    id: str
    seq: int
    log: str
    kind: str
    fields: dict[str, str | int | bool] = {}
    at: AwareDatetime
    prev_hash: str
    hash: str = ""

    @model_validator(mode="after")
    def _content_free(self) -> Self:
        pol = FreeTextPolicy()
        for k, v in self.fields.items():
            if isinstance(v, str):
                if k in REASON_KEYS:
                    if pol.check(k, v) is not None:
                        raise ValueError(f"field {k} violates the free-text policy")
                elif not ID.match(v):
                    raise ValueError(f"field {k} is outside the permitted grammar")
        return self


def canonical(r: GovRecord) -> str:
    return json.dumps(
        r.model_dump(mode="json", exclude={"hash"}),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def rhash(prev: str, r: GovRecord) -> str:
    return hashlib.sha256((prev + canonical(r)).encode()).hexdigest()


def verify(records: tuple[GovRecord, ...] | list[GovRecord]) -> bool:
    prev = GENESIS
    for i, r in enumerate(records):
        if r.prev_hash != prev or r.seq != i or r.hash != rhash(prev, r):
            return False
        prev = r.hash
    return True


class ChainLog:
    def __init__(self, name: str) -> None:
        self.name = name
        self.records: list[GovRecord] = []
        self.fail_next = 0
        self.anchor: tuple[int, str] | None = None

    def append(self, kind: str, at: datetime, **fields: str | int | bool) -> GovRecord:
        if self.fail_next:
            self.fail_next -= 1
            raise LogUnavailable(self.name)
        prev = self.records[-1].hash if self.records else GENESIS
        seq = len(self.records)
        rid = (
            f"{self.name}-" + hashlib.sha256(f"{self.name}|{seq}|{prev}".encode()).hexdigest()[:16]
        )
        r = GovRecord(
            id=rid, seq=seq, log=self.name, kind=kind, fields=fields, at=at, prev_hash=prev
        )
        r = r.model_copy(update={"hash": rhash(prev, r)})
        self.records.append(r)
        self.anchor = (seq, r.hash)
        return r

    def verified(self) -> bool:
        if not verify(self.records):
            return False
        a = self.anchor
        return a is None or (len(self.records) > a[0] and self.records[a[0]].hash == a[1])
