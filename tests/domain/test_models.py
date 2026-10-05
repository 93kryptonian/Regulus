from datetime import date

import pytest
from pydantic import ValidationError

from regulus.domain import (
    Article,
    EventType,
    Obligation,
    ObligationContent,
    Origin,
    Regulation,
    RegulationKind,
    RegulatoryEvent,
    Sector,
    text_hash,
)

D = date(2026, 1, 1)


def event(t: EventType, **kw: object) -> RegulatoryEvent:
    return RegulatoryEvent(
        id="e", type=t, regulation_id="a", occurred_on=D, detected_on=D, basis="src", **kw
    )  # type: ignore[arg-type]


def roundtrip(m):  # type: ignore[no-untyped-def]
    assert type(m).model_validate_json(m.model_dump_json()) == m


def test_regulation_id_derived_and_roundtrip(regulation: Regulation) -> None:
    assert regulation.id == "PP-33-2026"
    roundtrip(regulation)


def test_regulation_rejects_bad_id_year_title() -> None:
    k = RegulationKind.PP
    with pytest.raises(ValidationError):
        Regulation(id="x", kind=k, number="1", year=2020, title="t")
    with pytest.raises(ValidationError):
        Regulation.of(k, "1", 1800, title="t")
    with pytest.raises(ValidationError):
        Regulation.of(k, "1", 2020, title="")


def test_regulation_is_immutable_and_forbids_extra(regulation: Regulation) -> None:
    with pytest.raises(ValidationError):
        regulation.title = "x"
    with pytest.raises(ValidationError):
        Regulation.of(RegulationKind.PP, "1", 2020, title="t", foo=1)


@pytest.mark.parametrize("t", [EventType.AMEND, EventType.REPEAL, EventType.PARTIAL_REPEAL])
def test_event_requires_target(t: EventType) -> None:
    with pytest.raises(ValidationError):
        event(t)
    roundtrip(event(t, target_id="b"))


def test_event_new_forbids_target_and_self_target() -> None:
    roundtrip(event(EventType.NEW))
    with pytest.raises(ValidationError):
        event(EventType.NEW, target_id="b")
    with pytest.raises(ValidationError):
        event(EventType.AMEND, target_id="a")


def test_event_needs_review_target_optional_basis_required() -> None:
    event(EventType.NEEDS_REVIEW)
    with pytest.raises(ValidationError):
        RegulatoryEvent(
            id="e", type=EventType.NEW, regulation_id="a", occurred_on=D, detected_on=D, basis=""
        )


def test_article_valid(article: Article) -> None:
    assert article.text_hash == text_hash(article.text)
    roundtrip(article)


@pytest.mark.parametrize("ps,pe", [(0, 1), (3, 2), (-1, 1)])
def test_article_bad_pages(ps: int, pe: int) -> None:
    with pytest.raises(ValidationError):
        Article.of("r", "1", "text", ps, pe)


def test_article_empty_text_and_bad_hash(article: Article) -> None:
    with pytest.raises(ValidationError):
        Article.of("r", "1", "   ", 1, 1)
    with pytest.raises(ValidationError):
        Article(**{**article.model_dump(), "text_hash": "0" * 64})


def test_sector() -> None:
    roundtrip(Sector(code="fin", label="Finance"))
    with pytest.raises(ValidationError):
        Sector(code="", label="x")


def test_obligation_roundtrip_and_ai_needs_meta(obligation: Obligation) -> None:
    roundtrip(obligation)
    data = obligation.model_dump()
    data["generated"]["meta"] = None
    with pytest.raises(ValidationError):
        Obligation.model_validate(data)
    Obligation.model_validate({**data, "origin": Origin.HUMAN})


def test_obligation_duplicate_sectors(obligation: Obligation) -> None:
    with pytest.raises(ValidationError):
        Obligation.model_validate({**obligation.model_dump(), "sectors": ["a", "a"]})


def test_content_requires_text() -> None:
    with pytest.raises(ValidationError):
        ObligationContent(text="")
