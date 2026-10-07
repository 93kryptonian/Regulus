import re
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from regulus.domain.base import Model

from .stats import wilson

SMALL_N = 100
TOL = 1e-9


class EvidenceClass(StrEnum):
    REGRESSION = "REGRESSION"
    MUTATION = "MUTATION"
    PROPERTY = "PROPERTY"
    CORPUS_COVERAGE = "CORPUS_COVERAGE"
    GENERALIZATION = "GENERALIZATION"
    PRODUCTION = "PRODUCTION"


ABSENT = (EvidenceClass.GENERALIZATION, EvidenceClass.PRODUCTION)


class GateKind(StrEnum):
    HARD = "HARD"
    TARGET = "TARGET"
    REPORT_ONLY = "REPORT_ONLY"


class Formula(StrEnum):
    RATIO = "RATIO"
    MEAN = "MEAN"


class Status(StrEnum):
    OK = "OK"
    NOT_MEASURABLE = "NOT_MEASURABLE"
    NO_GOLD = "NO_GOLD"
    GATE_FAILED = "GATE_FAILED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    ERROR = "ERROR"


MEASURED = (Status.OK, Status.GATE_FAILED)
CORRECTNESS_WORDS = re.compile(
    r"precision|recall|accuracy|f1|correct|error[- ]?free|violation|false|unsupported|loss",
    re.IGNORECASE,
)


class Gate(Model):
    kind: GateKind
    expect: float = 0.0


class MetricDefinition(Model):
    id: str
    layer: str
    name: str
    population_id: str
    numerator_definition: str
    denominator_definition: str
    formula: Formula = Formula.RATIO
    evidence_class: EvidenceClass
    gate: Gate | None = None
    qualified_by: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if not re.fullmatch(r"[a-z0-9_.]+", self.id):
            raise ValueError("metric id must be lowercase dotted")
        if self.evidence_class in ABSENT:
            raise ValueError(f"no evidence of class {self.evidence_class.value} exists yet")
        if self.evidence_class is EvidenceClass.CORPUS_COVERAGE:
            if self.gate is not None:
                raise ValueError("a corpus-coverage metric cannot carry a gate")
            if CORRECTNESS_WORDS.search(self.name):
                raise ValueError("a corpus-coverage metric cannot be named as a correctness metric")
        if not self.numerator_definition or not self.denominator_definition:
            raise ValueError("numerator and denominator must be defined")
        return self


class MetricResult(Model):
    definition_id: str
    population_n: int
    numerator: float
    denominator: float
    value: float | None
    interval: tuple[float, float] | None = None
    status: Status
    gate_passed: bool | None = None
    note: str = ""

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.status in MEASURED:
            if self.denominator <= 0 or self.value is None:
                raise ValueError("a measured result needs a positive denominator and a value")
            if abs(self.value - self.numerator / self.denominator) > TOL:
                raise ValueError("value must equal numerator / denominator")
        else:
            if self.value is not None or self.interval is not None or self.gate_passed is not None:
                raise ValueError(f"{self.status.value} carries no value, interval or gate result")
        if self.interval is not None and self.denominator >= SMALL_N:
            raise ValueError("an interval is reported only for fewer than 100 observations")
        return self


def make_result(
    d: MetricDefinition,
    numerator: float,
    denominator: float,
    population_n: int,
    status: Status | None = None,
    note: str = "",
) -> MetricResult:
    if status is not None and status not in MEASURED:
        return MetricResult(
            definition_id=d.id, population_n=population_n, numerator=numerator,
            denominator=denominator, value=None, status=status, note=note,
        )  # fmt: skip
    if denominator <= 0:
        return MetricResult(definition_id=d.id, population_n=population_n, numerator=numerator,
                            denominator=denominator, value=None, status=Status.NOT_MEASURABLE,
                            note=note or "denominator is 0")  # fmt: skip
    value = numerator / denominator
    interval = None
    if d.formula is Formula.RATIO and denominator < SMALL_N and 0 <= numerator <= denominator:
        interval = wilson(numerator, denominator)
    passed: bool | None = None
    st = Status.OK
    if d.gate is not None and d.gate.kind is not GateKind.REPORT_ONLY:
        passed = abs(value - d.gate.expect) <= TOL
        if d.gate.kind is GateKind.HARD and not passed:
            st = Status.GATE_FAILED
    return MetricResult(definition_id=d.id, population_n=population_n, numerator=numerator,
                        denominator=denominator, value=value, interval=interval, status=st,
                        gate_passed=passed, note=note)  # fmt: skip


class Population(Model):
    id: str
    description: str
    source: str
    n: int
    built_by: str
    limitations: str


class Report(Model):
    inputs: dict[str, str]
    populations: tuple[Population, ...]
    definitions: tuple[MetricDefinition, ...]
    results: tuple[MetricResult, ...]
    known_gaps: tuple[str, ...] = ()
    classes_present: tuple[EvidenceClass, ...] = ()
    classes_absent: tuple[EvidenceClass, ...] = ABSENT
    limitations: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        pops = {p.id: p for p in self.populations}
        defs = {d.id: d for d in self.definitions}
        if len(pops) != len(self.populations) or len(defs) != len(self.definitions):
            raise ValueError("duplicate population or definition id")
        seen: set[str] = set()
        for d in self.definitions:
            if d.population_id not in pops:
                raise ValueError(f"{d.id}: unregistered population {d.population_id}")
        for r in self.results:
            found = defs.get(r.definition_id)
            if found is None:
                raise ValueError(f"result without a definition: {r.definition_id}")
            d = found
            if r.definition_id in seen:
                raise ValueError(f"two results for {r.definition_id}")
            seen.add(r.definition_id)
            if r.population_n != pops[d.population_id].n:
                raise ValueError(
                    f"{d.id}: population n {r.population_n} != registry {pops[d.population_id].n}"
                )
        for d in self.definitions:
            if d.qualified_by and d.qualified_by not in seen:
                raise ValueError(f"{d.id}: reported without its qualifying metric {d.qualified_by}")
        absent = {c for c in self.classes_absent}
        if absent & set(self.classes_present):
            raise ValueError("a class cannot be both present and absent")
        return self
