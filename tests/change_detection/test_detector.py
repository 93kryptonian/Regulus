from datetime import date, timedelta

from conftest import DET, rec, rel
from regulus.change_detection import (
    Action as A,
)
from regulus.change_detection import (
    Outcome,
    RegulationIndex,
    detect,
    detect_batch,
)
from regulus.domain import EventType as T
from regulus.domain import RegulationKind as K
from regulus.domain import ReviewReason as R

E: frozenset[str] = frozenset()


def types(res):  # type: ignore[no-untyped-def]
    return [e.type for e in res.events]


def test_new_only(index: RegulationIndex) -> None:
    r = detect(rec(), index, E, DET)
    assert r.outcome is Outcome.PROCESSED_OK and types(r) == [T.NEW]
    assert r.events[0].occurred_on == date(2026, 7, 16) and r.events[0].detected_on == DET


def test_valid_amend_repeal_partial(index: RegulationIndex) -> None:
    rr = rec(relations=(rel(A.MENGUBAH), rel(A.MENCABUT_SEBAGIAN, K.PP, "5", 2020, "PP 5/2020")))
    r = detect(rr, index, E, DET)
    assert sorted(types(r)) == sorted([T.NEW, T.AMEND, T.PARTIAL_REPEAL])
    tg = {e.type: e.target_id for e in r.events}
    assert tg[T.AMEND] == "UU-27-2022" and tg[T.PARTIAL_REPEAL] == "PP-5-2020"
    r2 = detect(rec(relations=(rel(A.MENCABUT),)), index, E, DET)
    assert T.REPEAL in types(r2)


def test_same_record_twice_is_idempotent(index: RegulationIndex) -> None:
    rr = rec(relations=(rel(A.MENGUBAH),))
    first = detect(rr, index, E, DET)
    again = detect(rr, index, {e.id for e in first.events}, DET)
    assert again.outcome is Outcome.PROCESSED_EMPTY and again.events == ()
    assert again.duplicates == 2


def test_relation_declared_twice_one_event(index: RegulationIndex) -> None:
    r = detect(
        rec(relations=(rel(A.MENGUBAH), rel(A.MENGUBAH, raw="UU No. 27 Tahun 2022"))), index, E, DET
    )
    assert types(r).count(T.AMEND) == 1 and r.duplicates == 1


def test_two_records_same_relation_two_events(index: RegulationIndex) -> None:
    a = detect(rec("33", relations=(rel(A.MENGUBAH),)), index, E, DET)
    b = detect(rec("34", relations=(rel(A.MENGUBAH),)), index, E, DET)
    ids = {e.id for e in a.events + b.events}
    assert len(ids) == 4


def test_unknown_target_needs_review(index: RegulationIndex) -> None:
    r = detect(rec(relations=(rel(A.MENCABUT, K.PP, "99", 2001, "PP 99/2001"),)), index, E, DET)
    nr = next(e for e in r.events if e.type is T.NEEDS_REVIEW)
    assert (
        nr.reason is R.UNRESOLVED_TARGET
        and nr.target_id is None
        and nr.declared_ref == "PP 99/2001"
    )
    assert T.REPEAL not in types(r)


def test_ambiguous_and_malformed_targets(index: RegulationIndex) -> None:
    amb = detect(rec(relations=(rel(A.MENGUBAH, None, "27", 2022),)), index, E, DET)
    assert R.AMBIGUOUS_TARGET in [e.reason for e in amb.events]
    mal = detect(rec(relations=(rel(A.MENGUBAH, K.UU, None, 2022),)), index, E, DET)
    assert R.MALFORMED_TARGET in [e.reason for e in mal.events]
    one = detect(rec(relations=(rel(A.MENGUBAH, None, "5", 2020),)), index, E, DET)
    assert R.MALFORMED_TARGET in [e.reason for e in one.events] and T.AMEND not in types(one)


def test_self_reference(index: RegulationIndex) -> None:
    r = detect(rec(relations=(rel(A.MENCABUT, K.PP, "33", 2026, "PP 33/2026"),)), index, E, DET)
    nr = next(e for e in r.events if e.type is T.NEEDS_REVIEW)
    assert nr.reason is R.SELF_REFERENCE and nr.target_id is None and T.REPEAL not in types(r)
    same = rec("5", 2020, title="Five", promulgated_on=date(2020, 1, 1))
    in_idx = detect(
        same.model_copy(update={"relations": (rel(A.MENGUBAH, K.PP, "5", 2020),)}), index, E, DET
    )
    assert R.SELF_REFERENCE in [e.reason for e in in_idx.events] and T.AMEND not in types(in_idx)


