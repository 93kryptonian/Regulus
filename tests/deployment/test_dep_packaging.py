import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from dep_helpers import ROOT

LOAD = """
import json, sys
import regulus
from regulus.governance.resources import default_matrix, default_policy, default_inventory, default_controls
from regulus.governance import inventory
from regulus.relevance.rules import load_rules
from regulus.relevance.taxonomy import load_taxonomy, load_scope
from regulus.obligations.lexicon import load_lexicon
default_matrix(); default_policy(); default_controls()
assert not inventory.check(default_inventory())
load_rules(); load_taxonomy(); load_scope(); load_lexicon()
print(regulus.__file__)
"""


def data_files_in_tree() -> set[str]:
    return {
        str(p.relative_to(ROOT / "src")) for p in (ROOT / "src" / "regulus").rglob("data/*.json")
    }


def missing_from(wheel_names: set[str], tree: set[str]) -> set[str]:
    return tree - wheel_names


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("wheel")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(out), "-q"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr[-500:]
    return next(out.glob("regulus-*.whl"))


def test_every_runtime_data_file_is_in_the_built_wheel(wheel):
    names = set(zipfile.ZipFile(wheel).namelist())
    tree = data_files_in_tree()
    assert len(tree) >= 7 and missing_from(names, tree) == set()
    assert any(n.startswith("regulus/governance/data/") for n in names)


def test_the_check_notices_a_data_file_the_wheel_lacks(wheel):
    names = set(zipfile.ZipFile(wheel).namelist())
    dropped = names - {"regulus/governance/data/access_matrix.v1.json"}
    assert missing_from(dropped, data_files_in_tree()) == {
        "regulus/governance/data/access_matrix.v1.json"
    }


def test_an_installed_copy_loads_every_data_file_with_the_repository_absent(wheel, tmp_path):
    target, empty = tmp_path / "site", tmp_path / "empty"
    empty.mkdir()
    zipfile.ZipFile(wheel).extractall(target)
    import os

    env = {**os.environ, "PYTHONPATH": str(target)}
    r = subprocess.run(
        [sys.executable, "-c", LOAD], capture_output=True, text=True, cwd=empty, env=env
    )
    assert r.returncode == 0, r.stderr[-800:]
    assert Path(r.stdout.strip()).is_relative_to(target) and not Path(
        r.stdout.strip()
    ).is_relative_to(ROOT)


def test_no_runtime_module_reads_repository_relative_data():
    bad = []
    for p in (ROOT / "src" / "regulus").rglob("*.py"):
        if "evaluation" in p.parts or "observability" in p.parts and p.name == "demo.py":
            continue
        text = p.read_text(encoding="utf-8")
        if 'Path("governance")' in text or '"governance" /' in text:
            bad.append(str(p))
    assert bad == []
