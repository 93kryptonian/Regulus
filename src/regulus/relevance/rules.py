import json
import re
from typing import Self

from pydantic import Field, model_validator

from regulus.domain import Regulation
from regulus.domain.base import Model

from .models import (
    AssessmentContext,
    Effect,
    Evidence,
    Kind,
    Strength,
    TextSource,
    title_source,
)
from .taxonomy import ScopeProfile, SectorTaxonomy, _load

ORDER = [
    "EXCLUDED_REGULATION",
    "WATCHLIST_TARGET",
    "SECTOR_MAP",
    "ISSUER_SECTOR",
    "TITLE_LEXICON",
    "TEXT_LEXICON",
]


class Lexicon(Model):
    sector: str
    terms: tuple[str, ...] = Field(min_length=1)


class RuleSet(Model):
    version: str = Field(min_length=1)
    issuer_sectors: dict[str, tuple[str, ...]] = {}
    lexicons: tuple[Lexicon, ...] = ()

    @model_validator(mode="after")
    def _norm(self) -> Self:
        if any(k != _issuer_key(k) for k in self.issuer_sectors):
            raise ValueError("issuer keys must be normalized (casefolded, single spaces)")
        return self

    def validate_against(self, taxonomy: SectorTaxonomy) -> None:
        used = {c for v in self.issuer_sectors.values() for c in v} | {
            x.sector for x in self.lexicons
        }
        if unknown := used - taxonomy.codes:
            raise ValueError(f"sectors not in taxonomy: {sorted(unknown)}")


def _issuer_key(s: str) -> str:
    return " ".join(s.split()).casefold()


def load_rules(name: str = "ruleset.v1.json") -> RuleSet:
    return RuleSet.model_validate(json.loads(_load(name)))


def _find(term: str, text: str) -> tuple[int, int] | None:
    pattern = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in term.split()) + r"(?!\w)"
    m = re.search(pattern, text, re.IGNORECASE)
    return (m.start(), m.end()) if m else None


def _sector_effect(sector: str, scope: ScopeProfile) -> Effect:
    return Effect.SUPPORTS_RELEVANCE if sector in scope.sectors_in_scope else Effect.SECTOR_ONLY


def _det(rule: str, strength: Strength, effect: Effect, source: str, **kw: object) -> Evidence:
    return Evidence(
        kind=Kind.DETERMINISTIC,
        rule_id=rule,
        strength=strength,
        effect=effect,
        source_id=source,
        **kw,
    )


def lexicon_hits(
    rule: str, strength: Strength, source: str, text: str, scope: ScopeProfile, rules: RuleSet
) -> list[Evidence]:
    out = []
    for lex in rules.lexicons:
        hits = [(h, t) for t in lex.terms if (h := _find(t, text))]
        if hits:
            (s, e), term = min(hits)
            out.append(
                _det(
                    rule,
                    strength,
                    _sector_effect(lex.sector, scope),
                    source,
                    sector=lex.sector,
                    span=(s, e),
                    quote=text[s:e],
                    detail=f"term:{term}",
                )
            )
    return out


def signals(ctx: AssessmentContext, scope: ScopeProfile, rules: RuleSet) -> list[Evidence]:
    regs: list[Regulation] = [ctx.regulation] + ([ctx.target] if ctx.target else [])
    out: list[Evidence] = []
    for r in regs:
        if r.id in scope.exclusions:
            out.append(
                _det(
                    "EXCLUDED_REGULATION",
                    Strength.STRONG,
                    Effect.CONTRADICTS_RELEVANCE,
                    r.id,
                    detail=f"excluded:{r.id}",
                )
            )
    if ctx.event.target_id and ctx.event.target_id in scope.watchlist:
        out.append(
            _det(
                "WATCHLIST_TARGET",
                Strength.STRONG,
                Effect.SUPPORTS_RELEVANCE,
                ctx.event.target_id,
                detail=f"watchlist:{ctx.event.target_id}",
            )
        )
    for r in regs:
        for sector in scope.sector_map.get(r.id, ()):
            out.append(
                _det(
                    "SECTOR_MAP",
                    Strength.STRONG,
                    _sector_effect(sector, scope),
                    r.id,
                    sector=sector,
                    detail=f"mapped:{r.id}",
                )
            )
    for r in regs:
        for sector in rules.issuer_sectors.get(_issuer_key(r.issuer or ""), ()):
            out.append(
                _det(
                    "ISSUER_SECTOR",
                    Strength.MODERATE,
                    _sector_effect(sector, scope),
                    r.id,
                    sector=sector,
                    detail=f"issuer:{r.issuer}",
                )
            )
    for r in regs:
        out += lexicon_hits(
            "TITLE_LEXICON", Strength.MODERATE, title_source(r.id), r.title, scope, rules
        )
    texts: tuple[TextSource, ...] = ctx.texts
    for t in texts:
        out += lexicon_hits("TEXT_LEXICON", Strength.WEAK, t.owner_id, t.text, scope, rules)
    seen, uniq = set(), []
    for e in out:
        key = (e.rule_id, e.source_id, e.sector, e.span, e.detail)
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return sorted(
        uniq,
        key=lambda e: (ORDER.index(e.rule_id), e.source_id, e.span or (-1, -1), e.sector or ""),
    )
