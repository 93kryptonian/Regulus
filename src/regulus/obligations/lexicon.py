import json
import re
from importlib import resources

from pydantic import Field

from regulus.domain.base import Model


class Lexicon(Model):
    version: str = Field(min_length=1)
    obligation_markers: tuple[str, ...]
    prohibition_markers: tuple[str, ...]
    negated_markers: tuple[str, ...]
    abbreviations: tuple[str, ...]
    condition_triggers: tuple[str, ...]
    exception_triggers: tuple[str, ...]
    deadline_triggers: tuple[str, ...]
    duration_units: tuple[str, ...]
    frequency_units: tuple[str, ...]
    frequency_phrases: tuple[str, ...]
    object_boundaries: tuple[str, ...]
    verb_prefixes: tuple[str, ...]


def load_lexicon(name: str = "lexicon.v1.json") -> Lexicon:
    raw = resources.files("regulus.obligations").joinpath("data", name).read_text(encoding="utf-8")
    return Lexicon.model_validate(json.loads(raw))


def phrase(term: str) -> str:
    return r"\s+".join(re.escape(p) for p in term.split())


def alternation(terms: tuple[str, ...]) -> str:
    return "|".join(phrase(t) for t in sorted(terms, key=len, reverse=True))
