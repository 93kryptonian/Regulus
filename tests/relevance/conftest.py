from datetime import UTC, date, datetime

import pytest

from regulus.domain import EventType as T
from regulus.domain import Regulation, RegulatoryEvent
from regulus.domain import RegulationKind as K
from regulus.relevance import (
    AssessmentConfig,
    AssessmentContext,
    ScopeProfile,
    TextSource,
    load_rules,
    load_scope,
    load_taxonomy,
)
from regulus.relevance.models import title_source

NOW = datetime(2026, 8, 1, tzinfo=UTC)
D = date(2026, 7, 16)


def reg(kind: K, number: str, year: int, title: str, issuer: str | None = None) -> Regulation:
    return Regulation.of(kind, number, year, title=title, issuer=issuer)


UU27 = reg(K.UU, "27", 2022, "Pelindungan Data Pribadi")
PP33 = reg(K.PP, "33", 2026, "Peraturan Pelaksanaan Undang-Undang Nomor 27 Tahun 2022")
PP30 = reg(K.PP, "14", 2012, "Kegiatan Usaha Penyediaan Tenaga Listrik")
OJK = reg(K.POJK, "31/POJK.05", 2016, "Usaha Pergadaian", "Otoritas Jasa Keuangan")
NEUTRAL = reg(K.PERMEN, "9", 2020, "Tata Cara Administrasi Surat Menyurat")
OTHER = reg(K.PERMEN, "10", 2020, "Prosedur Internal Lembaga")


def event(
    actor: Regulation, type: T = T.NEW, target: Regulation | None = None, **kw: object
) -> RegulatoryEvent:
    return RegulatoryEvent(
        id=f"e-{actor.id}-{type}",
        type=type,
        regulation_id=actor.id,
        target_id=target.id if target else None,
        occurred_on=D,
        detected_on=D,
        basis="b",
        **kw,
    )  # type: ignore[arg-type]


def ctx(
    actor: Regulation,
    type: T = T.NEW,
    target: Regulation | None = None,
    texts: tuple[TextSource, ...] = (),
    **kw: object,
) -> AssessmentContext:
    return AssessmentContext(
        event=event(actor, type, target, **kw), regulation=actor, target=target, texts=texts
    )


@pytest.fixture
def config() -> AssessmentConfig:
    return AssessmentConfig(taxonomy=load_taxonomy(), scope=load_scope(), rules=load_rules())


def with_scope(config: AssessmentConfig, **kw: object) -> AssessmentConfig:
    scope = ScopeProfile.model_validate({**config.scope.model_dump(), **kw})
    return AssessmentConfig(taxonomy=config.taxonomy, scope=scope, rules=config.rules)


__all__ = ["title_source"]
