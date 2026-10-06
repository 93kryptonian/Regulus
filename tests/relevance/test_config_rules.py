import pytest
from pydantic import ValidationError

from conftest import NEUTRAL, OJK, OTHER, PP30, PP33, UU27, ctx, with_scope
from regulus.domain import EventType as T
from regulus.relevance import (
    RuleSet,
    ScopeProfile,
    SectorTaxonomy,
    TextSource,
    load_rules,
    load_scope,
    load_taxonomy,
)
from regulus.relevance.models import Effect, Evidence, Kind, Strength
from regulus.relevance.rules import _find, signals


def test_shipped_data_is_valid_and_consistent() -> None:
    t, s, r = load_taxonomy(), load_scope(), load_rules()
    s.validate_against(t)
    r.validate_against(t)
    assert t.codes == {
        "DATA_PROTECTION",
        "ENERGY_UTILITIES",
        "ENVIRONMENT",
        "FINANCIAL_SERVICES",
        "GENERAL",
        "LAND_FORESTRY",
        "TRANSPORT_AVIATION",
    }


def test_taxonomy_rejects_duplicate_codes() -> None:
    with pytest.raises(ValidationError):
        SectorTaxonomy.model_validate(
            {"version": "1", "sectors": [{"code": "A", "label": "a"}, {"code": "A", "label": "b"}]}
        )


def test_unknown_sector_in_scope_or_rules_is_rejected() -> None:
    t = load_taxonomy()
    with pytest.raises(ValueError):
        ScopeProfile(id="x", version="1", sectors_in_scope=("NOPE",)).validate_against(t)
    with pytest.raises(ValueError):
        ScopeProfile(
            id="x", version="1", sectors_in_scope=(), sector_map={"r": ("NOPE",)}
        ).validate_against(t)
    with pytest.raises(ValueError):
        RuleSet.model_validate(
            {"version": "1", "lexicons": [{"sector": "NOPE", "terms": ["x"]}]}
        ).validate_against(t)


def test_issuer_keys_must_be_normalized() -> None:
    with pytest.raises(ValidationError):
        RuleSet.model_validate({"version": "1", "issuer_sectors": {"Bank  Indonesia": ["GENERAL"]}})


def test_whole_word_case_insensitive_matching() -> None:
    assert _find("data", "Pengelolaan database") is None
    assert _find("data", "Pengelolaan DATA pribadi") == (12, 16)
    assert _find("data pribadi", "data   pribadi") == (0, 14)
    assert _find("pergadaian", "pergadaiannya") is None


def test_watchlist_and_sector_map_are_strong(config) -> None:  # type: ignore[no-untyped-def]
    ev = signals(ctx(OJK, T.AMEND, UU27), config.scope, config.rules)
    rules = [(e.rule_id, e.strength, e.effect) for e in ev]
    assert ("WATCHLIST_TARGET", Strength.STRONG, Effect.SUPPORTS_RELEVANCE) in rules
    assert ("SECTOR_MAP", Strength.STRONG, Effect.SUPPORTS_RELEVANCE) in rules
    assert [e.rule_id for e in ev] == sorted(
        (e.rule_id for e in ev),
        key=lambda r: [
            "EXCLUDED_REGULATION",
            "WATCHLIST_TARGET",
            "SECTOR_MAP",
            "ISSUER_SECTOR",
            "TITLE_LEXICON",
            "TEXT_LEXICON",
        ].index(r),
    )


def test_issuer_and_title_signals(config) -> None:  # type: ignore[no-untyped-def]
    ev = signals(ctx(OJK), config.scope, config.rules)
    by = {e.rule_id: e for e in ev}
    assert (
        by["ISSUER_SECTOR"].sector == "FINANCIAL_SERVICES"
        and by["ISSUER_SECTOR"].strength is Strength.MODERATE
    )
    t = by["TITLE_LEXICON"]
    assert t.quote == "Pergadaian" and t.source_id == f"{OJK.id}#title" and t.span == (6, 16)


def test_out_of_scope_sector_is_sector_only(config) -> None:  # type: ignore[no-untyped-def]
    (e,) = [
        x for x in signals(ctx(PP30), config.scope, config.rules) if x.rule_id == "TITLE_LEXICON"
    ]
    assert e.sector == "ENERGY_UTILITIES" and e.effect is Effect.SECTOR_ONLY


def test_text_lexicon_is_weak_with_verifiable_quote(config) -> None:  # type: ignore[no-untyped-def]
    text = "Pengendali Data Pribadi wajib melapor."
    ev = [
        e
        for e in signals(
            ctx(NEUTRAL, texts=(TextSource(owner_id="a1", text=text),)), config.scope, config.rules
        )
        if e.rule_id == "TEXT_LEXICON"
    ]
    assert ev and all(e.strength is Strength.WEAK and e.source_id == "a1" for e in ev)
    assert all(text[e.span[0] : e.span[1]] == e.quote for e in ev if e.span)


def test_exclusion_signal(config) -> None:  # type: ignore[no-untyped-def]
    cfg = with_scope(config, exclusions=(OTHER.id,))
    ev = signals(ctx(OTHER), cfg.scope, cfg.rules)
    assert [(e.rule_id, e.effect) for e in ev] == [
        ("EXCLUDED_REGULATION", Effect.CONTRADICTS_RELEVANCE)
    ]


def test_evidence_requires_span_and_quote_together() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=Kind.DETERMINISTIC,
            rule_id="r",
            strength=Strength.WEAK,
            effect=Effect.SECTOR_ONLY,
            source_id="s",
            span=(0, 3),
        )
    with pytest.raises(ValidationError):
        Evidence(
            kind=Kind.DETERMINISTIC,
            rule_id="r",
            strength=Strength.WEAK,
            effect=Effect.SECTOR_ONLY,
            source_id="s",
            span=(0, 3),
            quote="ab",
        )


def test_signals_are_deterministic_and_deduplicated(config) -> None:  # type: ignore[no-untyped-def]
    c = ctx(PP33, T.AMEND, UU27)
    a, b = signals(c, config.scope, config.rules), signals(c, config.scope, config.rules)
    assert a == b and len({(e.rule_id, e.source_id, e.sector, e.span, e.detail) for e in a}) == len(
        a
    )
