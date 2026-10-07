import re

from regulus.domain.base import Model

PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<![\w.])\+?\d[\d\s().-]{8,}\d(?![\w.])"),
    "url": re.compile(r"https?://|www\."),
    "credential": re.compile(
        r"\b(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]{8,}|password\s*[=:]|api[_-]?key\s*[=:]|secret\s*[=:])",
        re.IGNORECASE,
    ),
}
ISO = re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.+Z-]+)?")
FREE_TEXT_FIELDS = ("reason", "reject_text")
FREE_TEXT_PREFIXES = ("note:",)


class FreeTextPolicy(Model):
    max_length: int = 500

    def covers(self, field: str) -> bool:
        return field in FREE_TEXT_FIELDS or field.startswith(FREE_TEXT_PREFIXES)

    def check(self, field: str, value: str) -> str | None:
        if len(value) > self.max_length:
            return "too_long"
        plain = ISO.sub("", value)
        for kind, rx in PATTERNS.items():
            if rx.search(plain):
                return kind
        return None
