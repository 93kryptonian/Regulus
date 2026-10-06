import pytest
from helpers import ACTOR, INTRO, OTHER, TARGET, amending, doc, ev, make, reg, target_articles

from regulus.documents import DocStatus
from regulus.domain import EventType as T
from regulus.domain import RegulationKind as K
from regulus.lineage import Effect, IssueCode, analyze_impact, project
from regulus.lineage.models import ChangedKind, ImpactStatus, TargetCheck

POINTS = (
    "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut:\nPasal 5\n(1) Setiap orang wajib melapor.",
    "2. Di antara Pasal 5 dan Pasal 6 disisipkan 1 (satu) Pasal, yakni Pasal 5A, yang berbunyi sebagai berikut:\n"
    "Pasal 5A\nSetiap pengendali wajib menjaga data.",
    "3. Pasal 7 dihapus.",
    "4. Pasal 9 dicabut.",
    '5. Kata "Menteri" dalam Pasal 3 ayat (1) diganti dengan kata "Kepala".',
    "6. Pada Pasal 8, diperbaiki seperlunya.",
)


def amend_input(points=POINTS, intro=INTRO, targets=True, **kw):  # type: ignore[no-untyped-def]
    e = ev(ACTOR, T.AMEND, TARGET)
    docs = {ACTOR.id: doc(ACTOR, amending(intro, *points))}
    ta = {TARGET.id: target_articles(*[str(i) for i in range(1, 10)])} if targets else {}
    return e, make([e], docs, ta, **kw), docs


def by(res, effect):  # type: ignore[no-untyped-def]
    return [i for i in res.impacts if i.effect is effect]


def test_modify_insert_delete_repeal_replace() -> None:
    e, inp, docs = amend_input()
    res = analyze_impact(e, inp)
    unit = docs[ACTOR.id].amendment_units[0]
    mod = next(i for i in res.impacts if i.article_number == "5" and i.effect is Effect.MODIFIED)
    assert mod.target_check is TargetCheck.CONFIRMED and mod.status is ImpactStatus.RESOLVED
    assert mod.new_text and unit.text[mod.new_text.start : mod.new_text.end].startswith(
        "Pasal 5\n(1) Setiap"
    )
    assert [i.article_number for i in by(res, Effect.ADDED)] == ["5A"]
    assert [i.article_number for i in by(res, Effect.DELETED)] == ["7"]
    assert [i.article_number for i in by(res, Effect.REPEALED)] == ["9"]
    path = next(i for i in res.impacts if i.article_number == "3")
    assert (path.effect, path.provision_path) == (Effect.MODIFIED, ("(1)",))
    kinds = {(c.article_number, c.kind) for c in res.changed}
    assert kinds == {
        ("5", ChangedKind.MODIFIED),
        ("5A", ChangedKind.ADDED),
        ("3", ChangedKind.TERM_REPLACED),
    }
    sup = {c.article_number: c.supersedes for c in res.changed}
    assert sup["5"] == f"{TARGET.id}:5" and sup["5A"] is None
    assert {(w.article_number, w.effect) for w in res.withdrawn} == {
        ("7", Effect.DELETED),
        ("9", Effect.REPEALED),
    }
    assert res.complete and [u.reason for u in res.unresolved_operations] == [
        "UNSUPPORTED_OPERATION"
    ]
    assert res.unresolved_operations[0].spans


def test_quoted_pasal_inside_new_wording_is_not_an_impact() -> None:
    e, inp, _ = amend_input()
    res = analyze_impact(e, inp)
    modified5 = [i for i in res.impacts if i.article_number == "5" and i.effect is Effect.MODIFIED]
    assert len(modified5) == 1


def test_ayat_modify_gives_article_modified_with_path() -> None:
    e, inp, _ = amend_input(
        ("1. Ketentuan ayat (2) dan ayat (3) Pasal 5 diubah sehingga berbunyi sebagai berikut: x",)
    )
    res = analyze_impact(e, inp)
    assert sorted((i.article_number, i.effect, i.provision_path) for i in res.impacts) == [
        ("5", Effect.MODIFIED, ("(2)",)),
        ("5", Effect.MODIFIED, ("(3)",)),
    ]


def test_range_repeal_gives_one_item_per_article() -> None:
    e, inp, _ = amend_input(
        ("1. Pasal 5 sampai dengan Pasal 8 dicabut dan dinyatakan tidak berlaku.",)
    )
    res = analyze_impact(e, inp)
    assert sorted(i.article_number for i in res.impacts) == ["5", "6", "7", "8"]
    assert {i.effect for i in res.impacts} == {Effect.REPEALED}


def test_unsupported_structural_locator_is_recognised_and_unresolved() -> None:
    e, inp, _ = amend_input(("1. Ketentuan BAB II diubah sehingga berbunyi sebagai berikut: x",))
    res = analyze_impact(e, inp)
    assert res.impacts == () and [u.reason for u in res.unresolved_operations] == [
        "UNSUPPORTED_LOCATOR"
    ]