def test_conflicting_relations_single_review_event(index: RegulationIndex) -> None:
    r = detect(rec(relations=(rel(A.MENGUBAH), rel(A.MENCABUT))), index, E, DET)
    assert (
        types(r).count(T.NEEDS_REVIEW) == 1 and T.AMEND not in types(r) and T.REPEAL not in types(r)
    )
    ev = next(e for e in r.events if e.type is T.NEEDS_REVIEW)
    assert ev.reason is R.CONFLICTING_RELATIONS and ev.declared_ref is None
    r2 = detect(rec(relations=(rel(A.MENCABUT), rel(A.MENCABUT_SEBAGIAN))), index, E, DET)
    assert R.CONFLICTING_RELATIONS in [e.reason for e in r2.events]
    ok = detect(rec(relations=(rel(A.MENGUBAH), rel(A.MENCABUT_SEBAGIAN))), index, E, DET)
    assert T.AMEND in types(ok) and T.PARTIAL_REPEAL in types(ok)


def test_metadata_conflict_gates_new_and_relations(index: RegulationIndex) -> None:
    rr = rec("5", 2020, title="Five", promulgated_on=date(2020, 2, 2), relations=(rel(A.MENGUBAH),))
    r = detect(rr, index, E, DET)
    assert types(r) == [T.NEEDS_REVIEW] and r.events[0].reason is R.METADATA_CONFLICT
    assert r.events[0].declared_ref is None
    assert [(c.field, c.indexed, c.incoming) for c in r.conflicts] == [
        ("promulgated_on", "2020-01-01", "2020-02-02")
    ]
    title = detect(
        rec("5", 2020, title="Different", promulgated_on=date(2020, 1, 1)), index, E, DET
    )
    assert types(title) == [T.NEEDS_REVIEW]


def test_same_data_or_missing_values_are_not_conflicts(index: RegulationIndex) -> None:
    same = rec("5", 2020, title="  five ", promulgated_on=date(2020, 1, 1))
    assert T.NEEDS_REVIEW not in types(detect(same, index, E, DET))
    sparse = rec(
        "5", 2020, title="Five", promulgated_on=date(2020, 1, 1), enacted_on=date(2019, 1, 1)
    )
    assert T.NEEDS_REVIEW not in types(detect(sparse, index, E, DET))


def test_conflict_dedup_and_new_version(index: RegulationIndex) -> None:
    a = rec("5", 2020, title="Five", promulgated_on=date(2020, 2, 2))
    first = detect(a, index, E, DET)
    again = detect(a, index, {e.id for e in first.events}, DET)
    assert again.events == () and again.duplicates == 1 and again.conflicts
    b = rec("5", 2020, title="Five", promulgated_on=date(2020, 3, 3))
    third = detect(b, index, {e.id for e in first.events}, DET)
    assert len(third.events) == 1 and third.events[0].id != first.events[0].id


def test_review_events_differ_by_action(index: RegulationIndex) -> None:
    mk = lambda a: detect(rec(relations=(rel(a, K.PP, "99", 2001, "PP 99/2001"),)), index, E, DET)  # noqa: E731
    ids = [
        {e.id for e in mk(a).events if e.type is T.NEEDS_REVIEW} for a in (A.MENGUBAH, A.MENCABUT)
    ]
    assert not ids[0] & ids[1]


def test_malformed_records_fail_without_events(index: RegulationIndex) -> None:
    for kw in (
        {"promulgated_on": None},
        {"title": " "},
        {"kind": None},
        {"year": 1800},
        {"number": ""},
    ):
        r = detect(rec(**kw), index, E, DET)
        assert r.outcome is Outcome.FAILED and r.events == () and r.errors


def test_deterministic_and_pure(index: RegulationIndex) -> None:
    rr = rec(relations=(rel(A.MENGUBAH), rel(A.MENCABUT, K.PP, "99", 2001, "x")))
    a = detect(rr, index, E, DET)
    b = detect(rr, index, E, DET)
    assert a.model_dump_json() == b.model_dump_json()
    assert [e.id for e in a.events] == sorted(e.id for e in a.events)
    assert detect(rr, index, E, DET + timedelta(days=9)).events[0].id == a.events[0].id


def test_replay_of_own_output_is_empty(index: RegulationIndex) -> None:
    rr = rec(relations=(rel(A.MENGUBAH),))
    ids = {e.id for e in detect(rr, index, E, DET).events}
    assert detect(rr, index, ids, DET).events == ()


def test_batch_one_result_per_record_in_order(index: RegulationIndex) -> None:
    rs = [rec("33", source_id="a"), rec("33", source_id="b"), rec(title="", source_id="c")]
    out = detect_batch(rs, index, E, DET)
    assert [o.source_id for o in out] == ["a", "b", "c"]
    assert out[1].outcome is Outcome.PROCESSED_EMPTY and out[2].outcome is Outcome.FAILED
    assert detect_batch([], index, E, DET) == []


def test_inputs_not_mutated(index: RegulationIndex) -> None:
    seen = {"x"}
    rr = rec(relations=(rel(A.MENGUBAH),))
    snap = rr.model_dump_json()
    detect(rr, index, seen, DET)
    assert seen == {"x"} and rr.model_dump_json() == snap
