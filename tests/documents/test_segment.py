from helpers import REG, STD, pages, seg

from regulus.documents.models import Code, Level
from regulus.documents.provenance import locate, reconstruct
from regulus.documents.segment import int_to_roman, roman_to_int


def codes(r) -> list[Code]:  # type: ignore[no-untyped-def]
    return [d.code for d in r.diagnostics]


def test_standard_body_articles_and_zones() -> None:
    r = seg(STD)
    assert [a.number for a in r.articles] == ["1", "2", "3"]
    assert r.articles[0].id == f"{REG}:1" and r.articles[0].text.startswith("Pasal 1\nDalam")
    assert "KETENTUAN" not in r.articles[0].text and "Ditetapkan" not in r.articles[2].text
    assert r.articles[2].text.endswith("patuh.")
    assert [e.article_number for e in r.explanations] == ["1", "2", "3"]
    assert r.explanations[0].text == "Pasal 1\nCukup jelas."
    assert r.diagnostics == [] and r.units == []


def test_parent_paths() -> None:
    r = seg(STD)
    assert [a.parent for a in r.articles] == [
        "BAB I",
        "BAB I",
        "BAB II > Bagian Kesatu > Paragraf 1",
    ]


def test_preamble_pasal_references_do_not_open_articles() -> None:
    r = seg(STD)
    assert all("UUD" not in a.text for a in r.articles)


def test_provisions_and_nesting() -> None:
    r = seg(STD)
    by = {(p.owner_id, p.path): p for p in r.provisions}
    assert (f"{REG}:2", ("(2)", "a")) in by and by[(f"{REG}:2", ("(2)", "b"))].level is Level.HURUF
    assert by[(f"{REG}:1", ("1",))].level is Level.ANGKA
    assert by[(f"{REG}:2", ("(1)",))].text == "(1) Pengendali wajib melapor."
    art = next(a for a in r.articles if a.number == "2")
    for p in r.provisions:
        if p.owner_id == art.id:
            assert art.text[p.span[0] : p.span[1]] == p.text


def test_stray_huruf_and_out_of_order_ayat_stay_text() -> None:
    r = seg("BAB I\nPasal 1\n(1) satu\nb. stray\n(3) lompat\n(2) dua")
    paths = [p.path for p in r.provisions]
    assert ("(1)",) in paths and ("b",) not in paths and ("(3)",) not in paths
    assert ("(2)",) in paths
    assert codes(r).count(Code.MARKER_OUT_OF_SEQUENCE) == 2
    assert "b. stray" in r.articles[0].text


def test_article_gap_duplicate_backward() -> None:
    r = seg("BAB I\nPasal 1\na\nPasal 3\nb\nPasal 3\nc\nPasal 2\nd\nPasal 4\ne")
    assert [a.number for a in r.articles] == ["1", "3", "4"]
    assert codes(r).count(Code.ARTICLE_GAP) == 1 and codes(r).count(Code.DUPLICATE_ARTICLE) == 2
    gap = next(d for d in r.diagnostics if d.code is Code.ARTICLE_GAP)
    assert gap.detail == "2" and gap.article_number == "3"


def test_first_article_not_one_is_gap() -> None:
    r = seg("BAB I\nPasal 3\nx")
    assert r.diagnostics[0].code is Code.ARTICLE_GAP and r.diagnostics[0].detail == "1,2"


def test_lettered_articles() -> None:
    r2 = seg("BAB I\nPasal 1\nx\nPasal 1A\ny\nPasal 1B\nz\nPasal 2\nw\nPasal 2\nv")
    assert [a.number for a in r2.articles] == ["1", "1A", "1B", "2"]
    assert codes(r2) == [Code.DUPLICATE_ARTICLE]


def test_tolerates_missing_space_marker() -> None:
    r = seg("BAB I\nPasal1\nx\nPasal2\ny")
    assert [a.number for a in r.articles] == ["1", "2"]


def test_article_crossing_page_break_has_two_fragments() -> None:
    r = seg("BAB I\nPasal 1\nawal kalimat", "lanjutan kalimat\nPasal 2\nlain")
    a1 = r.articles[0]
    assert a1.text == "Pasal 1\nawal kalimat\nlanjutan kalimat" and (
        a1.page_start,
        a1.page_end,
    ) == (1, 2)
    assert [f.page for f in r.provenance[a1.id]] == [1, 2]


def test_marker_as_last_line_of_page() -> None:
    r = seg("BAB I\nPasal 1\nx\nPasal 2", "isi pasal dua")
    a2 = r.articles[1]
    assert a2.text == "Pasal 2\nisi pasal dua" and (a2.page_start, a2.page_end) == (1, 2)


def test_headers_and_labels_removed_across_pages() -> None:
    texts = [
        f"PRESIDEN\nREPUBLIK\n- {i} -\n" + b
        for i, b in enumerate(["BAB I\nPasal 1\na", "b\nPasal 2\nc", "d", "e\nPasal 3\nf", "g"], 1)
    ]
    r = seg(*texts)
    assert "PRESIDEN" not in "".join(a.text for a in r.articles)
    assert r.articles[0].text == "Pasal 1\na\nb"


def test_explanation_does_not_create_articles() -> None:
    r = seg(STD + "\nPasal 4\nCukup jelas.")
    assert [a.number for a in r.articles] == ["1", "2", "3"] and r.explanations[
        -1
    ].article_number == "4"


