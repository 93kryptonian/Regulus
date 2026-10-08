import pytest
from ref_helpers import write_xlsx

from regulus.reference.xlsx import SheetError, read_rows


def test_inline_strings_and_header_order_independence(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["b", "a", "extra"], [["1", "2", "x"], ["3", "4", "y"]])
    assert read_rows(f, ("a", "b")) == [{"a": "2", "b": "1"}, {"a": "4", "b": "3"}]


def test_shared_strings_are_resolved(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a", "b"], [["x", "y"], ["x", "z"]], shared=True)
    assert read_rows(f, ("a", "b")) == [{"a": "x", "b": "y"}, {"a": "x", "b": "z"}]


def test_empty_cells_keep_columns_aligned(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a", "b", "c"], [["1", "", "3"], ["", "5", ""]], sparse=True)
    assert read_rows(f, ("a", "b", "c")) == [
        {"a": "1", "b": "", "c": "3"},
        {"a": "", "b": "5", "c": ""},
    ]


def test_blank_rows_are_skipped(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a"], [["1"], [""], ["2"]], sparse=True)
    assert [r["a"] for r in read_rows(f, ("a",))] == ["1", "2"]


def test_special_characters_survive(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a"], [["A & B < C"]])
    assert read_rows(f, ("a",))[0]["a"] == "A & B < C"


def test_missing_columns_are_named_not_valued(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a"], [["SECRET-VALUE"]])
    with pytest.raises(SheetError) as e:
        read_rows(f, ("a", "b", "c"))
    assert e.value.fields == ["b", "c"] and "SECRET-VALUE" not in str(e.value)


def test_a_file_that_is_not_a_workbook_is_refused(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"not a zip")
    with pytest.raises(SheetError) as e:
        read_rows(f, ("a",))
    assert e.value.fields == ["file"]
    with pytest.raises(SheetError):
        read_rows(tmp_path / "missing.xlsx", ("a",))


def test_reading_twice_is_identical(tmp_path):
    f = tmp_path / "a.xlsx"
    write_xlsx(f, ["a"], [["1"], ["2"]])
    assert read_rows(f, ("a",)) == read_rows(f, ("a",))
