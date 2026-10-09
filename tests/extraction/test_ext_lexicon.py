import hashlib
import json
from importlib import resources

import pytest
from ext_helpers import make_result

from regulus.extraction import LexiconError, build_package, load_signals

PINNED = "ea688f2418775f9044350eaf09b79ec622a4b38f85e3e55ebfc9f577ea4e55c5"


def _raw() -> str:
    return (
        resources.files("regulus.extraction").joinpath("data", "signals.v1.json").read_text("utf-8")
    )


def test_frozen_lexicon_bytes_are_pinned() -> None:
    sha = hashlib.sha256(_raw().encode()).hexdigest()
    assert sha == PINNED, "signals.v1.json changed: a lexicon change is a new version"


def test_loads_with_version() -> None:
    lex = load_signals()
    assert lex.version == "1" and "dapat" in lex.permission


def test_missing_file_names_the_file() -> None:
    with pytest.raises(LexiconError, match="signals.nope.json"):
        load_signals("signals.nope.json")


BASE = json.loads(_raw())
BAD = {
    "dup": {**BASE, "permission": ["dapat", "dapat"]},
    "empty": {**BASE, "sanction": []},
    "upper": {**BASE, "duty_verbs": ["Melakukan"]},
    "blank": {**BASE, "definition": [" "]},
    "extra": {**BASE, "unknown": ["x"]},
    "noversion": {k: v for k, v in BASE.items() if k != "version"},
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_invalid_lexicon_files_fail_closed(name: str, monkeypatch) -> None:
    fake = _Fake(json.dumps(BAD[name]))
    monkeypatch.setattr("regulus.extraction.lexicon.resources.files", lambda _p: fake)
    with pytest.raises(LexiconError, match="signals.v1.json"):
        load_signals()


class _Fake:
    def __init__(self, text: str) -> None:
        self.text = text

    def joinpath(self, *_a: str) -> "_Fake":
        return self

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.text


def test_invalid_json_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr("regulus.extraction.lexicon.resources.files", lambda _p: _Fake("{nope"))
    with pytest.raises(LexiconError):
        load_signals()


def test_build_package_refuses_without_partial_package(monkeypatch) -> None:
    def boom() -> None:
        raise LexiconError("signals.v1.json: broken")

    monkeypatch.setattr("regulus.extraction.package.load_signals", boom)
    with pytest.raises(LexiconError):
        build_package(make_result())
