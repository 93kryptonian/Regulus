import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from regulus.domain import Article, text_hash

from .models import (
    AmendmentUnit,
    Code,
    Diagnostic,
    Explanation,
    Level,
    Page,
    PageStatus,
    Provision,
    Severity,
    SourceSpan,
)
from .provenance import Line, build, owner_offset, page_lines

BAB = re.compile(r"^BAB\s+([IVXLCDM]+)$")
BAGIAN = re.compile(
    r"^Bagian\s+(Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|Kedelapan|Kesembilan|"
    r"Kesepuluh|Kesebelas|Kedua\s*belas|Ketiga\s*belas|Ke-?\d+)$",
    re.I,
)
PARAGRAF = re.compile(r"^Paragraf\s+(\d+)$")
PASAL = re.compile(r"^Pasal\s*(\d+)([A-Z]?)$")
PASAL_ROMAN = re.compile(r"^Pasal\s+([IVXLCDM]+)$")
AYAT = re.compile(r"^\(\s*(\d+)\s*([a-z]?)\s*\)")
HURUF = re.compile(r"^([a-z])\.(?:\s+|$)")
ANGKA = re.compile(r"^(\d+)\.(?:\s+|$)")
DECISION = re.compile(r"^(MEMUTUSKAN|Menetapkan)\b")
RANK = {Level.AYAT: 1, Level.HURUF: 2, Level.ANGKA: 3}
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int:
    total = 0
    for a, b in zip(s, s[1:] + " ", strict=False):
        v = ROMAN[a]
        total += -v if ROMAN.get(b, 0) > v else v
    return total


def int_to_roman(n: int) -> str:
    out = ""
    for v, r in [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]:
        while n >= v:
            out, n = out + r, n - v
    return out


def _next_suffix(last: str, cur: str) -> bool:
    return bool(cur) and (cur == "A" if not last else ord(cur) == ord(last) + 1)


def classify(n: int, suf: str, last: tuple[int, str] | None) -> tuple[str, list[str]]:
    if last is None:
        return ("ok", []) if (n == 1 and not suf) else ("gap", [str(i) for i in range(1, n)])
    ln, ls = last
    if not suf and n == ln + 1:
        return "ok", []
    if n == ln and _next_suffix(ls, suf):
        return "ok", []
    if n > ln:
        miss = [str(i) for i in range(ln + 1, n)] + ([str(n)] if suf else [])
        return "gap", miss
    return "dup", []


@dataclass
class Marker:
    level: Level
    path: tuple[str, ...]
    line: Line


@dataclass
class Owner:
    kind: str
    label: str
    parent: str | None
    lines: list[Line]
    markers: list[Marker] = field(default_factory=list)
    stack: list[Marker] = field(default_factory=list)
    last_ayat: tuple[int, str] | None = None
    last_huruf: str | None = None
    last_angka: int | None = None


@dataclass
class Segmented:
    articles: list[Article] = field(default_factory=list)
    units: list[AmendmentUnit] = field(default_factory=list)
    provenance: dict[str, tuple[SourceSpan, ...]] = field(default_factory=dict)
    provisions: list[Provision] = field(default_factory=list)
    explanations: list[Explanation] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _names(miss: list[str]) -> str:
    return ",".join(miss[:20]) + ("..." if len(miss) > 20 else "")


