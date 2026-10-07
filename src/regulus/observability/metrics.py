from dataclasses import dataclass, field

from .taxonomy import ErrorClass, Outcome, Stage

BUCKETS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)
CAP = 200


class InvalidMetric(Exception):
    pass


@dataclass(frozen=True)
class Spec:
    name: str
    kind: str
    help: str
    labels: dict[str, frozenset[str]] = field(default_factory=dict)


def _vals(e) -> frozenset[str]:  # type: ignore[no-untyped-def]
    return frozenset(x.value for x in e)


def specs(providers: frozenset[str], currencies: frozenset[str]) -> dict[str, Spec]:
    stage, outcome, err = _vals(Stage), _vals(Outcome), _vals(ErrorClass)
    kinds = frozenset({"GENERATE", "CLASSIFY", "EMBED"})
    rows = [
        Spec(
            "regulus_stage_duration_ms",
            "histogram",
            "stage duration in milliseconds",
            {"stage": stage, "outcome": outcome},
        ),
        Spec(
            "regulus_stage_total", "counter", "finished spans", {"stage": stage, "outcome": outcome}
        ),
        Spec(
            "regulus_failures_total",
            "counter",
            "faults by class",
            {"stage": stage, "error_class": err},
        ),
        Spec("regulus_retries_total", "counter", "retried attempts", {"stage": stage}),
        Spec(
            "regulus_items_total",
            "counter",
            "items by outcome",
            {"stage": stage, "outcome": outcome},
        ),
        Spec(
            "regulus_ai_calls_total",
            "counter",
            "AI calls",
            {"provider": providers, "kind": kinds, "priced": frozenset({"true", "false"})},
        ),
        Spec(
            "regulus_ai_tokens_total",
            "counter",
            "AI tokens",
            {"provider": providers, "kind": kinds, "direction": frozenset({"input", "output"})},
        ),
        Spec(
            "regulus_ai_cost_micro_total",
            "counter",
            "AI cost in micro-units",
            {"provider": providers, "currency": currencies},
        ),
        Spec(
            "regulus_obs_dropped_events_total",
            "counter",
            "dropped observation events",
            {"reason": frozenset({"buffer_full", "sink_error", "invalid_event"})},
        ),
    ]
    return {s.name: s for s in rows}


class Registry:
    def __init__(
        self,
        providers: frozenset[str] = frozenset({"rules"}),
        currencies: frozenset[str] = frozenset({"XXX"}),
    ) -> None:
        self.specs = specs(providers, currencies)
        self.counters: dict[str, dict[tuple[tuple[str, str], ...], int]] = {
            n: {} for n in self.specs
        }
        self.hist: dict[str, dict[tuple[tuple[str, str], ...], list[int]]] = {
            n: {} for n in self.specs
        }

    def _key(self, name: str, labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
        spec = self.specs.get(name)
        if spec is None:
            raise InvalidMetric(f"unknown metric {name}")
        if set(labels) != set(spec.labels):
            raise InvalidMetric(f"{name}: labels must be {sorted(spec.labels)}")
        for k, v in labels.items():
            if v not in spec.labels[k]:
                raise InvalidMetric(f"{name}: value outside the enum for {k}")
        key = tuple(sorted(labels.items()))
        store = self.hist[name] if spec.kind == "histogram" else self.counters[name]
        if key not in store and len(store) >= CAP:
            raise InvalidMetric(f"{name}: label combination cap reached")
        return key

    def inc(self, name: str, labels: dict[str, str], value: int = 1) -> None:
        if type(value) is not int or value < 0:
            raise InvalidMetric("counters take non-negative integers")
        key = self._key(name, labels)
        self.counters[name][key] = self.counters[name].get(key, 0) + value

    def observe(self, name: str, labels: dict[str, str], value: int) -> None:
        key = self._key(name, labels)
        row = self.hist[name].setdefault(key, [0] * (len(BUCKETS) + 2))
        for i, b in enumerate(BUCKETS):
            row[i] += value <= b
        row[-2] += 1
        row[-1] += value

    def total(self, name: str) -> int:
        return sum(self.counters[name].values())

    def label_sets(self) -> int:
        return sum(len(v) for v in self.counters.values()) + sum(len(v) for v in self.hist.values())

    def text(self) -> str:
        out: list[str] = []
        for name in sorted(self.specs):
            spec = self.specs[name]
            out += [f"# HELP {name} {spec.help}", f"# TYPE {name} {spec.kind}"]
            if spec.kind == "counter":
                for key in sorted(self.counters[name]):
                    out.append(f"{name}{_fmt(key)} {self.counters[name][key]}")
            else:
                for key in sorted(self.hist[name]):
                    row = self.hist[name][key]
                    for i, b in enumerate(BUCKETS):
                        out.append(f"{name}_bucket{_fmt((*key, ('le', str(b))))} {row[i]}")
                    out.append(f"{name}_bucket{_fmt((*key, ('le', '+Inf')))} {row[-2]}")
                    out.append(f"{name}_sum{_fmt(key)} {row[-1]}")
                    out.append(f"{name}_count{_fmt(key)} {row[-2]}")
        return "\n".join(out) + "\n"


def _fmt(key: tuple[tuple[str, str], ...]) -> str:
    return "{" + ",".join(f'{k}="{v}"' for k, v in key) + "}" if key else ""