def test_unit_naming_another_target_is_a_mismatch_issue() -> None:
    other_intro = (
        "Beberapa ketentuan dalam Peraturan Pemerintah Nomor 11 Tahun 2021 diubah sebagai berikut:"
    )
    e, inp, _ = amend_input(("1. Pasal 7 dihapus.",), intro=other_intro)
    res = analyze_impact(e, inp)
    assert res.impacts == () and [i.code for i in res.issues] == [IssueCode.UNIT_TARGET_MISMATCH]
    assert [u.reason for u in res.unresolved_operations] == ["UNIT_TARGET_MISMATCH"]
    full = project(inp)
    assert full.relations[0].integrity.value == "CONFLICT"


def test_unit_naming_two_regulations_is_ambiguous_not_guessed() -> None:
    both = (
        "Ketentuan dalam Peraturan Pemerintah Nomor 10 Tahun 2020 sebagaimana telah diubah dengan "
        "Peraturan Pemerintah Nomor 11 Tahun 2021, diubah lagi sebagai berikut:"
    )
    e, inp, _ = amend_input(("1. Pasal 7 dihapus.",), intro=both)
    res = analyze_impact(e, inp)
    assert res.impacts == () and [u.reason for u in res.unresolved_operations] == [
        "AMBIGUOUS_UNIT_TARGET"
    ]


def test_unit_without_named_target_binds_to_the_event_target() -> None:
    e, inp, _ = amend_input(
        ("1. Pasal 7 dihapus.",), intro="Beberapa ketentuan diubah sebagai berikut:"
    )
    assert [i.article_number for i in analyze_impact(e, inp).impacts] == ["7"]


def test_binding_uses_only_the_analysed_event() -> None:
    e1 = ev(ACTOR, T.AMEND, TARGET)
    e2 = ev(ACTOR, T.AMEND, OTHER)
    docs = {
        ACTOR.id: doc(
            ACTOR, amending("Beberapa ketentuan diubah sebagai berikut:", "1. Pasal 7 dihapus.")
        )
    }
    inp = make([e1, e2], docs)
    r1, r2 = analyze_impact(e1, inp), analyze_impact(e2, inp)
    assert {i.target_regulation_id for i in r1.impacts} == {TARGET.id}
    assert {i.target_regulation_id for i in r2.impacts} == {OTHER.id}


def test_target_article_missing_and_already_exists_are_unresolved() -> None:
    pts = (
        "1. Pasal 42 dihapus.",
        "2. Di antara Pasal 5 dan Pasal 6 disisipkan 1 (satu) Pasal, yakni Pasal 5A, yang berbunyi sebagai berikut: x",
        "3. Di antara Pasal 5 dan Pasal 77 disisipkan 1 (satu) Pasal, yakni Pasal 5B, yang berbunyi sebagai berikut: x",
    )
    e, inp, _ = amend_input(pts)
    ta = target_articles(*[str(i) for i in range(1, 10)], "5A")
    res = analyze_impact(e, inp.model_copy(update={"target_articles": {TARGET.id: ta}}))
    reasons = {(i.article_number, i.unresolved_reason, i.target_check) for i in res.impacts}
    assert ("42", "TARGET_ARTICLE_MISSING", TargetCheck.MISSING) in reasons
    assert ("5A", "ARTICLE_ALREADY_EXISTS", TargetCheck.ALREADY_EXISTS) in reasons
    assert ("5B", "ANCHOR_MISSING", TargetCheck.MISSING) in reasons
    assert res.changed == () and res.withdrawn == ()


def test_without_target_articles_nothing_is_confirmed() -> None:
    e, inp, _ = amend_input(targets=False)
    res = analyze_impact(e, inp)
    assert {i.target_check for i in res.impacts} == {TargetCheck.NOT_CHECKED}
    assert all(i.status is ImpactStatus.RESOLVED for i in res.impacts)
    assert all(c.supersedes is None for c in res.changed)


def test_partial_document_makes_the_result_incomplete_and_flags_items() -> None:
    e = ev(ACTOR, T.AMEND, TARGET)
    docs = {ACTOR.id: doc(ACTOR, amending(INTRO, "1. Pasal 7 dihapus."), fail=True)}
    res = analyze_impact(e, make([e], docs))
    assert not res.complete and res.incomplete_sources[0].status == "PARTIAL"
    assert res.impacts and all(i.source_status == "PARTIAL" for i in res.impacts)


def test_missing_document_and_empty_impacts_are_never_no_impact() -> None:
    e = ev(ACTOR, T.AMEND, TARGET)
    res = analyze_impact(e, make([e]))
    assert res.impacts == () and not res.complete
    assert (
        res.incomplete_sources[0].ref == ACTOR.id and res.incomplete_sources[0].status == "MISSING"
    )
    no_units = doc(ACTOR, "Pasal 1\nisi")
    res2 = analyze_impact(e, make([e], {ACTOR.id: no_units}))
    assert [u.reason for u in res2.unresolved_operations] == [
        "NO_AMENDMENT_UNITS"
    ] and res2.complete


