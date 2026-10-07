# Regulus — Observability & Cost Contract

**Phase:** 13 · **Status:** FROZEN

```
Phase 11  runs the workflow            Phase 12  measures behaviour against contracts
Phase 13  can we see what happened inside a run, how long each part took,
          where it failed, and what the AI-enriched path cost?
Phase 14  what the system does when it goes wrong
```

> Observability watches the system; it never changes what the system does. If every
> sink is down, slow or hostile, the pipeline's outputs are byte-identical, and the
> pipeline never waits for a sink (§8).

**Scope statement.** Phase 13 validates observability behaviour under controlled local
workloads and failure injection. No production traffic exists, and no operational SLO,
capacity or uptime claim is made.

## 1. Boundary

| Does | Does not |
|---|---|
| emit structured events for run and stage lifecycles, with correlation ids | change any result, status, ledger record or review decision |
| classify failures with a closed taxonomy | decide retries (Phase 11) or recovery policy (Phase 14) |
| keep counters and histograms with fixed names, labels and buckets | add dashboards, alert routing, a metrics server or a vendor SDK |
| account tokens and cost for AI calls from provider-reported usage | estimate silently, or invent prices |
| prove its own invariants (lifecycle, non-interference, cardinality, privacy, cost arithmetic) | claim production performance |

Instrumentation attaches at **existing port boundaries** (the Phase 11 pipeline ports, the
review `apply`, the notification outbox) through wrappers. Frozen Phase 3–11 internals are not
edited. Consequence, stated up front: stage granularity is the granularity of those ports. A
sub-stage inside one port call (for example extraction versus generation inside `GENERATE`) is
not separately visible unless a real adapter splits the port.

## 2. Correlation and events

Identifiers, all deterministic and replay-stable:

| Id | Source |
|---|---|
| `run_id` | Phase 11 run key (`event_id:config_version`) |
| `trace_id` | `sha256(run_id)[:16]` |
| `span_id` | `sha256(trace_id, stage, item, attempt)[:12]` |
| `item_id`, `task_id`, `obligation_id` | existing ids, carried as fields |

```
ObsEvent(seq, trace_id, span_id, parent_span_id, run_id, stage, kind, outcome | None,
         error_class | None, attempt, started_at, duration_ms | None, counts{closed keys}, attrs{closed keys})
kind    : SPAN_STARTED | SPAN_FINISHED | SPAN_ABANDONED | POINT
outcome : OK | ABSTAINED | REFUSED | FAILED_RETRYABLE | FAILED_PERMANENT | SKIPPED
```

`seq` is a per-run counter. Time comes from an **injected monotonic clock** for durations and
an injected wall clock for `started_at`; both are fakes in tests, so a run's event stream is
byte-identical when replayed with the same clocks.

**Stages** (closed): `RUN`, `DETECTED_NOTIFY`, `PROCESS`, `GENERATE`, `ENRICH`, `SUBMIT`,
`REVIEW_ACTION`, `NOTIFY_DELIVER`, `TICK`.

**Closed vocabularies.** `counts` keys and `attrs` keys come from a fixed list (for example
`items`, `retries`, `candidates`, `tokens_in`, `tokens_out`, `status`, `error_class`,
`action`, `store`). Values are ints, booleans or members of a closed enum; no free text.

## 3. Lifecycle rules

1. Every `SPAN_STARTED` is followed by exactly one `SPAN_FINISHED` or `SPAN_ABANDONED`.
2. `parent_span_id` references a span in the same trace that started earlier; the `RUN` span
   has none.
3. A child finishes before its parent finishes.
4. `duration_ms` is a non-negative integer for finished spans.
5. A crash leaves spans open. On the next start of the same run, recovery appends
   `SPAN_ABANDONED` for each open span and records `recovered = true`; abandoned spans are
   counted, never dropped.
6. A retry is a **new span** with `attempt + 1` under the same parent; the earlier attempt keeps
   its own outcome.

