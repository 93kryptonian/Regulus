import pytest
from ob_helpers import cands, one, run, val

from regulus.obligations import FieldStatus as F
from regulus.obligations import Modality as M
from regulus.obligations import ResultStatus as S
from regulus.obligations.models import DiagCode


def st(f) -> F:  # type: ignore[no-untyped-def]
    return f.status


def test_basic_candidate_and_not_stated_fields() -> None:
    c = one("Pasal 1\nPelaku usaha wajib menyampaikan laporan kepada Lembaga.")
    assert (val(c.actor), c.marker.value, val(c.action), val(c.object)) == (
        "Pelaku usaha",
        "wajib",
        "menyampaikan",
        "laporan",
    )
    assert c.modality is M.OBLIGATION
    assert st(c.deadline) is F.NOT_STATED and st(c.frequency) is F.NOT_STATED
    assert c.conditions == () and c.exceptions == () and c.undetermined == ()


def test_frequency_is_stated_or_not_stated_never_inferred() -> None:
    c = one("Pasal 1\nPelaku usaha wajib menyampaikan laporan setiap 3 bulan.")
    assert val(c.frequency) == "setiap 3 bulan" and val(c.object) == "laporan"
    c2 = one("Pasal 1\nPelaku usaha wajib menyampaikan laporan.")
    assert st(c2.frequency) is F.NOT_STATED
    c3 = one("Pasal 1\nPelaku usaha wajib menyampaikan laporan secara berkala.")
    assert val(c3.frequency) == "secara berkala"
    c4 = one("Pasal 1\nPelaku usaha wajib melapor setiap tahun.")
    assert (val(c4.action), val(c4.frequency), c4.object.status) == (
        "melapor",
        "setiap tahun",
        F.NOT_STATED,
    )


def test_deadline_forms_are_verbatim() -> None:
    c = one("Pasal 1\nPengendali wajib memberitahukan kegagalan paling lambat 3 x 24 jam.")
    assert val(c.deadline) == "paling lambat 3 x 24 jam" and val(c.object) == "kegagalan"
    c2 = one(
        "Pasal 1\nPengendali wajib memberitahukan kegagalan paling lama 14 (empat belas) hari kerja setelah diketahui."
    )
    assert val(c2.deadline) == "paling lama 14 (empat belas) hari kerja setelah diketahui"
    assert (
        val(
            one(
                "Pasal 1\nPengendali wajib memberitahukan kegagalan dalam jangka waktu 30 hari."
            ).deadline
        )
        == "dalam jangka waktu 30 hari"
    )


def test_deadline_trigger_without_duration_is_undetermined() -> None:
    c = one("Pasal 1\nPengendali wajib memberitahukan kegagalan paling lambat segera.")
    assert st(c.deadline) is F.UNDETERMINED and c.deadline.reason


def test_leading_condition_and_actor_after_the_comma() -> None:
    c = one("Pasal 1\nDalam hal terjadi kegagalan, Pengendali wajib memberitahukan Subjek.")
    assert [x.value for x in c.conditions] == ["Dalam hal terjadi kegagalan"] and val(
        c.actor
    ) == "Pengendali"


def test_leading_adjunct_without_comma_leaves_actor_undetermined() -> None:
    c = one("Pasal 1\nApabila terjadi kegagalan Pengendali wajib memberitahukan Subjek.")
    assert st(c.actor) is F.UNDETERMINED and c.undetermined == ("conditions",)


def test_trailing_condition_and_exception() -> None:
    c = one(
        "Pasal 1\nPengendali wajib menghapus data apabila diminta Subjek, kecuali ditentukan lain oleh hukum."
    )
    assert [x.value for x in c.conditions] == ["apabila diminta Subjek"]
    assert [x.value for x in c.exceptions] == ["kecuali ditentukan lain oleh hukum"] and val(
        c.object
    ) == "data"


def test_exception_with_nothing_after_it_is_undetermined() -> None:
    c = one("Pasal 1\nPengendali wajib menghapus data kecuali.")
    assert c.exceptions == () and c.undetermined == ("exceptions",)


def test_prohibition_and_impersonal_actor() -> None:
    c = one("Pasal 1\nSetiap Orang dilarang menggunakan data pribadi milik orang lain.")
    assert (
        c.modality is M.PROHIBITION
        and val(c.actor) == "Setiap Orang"
        and val(c.action) == "menggunakan"
    )
    assert st(one("Pasal 1\nDilarang menggunakan data pribadi.").actor) is F.NOT_STATED
    assert one("Pasal 1\nPengendali tidak boleh menjual data.").marker.value == "tidak boleh"


def test_permissions_and_non_deontic_text_yield_nothing() -> None:
    for t in (
        "Pengendali dapat menggunakan data.",
        "Subjek berhak meminta penjelasan.",
        "Subjek boleh mengajukan keberatan.",
    ):
        out, _ = run(f"Pasal 1\n{t}")
        assert out.results[0].status is S.NO_OBLIGATION and out.results[0].diagnostics == ()


def test_negated_marker_is_an_exemption_not_a_duty() -> None:
    out, _ = run("Pasal 1\nPengendali tidak wajib menunjuk petugas.")
    r = out.results[0]
    assert r.status is S.NO_OBLIGATION and [d.code for d in r.diagnostics] == [
        DiagCode.NEGATED_MARKER
    ]
    out2, _ = run("Pasal 1\nPengendali tidak harus melapor.")
    assert out2.results[0].candidates == ()


