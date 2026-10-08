import json
from pathlib import Path

from ref_helpers import ROOT

from regulus.reference.models import Role, Split, SplitAssignment
from regulus.reference.split import load_split, split_problems
from regulus.reference.synthetic import synthetic_corpus

SPLIT = ROOT / "evaluation" / "reference_split.v1.json"


def mk(*pairs, expected=None):
    return Split(
        version="t",
        assignments=tuple(SplitAssignment(regulation_id=i, role=r, reason="t") for i, r in pairs),
        expected_obligations=expected or {},
    )


def test_the_committed_split_is_valid_data_and_by_regulation():
    s = load_split(SPLIT)
    ids = [a.regulation_id for a in s.assignments]
    assert (
        len(ids) == len(set(ids)) == 6 and len(s.ids(Role.TEST)) == 3 and len(s.ids(Role.DEV)) == 3
    )
    assert set(s.ids(Role.DEV)).isdisjoint(s.ids(Role.TEST))
    assert s.expected_obligations == {"DEV": 162, "TEST": 165}


def test_a_regulation_in_both_roles_fails():
    c = synthetic_corpus()
    s = mk(("syn-a", Role.DEV), ("syn-a", Role.TEST), ("syn-b", Role.TEST), ("syn-c", Role.TEST))
    assert any("more than once" in p for p in split_problems(c, s))


def test_unassigned_and_unknown_regulations_fail():
    c = synthetic_corpus()
    s = mk(("syn-a", Role.DEV), ("syn-b", Role.TEST), ("ghost", Role.TEST))
    p = split_problems(c, s)
    assert any("syn-c" in x and "not in the split" in x for x in p) and any("ghost" in x for x in p)


def test_a_test_role_needs_two_regulations_and_expected_totals_are_checked():
    c = synthetic_corpus()
    p = split_problems(
        c, mk(("syn-a", Role.DEV), ("syn-b", Role.DEV), ("syn-c", Role.TEST), expected={"TEST": 99})
    )
    assert any("at least two" in x for x in p) and any("expected 99" in x for x in p)


def test_a_valid_split_has_no_problems():
    c = synthetic_corpus()
    assert (
        split_problems(c, mk(("syn-a", Role.DEV), ("syn-b", Role.TEST), ("syn-c", Role.TEST))) == []
    )


def test_the_split_file_has_no_row_content():
    raw = SPLIT.read_text(encoding="utf-8")
    assert (
        set(json.loads(raw)) == {"version", "assignments", "expected_obligations"}
        and Path(SPLIT).exists()
    )