def test_annex_flagged_and_excluded() -> None:
    r = seg("BAB I\nPasal 1\nisi\nLAMPIRAN I\nPasal 2\ntabel")
    assert [a.number for a in r.articles] == ["1"] and codes(r) == [Code.ANNEX_NOT_PROCESSED]


def test_no_pasal_gives_nothing() -> None:
    r = seg("hanya teks biasa\nbukan peraturan")
    assert r.articles == [] and r.units == [] and r.diagnostics == []


AMEND = """PERATURAN PEMERINTAH
TENTANG PERUBAHAN ATAS PERATURAN PEMERINTAH NOMOR 5
Menimbang : bahwa.
MEMUTUSKAN:
Menetapkan: PERATURAN PEMERINTAH TENTANG PERUBAHAN.
Pasal I
Beberapa ketentuan diubah sehingga berbunyi sebagai berikut:
1. Ketentuan Pasal 5 diubah sehingga berbunyi:
Pasal 5
(1) Setiap orang wajib.
2. Di antara Pasal 6 disisipkan Pasal 6A.
Pasal II
Peraturan ini mulai berlaku.
Ditetapkan di Jakarta"""


def test_amending_regulation_units() -> None:
    r = seg(AMEND)
    assert r.articles == [] and [u.label for u in r.units] == ["I", "II"]
    assert (
        r.units[0].id == f"{REG}:unit-I" and "Pasal 5\n(1) Setiap orang wajib." in r.units[0].text
    )
    assert r.diagnostics == []
    assert [p.path for p in r.provisions] == [("1",), ("2",)]


def test_amending_unit_gap_and_mode_conflict() -> None:
    r = seg(AMEND.replace("Pasal II", "Pasal III"))
    gap = next(d for d in r.diagnostics if d.code is Code.ARTICLE_GAP)
    assert gap.detail == "II"
    conflict = seg(AMEND.replace("PERUBAHAN", "PENGATURAN"))
    assert Code.BODY_MODE_CONFLICT in codes(conflict) and len(conflict.units) == 2


def test_misread_first_marker_flags_mode_conflict() -> None:
    r = seg(STD.replace("Pasal 1\nDalam", "Pasal I\nDalam"))
    assert Code.BODY_MODE_CONFLICT in codes(r)


def test_mixed_forms_in_standard_mode() -> None:
    r = seg("BAB I\nPasal 1\nx\nPasal II\ny\nPasal 2\nz")
    assert [a.number for a in r.articles] == ["1", "2"] and Code.MIXED_BODY_FORMS in codes(r)
    assert "Pasal II" in r.articles[0].text


def test_provenance_reconstructs_and_locates() -> None:
    texts = ("BAB I\nPasal 1\n  awal  \n", "  lanjutan\n\n  \nPasal 2\nx")
    r = seg(*texts)
    pmap = {p.number: p for p in pages(*texts)}
    for a in r.articles:
        assert reconstruct(r.provenance[a.id], pmap) == a.text
        assert locate(r.provenance[a.id], 0, len(a.text)) != ()
    a1 = r.articles[0]
    assert a1.text == "Pasal 1\n  awal\nlanjutan"
    frags = r.provenance[a1.id]
    assert len(frags) == 2
    for st in range(len(a1.text)):
        for en in range(st + 1, len(a1.text) + 1):
            spans = locate(frags, st, en)
            got = "".join(pmap[x.page].text[x.start : x.end] for x in spans)
            skip = {
                i for i in range(st, en) if i == len(pmap[1].text[frags[0].start : frags[0].end])
            }
            assert got == "".join(c for i, c in enumerate(a1.text[st:en], st) if i not in skip)


def test_roman_helpers_and_determinism() -> None:
    assert [roman_to_int(x) for x in ("I", "IV", "IX", "XIV")] == [1, 4, 9, 14]
    assert all(int_to_roman(roman_to_int(x)) == x for x in ("II", "XL", "XCIX"))
    a, b = seg(STD), seg(STD)
    assert [x.model_dump_json() for x in a.articles] == [x.model_dump_json() for x in b.articles]


def test_catchword_does_not_enter_article_text_or_provenance() -> None:
    texts = (
        "BAB I\nPasal 1\nawal\nPasal 2 ...",
        "Pasal 2\nisi dua\nPasal 3 . ..",
        "Pasal 3\nisi tiga",
    )
    r = seg(*texts)
    pmap = {p.number: p for p in pages(*texts)}
    assert [a.number for a in r.articles] == ["1", "2", "3"] and r.diagnostics == []
    assert r.articles[0].text == "Pasal 1\nawal"
    assert r.articles[1].text == "Pasal 2\nisi dua" and r.articles[2].text == "Pasal 3\nisi tiga"
    for a in r.articles:
        assert reconstruct(r.provenance[a.id], pmap) == a.text
    assert [(a.page_start, a.page_end) for a in r.articles] == [(1, 1), (2, 2), (3, 3)]


def test_numbered_catchword_does_not_break_list_numbering() -> None:
    items = "\n".join(f"{i}. Butir {i} adalah x" for i in range(1, 14))
    texts = (
        f"BAB I\nPasal 1\nberikut:\n{items}\n14. Kesepakatan . . .",
        "14. Kesepakatan Perdamaian adalah z\n15. Lima belas adalah w",
    )
    r = seg(*texts)
    nums = [p.path[-1] for p in r.provisions]
    assert nums == [str(i) for i in range(1, 16)]
    assert Code.MARKER_OUT_OF_SEQUENCE not in codes(r)
    p14 = next(p for p in r.provisions if p.path[-1] == "14")
    assert p14.text.startswith("14. Kesepakatan Perdamaian adalah z")