def segment(pages: Sequence[Page], regulation_id: str, document_id: str) -> Segmented:
    pmap = {p.number: p for p in pages}
    lines = [ln for p in pages if p.status is PageStatus.OK for ln in page_lines(p)]
    out = Segmented()
    strip = [ln.text.strip() for ln in lines]
    has_decision = any(DECISION.match(s) for s in strip)
    first_menimbang = next((i for i, s in enumerate(strip) if s.startswith("Menimbang")), None)
    head = strip[:first_menimbang] if first_menimbang is not None else []
    title_cue = any("PERUBAHAN" in s.upper() for s in head)

    def diag(
        code: Code, sev: Severity, line: Line, num: str | None = None, detail: str = ""
    ) -> None:
        out.diagnostics.append(
            Diagnostic(code=code, severity=sev, page=line.page, article_number=num, detail=detail)
        )

    zone, after_decision, mode = "PREAMBLE", False, None
    owner: Owner | None = None
    expl: tuple[str, list[Line]] | None = None
    chapter = section = para = None
    last_art: tuple[int, str] | None = None
    last_unit: int | None = None

    def flush_owner() -> None:
        nonlocal owner
        o, owner = owner, None
        if o is None:
            return
        b = build(o.lines, pmap, document_id)
        if b is None:
            return
        fr = b.fragments
        if o.kind == "ARTICLE":
            art = Article(
                id=f"{regulation_id}:{o.label}",
                regulation_id=regulation_id,
                number=o.label,
                parent=o.parent,
                text=b.text,
                page_start=fr[0].page,
                page_end=fr[-1].page,
                text_hash=text_hash(b.text),
            )
            assert art.text == b.text
            out.articles.append(art)
            oid = art.id
        else:
            oid = f"{regulation_id}:unit-{o.label}"
            unit = AmendmentUnit(
                id=oid,
                label=o.label,
                text=b.text,
                page_start=fr[0].page,
                page_end=fr[-1].page,
                text_hash=text_hash(b.text),
            )
            assert unit.text == b.text
            out.units.append(unit)
        out.provenance[oid] = fr
        starts = [owner_offset(b, m.line) for m in o.markers] + [len(b.text)]
        for m, s, e in zip(o.markers, starts, starts[1:], strict=False):
            while s < e and b.text[s].isspace():
                s += 1
            while e > s and b.text[e - 1].isspace():
                e -= 1
            if s < e:
                out.provisions.append(
                    Provision(
                        owner_id=oid, level=m.level, path=m.path, text=b.text[s:e], span=(s, e)
                    )
                )

    def flush_expl() -> None:
        nonlocal expl
        e, expl = expl, None
        if e is None:
            return
        b = build(e[1], pmap, document_id)
        if b is not None:
            out.explanations.append(
                Explanation(article_number=e[0], text=b.text, fragments=b.fragments)
            )

    def provision(o: Owner, line: Line, s: str) -> None:
        levels = {Level.ANGKA} if o.kind == "UNIT" else set(Level)
        found: tuple[Level, str, bool] | None = None
        if (m := AYAT.match(s)) and Level.AYAT in levels:
            n, suf = int(m.group(1)), m.group(2)
            ok = classify(n, suf, o.last_ayat)[0] == "ok" and not (o.last_ayat is None and n != 1)
            found = (Level.AYAT, f"({n}{suf})", ok)
            if ok:
                o.last_ayat, o.last_huruf, o.last_angka = (n, suf), None, None
        elif (m := HURUF.match(s)) and Level.HURUF in levels:
            c = m.group(1)
            ok = c == "a" or (o.last_huruf is not None and ord(c) == ord(o.last_huruf) + 1)
            found = (Level.HURUF, c, ok)
            if ok:
                o.last_huruf, o.last_angka = c, None if c == "a" else o.last_angka
        elif (m := ANGKA.match(s)) and Level.ANGKA in levels:
            n = int(m.group(1))
            ok = n == 1 or (o.last_angka is not None and n == o.last_angka + 1)
            found = (Level.ANGKA, str(n), ok)
            if ok:
                o.last_angka = n
        if found is None:
            return
        level, label, ok = found
        if not ok:
            diag(Code.MARKER_OUT_OF_SEQUENCE, Severity.WARNING, line, o.label, label)
            return
        while o.stack and RANK[o.stack[-1].level] >= RANK[level]:
            o.stack.pop()
        mk = Marker(level, tuple(x.path[-1] for x in o.stack) + (label,), line)
        o.stack.append(mk)
        o.markers.append(mk)

    for ln, s in zip(lines, strip, strict=True):
        if s == "PENJELASAN" and zone != "EXPLANATION":
            flush_owner()
            zone = "EXPLANATION"
            continue
        if s.startswith("LAMPIRAN") and zone in ("BODY", "CLOSING"):
            flush_owner()
            zone = "ANNEX"
            diag(Code.ANNEX_NOT_PROCESSED, Severity.WARNING, ln)
            continue
        if zone == "BODY" and s.startswith("Ditetapkan di"):
            flush_owner()
            zone = "CLOSING"
            continue
        if zone == "PREAMBLE":
            if DECISION.match(s):
                after_decision = True
            is_marker = bool(BAB.match(s) or PASAL.match(s) or PASAL_ROMAN.match(s))
            if not (is_marker and (after_decision or not has_decision)):
                continue
            zone = "BODY"
        if zone == "EXPLANATION":
            if m := PASAL.match(s):
                flush_expl()
                expl = (m.group(1) + m.group(2), [ln])
            elif expl:
                expl[1].append(ln)
            continue
        if zone != "BODY":
            continue

        pm, rm = PASAL.match(s), PASAL_ROMAN.match(s)
        if mode is None and (pm or rm):
            mode = "STANDARD" if pm else "AMENDING"
            if title_cue != (mode == "AMENDING"):
                diag(Code.BODY_MODE_CONFLICT, Severity.ERROR, ln, detail=f"mode={mode}")
        if mode == "AMENDING":
            if rm:
                v = roman_to_int(rm.group(1))
                if last_unit is None and v != 1 or last_unit is not None and v > last_unit + 1:
                    miss = [int_to_roman(i) for i in range((last_unit or 0) + 1, v)]
                    diag(Code.ARTICLE_GAP, Severity.ERROR, ln, rm.group(1), _names(miss))
                if last_unit is not None and v <= last_unit:
                    diag(Code.DUPLICATE_ARTICLE, Severity.ERROR, ln, rm.group(1))
                else:
                    flush_owner()
                    last_unit = v
                    owner = Owner("UNIT", rm.group(1), None, [ln])
                    continue
        else:
            if m := BAB.match(s):
                flush_owner()
                chapter, section, para = f"BAB {m.group(1)}", None, None
                continue
            if m := BAGIAN.match(s):
                flush_owner()
                section, para = f"Bagian {m.group(1)}", None
                continue
            if m := PARAGRAF.match(s):
                flush_owner()
                para = f"Paragraf {m.group(1)}"
                continue
            if rm:
                diag(Code.MIXED_BODY_FORMS, Severity.ERROR, ln, rm.group(1))
            elif pm:
                n, suf = int(pm.group(1)), pm.group(2)
                kind, miss = classify(n, suf, last_art)
                label = f"{n}{suf}"
                if kind == "dup":
                    diag(Code.DUPLICATE_ARTICLE, Severity.ERROR, ln, label)
                else:
                    if kind == "gap":
                        diag(Code.ARTICLE_GAP, Severity.ERROR, ln, label, _names(miss))
                    flush_owner()
                    last_art = (n, suf)
                    parent = " > ".join(x for x in (chapter, section, para) if x) or None
                    owner = Owner("ARTICLE", label, parent, [ln])
                    continue
        if owner is not None:
            owner.lines.append(ln)
            provision(owner, ln, s)
    flush_owner()
    flush_expl()
    return out
