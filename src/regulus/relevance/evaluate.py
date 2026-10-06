import datetime as _dt
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from regulus.domain import Regulation, RegulatoryEvent
from regulus.domain.base import Model

from .assess import AssessmentConfig, _texts, assess
from .classifier import RelevanceClassifier
from .models import (
    AssessmentContext,
    AssessStatus,
    Relevance,
    RelevanceAssessment,
    TextSource,
)

EPOCH = _dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)


class GoldCase(Model):
    case_id: str = Field(min_length=1)
    event: RegulatoryEvent
    regulation: Regulation
    target: Regulation | None = None
    texts: tuple[TextSource, ...] = ()
    relevance: Relevance
    sectors: tuple[str, ...] = ()
    rationale: str = Field(min_length=10)
    annotator: str = Field(min_length=1)
    guideline_version: str = Field(min_length=1)

    def context(self) -> AssessmentContext:
        return AssessmentContext(
            event=self.event, regulation=self.regulation, target=self.target, texts=self.texts
        )


class SectorScore(Model):
    tp: int
    fp: int
    fn: int
    f1: float | None


class Report(Model):
    total: int
    confusion: dict[str, dict[str, int]]
    precision: float | None
    recall: float | None
    f1: float | None
    abstention_rate: float
    recall_decided: float | None
    false_not_relevant: tuple[str, ...]
    false_relevant: tuple[str, ...]
    sectors: dict[str, SectorScore]
    sector_micro_f1: float | None
    sector_macro_f1: float | None
    sector_exact_match: float
    explainability_violations: tuple[str, ...]


def _ratio(n: int, d: int) -> float | None:
    return n / d if d else None


def _f1(p: float | None, r: float | None) -> float | None:
    return 2 * p * r / (p + r) if p is not None and r is not None and p + r else None


def load_gold(path: Path) -> list[GoldCase]:
    return [GoldCase.model_validate(x) for x in json.loads(path.read_text(encoding="utf-8"))]


def evaluate(cases: Sequence[GoldCase], assessments: Sequence[RelevanceAssessment]) -> Report:
    if len(cases) != len(assessments):
        raise ValueError("one assessment per gold case")
    names = [r.value for r in Relevance]
    confusion = {g: dict.fromkeys(names, 0) for g in names}
    tp = fp = fn = decided_gold_rel = 0
    fnr, frel, violations = [], [], []
    per: dict[str, list[int]] = {}
    exact = 0
    for c, a in zip(cases, assessments, strict=True):
        confusion[c.relevance.value][a.relevance.value] += 1
        gold_rel, pred_rel = c.relevance is Relevance.RELEVANT, a.relevance is Relevance.RELEVANT
        tp += gold_rel and pred_rel
        fp += (not gold_rel) and pred_rel
        fn += gold_rel and not pred_rel
        decided_gold_rel += gold_rel and a.relevance is not Relevance.INSUFFICIENT_EVIDENCE
        if gold_rel and a.relevance is Relevance.NOT_RELEVANT:
            fnr.append(c.case_id)
        if pred_rel and not gold_rel:
            frel.append(c.case_id)
        g, p = set(c.sectors), set(a.sectors)
        exact += g == p
        for s in g | p:
            row = per.setdefault(s, [0, 0, 0])
            row[0] += s in g and s in p
            row[1] += s not in g and s in p
            row[2] += s in g and s not in p
        if a.relevance is not Relevance.INSUFFICIENT_EVIDENCE:
            texts = _texts(c.context())
            bad = not a.evidence or any(
                e.span and (texts.get(e.source_id) or "")[e.span[0] : e.span[1]] != e.quote
                for e in a.evidence
            )
            if bad:
                violations.append(c.case_id)
    sectors = {
        s: SectorScore(tp=t, fp=f, fn=n, f1=_f1(_ratio(t, t + f), _ratio(t, t + n)))
        for s, (t, f, n) in sorted(per.items())
    }
    stp, sfp, sfn = (sum(v[i] for v in per.values()) for i in range(3))
    macro = [x.f1 or 0.0 for x in sectors.values()]
    prec, rec = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    insufficient = sum(1 for a in assessments if a.relevance is Relevance.INSUFFICIENT_EVIDENCE)
    return Report(
        total=len(cases),
        confusion=confusion,
        precision=prec,
        recall=rec,
        f1=_f1(prec, rec),
        abstention_rate=insufficient / len(cases) if cases else 0.0,
        recall_decided=_ratio(tp, decided_gold_rel),
        false_not_relevant=tuple(fnr),
        false_relevant=tuple(frel),
        sectors=sectors,
        sector_micro_f1=_f1(_ratio(stp, stp + sfp), _ratio(stp, stp + sfn)),
        sector_macro_f1=sum(macro) / len(macro) if macro else None,
        sector_exact_match=exact / len(cases) if cases else 0.0,
        explainability_violations=tuple(violations),
    )


def run(
    cases: Sequence[GoldCase],
    config: AssessmentConfig,
    classifier: RelevanceClassifier | None = None,
) -> Report:
    out = []
    for c in cases:
        res = assess(c.context(), config, classifier, EPOCH)
        if res.status is not AssessStatus.ASSESSED or res.assessment is None:
            raise ValueError(f"gold case {c.case_id} is not assessable: {res.reason}")
        out.append(res.assessment)
    return evaluate(cases, out)
