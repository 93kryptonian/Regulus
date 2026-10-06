import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from regulus.documents import ProcessedDocument, process
from regulus.documents.models import PageFailure, PageSource, RawPage
from regulus.domain.base import Model
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef

from .extract import ObligationExtractor, extract
from .lexicon import load_lexicon
from .models import (
    ExtractionInput,
    ExtractionResult,
    FieldState,
    FieldStatus,
    ObligationCandidate,
    ResultStatus,
)
from .rules import RulesExtractor
from .segment import find_markers

REG = "GOLD-1-2026"
FIELDS = ("actor", "action", "object", "deadline", "frequency")
LISTS = ("conditions", "exceptions")


class GoldCandidate(Model):
    marker_index: int = Field(ge=0)
    modality: str
    fields: dict[str, str | None] = {}
    undetermined: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    exceptions: tuple[str, ...] = ()
    items: int = 0


class GoldCase(Model):
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    citation: str | None = None
    text: str
    candidates: tuple[GoldCandidate, ...] = ()
    rationale: str = Field(min_length=10)


class PRF(Model):
    tp: int
    fp: int
    fn: int
    precision: float | None
    recall: float | None
    f1: float | None


class GoldReport(Model):
    total: int
    candidates: PRF
    fields: dict[str, PRF]
    not_stated_accuracy: float | None
    multiplicity_accuracy: float
    unsupported_claims: int
    citation_failures: int
    silent_loss: int
    false_no_obligation: tuple[str, ...]
    unresolved_cases: tuple[str, ...]


def load_gold(path: Path) -> list[GoldCase]:
    return [GoldCase.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def case_document(text: str) -> ProcessedDocument:
    def reader(data: bytes) -> list[RawPage | PageFailure]:
        return [RawPage(number=1, source=PageSource.NATIVE, text="BAB I\n" + text)]

    return process(b"gold" + text.encode(), REG, reader)


def _prf(tp: int, fp: int, fn: int) -> PRF:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p is not None and r is not None and p + r else None
    return PRF(tp=tp, fp=fp, fn=fn, precision=p, recall=r, f1=f)


def _state_value(st: FieldState) -> str | None:
    return st.value.value if st.status is FieldStatus.PRESENT and st.value else None


def _run_case(
    case: GoldCase, extractor: ObligationExtractor
) -> tuple[ExtractionResult, ProcessedDocument]:
    doc = case_document(case.text)
    if len(doc.articles) != 1:
        raise ValueError(f"gold case {case.case_id} must contain exactly one article")
    a = doc.articles[0]
    change = ChangedProvision(
        regulation_id=REG,
        article_number=a.number,
        kind=ChangedKind.NEW_REGULATION_ARTICLE,
        text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
    )
    out = extract(ExtractionInput(changes=(change,), documents={REG: doc}), extractor)
    return out.results[0], doc


def evaluate_gold(
    cases: Sequence[GoldCase], extractor: ObligationExtractor | None = None
) -> GoldReport:
    extractor = extractor or RulesExtractor()
    lex = load_lexicon()
    cand_tp = cand_fp = cand_fn = 0
    counts: dict[str, list[int]] = {n: [0, 0, 0] for n in (*FIELDS, "condition", "exception")}
    ns_total = ns_ok = multi_ok = unsupported = cite_fail = silent = 0
    false_no, unresolved = [], []
    for case in cases:
        res, doc = _run_case(case, extractor)
        text = doc.articles[0].text
        markers = [m for m in find_markers(text, (0, len(text)), lex) if not m.negated]
        index_of = {m.start: i for i, m in enumerate(markers)}
        pred: dict[int, ObligationCandidate] = {
            index_of[c.marker.citation.start]: c
            for c in res.candidates
            if c.marker.citation.start in index_of
        }
        gold = {g.marker_index: g for g in case.candidates}
        multi_ok += len(res.candidates) == len(case.candidates)
        if gold and res.status is ResultStatus.NO_OBLIGATION:
            false_no.append(case.case_id)
        if res.status is ResultStatus.UNRESOLVED:
            unresolved.append(case.case_id)
        covered = set(pred) | {
            index_of[d.span[0]]
            for d in res.diagnostics
            if d.code.value == "UNEXTRACTED_DEONTIC" and d.span and d.span[0] in index_of
        }
        if res.status not in (ResultStatus.FAILED, ResultStatus.NOT_EXTRACTABLE):
            silent += len(set(index_of.values()) - covered)
        for c in res.candidates:
            cites = [c.clause, c.marker.citation, *c.items]
            for f in (c.actor, c.action, c.object, c.deadline, c.frequency):
                if f.value:
                    cites.append(f.value.citation)
            cites += [v.citation for v in (*c.conditions, *c.exceptions)]
            for ct in cites:
                if text[ct.start : ct.end] != ct.quote:
                    cite_fail += 1
                    unsupported += 1
        for i in set(pred) | set(gold):
            p, g = pred.get(i), gold.get(i)
            if p and g:
                cand_tp += 1
            elif p:
                cand_fp += 1
            else:
                cand_fn += 1
            for name in FIELDS:
                gv = g.fields.get(name) if g else None
                gu = bool(g and name in g.undetermined)
                pv = _state_value(getattr(p, name)) if p else None
                if g and gv is None and not gu:
                    ns_total += 1
                    ns_ok += bool(p and getattr(p, name).status is FieldStatus.NOT_STATED)
                row = counts[name]
                row[0] += pv is not None and pv == gv
                row[1] += pv is not None and pv != gv
                row[2] += gv is not None and pv != gv
            for name, plural in (("condition", "conditions"), ("exception", "exceptions")):
                gvals = set(getattr(g, plural)) if g else set()
                pvals = {v.value for v in getattr(p, plural)} if p else set()
                row = counts[name]
                row[0] += len(gvals & pvals)
                row[1] += len(pvals - gvals)
                row[2] += len(gvals - pvals)
    return GoldReport(
        total=len(cases),
        candidates=_prf(cand_tp, cand_fp, cand_fn),
        fields={k: _prf(*v) for k, v in counts.items()},
        not_stated_accuracy=ns_ok / ns_total if ns_total else None,
        multiplicity_accuracy=multi_ok / len(cases) if cases else 0.0,
        unsupported_claims=unsupported,
        citation_failures=cite_fail,
        silent_loss=silent,
        false_no_obligation=tuple(false_no),
        unresolved_cases=tuple(unresolved),
    )
