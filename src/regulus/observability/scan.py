import re
from collections.abc import Iterable, Mapping

from regulus.domain.base import Model

PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])"),
    "url": re.compile(r"https?://|www\."),
    "credential": re.compile(
        r"\b(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{8,}|password\s*[=:]|api[_-]?key\s*[=:]|secret\s*[=:])",
        re.IGNORECASE,
    ),
    "long_hex": re.compile(r"\b[0-9a-f]{40,}\b"),
}
# 16- and 12-char hex ids are the permitted trace and span ids; 64-char hashes are ledger hashes, not credentials


class Finding(Model):
    artifact: str
    kind: str


ISO = re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.+Z-]+)?")


def scan(artifacts: Mapping[str, str], forbidden_texts: Iterable[str] = ()) -> list[Finding]:
    out: list[Finding] = []
    needles = [t for t in forbidden_texts if len(t) >= 12]
    for name, text in sorted(artifacts.items()):
        plain = ISO.sub("", text)
        for kind, rx in PATTERNS.items():
            if kind == "long_hex":
                continue
            if rx.search(plain):
                out.append(Finding(artifact=name, kind=kind))
        for t in needles:
            if t in text:
                out.append(Finding(artifact=name, kind="source_or_obligation_text"))
                break
    return out
