import re
from enum import StrEnum

from pydantic import Field

from regulus.domain.base import Model


class OpKind(StrEnum):
    MODIFY = "MODIFY"
    INSERT = "INSERT"
    APPEND = "APPEND"
    DELETE = "DELETE"
    REPEAL_PROVISION = "REPEAL_PROVISION"
    REPLACE_TERM = "REPLACE_TERM"


class TargetLevel(StrEnum):
    ARTICLE = "ARTICLE"
    AYAT = "AYAT"
    HURUF = "HURUF"


class Reason(StrEnum):
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    AMBIGUOUS_OPERATION = "AMBIGUOUS_OPERATION"
    LOCATOR_UNPARSEABLE = "LOCATOR_UNPARSEABLE"
    UNSUPPORTED_LOCATOR = "UNSUPPORTED_LOCATOR"


class Locator(Model):
    article: str
    path: tuple[str, ...] = ()


class Operation(Model):
    kind: OpKind
    locators: tuple[Locator, ...]
    target_level: TargetLevel | None = None
    anchors: tuple[Locator, ...] = ()
    sentence: tuple[int, int]
    new_text: tuple[int, int] | None = None
    old_term: str | None = None
    new_term: str | None = None


class Unresolved(Model):
    reason: Reason
    detail: str = Field(default="")


Parsed = Operation | Unresolved

_ART = r"Pasal\s+(\d+[A-Z]?)"
_AYAT = r"ayat\s*\(\s*(\d+[a-z]?)\s*\)"
_SEP = r"(?:\s*,\s*|\s+dan\s+)"
_F = re.IGNORECASE
_ART_ITEM = r"Pasal\s+\d+[A-Z]?(?:\s+sampai\s+dengan\s+Pasal\s+\d+[A-Z]?)?"
_AYAT_LIST = rf"{_AYAT}(?:{_SEP}{_AYAT})*"
_LOC_ARTICLES = re.compile(rf"^{_ART_ITEM}(?:{_SEP}{_ART_ITEM})*$", _F)
_ART_N = r"Pasal\s+(?P<art>\d+[A-Z]?)"
_LOC_AYAT_FIRST = re.compile(
    rf"^(?:huruf\s+(?P<huruf>[a-z])\s+)?(?P<ayats>{_AYAT_LIST})\s+{_ART_N}$", _F
)
_LOC_ART_FIRST = re.compile(
    rf"^{_ART_N}\s+(?P<ayats>{_AYAT_LIST})(?:\s+huruf\s+(?P<huruf>[a-z]))?$", _F
)
_UNSUPPORTED = re.compile(r"^(BAB|Bagian|Paragraf|Penjelasan|Lampiran)\b", _F)
_MAX_RANGE = 200


class _LocatorError(Exception):
    def __init__(self, reason: Reason, detail: str) -> None:
        super().__init__(detail)
        self.reason, self.detail = reason, detail


def _split_article(label: str) -> tuple[int, str]:
    m = re.fullmatch(r"(\d+)([A-Z]?)", label.upper())
    assert m
    return int(m.group(1)), m.group(2)


def parse_locator(text: str) -> tuple[Locator, ...]:
    t = " ".join(text.split())
    if _UNSUPPORTED.match(t):
        raise _LocatorError(Reason.UNSUPPORTED_LOCATOR, t[:60])
    if _LOC_ARTICLES.match(t):
        out: list[Locator] = []
        for part in re.split(_SEP, t, flags=_F):
            labels = re.findall(r"Pasal\s+(\d+[A-Z]?)", part, _F)
            if len(labels) == 2:
                (a, sa), (b, sb) = _split_article(labels[0]), _split_article(labels[1])
                if sa or sb or b < a or b - a >= _MAX_RANGE:
                    raise _LocatorError(Reason.LOCATOR_UNPARSEABLE, part)
                out += [Locator(article=str(i)) for i in range(a, b + 1)]
            else:
                out.append(Locator(article=labels[0].upper()))
        return tuple(out)
    for pattern in (_LOC_AYAT_FIRST, _LOC_ART_FIRST):
        if m := pattern.match(t):
            huruf = m.group("huruf")
            paths = [
                ("(" + a + ")",) + ((huruf.lower(),) if huruf else ())
                for a in re.findall(_AYAT, m.group("ayats"), _F)
            ]
            return tuple(Locator(article=m.group("art").upper(), path=p) for p in paths)
    raise _LocatorError(Reason.LOCATOR_UNPARSEABLE, t[:60])


_TAIL = r"\s*,?\s+yang\s+berbunyi\s+sebagai\s+berikut\s*:?"
_PATTERNS: dict[OpKind, re.Pattern[str]] = {
    OpKind.MODIFY: re.compile(
        r"^(?:Ketentuan\s+)?(?P<loc>[^:;]{1,200}?)\s+diubah\s*,?\s+sehingga\s+berbunyi\s+sebagai\s+berikut\s*:?",
        _F | re.DOTALL,
    ),
    OpKind.DELETE: re.compile(
        r"^(?:Ketentuan\s+)?(?P<loc>[^:;]{1,200}?)\s+dihapus\s*\.?\s*$", _F | re.DOTALL
    ),
    OpKind.REPEAL_PROVISION: re.compile(
        r"^(?:Ketentuan\s+)?(?P<loc>[^:;]{1,200}?)\s+dicabut(?:\s+dan\s+dinyatakan\s+tidak\s+berlaku)?\s*\.?\s*$",
        _F | re.DOTALL,
    ),
    OpKind.INSERT: re.compile(
        r"^Di\s+antara\s+(?P<a1>[^:;]{1,120}?)\s+dan\s+(?P<a2>[^:;]{1,120}?)\s+disisipkan\s+\d+\s*"
        r"\([^)]*\)\s+(?P<unit>Pasal|ayat|huruf)\s*,\s*yakni\s+(?P<label>[^,:;]{1,40}?)" + _TAIL,
        _F | re.DOTALL,
    ),
    OpKind.APPEND: re.compile(
        r"^(?:Ketentuan\s+)?(?P<loc>[^:;]{1,200}?)\s+ditambah\s+\d+\s*\([^)]*\)\s+(?P<unit>ayat|huruf)\s*,"
        r"\s*yakni\s+(?P<label>[^,:;]{1,40}?)" + _TAIL,
        _F | re.DOTALL,
    ),
    OpKind.REPLACE_TERM: re.compile(
        r"^(?P<kind>Kata|Frasa|Istilah|Angka)\s+[\"“'‘](?P<old>.+?)[\"”'’]\s+(?:dalam|pada)\s+"
        r"(?P<loc>[^:;\"“]{1,200}?)\s+diganti\s+dengan\s+(?:kata|frasa|istilah|angka)?\s*[\"“'‘](?P<new>.+?)[\"”'’]",
        _F | re.DOTALL,
    ),
}
_MARKER = re.compile(r"^\s*\d+\.[a-z]?\s*")


