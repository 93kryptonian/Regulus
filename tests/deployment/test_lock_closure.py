import importlib.util
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("lockscript", ROOT / "scripts" / "lock.py")
assert spec and spec.loader
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)

PINS = lock.parse((ROOT / "requirements.lock").read_text(encoding="utf-8"))


def test_lock_is_current():
    assert (ROOT / "requirements.lock").read_text(encoding="utf-8") == lock.render(
        lock.closure(lock.declared())
    )


def test_lock_covers_every_declared_runtime_dependency():
    for r in lock.declared():
        assert canonicalize_name(r.name) in PINS


def test_lock_versions_satisfy_declared_ranges():
    for r in lock.declared():
        assert r.specifier.contains(Version(PINS[canonicalize_name(r.name)]), prereleases=True)


def test_lock_pins_installed_versions():
    for name, version in PINS.items():
        assert metadata.version(name) == version


def test_lock_contains_only_reachable_packages():
    declared = {canonicalize_name(r.name) for r in lock.declared()}
    reach = set(lock.closure(lock.declared()))
    assert declared <= set(PINS) == reach
    for dev in ("pytest", "mypy", "ruff", "reportlab", "pytesseract", "regulus"):
        assert dev not in PINS


def test_lock_misses_dependency_is_detected():
    short = {k: v for k, v in PINS.items() if k != "pydantic-core"}
    assert short != lock.closure(lock.declared())
    assert "pydantic-core" in lock.closure([Requirement("pydantic>=2.7")])


def test_lock_without_dev_extras_in_closure():
    assert "pytesseract" not in lock.closure(lock.declared())
