import pytest

from regulus.lineage.amendment import (
    Locator as L,
)
from regulus.lineage.amendment import (
    Operation,
    OpKind,
    Reason,
    TargetLevel,
    Unresolved,
    parse_locator,
    parse_operation,
)


def op(text: str) -> Operation:
    r = parse_operation(text)
    assert isinstance(r, Operation), r
    return r


def bad(text: str, reason: Reason) -> None:
    r = parse_operation(text)
    assert isinstance(r, Unresolved) and r.reason is reason, r


def test_modify_article_and_new_text_pointer() -> None:
    t = "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut:\nPasal 5\n(1) Setiap orang wajib.\n"
    o = op(t)
    assert o.kind is OpKind.MODIFY and o.locators == (L(article="5"),)
    assert t[o.sentence[0] : o.sentence[1]].endswith("berikut:")
    assert o.new_text and t[o.new_text[0] : o.new_text[1]].startswith("Pasal 5\n(1)")
    assert t[o.new_text[1] - 1] == "."


@pytest.mark.parametrize("sep", [" :", ":", "", ",", " "])
def test_terminating_colon_is_optional_formula_words_are_exact(sep: str) -> None:
    o = op(
        f"2. Ketentuan Pasal 1 ayat (5) diubah sehingga berbunyi sebagai berikut{sep} Organisasi pers ialah x."
    )
    assert o.locators == (L(article="1", path=("(5)",)),)
    assert o.new_text is not None


def test_locator_forms() -> None:
    assert parse_locator("Pasal 5") == (L(article="5"),)
    assert parse_locator("Pasal 5A") == (L(article="5A"),)
    assert parse_locator("Pasal 5 dan Pasal 6") == (L(article="5"), L(article="6"))
    assert parse_locator("Pasal 5, Pasal 7 dan Pasal 9") == (
        L(article="5"),
        L(article="7"),
        L(article="9"),
    )
    assert parse_locator("Pasal 5 sampai dengan Pasal 8") == tuple(
        L(article=str(i)) for i in range(5, 9)
    )
    assert parse_locator("ayat (2) dan ayat (3) Pasal 5") == (
        L(article="5", path=("(2)",)),
        L(article="5", path=("(3)",)),
    )
    assert parse_locator("Pasal 5 ayat (2)") == (L(article="5", path=("(2)",)),)
    assert parse_locator("huruf b ayat (2) Pasal 5") == (L(article="5", path=("(2)", "b")),)
    assert parse_locator("Pasal 5 ayat (2) huruf b") == (L(article="5", path=("(2)", "b")),)
    assert parse_locator("pasal  5  AYAT ( 2 )") == (L(article="5", path=("(2)",)),)


@pytest.mark.parametrize(
    "loc",
    [
        "Pasal I",
        "Pasal",
        "Pasal 8 sampai dengan Pasal 5",
        "Pasal 5A sampai dengan Pasal 7",
        "judul Bab 11",
        "ayat (2)",
        "Pasal 5 dan",
    ],
)
def test_unparseable_locators_are_unresolved_not_guessed(loc: str) -> None:
    bad(f"1. Ketentuan {loc} diubah sehingga berbunyi sebagai berikut:", Reason.LOCATOR_UNPARSEABLE)


@pytest.mark.parametrize(
    "loc", ["BAB II", "Bagian Kedua", "Paragraf 1", "Penjelasan Pasal 5", "Lampiran I"]
)
def test_structural_locators_are_recognized_and_unsupported(loc: str) -> None:
    bad(f"1. Ketentuan {loc} diubah sehingga berbunyi sebagai berikut:", Reason.UNSUPPORTED_LOCATOR)


def test_delete_and_repeal_provision() -> None:
    assert op("1. Pasal 7 dihapus.").kind is OpKind.DELETE
    d = op("2. Ketentuan ayat (3) Pasal 5 dihapus.")
    assert (
        d.kind is OpKind.DELETE
        and d.locators == (L(article="5", path=("(3)",)),)
        and d.new_text is None
    )
    assert op("3. Pasal 9 dicabut.").kind is OpKind.REPEAL_PROVISION
    assert op(
        "4. Pasal 5 sampai dengan Pasal 8 dicabut dan dinyatakan tidak berlaku."
    ).locators == tuple(L(article=str(i)) for i in range(5, 9))


def test_insert_article_ayat_huruf() -> None:
    a = op(
        "1. Di antara Pasal 5 dan Pasal 6 disisipkan 1 (satu) Pasal, yakni Pasal 5A, yang berbunyi sebagai berikut:\nPasal 5A\nisi"
    )
    assert (
        a.kind is OpKind.INSERT
        and a.target_level is TargetLevel.ARTICLE
        and a.locators == (L(article="5A"),)
    )
    assert [x.article for x in a.anchors] == ["5", "6"]
    y = op(
        "2. Di antara ayat (2) dan ayat (3) Pasal 5 disisipkan 1 (satu) ayat, yakni ayat (2a), yang berbunyi sebagai berikut: (2a) isi"
    )
    assert y.target_level is TargetLevel.AYAT and y.locators == (L(article="5", path=("(2a)",)),)
    h = op(
        "3. Di antara huruf a dan huruf b ayat (2) Pasal 5 disisipkan 1 (satu) huruf, yakni huruf a1, yang berbunyi sebagai berikut: a1. isi"
    )
    assert h.target_level is TargetLevel.HURUF and h.locators == (
        L(article="5", path=("(2)", "a1")),
    )


