from pdfgen import make_pdf

from regulus.documents import PdfPlumberReader
from regulus.ingestion.registry import InMemoryRegistry

READER = PdfPlumberReader()
REG = "syn-reg-1"
HEAD = [
    "PERATURAN PEMERINTAH",
    "NOMOR 1 TAHUN 2026",
    "TENTANG CONTOH",
    "Menimbang : bahwa perlu diatur.",
    "Mengingat : Pasal 5 ayat (2) UUD.",
    "MEMUTUSKAN:",
    "Menetapkan: PERATURAN PEMERINTAH TENTANG CONTOH.",
    "BAB I",
    "KETENTUAN UMUM",
]


def body(n: int = 6, glitch: dict[int, str] | None = None, tweak: str = "") -> list[str]:
    lines: list[str] = []
    for i in range(1, n + 1):
        lines.append((glitch or {}).get(i, f"Pasal {i}"))
        lines.append(
            f"Setiap pelaku usaha wajib melaksanakan kewajiban nomor {i} dengan baik{tweak}."
        )
    return lines


def tail(n: int = 6) -> list[str]:
    out = [
        "Ditetapkan di Jakarta",
        "pada tanggal 1 Januari 2026",
        "PENJELASAN",
        "ATAS PERATURAN",
        "I. UMUM",
    ]
    for i in range(1, n + 1):
        out += [f"Pasal {i}", "Cukup jelas."]
    return out


def pdf(
    n: int = 6,
    glitch: dict[int, str] | None = None,
    tweak: str = "",
    title: str = "t",
    extra: list[str] | None = None,
) -> bytes:
    lines = HEAD + body(n, glitch, tweak) + (extra or []) + tail(n)
    pages = ["\n".join(lines[i : i + 14]) for i in range(0, len(lines), 14)]
    return make_pdf(pages, title=title)


def fresh() -> InMemoryRegistry:
    return InMemoryRegistry()
