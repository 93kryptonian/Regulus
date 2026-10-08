import zipfile
from pathlib import Path

from regulus.reference.load import COUNTS, DETAIL, SECTORS

ROOT = Path(__file__).parents[2]
REAL = ROOT / "reference"


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(
    path: Path, header: list[str], rows: list[list[str]], shared: bool = False, sparse: bool = False
) -> None:
    strings: list[str] = []

    def cell(r: int, c: int, v: str) -> str:
        ref = f"{_col(c)}{r}"
        if v == "" and sparse:
            return ""
        esc = v.replace("&", "&amp;").replace("<", "&lt;")
        if shared:
            if v not in strings:
                strings.append(v)
            return f'<c r="{ref}" t="s"><v>{strings.index(v)}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{esc}</t></is></c>'

    body = ""
    for ri, row in enumerate([header, *rows], 1):
        body += f'<row r="{ri}">' + "".join(cell(ri, ci, v) for ci, v in enumerate(row)) + "</row>"
    sheet = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>'
    wb = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="result" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        if shared:
            sst = "".join(
                f"<si><t>{s.replace('&', '&amp;').replace('<', '&lt;')}</t></si>" for s in strings
            )
            z.writestr(
                "xl/sharedStrings.xml",
                f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{sst}</sst>',
            )


def write_reference_dir(directory: Path, detail, counts, sectors) -> None:  # type: ignore[no-untyped-def]
    directory.mkdir(parents=True, exist_ok=True)
    cols = ["Obligation", "Regulation_id", "Pasal", "Bunyi_Pasal", "Regulation", "Sector"]
    write_xlsx(directory / DETAIL, cols, [[r[c] for c in cols] for r in detail])
    ccols = ["guid", "regulation", "obligation_count"]
    write_xlsx(directory / COUNTS, ccols, [[r[c] for c in ccols] for r in counts], shared=True)
    write_xlsx(directory / SECTORS, ["Sector"], [[r["Sector"]] for r in sectors])
