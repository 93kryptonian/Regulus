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
