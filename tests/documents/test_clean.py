import pytest

from regulus.documents.clean import clean, page_diagnostics
from regulus.documents.models import Code, PageFailure, PageSource, PageStatus, RawPage


def raw(n: int, text: str, **kw: object) -> RawPage:
    return RawPage(number=n, source=PageSource.NATIVE, text=text, **kw)  # type: ignore[arg-type]


def test_page_label_removed_and_recorded() -> None:
    (p,) = clean([raw(1, "- 20 -\nPasal 1\nisi")])
    assert p.text == "Pasal 1\nisi" and p.label == "20"
    assert [(r.index, r.text) for r in p.removed] == [(0, "- 20 -")]


def test_repeated_header_removed_only_when_common() -> None:
    pages = [
        raw(i, f"PRESIDEN\nREPUBLIK INDONESIA\n- {i} -\nbody {i}\nmore {i}") for i in range(1, 6)
    ]
    out = clean(pages)
    assert all(
        "PRESIDEN" not in p.text and p.text == f"body {p.number}\nmore {p.number}" for p in out
    )
    assert all(len(p.removed) == 3 for p in out)


def test_header_kept_when_too_few_pages_or_not_repeated() -> None:
    few = clean([raw(i, f"PRESIDEN\nbody {i}") for i in range(1, 4)])
    assert all(p.text.startswith("PRESIDEN") for p in few)
    mixed = clean([raw(i, f"PRESIDEN\nx{i}" if i == 1 else f"y{i}\nz{i}") for i in range(1, 6)])
    assert mixed[0].text.startswith("PRESIDEN")


def test_line_endings_normalized_and_nothing_else() -> None:
    (p,) = clean([raw(1, "a  b\r\nc\rd")])
    assert p.text == "a  b\nc\nd"


def test_empty_and_failed_pages() -> None:
    a, b, c = clean([raw(1, "  \n "), PageFailure(number=2, error="boom"), raw(3, "x")])
    assert a.status is PageStatus.EMPTY and b.status is PageStatus.FAILED and b.error == "boom"
    assert c.status is PageStatus.OK
    codes = [d.code for d in page_diagnostics([a, b, c])]
    assert codes == [Code.PAGE_EMPTY, Code.PAGE_FAILED]


def test_encoding_and_low_confidence_diagnostics() -> None:
    p1, p2 = clean([raw(1, "bad � char"), raw(2, "x", ocr_confidence=0.3)])
    assert [d.code for d in page_diagnostics([p1, p2])] == [
        Code.ENCODING_ISSUE,
        Code.LOW_OCR_CONFIDENCE,
    ]
    assert p1.text == "bad � char"


def test_clean_is_deterministic() -> None:
    pages = [raw(i, f"H\nbody {i}\nF") for i in range(1, 6)]
    assert [p.model_dump_json() for p in clean(pages)] == [
        p.model_dump_json() for p in clean(pages)
    ]


def test_text_is_never_stripped() -> None:
    (p,) = clean([raw(1, "  indented\ntrailing  \n")])
    assert p.text == "  indented\ntrailing  \n"


def _kinds(p) -> list[str]:  # type: ignore[no-untyped-def]
    return [r.kind.value for r in p.removed]


def test_catchword_removed_when_next_page_starts_with_its_prefix() -> None:
    a, b = clean(
        [raw(1, "isi\n14. Kesepakatan . . ."), raw(2, "14. Kesepakatan Perdamaian adalah x\nlain")]
    )
    assert a.text == "isi" and b.text.startswith("14. Kesepakatan Perdamaian")
    assert [(r.index, r.text, r.kind.value) for r in a.removed] == [
        (1, "14. Kesepakatan . . .", "CATCHWORD")
    ]


@pytest.mark.parametrize("tail", ["...", " . . .", " .. .", " . .."])
def test_catchword_ellipsis_variants_and_any_structural_form(tail: str) -> None:
    for head in ("Pasal 2", "(4) Pemasangan", "a. Informasi", "BAB I", "Bagian"):
        a, _ = clean([raw(1, f"x\n{head}{tail}"), raw(2, f"{head} dan seterusnya\ny")])
        assert a.text == "x" and _kinds(a) == ["CATCHWORD"], head


def test_catchword_is_case_and_whitespace_insensitive() -> None:
    a, _ = clean([raw(1, "x\nPASAL   2 ..."), raw(2, "pasal 2\nisi")])
    assert a.text == "x"


def test_same_ellipsis_line_not_adjacent_is_retained() -> None:
    a, _ = clean([raw(1, "x\nPasal 2 ..."), raw(2, "sesuatu lain\nsama sekali berbeda")])
    assert a.text == "x\nPasal 2 ..." and a.removed == ()


def test_continuation_must_be_in_top_edge_only() -> None:
    top = "\n".join(f"baris {i}" for i in range(6))
    a, _ = clean([raw(1, "x\nPasal 2 ..."), raw(2, top + "\nPasal 2 lanjutan")])
    assert a.text == "x\nPasal 2 ..."


def test_ellipsis_line_mid_page_is_retained() -> None:
    body = "\n".join(["Pasal 2 ..."] + [f"baris {i}" for i in range(6)])
    a, _ = clean([raw(1, body), raw(2, "Pasal 2 lanjutan")])
    assert a.text == body


def test_line_without_ellipsis_tail_is_retained() -> None:
    a, _ = clean([raw(1, "x\n14. Kesepakatan"), raw(2, "14. Kesepakatan Perdamaian adalah")])
    assert a.text == "x\n14. Kesepakatan" and a.removed == ()


def test_dots_only_and_single_dot_are_not_catchwords() -> None:
    a, _ = clean([raw(1, "x\n. . ."), raw(2, ". . . lanjut")])
    assert a.text == "x\n. . ."
    c, _ = clean([raw(1, "x\nPasal 2."), raw(2, "Pasal 2 lagi")])
    assert c.text == "x\nPasal 2."


def test_no_catchword_removal_without_a_readable_adjacent_page() -> None:
    a, _, _ = clean(
        [raw(1, "x\nPasal 2 ..."), PageFailure(number=2, error="e"), raw(3, "Pasal 2 isi")]
    )
    assert a.text == "x\nPasal 2 ..."
    e, _ = clean([raw(1, "x\nPasal 2 ..."), raw(2, "  ")])
    assert e.text == "x\nPasal 2 ..."


def test_noise_and_catchword_are_recorded_separately_in_order() -> None:
    pages = [
        raw(1, "H\nbody 1\nPasal 2 ...\n- 1 -"),
        raw(2, "H\nPasal 2 lanjut\n- 2 -"),
        raw(3, "H\nbody 3\n- 3 -"),
        raw(4, "H\nbody 4\n- 4 -"),
    ]
    first = clean(pages)[0]
    assert first.text == "body 1"
    assert [(r.index, r.kind.value) for r in first.removed] == [
        (0, "NOISE"),
        (2, "CATCHWORD"),
        (3, "NOISE"),
    ]
