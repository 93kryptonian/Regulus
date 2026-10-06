import json
from importlib import resources
from typing import Self

from pydantic import Field, model_validator

from regulus.domain import Sector
from regulus.domain.base import Model


class SectorTaxonomy(Model):
    version: str = Field(min_length=1)
    sectors: tuple[Sector, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        codes = [s.code for s in self.sectors]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate sector codes")
        return self

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(s.code for s in self.sectors)


class ScopeProfile(Model):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    sectors_in_scope: tuple[str, ...]
    watchlist: tuple[str, ...] = ()
    sector_map: dict[str, tuple[str, ...]] = {}
    exclusions: tuple[str, ...] = ()

    def validate_against(self, taxonomy: SectorTaxonomy) -> None:
        used = set(self.sectors_in_scope) | {c for v in self.sector_map.values() for c in v}
        if unknown := used - taxonomy.codes:
            raise ValueError(f"sectors not in taxonomy: {sorted(unknown)}")


def _load(name: str) -> str:
    return resources.files("regulus.relevance").joinpath("data", name).read_text(encoding="utf-8")


def load_taxonomy(name: str = "sector_taxonomy.v1.json") -> SectorTaxonomy:
    return SectorTaxonomy.model_validate(json.loads(_load(name)))


def load_scope(name: str = "scope_profile.sample.json") -> ScopeProfile:
    return ScopeProfile.model_validate(json.loads(_load(name)))
