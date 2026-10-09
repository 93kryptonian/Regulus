import json
from importlib import resources

from pydantic import Field, ValidationError, model_validator

from regulus.domain.base import Model

NAME = "signals.v1.json"


class LexiconError(Exception):
    pass


class SignalsLexicon(Model):
    version: str = Field(min_length=1)
    permission: tuple[str, ...]
    sanction: tuple[str, ...]
    responsibility: tuple[str, ...]
    duty_verbs: tuple[str, ...]
    passive_duties: tuple[str, ...]
    definition: tuple[str, ...]

    @model_validator(mode="after")
    def _terms(self) -> "SignalsLexicon":
        for name in (
            "permission",
            "sanction",
            "responsibility",
            "duty_verbs",
            "passive_duties",
            "definition",
        ):
            terms = getattr(self, name)
            norm = [" ".join(t.lower().split()) for t in terms]
            if not terms or any(not t for t in norm) or len(set(norm)) != len(norm):
                raise ValueError(f"{name}: empty, blank or duplicate terms")
            if norm != list(terms):
                raise ValueError(f"{name}: terms must be lowercase with single spaces")
        return self


def load_signals(name: str = NAME) -> SignalsLexicon:
    try:
        raw = (
            resources.files("regulus.extraction").joinpath("data", name).read_text(encoding="utf-8")
        )
        return SignalsLexicon.model_validate(json.loads(raw))
    except (OSError, ValueError, ValidationError) as e:
        raise LexiconError(f"{name}: {type(e).__name__}") from e