## 4. Failure classification

A closed taxonomy maps what the system already says to one `error_class`:

| Source | Mapping |
|---|---|
| Phase 11 `Unavailable` | `UNAVAILABLE` (retryable) |
| Phase 11 `Permanent` | `PERMANENT` |
| submission statuses `CONFLICT`, `NOT_SUBMITTABLE`, `EVIDENCE_INVALID`, `NOT_GENERATED` | `REJECTED_INPUT` (permanent) |
| store errors | `STORE` (retryable) |
| Phase 9 `DENIED`, `STALE`, `INCOMPLETE_REVIEW`, `INVALID_TRANSITION`, `EVIDENCE_INVALID` | outcome `REFUSED`, `error_class` = the status; **an expected refusal is not a fault** |
| `NOT_RECORDED` | `STORE` |
| notification `FAILED_RETRYABLE` / `FAILED_PERMANENT` / dead letter | `CHANNEL_UNAVAILABLE` / `CHANNEL_REJECTED` / `DEAD_LETTER` |
| anything unmapped | `UNCLASSIFIED`, counted and listed in the report; never hidden in `OK` |

The report distinguishes **faults** (`FAILED_*`) from **refusals** (`REFUSED`) and
**abstentions** (`ABSTAINED`: the system declined to decide, for example `INSUFFICIENT_EVIDENCE`).

## 5. Metrics

In-memory registry, no server. Fixed names, labels and buckets:

| Metric | Type | Labels |
|---|---|---|
| `regulus_stage_duration_ms` | histogram, fixed buckets | `stage`, `outcome` |
| `regulus_stage_total` | counter | `stage`, `outcome` |
| `regulus_failures_total` | counter | `stage`, `error_class` |
| `regulus_retries_total` | counter | `stage` |
| `regulus_items_total` | counter | `stage`, `outcome` |
| `regulus_ai_calls_total` | counter | `provider`, `kind`, `priced` |
| `regulus_ai_tokens_total` | counter | `provider`, `kind`, `direction` |
| `regulus_ai_cost_micro_total` | counter | `provider`, `currency` |
| `regulus_obs_dropped_events_total` | counter | `reason` |

**Cardinality rules.** Labels take only closed-enum values. Ids (`run_id`, `item_id`,
`task_id`, `obligation_id`) appear in events, **never as metric labels**. The registry refuses
an unknown metric name, an unknown label, or a label value outside its enum, and enforces a
hard cap on label combinations per metric.

Export is a deterministic OpenMetrics-style text rendering and JSON-lines events written by
sinks; there is no network dependency.

## 6. AI and LLM cost

Today every provider (extractor, generator, classifier, embedding) is a rules-only or offline
reference and makes **no model calls**. Phase 13 therefore reports "0 AI calls", never
"cost 0", and it builds the accounting that a future adapter (for example an OpenAI one, kept
as optional backlog) plugs into.

```
UsageRecord(run_id, span_id, provider, model, kind: GENERATE|CLASSIFY|EMBED,
            input_tokens, output_tokens, source: REPORTED | ESTIMATED, latency_ms)
PriceTable(version, currency, entries{model: (input_micro_per_mtok, output_micro_per_mtok)})
```

1. **Tokens come from the provider's own usage report** (`REPORTED`). An `ESTIMATED` record is
   allowed only when the provider reports nothing, is labelled, and is totalled separately.
2. **Money is integer micro-units** (no float drift). `cost = ceil(tokens × price / 1_000_000)`
   per direction, summed in integers.
3. **Unpriced is a state, not a zero.** A call whose model is absent from the price table is
   `priced = false`: counted, its tokens shown, excluded from the money total, and the report
   states "N calls unpriced".
4. **Prices are configuration**, versioned, supplied by the operator. The repository ships no
   claim about any vendor's real prices; test fixtures use obviously fake models and prices.
