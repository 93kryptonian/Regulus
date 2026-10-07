from regulus.domain.base import Model

from .models import (
    EvidenceClass,
    Formula,
    Gate,
    GateKind,
    MetricDefinition,
    MetricResult,
    Population,
    Status,
    make_result,
)

HARD0 = Gate(kind=GateKind.HARD, expect=0.0)
HARD1 = Gate(kind=GateKind.HARD, expect=1.0)
TARGET0 = Gate(kind=GateKind.TARGET, expect=0.0)
EC = EvidenceClass


class Builder(Model):
    model_config = {"arbitrary_types_allowed": True, "frozen": False, "extra": "forbid"}
    populations: dict[str, Population] = {}
    definitions: dict[str, MetricDefinition] = {}
    results: dict[str, MetricResult] = {}
    known_gaps: list[str] = []
    errors: list[str] = []
    classes: set[EvidenceClass] = set()

    def population(
        self, id: str, description: str, source: str, n: int, built_by: str, limitations: str
    ) -> None:
        self.populations[id] = Population(id=id, description=description, source=source, n=n,
                                          built_by=built_by, limitations=limitations)  # fmt: skip

    def metric(
        self,
        id: str,
        layer: str,
        name: str,
        pop: str,
        numerator: str,
        denominator: str,
        cls: EvidenceClass,
        gate: Gate | None = None,
        formula: Formula = Formula.RATIO,
        qualified_by: str | None = None,
    ) -> MetricDefinition:
        d = MetricDefinition(id=id, layer=layer, name=name, population_id=pop, numerator_definition=numerator,
                             denominator_definition=denominator, formula=formula, evidence_class=cls,
                             gate=gate, qualified_by=qualified_by)  # fmt: skip
        if id in self.definitions:
            raise ValueError(f"duplicate metric {id}")
        self.definitions[id] = d
        return d

    def record(self, d: MetricDefinition, numerator: float, denominator: float, note: str = "",
               status: Status | None = None) -> MetricResult:  # fmt: skip
        n = self.populations[d.population_id].n
        r = make_result(d, numerator, denominator, n, status, note)
        self.results[d.id] = r
        if r.status in (Status.OK, Status.GATE_FAILED):
            self.classes.add(d.evidence_class)
        return r

    def unmeasurable(
        self, d: MetricDefinition, note: str, status: Status = Status.NOT_MEASURABLE
    ) -> None:
        self.record(d, 0, 0, note, status)
