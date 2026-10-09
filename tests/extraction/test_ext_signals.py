import pytest
from ext_helpers import prov

from regulus.documents.models import Level
from regulus.extraction import SignalKind as K
from regulus.extraction import load_signals
from regulus.extraction.signals import SignalMatcher, selects_term
from regulus.obligations import load_lexicon

M = SignalMatcher(load_signals(), load_lexicon())


def kinds(text: str, **kw) -> list[tuple[str, str]]:
    return [(s.kind.value, s.term) for s in M.signals(text, **kw)]


def test_no_signal_is_explicit_and_exclusive() -> None:
    got = M.signals("Pasal 1\nBerikut uraian umum tanpa kata kunci.", own_label="1")
    assert [s.kind for s in got] == [K.NO_SIGNAL] and (got[0].start, got[0].end) == (0, 0)


def test_whole_word_and_case_insensitive() -> None:
    assert ("PERMISSION", "dapat") in kinds("Pelaku DAPAT mengajukan")
    assert not any(k == "PERMISSION" for k, _ in kinds("mendapatkan dapatkan"))
    assert not any(k == "SANCTION" for k, _ in kinds("dendang dendanya"))


def test_every_kind_with_exact_offsets() -> None:
    text = (
        "Pasal 9\nDalam hal terjadi insiden, pelaku usaha wajib menyampaikan laporan paling lama 3 (tiga) hari "
        "setiap bulan dan dilarang menyimpan data; pelaku dapat mengajukan keberatan, "
        "dikenakan sanksi administratif, bertanggung jawab; sesuai Pasal 2 ayat (1). "
        "Yang dimaksud dengan data adalah informasi. Laporan disampaikan."
    )
    provs = (
        prov("o", Level.HURUF, ("1", "a"), "a", (10, 12)),
        prov("o", Level.HURUF, ("1", "b"), "b", (20, 30)),
    )
    got = M.signals(text, provs, "9")
    found = {s.kind for s in got}
    assert found == {
        K.EXPLICIT_OBLIGATION, K.EXPLICIT_PROHIBITION, K.PERMISSION, K.SANCTION,
        K.RESPONSIBILITY, K.DUTY_VERB, K.PASSIVE_DUTY, K.CONDITION, K.DEADLINE,
        K.FREQUENCY, K.ENUMERATION, K.DEFINITION, K.CROSS_REFERENCE,
    }  # fmt: skip
    for s in got:
        assert selects_term(text, s)
        if s.kind not in (K.ENUMERATION, K.NO_SIGNAL):
            assert " ".join(text[s.start : s.end].lower().split()) == s.term
    enum = next(s for s in got if s.kind is K.ENUMERATION)
    assert (enum.start, enum.end) == (10, 30)


def test_multiword_span_with_irregular_whitespace() -> None:
    text = "Pasal 1\nPelaku  dikenakan\nsanksi   administratif."
    s = next(s for s in M.signals(text, own_label="1") if s.kind is K.SANCTION)
    assert text[s.start : s.end] == "dikenakan\nsanksi" and s.term == "dikenakan sanksi"


def test_offsets_are_code_points_not_bytes() -> None:
    text = "Pasal 1\n“Pelaku” — café “naïve” wajib melapor, tidak boleh diubah."
    got = M.signals(text, own_label="1")
    ob = next(s for s in got if s.kind is K.EXPLICIT_OBLIGATION)
    assert text[ob.start : ob.end] == "wajib" and ob.start != len(text[: ob.start].encode())
    assert all(selects_term(text, s) for s in got)


def test_negated_marker_is_not_an_explicit_signal_and_prohibition_not_permission() -> None:
    got = kinds("Pelaku tidak wajib melapor.")
    assert not any(k.startswith("EXPLICIT") for k, _ in got)
    got = kinds("Pelaku tidak boleh menyimpan dan tidak diperbolehkan menghapus.")
    assert ("EXPLICIT_PROHIBITION", "tidak boleh") in got
    assert not any(k == "PERMISSION" for k, _ in got)


def test_permission_and_passive_are_never_obligations() -> None:
    got = kinds("Pelaku berhak dan dapat mengajukan; laporan disimpan.")
    assert not any(k.startswith("EXPLICIT") for k, _ in got)
    assert {"PERMISSION", "PASSIVE_DUTY"} <= {k for k, _ in got}


def test_self_reference_is_not_a_signal_and_other_is() -> None:
    got = kinds("Pasal 4\nsebagaimana dimaksud dalam Pasal 4 dan Pasal 7 ayat (2)", own_label="4")
    assert [t for k, t in got if k == "CROSS_REFERENCE"] == ["pasal 7 ayat (2)"]


def test_ordering_is_stable_and_total() -> None:
    text = "Pasal 1\nwajib dan dilarang dan dapat dan denda dan wajib"
    a = M.signals(text, own_label="1")
    assert a == M.signals(text, own_label="1")
    keys = [(s.start, s.end) for s in a]
    assert keys == sorted(keys)


def test_very_long_article_is_not_truncated() -> None:
    text = "Pasal 1\n" + "Pelaku wajib melapor. " * 5000
    got = [s for s in M.signals(text, own_label="1") if s.kind is K.EXPLICIT_OBLIGATION]
    assert len(got) == 5000 and all(selects_term(text, s) for s in got)


@pytest.mark.parametrize("phrase", ["setiap bulan", "setiap 3 (tiga) bulan", "secara berkala"])
def test_frequency_forms(phrase: str) -> None:
    assert ("FREQUENCY", phrase) in kinds(f"Pelaku melapor {phrase}.")


def test_exception_triggers_map_to_condition() -> None:
    got = kinds("Pelaku wajib melapor, kecuali dikecualikan oleh Menteri.")
    assert [t for k, t in got if k == "CONDITION"] == ["kecuali", "dikecualikan"]


def test_negated_marker_is_omitted_here_but_kept_by_phase6() -> None:
    from ext_helpers import article_text, make_result

    from regulus.extraction import build_package

    r = make_result([("1", article_text("1", "Pelaku usaha tidak wajib melapor."))])
    u = build_package(r).units[0]
    assert not any(s.kind.value.startswith("EXPLICIT") for s in u.signals)
    assert any(d.code == "NEGATED_MARKER" for d in u.phase6.diagnostics)
    assert u.phase6.status.value == "NO_OBLIGATION" and u.phase6.candidates == ()