5. **Totals** per run, stage and model are recomputable from the usage records, and the
   reported totals must equal that recomputation exactly.
6. Failed and retried calls that consumed tokens are still recorded (retries cost money).
7. No prompt or response text, and no source or obligation text, is stored with usage.

## 7. Privacy and data protection

- **No direct personal data and no human-readable identifiers.** Events, metrics, usage
  records, errors and exports carry ids, counts, closed-enum values and durations only. They
  never carry source or obligation text, names, emails, phone numbers, credentials, tokens or
  URLs. A schema allow-list enforces it and a scan test checks outputs.
- **Opaque system identifiers** (run, trace, span, item, task and obligation ids, and the opaque
  reviewer or staff ids the Phase 9 and 11 contracts already carry) may appear only where
  those contracts require them. They are not declared non-personal: they remain subject to the
  same access, retention and governance controls as the records they come from.
- Sink credentials and endpoints are host-injected and never appear in an event or error.
- The lawful basis and retention period for these records, and the mapping to ISO 27001:2022
  logging and monitoring controls (A.8.15 Logging, A.8.16 Monitoring activities), are to be
  confirmed with the internal legal and GRC teams; this contract asserts neither.

## 8. Sink isolation and failure semantics

**Sink isolation.** Wrapper execution never waits for sink delivery. The only observability
work on the wrapped call's control path is a **non-blocking, bounded, O(1) enqueue** into an
in-memory `ObservationBuffer`; the buffer never calls a sink. Sinks are driven by a separate
`drain(sink, max_events)` that the host (or the test or demo driver) calls **outside** any
wrapped call. A slow, blocked, unavailable or raising sink can therefore delay, fail or retry
only the drain, never the wrapped operation, its result, its latency, its timeouts or its
retries. No thread or async framework is required: the drain is a plain function the driver
calls between operations, with a per-call event budget so one drain cannot run unbounded.
A sink that never returns blocks the driver that called `drain`, not the pipeline.

```
wrapped operation ──► result returned to the caller
        │
        └──► non-blocking enqueue ──► bounded buffer ◄── drain(sink, budget)  (driven separately)
```

| Situation | Behaviour |
|---|---|
| a sink raises | the drain records `sink_error`, keeps the event buffered up to a retry limit, then counts it dropped; the pipeline never sees it |
| a sink is slow or blocked | only `drain` is delayed; wrapped operations return without waiting; events accumulate in the buffer |
| buffer full | the enqueue does not block: the newest event is dropped and `regulus_obs_dropped_events_total{reason="buffer_full"}` increases; a drop is visible, never silent |
| invalid event (unknown key, wrong type, disallowed value) | rejected at construction; counted as `invalid_event`; the pipeline continues |
| clock goes backwards | `duration_ms` clamps to 0 and the span is flagged `clock_regression` |
| crash with open spans | abandoned on recovery (§3.5) |
| instrumentation raises | caught at the wrapper; the wrapped call's result is returned unchanged |

## 9. Hard invariants (tested as properties)

1. **Non-interference.** For every seeded run (including injected faults), pipeline results,
   statuses, ledger records and review outcomes are identical with instrumentation absent,
   present, and with every sink failing.
2. **Lifecycle completeness.** After recovery there is no orphan, double-finished or
   un-finished span, and every parent reference resolves.
3. **Determinism.** The same run with the same injected clocks gives a byte-identical event
   stream and metric text.
4. **Closed vocabulary and cardinality.** No event or metric contains a key, label or value
   outside the allow-lists; combinations stay under the cap.
5. **No sensitive content.** A scan of every emitted artifact finds no source or obligation
   text, direct personal data, human-readable identifiers or credential patterns, and no
   opaque id outside its permitted field.
6. **Cost arithmetic.** Reported totals equal the exact integer recomputation from usage
   records; unpriced calls are never summed as zero-cost.
