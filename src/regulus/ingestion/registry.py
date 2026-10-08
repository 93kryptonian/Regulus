from typing import Protocol

from .models import IngestionResult


class IngestionRegistry(Protocol):
    def find(self, regulation_id: str, processing_key: str) -> IngestionResult | None: ...

    def owner_of(self, content_hash: str) -> str | None: ...

    def versions(self, regulation_id: str) -> tuple[tuple[str, str], ...]: ...

    def add(self, result: IngestionResult) -> None: ...


class InMemoryRegistry:
    def __init__(self) -> None:
        self._results: dict[tuple[str, str], IngestionResult] = {}
        self._owner: dict[str, str] = {}
        self._versions: dict[str, list[tuple[str, str]]] = {}

    def find(self, regulation_id: str, processing_key: str) -> IngestionResult | None:
        return self._results.get((regulation_id, processing_key))

    def owner_of(self, content_hash: str) -> str | None:
        return self._owner.get(content_hash)

    def versions(self, regulation_id: str) -> tuple[tuple[str, str], ...]:
        return tuple(self._versions.get(regulation_id, ()))

    def add(self, result: IngestionResult) -> None:
        ident = result.identity
        rid = ident.regulation_id
        self._results[(rid, ident.processing_key)] = result
        self._owner.setdefault(ident.content_hash, rid)
        entry = (ident.content_hash, ident.text_fingerprint)
        if entry not in self._versions.setdefault(rid, []):
            self._versions[rid].append(entry)