def test_target_document_not_ok_is_listed_as_incomplete() -> None:
    e, inp, _ = amend_input()
    inp = inp.model_copy(
        update={"target_articles": {TARGET.id: target_articles("5", status=DocStatus.PARTIAL)}}
    )
    res = analyze_impact(e, inp)
    assert not res.complete and res.incomplete_sources[0].ref == TARGET.id


def test_unrelated_failed_document_does_not_affect_completeness() -> None:
    e, inp, docs = amend_input()
    docs[OTHER.id] = doc(OTHER, "x", fail=True)
    assert analyze_impact(e, inp.model_copy(update={"documents": docs})).complete


def test_repeal_is_regulation_level_with_derived_article_items() -> None:
    e = ev(ACTOR, T.REPEAL, TARGET)
    res = analyze_impact(e, make([e], targets={TARGET.id: target_articles("1", "2", "3")}))
    top = [i for i in res.impacts if i.article_number is None]
    assert len(top) == 1 and not top[0].derived and top[0].effect is Effect.REPEALED
    derived = [i for i in res.impacts if i.derived]
    assert [i.article_number for i in derived] == ["1", "2", "3"] and len(res.withdrawn) == 3
    assert len(analyze_impact(e, make([e])).impacts) == 1


SCOPE = (
    "Pasal 20\nPada saat Peraturan Pemerintah ini mulai berlaku, Pasal 5 sampai dengan Pasal 8 "
    "Peraturan Pemerintah Nomor 10 Tahun 2020 tentang Target dicabut dan dinyatakan tidak berlaku."
)


def test_partial_repeal_with_parseable_scope() -> None:
    e = ev(ACTOR, T.PARTIAL_REPEAL, TARGET)
    docs = {ACTOR.id: doc(ACTOR, "BAB I\nPasal 1\nx\n" + SCOPE.replace("Pasal 20", "Pasal 2"))}
    res = analyze_impact(e, make([e], docs, {TARGET.id: target_articles(*"123456789")}))
    assert sorted((i.article_number, i.effect) for i in res.impacts) == [
        (str(n), Effect.REPEALED) for n in range(5, 9)
    ]
    assert len(res.withdrawn) == 4 and all(i.source.spans for i in res.impacts)


def test_partial_repeal_without_scope_is_unresolved_not_everything_else() -> None:
    e = ev(ACTOR, T.PARTIAL_REPEAL, TARGET)
    docs = {ACTOR.id: doc(ACTOR, "BAB I\nPasal 1\nketentuan lain yang tidak menyebut apa pun.")}
    res = analyze_impact(e, make([e], docs))
    (item,) = res.impacts
    assert (item.effect, item.article_number, item.status, item.unresolved_reason) == (
        Effect.PARTIALLY_REPEALED,
        None,
        ImpactStatus.UNRESOLVED,
        "SCOPE_UNRESOLVED",
    )
    assert res.withdrawn == ()


def test_partial_repeal_of_another_regulation_is_not_used() -> None:
    e = ev(ACTOR, T.PARTIAL_REPEAL, TARGET)
    other_scope = SCOPE.replace("Nomor 10 Tahun 2020", "Nomor 11 Tahun 2021")
    docs = {
        ACTOR.id: doc(ACTOR, "BAB I\nPasal 1\nx\n" + other_scope.replace("Pasal 20", "Pasal 2"))
    }
    (item,) = analyze_impact(e, make([e], docs)).impacts
    assert item.unresolved_reason == "SCOPE_UNRESOLVED"


def test_new_event_exposes_its_own_articles_not_impacts() -> None:
    e = ev(ACTOR, T.NEW)
    res = analyze_impact(
        e, make([e], {ACTOR.id: doc(ACTOR, "BAB I\nPasal 1\nisi satu\nPasal 2\nisi dua")})
    )
    assert (
        res.impacts == ()
        and [c.kind for c in res.changed] == [ChangedKind.NEW_REGULATION_ARTICLE] * 2
    )
    assert [c.article_number for c in res.changed] == ["1", "2"]
    assert not analyze_impact(e, make([e])).complete


def test_new_wording_pointer_verifies_against_unit_text_and_provenance() -> None:
    e, inp, docs = amend_input()
    res = analyze_impact(e, inp)
    d = docs[ACTOR.id]
    unit = d.amendment_units[0]
    for c in res.changed:
        assert c.text_ref.owner_id == unit.id and unit.text[c.text_ref.start : c.text_ref.end]
    assert all(i.source.spans for i in res.impacts)
    for i in res.impacts:
        for sp in i.source.spans:
            assert sp.document_id == d.document.id


def test_changed_provisions_are_deterministic_and_inputs_untouched() -> None:
    e, inp, _ = amend_input()
    snap = inp.model_dump_json()
    a, b = analyze_impact(e, inp), analyze_impact(e, inp)
    assert a.model_dump_json() == b.model_dump_json() and inp.model_dump_json() == snap


@pytest.mark.parametrize("kind", [K.PP, K.UU])
def test_real_domain_objects_accepted(kind: K) -> None:
    r = reg(kind, "99", 2024)
    e = ev(r, T.NEW)
    assert analyze_impact(e, make([e], regs=[r])).impacts == ()