7. **Classification totality.** Every non-OK outcome has an `error_class`; `UNCLASSIFIED` is
   counted and listed.
8. **Drop accounting.** `emitted = delivered + dropped + buffered`, with drops visible as a metric.
9. **Sink isolation.** No sink is invoked during a wrapped call. A test sink that fails the test
   if it is called inside a wrapper is never called there, and enqueue stays bounded and
   non-blocking under any sink behaviour.

## 10. Evaluation (Phase 12 layer)

A new `observability` layer joins the Phase 12 report, with populations and denominators
stated per metric. Evidence classes: `PROPERTY` (seeded runs) and `REGRESSION` (hand-written
event and cost cases with rationale). No `CORPUS_COVERAGE` row claims performance.

| Metric | Numerator / denominator | Class | Gate |
|---|---|---|---|
| non-interference violations | seeded runs whose outputs differ with observability absent, present or failing / seeded runs | `PROPERTY` | **HARD: 0** |
| lifecycle violations | runs with an orphan, double-finished or unresolved-parent span / seeded runs (with injected crashes) | `PROPERTY` | **HARD: 0** |
| nondeterminism | runs whose replayed event stream differs / seeded runs | `PROPERTY` | **HARD: 0** |
| vocabulary and cardinality violations | events, label sets outside the allow-lists / events and label sets emitted | `PROPERTY` | **HARD: 0** |
| sensitive-content hits | artifacts containing a forbidden pattern / artifacts scanned | `PROPERTY` | **HARD: 0** |
| cost arithmetic mismatches | totals differing from recomputation / totals checked | `REGRESSION` | **HARD: 0** |
| unpriced calls summed as zero | unpriced calls included in a money total / unpriced calls | `REGRESSION` | **HARD: 0** |
| unclassified outcomes | `UNCLASSIFIED` outcomes / non-OK outcomes | `PROPERTY` | REPORT_ONLY, counted |
| accounting of dropped events | runs where `emitted ≠ delivered + dropped + buffered` / seeded runs with failing sinks | `PROPERTY` | **HARD: 0** |
| sink calls inside a wrapped call | wrapped calls during which a sink was invoked / wrapped calls | `PROPERTY` | **HARD: 0** |
| stage latency and failure distributions | per stage, from the local workload | local run, **descriptive only** | none |

The latency numbers are produced under injected or local clocks and are described as such;
they support "the measurement works", not "the system is fast".

## 11. Local operational demonstration

`python -m regulus.observability.demo` runs a deterministic synthetic workload (and, if the
local corpus is present, a real-corpus run) with failure injection: pipeline outages, store
faults, channel failures, a fake priced AI provider. It writes `events.jsonl`, `metrics.txt`,
`cost.json` and a short Markdown run summary under `evaluation/reports/observability/`. The
summary states the scope statement above and what was injected; it contains no source text.

## 12. Module layout

```
src/regulus/observability/
├── taxonomy.py   closed stages, outcomes, error classes, keys; mapping from existing statuses
├── events.py     ObsEvent, trace/span ids, validation
├── clock.py      injected monotonic and wall clocks
├── sinks.py      EventSink protocol, non-blocking bounded ObservationBuffer, drain, JSON-lines and in-memory sinks
├── metrics.py    registry with fixed names, labels, buckets and a cardinality cap; text export
├── cost.py       UsageRecord, PriceTable, integer arithmetic, totals, unpriced handling
├── instrument.py wrappers for the pipeline ports, review apply and the notification outbox
├── scan.py       allow-list and forbidden-pattern scan of emitted artifacts
└── demo.py       local workload, failure injection and report writing
src/regulus/evaluation/layers/observability.py
tests/observability/
```

