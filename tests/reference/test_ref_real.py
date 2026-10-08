import json
import subprocess

import pytest
from ref_helpers import REAL, ROOT

from regulus.reference.load import available, load_corpus
from regulus.reference.metrics import instrument_problems
from regulus.reference.models import DiscrepancyKind as K
from regulus.reference.normalize import norm
from regulus.reference.scan import leaking_files, leaks, needles, public_text
from regulus.reference.split import load_split, split_problems
from regulus.reference.synthetic import synthetic_corpus

real = pytest.mark.reference
needs = pytest.mark.skipif(
    not available(REAL), reason="local reference absent: rows are NOT_MEASURABLE"
)

DECLARED = {
    "lt4b1e12ac0efd3": 37,
    "lt4b209de5e2d16": 93,
    "lt4f32463fb11ee": 34,
    "lt4f72ee9aba41a": 4,
    "lt57bac6099aa30": 2,
    "lt6a9164bf1e96a": 156,
}


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(REAL)


@real
@needs
def test_five_declared_counts_are_reproduced_and_one_is_over_by_one(corpus):
    derived = {
        r.regulation_id: len(corpus.obligations_of(r.regulation_id)) for r in corpus.regulations
    }
    assert {r.regulation_id: r.declared_count for r in corpus.regulations} == DECLARED
    off = {i: derived[i] - DECLARED[i] for i in DECLARED if derived[i] != DECLARED[i]}
    assert off == {"lt4b209de5e2d16": 1}
    exceeds = [d for d in corpus.discrepancies if d.kind is K.COUNT_EXCEEDS_DECLARED]
    assert [d.regulation_id for d in exceeds] == ["lt4b209de5e2d16"]
    assert sum(1 for d in corpus.discrepancies if d.kind is K.COUNT_MATCHED) == 5
    assert sum(derived.values()) == 327


@real
@needs
def test_reference_integrity_facts(corpus):
    kinds = {d.kind for d in corpus.discrepancies}
    assert K.PARSE_ERROR not in kinds and K.UNKNOWN_SECTOR not in kinds
    assert len(corpus.sectors) == 176 and len(corpus.regulations) == 6
    assert K.LABEL_COPIES_IDENTICAL in kinds and K.IRREGULAR_MULTIPLICITY in kinds
    assert all(
        any(link.obligation_id == o.obligation_id for link in corpus.links)
        for o in corpus.obligations
    )


@real
@needs
def test_the_committed_split_is_valid_on_the_real_corpus(corpus):
    assert split_problems(corpus, load_split(ROOT / "evaluation" / "reference_split.v1.json")) == []


@real
@needs
def test_the_instrument_holds_on_the_real_corpus(corpus):
    assert instrument_problems(corpus) == []


@real
@needs
def test_loading_twice_is_identical(corpus):
    assert load_corpus(REAL) == corpus


@real
@needs
def test_no_committed_artifact_contains_reference_content(corpus):
    public = public_text(ROOT / "pdf", corpus)
    assert len(public) == 6
    assert leaking_files(ROOT, corpus, public) == []


def test_the_leak_scan_detects_content(tmp_path):
    c = synthetic_corpus()
    ns = needles(c)
    sample = next(iter(ns))
    assert leaks(f"prefix {sample.upper()} suffix", ns) == 1 and leaks("nothing here", ns) == 0
    (tmp_path / "a.md").write_text(f"x {sample} y")
    (tmp_path / "b.md").write_text("clean")
    assert leaking_files(tmp_path, c) == ["a.md"]


def test_statute_wording_is_not_treated_as_expert_content():
    c = synthetic_corpus()
    sample = next(iter(needles(c)))
    reg = next(o.regulation_id for o in c.obligations if norm(o.text) == sample)
    assert sample in needles(c) and sample not in needles(c, {reg: f"xx {sample} yy"})


def test_the_reference_folder_is_never_tracked():
    out = subprocess.run(["git", "ls-files", "reference"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0 and out.stdout.strip() == ""
    ig = subprocess.run(["git", "check-ignore", "-q", "reference/x"], cwd=ROOT)
    assert ig.returncode == 0


def test_the_split_file_names_no_content():
    doc = json.loads((ROOT / "evaluation" / "reference_split.v1.json").read_text())
    assert all(set(a) == {"regulation_id", "role", "reason"} for a in doc["assignments"])