def _inserted_label(unit: str, label: str) -> tuple[str, ...]:
    lab = " ".join(label.split())
    if unit.lower() == "pasal":
        m = re.fullmatch(r"Pasal\s+(\d+[A-Z])", lab, _F)
        return (m.group(1).upper(),) if m else ()
    if unit.lower() == "ayat":
        m = re.fullmatch(r"ayat\s*\(\s*(\d+[a-z])\s*\)", lab, _F)
        return ("(" + m.group(1) + ")",) if m else ()
    m = re.fullmatch(r"huruf\s+([a-z]\d*)", lab, _F)
    return (m.group(1).lower(),) if m else ()


def _insert(m: re.Match[str], base: int) -> Operation | Unresolved:
    unit = m.group("unit").lower()
    label = _inserted_label(unit, m.group("label"))
    if not label:
        return Unresolved(reason=Reason.LOCATOR_UNPARSEABLE, detail="inserted label")
    a1, a2 = " ".join(m.group("a1").split()), " ".join(m.group("a2").split())
    try:
        if unit == "pasal":
            anchors = parse_locator(a1) + parse_locator(a2)
            if len(anchors) != 2 or any(x.path for x in anchors):
                raise _LocatorError(Reason.LOCATOR_UNPARSEABLE, "anchors")
            level, loc = TargetLevel.ARTICLE, Locator(article=label[0])
        else:
            tail = re.search(r"\s+(Pasal\s+\d+[A-Z]?)$", a2, _F)
            ctx = parse_locator(a2) if unit == "ayat" and not tail else None
            if tail is None or ctx is not None:
                raise _LocatorError(Reason.LOCATOR_UNPARSEABLE, "anchors")
            article = parse_locator(tail.group(1))[0].article
            first = re.fullmatch(_AYAT if unit == "ayat" else r"huruf\s+[a-z]", a1, _F)
            second = a2[: tail.start()]
            ok_second = re.fullmatch(
                _AYAT if unit == "ayat" else r"huruf\s+[a-z]\s+" + _AYAT, second, _F
            )
            if not first or not ok_second:
                raise _LocatorError(Reason.LOCATOR_UNPARSEABLE, "anchors")
            if unit == "ayat":
                level, loc = TargetLevel.AYAT, Locator(article=article, path=(label[0],))
            else:
                ay = re.search(_AYAT, second, _F)
                level = TargetLevel.HURUF
                loc = Locator(
                    article=article, path=("(" + (ay.group(1) if ay else "") + ")", label[0])
                )
            anchors = (Locator(article=article), Locator(article=article))
    except _LocatorError as e:
        return Unresolved(reason=e.reason, detail=e.detail)
    return Operation(
        kind=OpKind.INSERT,
        locators=(loc,),
        target_level=level,
        anchors=anchors,
        sentence=(base, base + m.end()),
        new_text=(base + m.end(), -1),
    )


def parse_operation(text: str) -> Parsed:
    lead = _MARKER.match(text)
    base = lead.end() if lead else 0
    body = text[base:]
    hits = [(k, m) for k, p in _PATTERNS.items() if (m := p.match(body))]
    if not hits:
        return Unresolved(reason=Reason.UNSUPPORTED_OPERATION, detail=" ".join(body.split())[:80])
    if len(hits) > 1:
        return Unresolved(reason=Reason.AMBIGUOUS_OPERATION, detail=",".join(k for k, _ in hits))
    kind, m = hits[0]
    if kind is OpKind.INSERT:
        res = _insert(m, base)
        if isinstance(res, Operation):
            return _finish(res, text)
        return res
    try:
        locators = parse_locator(m.group("loc"))
    except _LocatorError as e:
        return Unresolved(reason=e.reason, detail=e.detail)
    level = None
    if kind is OpKind.APPEND:
        level = TargetLevel.AYAT if m.group("unit").lower() == "ayat" else TargetLevel.HURUF
    op = Operation(
        kind=kind,
        locators=locators,
        target_level=level,
        sentence=(base, base + m.end()),
        new_text=(base + m.end(), -1) if kind in (OpKind.MODIFY, OpKind.APPEND) else None,
        old_term=m.group("old") if kind is OpKind.REPLACE_TERM else None,
        new_term=m.group("new") if kind is OpKind.REPLACE_TERM else None,
    )
    return _finish(op, text)


def _finish(op: Operation, text: str) -> Operation:
    if op.new_text is None:
        return op
    s = op.new_text[0]
    e = len(text)
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return op.model_copy(update={"new_text": (s, e) if s < e else None})