def test_whole_word_markers_only() -> None:
    out, _ = run(
        "Pasal 1\nKewajiban penunjukan sebagaimana dimaksud dalam Pasal 5 dilaksanakan oleh Menteri."
    )
    assert out.results[0].status is S.NO_OBLIGATION
    assert [c.marker.value for c in cands("Pasal 1\nPengendali berkewajiban menyimpan arsip.")] == [
        "berkewajiban"
    ]
    assert cands("Pasal 1\nPengendali diwajibkan menyimpan arsip.")[0].marker.value == "diwajibkan"


def test_two_sentences_two_candidates_and_nothing_crosses() -> None:
    cs = cands(
        "Pasal 1\nA wajib menyampaikan laporan apabila diminta. B wajib menyimpan arsip paling lambat 3 hari."
    )
    assert [(val(c.actor), val(c.action)) for c in cs] == [
        ("A", "menyampaikan"),
        ("B", "menyimpan"),
    ]
    assert [x.value for x in cs[0].conditions] == ["apabila diminta"] and cs[1].conditions == ()
    assert st(cs[0].deadline) is F.NOT_STATED and val(cs[1].deadline) == "paling lambat 3 hari"


def test_repeated_marker_gives_two_candidates_sharing_the_actor() -> None:
    a, b = cands("Pasal 1\nPengendali wajib menyampaikan laporan dan wajib menyimpan arsip.")
    assert (
        val(a.actor) == val(b.actor) == "Pengendali"
        and a.actor.value.citation == b.actor.value.citation
    )  # type: ignore[union-attr]
    assert (val(a.action), val(b.action)) == ("menyampaikan", "menyimpan") and val(
        a.object
    ) == "laporan"


def test_coordinated_predicates_under_one_marker_stay_one_candidate() -> None:
    c = one("Pasal 1\nPengendali wajib menyampaikan laporan dan menyimpan arsip.")
    assert (
        val(c.action) == "menyampaikan laporan dan menyimpan arsip"
        and st(c.object) is F.UNDETERMINED
    )
    assert c.object.reason == "coordinated predicates under one marker"


def test_modality_change_in_one_sentence_gives_two_candidates() -> None:
    a, b = cands("Pasal 1\nPengendali wajib menyimpan arsip dan dilarang menghapus arsip.")
    assert (a.modality, b.modality) == (M.OBLIGATION, M.PROHIBITION)
    assert (val(a.action), val(b.action)) == ("menyimpan", "menghapus") and val(a.object) == "arsip"


def test_actor_with_comma_is_undetermined_not_guessed() -> None:
    c = one("Pasal 1\nDalam melakukan pemrosesan, Pengendali wajib menunjukkan bukti.")
    assert st(c.actor) is F.UNDETERMINED and c.actor.reason == "comma inside the actor phrase"


def test_object_with_comma_is_undetermined() -> None:
    c = one("Pasal 1\nPengendali wajib menyimpan arsip, dokumen, dan catatan.")
    assert st(c.object) is F.UNDETERMINED


def test_non_verb_after_marker_means_no_candidate_but_never_silent() -> None:
    out, _ = run("Pasal 1\nRencana lokasi harus sesuai dengan rencana tata ruang.")
    r = out.results[0]
    assert r.status is S.UNRESOLVED and r.candidates == ()
    assert [d.code for d in r.diagnostics] == [DiagCode.UNEXTRACTED_DEONTIC]


def test_marker_inside_a_cross_reference_still_surfaces() -> None:
    out, _ = run("Pasal 1\nKetentuan yang harus dipenuhi sebagaimana dimaksud dalam Pasal 5.")
    r = out.results[0]
    assert r.candidates or [d.code for d in r.diagnostics] == [DiagCode.UNEXTRACTED_DEONTIC]


def test_definition_and_authority_provisions_are_a_valid_no_obligation() -> None:
    out, _ = run(
        "Pasal 1\nDalam Peraturan ini yang dimaksud dengan:\n1. Data Pribadi adalah data tentang orang.\nPasal 2\nLembaga berwenang melakukan pengawasan."
    )
    assert [r.status for r in out.results] == [S.NO_OBLIGATION, S.NO_OBLIGATION]


def test_unlisted_lexeme_is_a_documented_recall_limit() -> None:
    out, _ = run("Pasal 1\nMenteri mewajibkan pengendali melapor.")
    assert out.results[0].status is S.NO_OBLIGATION


def test_untuk_after_the_marker_is_skipped() -> None:
    c = one("Pasal 1\nPengendali berkewajiban untuk menyimpan arsip.")
    assert val(c.action) == "menyimpan" and val(c.object) == "arsip"


def test_abbreviations_do_not_end_a_sentence() -> None:
    c = one("Pasal 1\nPengendali sesuai Peraturan No. 5 wajib menyimpan arsip.")
    assert val(c.actor) == "Pengendali sesuai Peraturan No. 5"


@pytest.mark.parametrize(
    "text",
    ["Pasal 1\n(1) Pengendali wajib menyimpan arsip.", "Pasal1\nPengendali wajib menyimpan arsip."],
)
def test_heading_and_ayat_label_are_not_part_of_the_actor(text: str) -> None:
    assert val(one(text).actor) == "Pengendali"


def test_wrapped_lines_are_handled() -> None:
    c = one("Pasal 1\nPengendali Data\nPribadi wajib menyampaikan\nlaporan setiap\n3 bulan.")
    assert val(c.actor) == "Pengendali Data\nPribadi" and val(c.frequency) == "setiap\n3 bulan"
