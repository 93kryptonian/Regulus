import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from regulus.generation.verify import tokens


class EmbeddingProvider(Protocol):
    id: str
    version: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


def _terms(text: str) -> list[str]:
    t = tokens(text)
    return t + [f"{a}_{b}" for a, b in zip(t, t[1:], strict=False)]


def _slot(term: str, dim: int) -> tuple[int, float]:
    h = int.from_bytes(hashlib.blake2b(term.encode(), digest_size=8).digest(), "big")
    return h % dim, 1.0 if (h >> 63) & 1 else -1.0


class LexicalEmbedding:
    id = "lexical"
    version: str

    def __init__(
        self, dimension: int = 1024, idf: dict[str, float] | None = None, default_idf: float = 1.0
    ) -> None:
        self.dimension = dimension
        self.idf = idf or {}
        self.default_idf = default_idf
        digest = hashlib.sha256(repr(sorted(self.idf.items())).encode()).hexdigest()[:8]
        self.version = f"1-d{dimension}-{digest}"

    @classmethod
    def fit(cls, texts: Sequence[str], dimension: int = 1024) -> "LexicalEmbedding":
        df: Counter[str] = Counter()
        for t in texts:
            df.update(set(_terms(t)))
        n = len(texts)
        idf = {term: math.log((n + 1) / (c + 1)) + 1.0 for term, c in df.items()}
        return cls(dimension, idf, math.log(n + 1) + 1.0)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dimension
            for term, tf in Counter(_terms(text)).items():
                slot, sign = _slot(term, self.dimension)
                vec[slot] += sign * (1.0 + math.log(tf)) * self.idf.get(term, self.default_idf)
            norm = math.sqrt(sum(x * x for x in vec))
            out.append([x / norm for x in vec] if norm else vec)
        return out
