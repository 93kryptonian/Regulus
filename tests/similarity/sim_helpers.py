from regulus.documents import process
from regulus.documents.models import PageFailure, PageSource, RawPage
from regulus.domain import ObligationStatus
from regulus.generation import ExtractiveGenerator, GenerationInput, Status, generate
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract
from regulus.similarity import SimilarityEntry


def entries(
    body: str, reg: str = "PP-1-2026", status: ObligationStatus = ObligationStatus.APPROVED
) -> list[SimilarityEntry]:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        return [RawPage(number=1, source=PageSource.NATIVE, text="BAB I\n" + body)]

    doc = process(b"x" + body.encode() + reg.encode(), reg, reader)
    changes = tuple(
        ChangedProvision(
            regulation_id=reg,
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )
    ex = extract(ExtractionInput(changes=changes, documents={reg: doc}), RulesExtractor())
    cands = tuple(c for r in ex.results for c in r.candidates)
    out = generate(GenerationInput(candidates=cands, documents={reg: doc}), ExtractiveGenerator())
    res = []
    for r, c in zip(
        out.results,
        sorted(cands, key=lambda c: (c.clause.owner_id, c.clause.start, c.id)),
        strict=True,
    ):
        assert r.status is Status.GENERATED and r.obligation is not None
        res.append(
            SimilarityEntry(
                obligation=r.obligation.model_copy(update={"status": status}),
                trace=r.trace,
                candidate_id=c.id,
            )
        )
    return res


def one(
    body: str, reg: str = "PP-1-2026", status: ObligationStatus = ObligationStatus.APPROVED
) -> SimilarityEntry:
    (e,) = entries(body, reg, status)
    return e


def query(body: str, reg: str = "PP-9-2026") -> SimilarityEntry:
    return one(body, reg, ObligationStatus.GENERATED)
