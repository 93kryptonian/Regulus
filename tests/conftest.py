import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from regulus.domain import (
    Article,
    Generated,
    GenerationMetadata,
    Obligation,
    ObligationContent,
    ObligationEvidence,
    ObligationStatus,
    Origin,
    OwnerKind,
    Regulation,
    RegulationKind,
)

for _d in (
    "review",
    "workflow",
    "observability",
    "reliability",
    "review_ui",
    "governance",
    "deployment",
    "reference",
    "documents",
    "ingestion",
    "extraction",
):
    sys.path.insert(0, str(Path(__file__).parent / _d))

NOW = datetime(2026, 1, 1, tzinfo=UTC)
TEXT = "Pengendali Data Pribadi wajib menyampaikan laporan setiap 3 bulan."


@pytest.fixture
def regulation() -> Regulation:
    return Regulation.of(RegulationKind.PP, "33", 2026, title="Pelaksanaan UU PDP")


@pytest.fixture
def article(regulation: Regulation) -> Article:
    return Article.of(regulation.id, "5", TEXT, 2, 2)


@pytest.fixture
def obligation(article: Article) -> Obligation:
    c = ObligationContent(text="Controller must report quarterly.", deadline="3 months")
    meta = GenerationMetadata(model="m", prompt_version="v1", generated_at=NOW)
    return Obligation(
        id="o1",
        article_id=article.id,
        source_owner_id=article.id,
        origin=Origin.AI,
        generated=Generated(content=c, meta=meta),
        current=c,
        status=ObligationStatus.PENDING_REVIEW,
    )


@pytest.fixture
def evidence(obligation: Obligation, article: Article) -> ObligationEvidence:
    quote = "wajib menyampaikan laporan"
    s = TEXT.index(quote)
    return ObligationEvidence(
        obligation_id=obligation.id,
        owner_id=article.id,
        owner_kind=OwnerKind.ARTICLE,
        span=(s, s + len(quote)),
        quote=quote,
    )
