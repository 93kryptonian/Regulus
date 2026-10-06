from regulus.documents.clean import clean
from regulus.documents.models import Page, PageSource, RawPage
from regulus.documents.segment import Segmented, segment

DOC = "doc-test"
REG = "PP-1-2026"


def pages(*texts: str) -> list[Page]:
    return clean(
        [RawPage(number=i, source=PageSource.NATIVE, text=t) for i, t in enumerate(texts, 1)]
    )


def seg(*texts: str) -> Segmented:
    return segment(pages(*texts), REG, DOC)


STD = """PERATURAN PEMERINTAH
NOMOR 1 TAHUN 2026
TENTANG CONTOH
Menimbang : bahwa perlu.
Mengingat : Pasal 5 ayat (2) UUD.
MEMUTUSKAN:
Menetapkan: PERATURAN PEMERINTAH TENTANG CONTOH.
BAB I
KETENTUAN UMUM
Pasal 1
Dalam Peraturan ini yang dimaksud dengan:
1. Data adalah keterangan.
2. Pengendali adalah pihak.
Pasal 2
(1) Pengendali wajib melapor.
(2) Laporan memuat:
a. identitas;
b. alasan.
(3) Laporan disampaikan setiap tahun.
BAB II
KEWAJIBAN
Bagian Kesatu
Umum
Paragraf 1
Pelaporan
Pasal 3
Setiap orang wajib patuh.
Ditetapkan di Jakarta
pada tanggal 1 Januari 2026
PENJELASAN
ATAS PERATURAN
I. UMUM
Pasal 1
Cukup jelas.
Pasal 2
Cukup jelas.
Pasal 3
Cukup jelas."""
