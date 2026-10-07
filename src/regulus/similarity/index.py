import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from .embedding import EmbeddingProvider
from .models import Representation, SearchConfig, SimilarityEntry
from .representation import embedding_text, represent


@dataclass
class IndexRecord:
    representation: Representation
    vector: list[float]
    article_id: str
    candidate_id: str | None


@dataclass
class VectorIndex:
    provider_id: str
    dimension: int
    records: dict[str, IndexRecord] = field(default_factory=dict)
    incomplete: int = 0
    cache: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    @property
    def version(self) -> str:
        key = "|".join(sorted(f"{i}:{r.representation.hash}" for i, r in self.records.items()))
        return (
            "idx-"
            + hashlib.sha256(f"{self.provider_id}|{self.dimension}|{key}".encode()).hexdigest()[:12]
        )

    def add(self, record: IndexRecord, provider_id: str) -> None:
        if provider_id != self.provider_id or len(record.vector) != self.dimension:
            raise ValueError("an index never mixes providers or dimensions")
        self.records[record.representation.obligation_id] = record

    def search(self, vector: Sequence[float], k: int, exclude: set[str]) -> list[tuple[str, float]]:
        scored = [
            (oid, sum(a * b for a, b in zip(vector, r.vector, strict=True)))
            for oid, r in self.records.items()
            if oid not in exclude
        ]
        scored.sort(key=lambda t: (-round(t[1], 12), t[0]))
        return [(oid, round(s, 12)) for oid, s in scored[:k]]


def build_index(
    entries: Sequence[SimilarityEntry],
    provider: EmbeddingProvider,
    cfg: SearchConfig,
    existing: VectorIndex | None = None,
) -> VectorIndex:
    pid = f"{provider.id}@{provider.version}"
    index = existing or VectorIndex(provider_id=pid, dimension=provider.dimension)
    if index.provider_id != pid or index.dimension != provider.dimension:
        raise ValueError("an index never mixes providers or dimensions")
    for e in entries:
        if e.obligation.status.value not in cfg.include_statuses:
            continue
        rep = represent(e.obligation, e.trace)
        key = (pid, rep.hash)
        vec = index.cache.get(key)
        if vec is None:
            try:
                vec = list(provider.embed([embedding_text(rep)])[0])
            except Exception:
                index.incomplete += 1
                continue
            index.cache[key] = vec
        index.add(IndexRecord(rep, vec, e.obligation.article_id, e.candidate_id), pid)
    return index
