from regulus.documents import ProcessedDocument, process
from regulus.documents.models import PageFailure, PageSource, RawPage
from regulus.generation import ExtractiveGenerator, GenerationInput, GenerationOutput, generate
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, ObligationCandidate, RulesExtractor, extract

REG = "PP-1-2026"


def make_doc(body: str) -> ProcessedDocument:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        return [RawPage(number=1, source=PageSource.NATIVE, text="BAB I\n" + body)]

    return process(b"x" + body.encode(), REG, reader)


def candidates(doc: ProcessedDocument) -> tuple[ObligationCandidate, ...]:
    changes = tuple(
        ChangedProvision(
            regulation_id=REG,
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )
    out = extract(ExtractionInput(changes=changes, documents={REG: doc}), RulesExtractor())
    return tuple(c for r in out.results for c in r.candidates)


def run(
    body: str, generator=None, **kw
) -> tuple[GenerationOutput, ProcessedDocument, tuple[ObligationCandidate, ...]]:  # type: ignore[no-untyped-def]
    doc = make_doc(body)
    cands = candidates(doc)
    out = generate(
        GenerationInput(candidates=cands, documents={REG: doc}, **kw),
        generator or ExtractiveGenerator(),
    )
    return out, doc, cands