@pytest.mark.parametrize(
    "text",
    [
        "1. Di antara Pasal 5 dan Pasal 6 disisipkan 1 (satu) Pasal, yakni ayat (2a), yang berbunyi sebagai berikut:",
        "1. Di antara Pasal 5 dan Pasal 6 disisipkan 1 (satu) BAB, yakni BAB IIA, yang berbunyi sebagai berikut:",
        "1. Di antara ayat (2) dan ayat (3) disisipkan 1 (satu) ayat, yakni ayat (2a), yang berbunyi sebagai berikut:",
    ],
)
def test_insert_with_inconsistent_or_unsupported_unit_is_unresolved(text: str) -> None:
    assert isinstance(parse_operation(text), Unresolved)


def test_append() -> None:
    o = op(
        "1. Pasal 6 ditambah 1 (satu) ayat, yakni ayat (6), yang berbunyi sebagai berikut: (6) isi"
    )
    assert (
        o.kind is OpKind.APPEND
        and o.target_level is TargetLevel.AYAT
        and o.locators == (L(article="6"),)
    )


def test_replace_term_keeps_old_and_new() -> None:
    o = op('1. Kata "Menteri" dalam Pasal 5 ayat (2) diganti dengan kata "Kepala Badan".')
    assert (o.kind, o.old_term, o.new_term) == (OpKind.REPLACE_TERM, "Menteri", "Kepala Badan")
    assert o.locators == (L(article="5", path=("(2)",)),)
    c = op("2. Frasa “Dewan Telekomunikasi” dalam Pasal 7 diganti dengan “Menteri”")
    assert (c.old_term, c.new_term) == ("Dewan Telekomunikasi", "Menteri")


@pytest.mark.parametrize(
    "text",
    [
        "1. Pasal 5 diperbaiki seperlunya.",
        "2. Pada Pasal 1, ditambahkan dengan ketentuan huruf d, e, dan f yang berbunyi sebagai berikut :",
        '3. Pada Pasal 5, perkataan "Dewan Telekomunikasi" diubah menjadi "Menteri"',
        "4. Ditambah ayat baru menjadi ayat (6) yang berbunyi sebagai berikut:",
        "",
    ],
)
def test_unknown_formulas_are_unresolved_with_nothing_inferred(text: str) -> None:
    bad(text, Reason.UNSUPPORTED_OPERATION)


def test_two_matching_patterns_are_ambiguous_not_first_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import re

    from regulus.lineage import amendment

    patterns = dict(amendment._PATTERNS)
    patterns[OpKind.REPEAL_PROVISION] = re.compile(r"^(?P<loc>Pasal\s+5)\s+dihapus\.$")
    monkeypatch.setattr(amendment, "_PATTERNS", patterns)
    bad("1. Pasal 5 dihapus.", Reason.AMBIGUOUS_OPERATION)


def test_sentence_with_colon_before_the_verb_is_not_matched() -> None:
    bad(
        "5. Pada Pasal 6 : Ketentuan ayat (1) diubah sehingga berbunyi sebagai berikut:",
        Reason.UNSUPPORTED_OPERATION,
    )


def test_real_instrument_formulas_pp20_1980_stay_unresolved() -> None:
    bad(
        '1. Pada judul Peraturan Pemerintah Nomor 21 Tahun 1967 yang berbunyi "Radio Amatirisme di Indonesia" '
        'diubah, sehingga berbunyi sebagai berikut : "Kegiatan Amatir Radio".',
        Reason.LOCATOR_UNPARSEABLE,
    )
    bad(
        "2. Pada Pasal 1, ditambahkan dengan ketentuan huruf d, e, dan f yang berbunyi sebagai berikut :",
        Reason.UNSUPPORTED_OPERATION,
    )
    bad(
        "5. Pada Pasal 6 :\na. Ketentuan ayat (1), ayat (3) dan ayat (5) diubah, sehingga berbunyi sebagai berikut :",
        Reason.UNSUPPORTED_OPERATION,
    )


def test_real_instrument_formulas_uu21_1982() -> None:
    ok = op(
        "2. Ketentuan Pasal 1 ayat (5) diubah sehingga berbunyi sebagai berikut Organisasi pers ialah organisasi wartawan."
    )
    assert ok.locators == (L(article="1", path=("(5)",)),)
    bad(
        "3. Ketentuan Pasal I ayat (10) diubah sehingga berbunyi sebagai berikut Pemerintah dalam ini adalah Menteri.",
        Reason.LOCATOR_UNPARSEABLE,
    )
    bad(
        "4. judul Bab 11 diubah sehingga berbunyi sebagai berikut TUGAS, FUNGSI, HAK DAN KEWAJIBAN PERS.",
        Reason.LOCATOR_UNPARSEABLE,
    )
    bad(
        "1.a Istilah-istilah dalam Undang-undang Nomor Tahun 1966 diubah sebagai berikut:",
        Reason.UNSUPPORTED_OPERATION,
    )


def test_offsets_are_relative_to_the_given_text() -> None:
    t = "12. Pasal 7 dihapus."
    o = op(t)
    assert t[o.sentence[0] : o.sentence[1]] == "Pasal 7 dihapus."


def test_parse_is_deterministic() -> None:
    t = "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut: isi"
    assert parse_operation(t) == parse_operation(t)
