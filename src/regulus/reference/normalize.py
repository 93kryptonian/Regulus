import re
import unicodedata

NORMALIZATION_VERSION = "1"
ARTICLE = re.compile(r"^pasal\s+(\d+)$", re.IGNORECASE)


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def parse_article(ref: str) -> int | None:
    m = ARTICLE.match(" ".join(ref.split()))
    return int(m.group(1)) if m else None