## 13. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| **Events and lifecycle** | |
| normal run | one `RUN` span with child stage spans, all finished, parents resolve |
| retry | new span, `attempt + 1`, earlier attempt keeps its outcome |
| crash mid-stage, then recovery | open spans become `SPAN_ABANDONED`, `recovered` set, none lost |
| double finish / finish without start | rejected, counted `invalid_event` |
| child finishes after parent | rejected or flagged |
| same run, same clocks, twice | byte-identical stream and metric text |
| clock goes backwards | duration 0, `clock_regression` flagged |
| **Non-interference** | |
| every sink raising / hanging / full | results identical to no instrumentation |
| slow sink | the wrapped operation returns without waiting for delivery; only `drain` is slow |
| blocked sink | no sink is invoked inside any wrapper; only the driver calling `drain` blocks |
| enqueue under a full buffer | O(1), non-blocking; the overflow is a visible drop |
| drain budget | one `drain` delivers at most `max_events` |
| instrumentation code raising | wrapped call's result unchanged |
| observability on, off, failing across seeded faults | identical outputs, ledger and review state |
| **Vocabulary, cardinality, privacy** | |
| unknown attr or count key; free-text value | rejected at construction |
| id used as a metric label | registry refuses |
| label value outside its enum; too many label combinations | refused; cap enforced |
| source or obligation text, email, token, URL in any artifact | scan finds none; an injected one is detected |
| error message containing text | reduced to its `error_class` |
| **Classification** | |
| each mapped source status | the specified `error_class` and outcome |
| expected refusal (`DENIED`, `STALE`) | `REFUSED`, not counted as a fault |
| abstention (`INSUFFICIENT_EVIDENCE`) | `ABSTAINED` |
| unmapped status | `UNCLASSIFIED`, counted and listed |
| **Cost** | |
| reported usage, priced model | exact integer cost; recomputation equals reported total |
| model missing from the price table | `priced = false`; tokens shown; excluded from money; "N unpriced" reported |
| estimated usage | labelled, totalled separately, never merged into reported |
| retried and failed calls with tokens | recorded and costed |
| rounding at 1 token, 0 tokens, very large counts | integer, no float drift, no overflow |
| rules-only providers | "0 AI calls", not "cost 0" |
| usage record carrying text | rejected |
| **Sinks and drops** | |
| bounded buffer overflow | newest dropped, counter increments, `emitted = delivered + dropped + buffered` |
| an opaque id outside the permitted fields; a human-readable name | rejected by the allow-list and detected by the scan |
| **Integration** | |
| Phase 11 run with injected pipeline, store and channel faults | complete event stream; faults classified; notification and run spans consistent with the ledger |
| Phase 12 report | gains the `observability` layer; hard gates pass; descriptive latency rows labelled local |
| real corpus run (if present) | events and metrics produced; privacy scan clean; no performance claim |

## 14. Gate

Contract frozen after adversarial review, then: taxonomy and event model with construction-time
validation, clocks and sinks, metrics registry, cost accounting, wrappers at the port
boundaries, the scan, every §13 row, the §9 properties over seeded faulty runs, the Phase 12
`observability` layer with baseline, the local demonstration, ruff and strict mypy clean,
full real-corpus run, then freeze.

## 15. Decisions to confirm

1. Observe at existing port boundaries through wrappers; frozen phases are not edited, and
   sub-stage visibility is limited to what the ports expose.
2. Events carry ids; metrics carry closed-enum labels only.
3. Failures, refusals and abstentions are three different outcomes.
4. Sink isolation by a non-blocking bounded buffer and a separately driven drain; no threads required.
5. Privacy as "no direct personal data or human-readable identifiers; only permitted opaque ids", not "no personal data".
6. Money in integer micro-units; unpriced is a state; estimated tokens are separate; no
   shipped vendor prices.
7. "0 AI calls" is reported for the rules-only providers, and a fake priced provider proves the
   accounting.
8. No exporter beyond text and JSON lines, no server, no vendor SDK.
9. Latency figures are descriptive, from injected or local clocks; no SLO, capacity or
   production claim.
10. Phase 13 adds an `observability` layer to the Phase 12 evaluation report.
