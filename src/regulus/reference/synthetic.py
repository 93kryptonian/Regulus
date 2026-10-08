from .load import Row, build_corpus
from .models import ReferenceCorpus

SECTORS = ("Sektor A", "Sektor B", "Sektor C")


def _row(text: str, rid: str, article: str, body: str, title: str, sector: str) -> Row:
    return {
        "Obligation": text,
        "Regulation_id": rid,
        "Pasal": article,
        "Bunyi_Pasal": body,
        "Regulation": title,
        "Sector": sector,
    }


def synthetic_rows() -> tuple[list[Row], list[Row], list[Row]]:
    d: list[Row] = []
    a = "Peraturan Sintetis A"
    d += [
        _row(
            "Melakukan pendaftaran usaha",
            "syn-a",
            "Pasal 1",
            "Setiap usaha wajib mendaftar.",
            a,
            "Sektor A",
        ),
        _row(
            "Melakukan pendaftaran usaha",
            "syn-a",
            "Pasal 2",
            "Pendaftaran dilakukan sebelum beroperasi.",
            a,
            "Sektor A",
        ),
    ]
    d += [
        _row(
            "Melaporkan kegiatan usaha",
            "syn-a",
            "Pasal 3",
            "Pelaku usaha wajib melapor.",
            a,
            "Sektor A",
        )
    ] * 2
    d += [
        _row(
            "Dilarang membuang limbah",
            "syn-a",
            "Pasal 4",
            "Setiap orang dilarang membuang limbah.",
            a,
            "Sektor B",
        )
    ]
    d += [
        _row(
            "Menyampaikan laporan berkala",
            "syn-a",
            "Pasal 5",
            "Laporan disampaikan setiap tahun.",
            a,
            "Sektor B",
        ),
        _row(
            "Menyampaikan laporan berkala",
            "syn-a",
            "Pasal 5",
            "Laporan disampaikan paling lambat Maret.",
            a,
            "Sektor B",
        ),
    ]
    for title in ("Peraturan Sintetis B", "Synthetic Regulation B"):
        d += [
            _row(
                "Menggunakan alat pelindung",
                "syn-b",
                "Pasal 7",
                "Pekerja wajib memakai alat pelindung.",
                title,
                "Sektor C",
            )
        ]
        d += [
            _row(
                "Menyimpan arsip",
                "syn-b",
                "Pasal 8",
                "Arsip disimpan lima tahun.",
                title,
                "Sektor C",
            )
        ] * 2
        d += [
            _row(
                "Menyimpan arsip",
                "syn-b",
                "Pasal 8",
                "Arsip dapat berbentuk elektronik.",
                title,
                "Sektor C",
            )
        ]
    d += [
        _row(
            "Memelihara catatan",
            "syn-c",
            "Pasal 9",
            "Catatan dipelihara.",
            "Peraturan Sintetis C",
            "Sektor A",
        ),
        _row(
            "Memelihara catatan",
            "syn-c",
            "Lampiran I",
            "Tabel lampiran.",
            "Peraturan Sintetis C",
            "Sektor A",
        ),
        _row(
            "Menyampaikan data",
            "syn-c",
            "Pasal 10",
            "Data disampaikan.",
            "Peraturan Sintetis C",
            "Sektor Z",
        ),
    ]
    counts = [
        {"guid": "syn-a", "regulation": "Peraturan Sintetis A", "obligation_count": "5"},
        {"guid": "syn-b", "regulation": "Peraturan Sintetis B", "obligation_count": "3"},
        {"guid": "syn-b", "regulation": "Synthetic Regulation B", "obligation_count": "3"},
    ]
    return d, counts, [{"Sector": s} for s in SECTORS]


def synthetic_corpus() -> ReferenceCorpus:
    d, c, s = synthetic_rows()
    return build_corpus(d, c, s)
