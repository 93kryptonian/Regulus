import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
COL = re.compile(r"^([A-Z]+)")


class SheetError(Exception):
    def __init__(self, fields: list[str]) -> None:
        self.fields = fields
        super().__init__("; ".join(fields))


def _col(ref: str) -> int:
    m = COL.match(ref)
    n = 0
    for ch in m.group(1) if m else "":
        n = n * 26 + ord(ch) - 64
    return n - 1


def _text(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.iter(NS + "t"))


def _shared(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    return [_text(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml"))]


def _first_sheet(z: zipfile.ZipFile) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheets = wb.find(NS + "sheets")
    if sheets is None or not len(sheets):
        raise SheetError(["sheet"])
    rid = sheets[0].get(REL + "id")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    for r in rels:
        if r.get("Id") == rid:
            target = r.get("Target", "")
            return target.lstrip("/") if target.startswith("/") else "xl/" + target
    raise SheetError(["sheet"])


def _cell(c: ET.Element, strings: list[str]) -> str:
    kind = c.get("t")
    if kind == "inlineStr":
        return _text(c)
    v = c.find(NS + "v")
    if v is None or v.text is None:
        return ""
    return strings[int(v.text)] if kind == "s" else v.text


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        z = zipfile.ZipFile(path)
        strings = _shared(z)
        sheet = ET.fromstring(z.read(_first_sheet(z)))
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError):
        raise SheetError(["file"]) from None
    table: list[list[str]] = []
    for row in sheet.iter(NS + "row"):
        cells: dict[int, str] = {}
        for c in row.findall(NS + "c"):
            cells[_col(c.get("r", "A"))] = _cell(c, strings)
        width = max(cells, default=-1) + 1
        table.append([cells.get(i, "") for i in range(width)])
    if not table:
        raise SheetError(list(required))
    header = [h.strip() for h in table[0]]
    if missing := [f for f in required if f not in header]:
        raise SheetError(missing)
    idx = {h: i for i, h in enumerate(header)}
    out = []
    for r in table[1:]:
        if not any(x.strip() for x in r):
            continue
        out.append({f: (r[idx[f]] if idx[f] < len(r) else "") for f in required})
    return out
