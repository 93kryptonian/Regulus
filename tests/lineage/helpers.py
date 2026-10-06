from datetime import date

from regulus.documents import DocStatus, ProcessedDocument, process
from regulus.documents.models import PageFailure, PageSource, RawPage
from regulus.domain import Article, Regulation, RegulatoryEvent
from regulus.domain import EventType as T
from regulus.domain import RegulationKind as K
from regulus.lineage import Declaration, LineageInput, TargetArticles

D = date(2026, 7, 16)


def reg(
    kind: K, number: str, year: int, title: str = "t", promulgated: date | None = None
) -> Regulation:
    return Regulation.of(kind, number, year, title=title, promulgated_on=promulgated)


TARGET = reg(K.PP, "10", 2020, "Target", date(2020, 1, 1))
ACTOR = reg(K.PP, "5", 2026, "Perubahan", D)
OTHER = reg(K.PP, "11", 2021, "Other", date(2021, 1, 1))


def ev(
    actor: Regulation,
    type: T,
    target: Regulation | None = None,
    on: date = D,
    eid: str | None = None,
    **kw: object,
) -> RegulatoryEvent:
    return RegulatoryEvent(
        id=eid or f"e-{actor.id}-{type}-{target.id if target else ''}-{on}",
        type=type,
        regulation_id=actor.id,
        target_id=target.id if target else None,
        occurred_on=on,
        detected_on=on,
        basis="b",
        **kw,
    )  # type: ignore[arg-type]


def doc(actor: Regulation, *pages: str, fail: bool = False) -> ProcessedDocument:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        out: list[RawPage | PageFailure] = [
            RawPage(number=i, source=PageSource.NATIVE, text=t) for i, t in enumerate(pages, 1)
        ]
        if fail:
            out.append(PageFailure(number=len(pages) + 1, error="boom"))
        return out

    return process(b"x" + actor.id.encode(), actor.id, reader)


def amending(
    intro: str, *points: str, title: str = "TENTANG PERUBAHAN ATAS PERATURAN PEMERINTAH"
) -> str:
    body = "\n".join(points)
    return (
        f"PERATURAN PEMERINTAH\nNOMOR 5 TAHUN 2026\n{title}\nMenimbang : bahwa.\nMEMUTUSKAN:\n"
        f"Menetapkan: PERATURAN PEMERINTAH.\nPasal I\n{intro}\n{body}\nPasal II\nPeraturan Pemerintah ini mulai berlaku pada tanggal diundangkan.\n"
        "Ditetapkan di Jakarta"
    )


INTRO = "Beberapa ketentuan dalam Peraturan Pemerintah Nomor 10 Tahun 2020 diubah sebagai berikut:"


def target_articles(*numbers: str, status: DocStatus = DocStatus.PROCESSED_OK) -> TargetArticles:
    return TargetArticles(
        status=status,
        articles=tuple(Article.of(TARGET.id, n, f"Pasal {n}\nisi {n}", 1, 1) for n in numbers),
    )


def make(
    events: list[RegulatoryEvent],
    docs: dict[str, ProcessedDocument] | None = None,
    targets: dict[str, TargetArticles] | None = None,
    regs: list[Regulation] | None = None,
    decl: list[Declaration] | None = None,
) -> LineageInput:
    return LineageInput(
        events=tuple(events),
        regulations=tuple(regs or [ACTOR, TARGET, OTHER]),
        declarations=tuple(decl or []),
        documents=docs or {},
        target_articles=targets or {},
    )
