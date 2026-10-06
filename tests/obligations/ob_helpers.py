from regulus.documents import ProcessedDocument, process
from regulus.documents.models import PageFailure, PageSource, RawPage
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, ExtractionOutput, RulesExtractor, extract
from regulus.obligations.models import FieldState, FieldStatus

REG = "PP-1-2026"


def make_doc(body: str, fail: bool = False) -> ProcessedDocument:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        out: list[RawPage | PageFailure] = [
            RawPage(number=1, source=PageSource.NATIVE, text="BAB I\n" + body)
        ]
        if fail:
            out.append(PageFailure(number=2, error="boom"))
        return out

    return process(b"x" + body.encode(), REG, reader)


def changes_for(
    doc: ProcessedDocument, kind: ChangedKind = ChangedKind.NEW_REGULATION_ARTICLE
) -> tuple[ChangedProvision, ...]:
    return tuple(
        ChangedProvision(
            regulation_id=REG,
            article_number=a.number,
            kind=kind,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )


def run(body: str, extractor=None, **kw) -> tuple[ExtractionOutput, ProcessedDocument]:  # type: ignore[no-untyped-def]
    doc = make_doc(body, kw.pop("fail", False))
    inp = ExtractionInput(changes=changes_for(doc), documents={REG: doc}, **kw)
    return extract(inp, extractor or RulesExtractor()), doc


def cands(body: str):  # type: ignore[no-untyped-def]
    out, _ = run(body)
    return [c for r in out.results for c in r.candidates]


def one(body: str):  # type: ignore[no-untyped-def]
    cs = cands(body)
    assert len(cs) == 1, cs
    return cs[0]


def val(f: FieldState) -> str | None:
    return f.value.value if f.status is FieldStatus.PRESENT and f.value else None
