from collections.abc import Iterable
from pathlib import Path

from .models import ReferenceCorpus
from .normalize import norm

MIN_LEN = 20
SUFFIXES = {".md", ".json", ".py", ".txt", ".toml", ".lock", ".jsonl"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "reference",
    "internal_docs",
    "steelix_ui",
    "build",
    "__pycache__",
    "pdf",
}


def public_text(pdf_dir: Path, corpus: ReferenceCorpus) -> dict[str, str]:
    import pdfplumber

    out: dict[str, str] = {}
    for reg in corpus.regulations:
        f = pdf_dir / f"{reg.regulation_id}.pdf"
        if f.is_file():
            with pdfplumber.open(f) as pdf:
                out[reg.regulation_id] = norm(" ".join(pg.extract_text() or "" for pg in pdf.pages))
    return out


def needles(corpus: ReferenceCorpus, public: dict[str, str] | None = None) -> frozenset[str]:
    # text found verbatim in the public source is statute, not expert content
    public = public or {}
    out: set[str] = set()
    for o in corpus.obligations:
        n = norm(o.text)
        if len(n) >= MIN_LEN and n not in public.get(o.regulation_id, ""):
            out.add(n)
    return frozenset(out)


def leaks(artifact: str, needle_set: frozenset[str]) -> int:
    body = norm(artifact)
    return sum(1 for n in needle_set if n in body)


def tracked_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if (
            p.is_file()
            and p.suffix in SUFFIXES
            and not (SKIP_DIRS & set(p.relative_to(root).parts))
        ):
            yield p


def leaking_files(
    root: Path, corpus: ReferenceCorpus, public: dict[str, str] | None = None
) -> list[str]:
    ns = needles(corpus, public)
    bad = []
    for p in tracked_files(root):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if leaks(text, ns):
            bad.append(str(p.relative_to(root)))
    return bad
