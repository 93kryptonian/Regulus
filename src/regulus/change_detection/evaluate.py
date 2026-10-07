import json
import random
from collections import Counter
from datetime import date
from pathlib import Path

from pydantic import Field

from regulus.domain import EventType, Regulation, RegulationStatus, RegulatoryEvent
from regulus.domain.base import Model

from .detector import detect, detect_batch
from .matcher import RegulationIndex
from .models import Outcome, SourceRecord
from .projection import project_status


class ExpectedEvent(Model):
    type: EventType
    target_id: str | None = None
    reason: str | None = None

    def key(self) -> tuple[str, str | None, str | None]:
        return (self.type.value, self.target_id, self.reason)


class GoldCase(Model):
    case_id: str = Field(min_length=1)
    record: SourceRecord
    seen: tuple[str, ...] = ()
    expected_outcome: Outcome
    expected_events: tuple[ExpectedEvent, ...] = ()
    tags: tuple[str, ...] = ()
    rationale: str = Field(min_length=10)


class ProjectionCase(Model):
    case_id: str = Field(min_length=1)
    regulation_id: str
    events: tuple[RegulatoryEvent, ...] = ()
    expected_status: RegulationStatus
    expected_anomalies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    rationale: str = Field(min_length=10)


class Gold(Model):
    index: tuple[Regulation, ...]
    detected_on: date
    cases: tuple[GoldCase, ...]
    projections: tuple[ProjectionCase, ...]


class DetectionReport(Model):
    cases: int
    outcome_ok: int
    type_ok: int
    target_total: int
    target_ok: int
    resolved_events: int
    false_resolutions: tuple[str, ...]
    review_expected: int
    review_reason_ok: int
    review_cases_predicted: int
    review_reasons: dict[str, int]
    projections: int
    projection_ok: int
    permutations: int
    permutation_violations: int
    replay_records: int
    replay_violations: int
    tags: tuple[str, ...]


def load_gold(path: Path) -> Gold:
    return Gold.model_validate(json.loads(path.read_text(encoding="utf-8")))


def evaluate_gold(gold: Gold, seed: int = 7, permutations: int = 20) -> DetectionReport:
    index = RegulationIndex(gold.index)
    outcome_ok = type_ok = target_total = target_ok = resolved = 0
    review_expected = review_reason_ok = review_cases = 0
    false_res: list[str] = []
    reasons: Counter[str] = Counter()
    for c in gold.cases:
        res = detect(c.record, index, set(c.seen), gold.detected_on)
        outcome_ok += res.outcome is c.expected_outcome
        pred = [
            (e.type.value, e.target_id, e.reason.value if e.reason else None) for e in res.events
        ]
        exp = [e.key() for e in c.expected_events]
        type_ok += Counter(t for t, _, _ in pred) == Counter(t for t, _, _ in exp)
        for t, tgt, _ in exp:
            if tgt is not None:
                target_total += 1
                target_ok += any(p[0] == t and p[1] == tgt for p in pred)
        for t, tgt, _ in pred:
            if tgt is not None:
                resolved += 1
                if not any(e[0] == t and e[1] == tgt for e in exp):
                    false_res.append(f"{c.case_id}:{t}->{tgt}")
        for t, _, rsn in exp:
            if t == EventType.NEEDS_REVIEW.value:
                review_expected += 1
                review_reason_ok += any(p[0] == t and p[2] == rsn for p in pred)
        if any(p[0] == EventType.NEEDS_REVIEW.value for p in pred):
            review_cases += 1
        for t, _, rsn in pred:
            if t == EventType.NEEDS_REVIEW.value and rsn:
                reasons[rsn] += 1
    proj_ok = 0
    for p in gold.projections:
        proj = project_status(p.regulation_id, p.events)
        proj_ok += proj.status is p.expected_status and proj.anomalies == p.expected_anomalies
    records = [c.record for c in gold.cases]
    rng = random.Random(seed)
    base_ids = {
        e.id for r in detect_batch(records, index, set(), gold.detected_on) for e in r.events
    }
    viol = 0
    for _ in range(permutations):
        order = records[:]
        rng.shuffle(order)
        got_ids = {
            e.id for r in detect_batch(order, index, set(), gold.detected_on) for e in r.events
        }
        viol += got_ids != base_ids
    replay_viol = sum(bool(detect(r, index, base_ids, gold.detected_on).events) for r in records)
    return DetectionReport(
        cases=len(gold.cases),
        outcome_ok=outcome_ok,
        type_ok=type_ok,
        target_total=target_total,
        target_ok=target_ok,
        resolved_events=resolved,
        false_resolutions=tuple(false_res),
        review_expected=review_expected,
        review_reason_ok=review_reason_ok,
        review_cases_predicted=review_cases,
        review_reasons=dict(sorted(reasons.items())),
        projections=len(gold.projections),
        projection_ok=proj_ok,
        permutations=permutations,
        permutation_violations=viol,
        replay_records=len(records),
        replay_violations=replay_viol,
        tags=tuple(
            sorted(
                {t for c in gold.cases for t in c.tags}
                | {t for p in gold.projections for t in p.tags}
            )
        ),
    )
