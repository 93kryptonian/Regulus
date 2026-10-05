# Regulus — Change Detection Contract

**Phase:** 2 · **Status:** FROZEN

Answers one question: **what regulatory event happened?** Nothing else.
No relevance, sector, obligation, similarity or semantic reading of legal text
(Phases 4–8). No LLM, DB, network or clock access: a pure function.

```
SourceRecord ─▶ [match targets] ─▶ [detect] ─▶ RegulatoryEvent[]   (DetectionResult)
RegulatoryEvent[] ─▶ [project] ─▶ Regulation.status                (cache, never authoritative)
```

## 1. Regulation vs event

A regulation **exists** in the corpus; an event is **something that happened to
it**. A record seen again produces no new event. The downstream boundary is
`RegulatoryEvent` only: later phases never re-derive change from raw records.

An event is: a regulation entering the corpus (`NEW`), or a declared relation
from that regulation onto another (`AMEND`, `REPEAL`, `PARTIAL_REPEAL`), or an
explicit refusal to decide (`NEEDS_REVIEW`).

Not events: re-ingestion, metadata-only refreshes without conflict, a record
that declares nothing, a regulation being referenced in text, status changes
(those are a projection, §6).

## 2. Input contract (Phase 2 types, not domain)

`SourceRecord`: `source_id` (provenance), `kind`, `number`, `year`, `title`,
`promulgated_on` (diundangkan), optional `enacted_on`, `issuer`,
`relations: tuple[DeclaredRelation, ...]`.

`DeclaredRelation`: `action` (`MENGUBAH` | `MENCABUT` | `MENCABUT_SEBAGIAN`),
`target: TargetRef`.

`TargetRef`: `raw` (verbatim text, always kept), and optional `kind`, `number`,
`year` parsed by the *source adapter*, not the detector.

The detector never parses prose and never repairs data: it consumes structured
declarations. Extracting relations from PDF text is Phase 3/5.

`action` is a closed enum. An unsupported action string is an adapter failure:
it is rejected when the `SourceRecord` is built and never reaches the detector.
Mapping is fixed: `MENGUBAH→AMEND`, `MENCABUT→REPEAL`,
`MENCABUT_SEBAGIAN→PARTIAL_REPEAL`. Partial-repeal *scope* (which articles) is
Phase 5.

The detecting regulation is the actor: `event.regulation_id` = the new
regulation, `event.target_id` = the affected one. `occurred_on` is the record's
`promulgated_on`. It is a Phase 2 projection of the promulgation date, **not** a
claim that the legal effect of the relation begins then; effectivity dates are
out of scope.

## 3. Matching

`RegulationIndex` maps natural key `(kind, number, year)` → `Regulation`
(Phase 1 id). A `TargetRef` is classified as exactly one of:

| Class | Condition | Result |
|---|---|---|
| RESOLVED | `kind`, `number`, `year` all present and exactly one index hit | target id |
| UNRESOLVED | all present, zero hits (target not in corpus) | `NEEDS_REVIEW(UNRESOLVED_TARGET)` |
| AMBIGUOUS | a field missing and ≥2 candidate hits | `NEEDS_REVIEW(AMBIGUOUS_TARGET)` |
| MALFORMED | no number or no year; or any field missing with ≤1 candidate | `NEEDS_REVIEW(MALFORMED_TARGET)` |

Rule: **never choose a probable target.** (Corpus growth could make a currently
unique partial reference ambiguous; the detector has no authority to turn an
incomplete reference into an identity.) A partial reference that happens to
match exactly one candidate is MALFORMED, not resolved. Matching is exact on
normalized `(kind, number, year)`; no fuzzy matching.

## 4. Detection rules

Per record, in order:

1. **Structural validity.** Missing/invalid `kind`, `number`, `year`, `title` or `promulgated_on` ⇒ `FAILED`, no events (no identity or date can be established).
2. **Identity gate.** Record's key already in the index with different `title`/`promulgated_on`/`enacted_on` ⇒ exactly one `NEEDS_REVIEW(METADATA_CONFLICT)`; **stop**: no `NEW`, no relation events from this record; the index entry is not overwritten. The conflicting fields are returned in `DetectionResult.conflicts`.
3. **NEW.** Emitted once per regulation identity (dedup via event id, not via index membership).
4. **Relations**, each independently:
   - self-reference (target resolves to, or raw equals, the record's own key) ⇒ `NEEDS_REVIEW(SELF_REFERENCE)`; the event carries `target_id=None` because Phase 1 forbids `target_id == regulation_id`;
   - target class per §3;
   - same `(action, target)` declared twice ⇒ one event;
   - contradictory actions on the same target by one record (e.g. `MENGUBAH` and `MENCABUT`; `MENCABUT` and `MENCABUT_SEBAGIAN`) ⇒ none of them is emitted; one `NEEDS_REVIEW(CONFLICTING_RELATIONS)`.
5. A record with no relations still yields its `NEW` (or nothing if already seen).

**Invariant:** a structurally conflicting source record cannot produce a
positive regulatory event.

`NEEDS_REVIEW` never carries a guessed target. The declared intent is preserved
(§7).

## 5. Determinism and idempotency

"Same state" is exactly: `(record, index snapshot, seen event ids, detected_on)`.
`detected_on` is an argument (injected clock), never read from the system.
Given the same four inputs, output is identical, including order (sorted by
event id).

Event identity is derived, never random:

```
id = "evt-" + sha256(type | regulation_id | target_id | discriminator)[:16]
discriminator = ""                                       NEW/AMEND/REPEAL/PARTIAL_REPEAL
              = reason:action:normalized(raw ref)         target reasons
              = reason:fingerprint(conflicting values)    METADATA_CONFLICT,
                                                          CONFLICTING_RELATIONS
```

Dates are deliberately excluded, so the same fact ingested on different days,
or with a corrected `occurred_on`, never creates a second event. An id already
in `seen` is dropped and counted in `duplicates`. A *changed* conflicting
version fingerprints differently and does raise a new `NEEDS_REVIEW`.

Detection never mutates the index or the event log; the caller persists
events and updates the index (Phase 11).

## 6. Status projection

`project_status(regulation_id, events) -> RegulationStatus`, pure. Events are
ordered by `(occurred_on, id)`; only events where the regulation is the
**target** (plus its own `NEW`) count. `NEEDS_REVIEW` is ignored.

| State after replay | Status |
|---|---|
| no events known | `UNKNOWN` |
| own `NEW` seen | `IN_FORCE` |
| then `AMEND` or `PARTIAL_REPEAL` | `AMENDED` |
| any `REPEAL` | `REPEALED` (absorbing) |

`Regulation.status` is a cache of this function; a mismatch means the cache is
stale, never that history is wrong. Ingestion order does not change the result,
only `(occurred_on, id)` does.

An `AMEND`/`PARTIAL_REPEAL`/`REPEAL` dated after a `REPEAL` of the same target
does not change status; `project_status` returns it in an `anomalies` list for
review (it is not silently accepted, and not dropped).

## 7. Output contract

`DetectionResult`: `source_id`, `outcome`, `events`, `duplicates`, `errors`,
`conflicts` (field, indexed value, incoming value: the evidence behind a
`METADATA_CONFLICT` or `CONFLICTING_RELATIONS` event, kept out of the event).

`outcome ∈ {PROCESSED_OK, PROCESSED_EMPTY, FAILED}`:
- `PROCESSED_OK`: ≥1 new event emitted.
- `PROCESSED_EMPTY`: processed, nothing new (e.g. exact re-ingestion).
- `FAILED`: structural invalidity; `errors` non-empty; no events.

`NOT_PROCESSED` is the absence of a result for a record; a batch must return
exactly one result per input record, in input order.

`basis` on every event: `src=<source_id>|rel=<action>|ref=<raw>` (or
`rel=` omitted for `NEW`): enough to trace an event to its declaration.

## 8. Required domain amendment A1 (Phase 1, re-freeze first)

`NEEDS_REVIEW` carried only `basis`, so a review queue could not filter by
cause, and `basis` must not double as a machine-readable taxonomy. Phase 1 is
amended and re-frozen **before** Phase 2 implementation.

`RegulatoryEvent` gains `reason: ReviewReason | None` and
`declared_ref: str | None`; `ReviewReason = UNRESOLVED_TARGET | AMBIGUOUS_TARGET |
MALFORMED_TARGET | SELF_REFERENCE | CONFLICTING_RELATIONS | METADATA_CONFLICT`.

| `reason` | `declared_ref` |
|---|---|
| `UNRESOLVED_TARGET`, `AMBIGUOUS_TARGET`, `MALFORMED_TARGET`, `SELF_REFERENCE` | required: raw target text |
| `CONFLICTING_RELATIONS`, `METADATA_CONFLICT` | `None` (evidence goes in `DetectionResult.conflicts`) |

Rules: `reason` required iff `type == NEEDS_REVIEW`; `declared_ref` allowed
only for the first four reasons, and required there.

## 9. Module layout

```
src/regulus/change_detection/
├── models.py       SourceRecord, DeclaredRelation, TargetRef, DetectionResult
├── matcher.py      RegulationIndex, classify/resolve
├── identity.py     event_id
├── detector.py     detect(), detect_batch()
└── projection.py   project_status()
tests/change_detection/
```

## 10. Adversarial cases (must each have a test)

| Case | Expected |
|---|---|
| Same record ingested twice | 2nd: `PROCESSED_EMPTY`, `duplicates=n`, same ids |
| Same relation declared twice | one event |
| Two different records, same relation | two events (different `regulation_id`) |
| Amend/repeal unknown target | `NEEDS_REVIEW(UNRESOLVED_TARGET)`, `target_id=None` |
| Partial ref matching ≥2 candidates | `NEEDS_REVIEW(AMBIGUOUS_TARGET)` |
| Missing year/number in ref | `NEEDS_REVIEW(MALFORMED_TARGET)` |
| Regulation amends/repeals itself | `NEEDS_REVIEW(SELF_REFERENCE)` |
| Same target amended and repealed in one record | single `NEEDS_REVIEW(CONFLICTING_RELATIONS)` |
| Known key, different title/date | one `NEEDS_REVIEW(METADATA_CONFLICT)`; no `NEW`, no relation events; index untouched |
| Same conflict twice / a third differing version | deduped / new event |
| Conflicting record that also declares relations | relations not processed |
| Malformed record (no promulgation date) | `FAILED`, no events |
| Repeal → later amendment (by date) | status stays `REPEALED`; anomaly reported |
| Amendment → later repeal | `AMENDED` then `REPEALED` |
| Records ingested in different order, same dates | identical projection |
| Repeated detector run, same state | byte-identical result |
| `detected_on` changes between runs | same event ids |
| Batch of N records | exactly N results, input order |

Plus property-style checks: `detect` is pure (inputs unchanged), idempotent
under replay of its own output, and never emits an event violating Phase 1
invariants.

## 11. Non-goals

Relevance, sector, obligation or lineage interpretation; fetching sources;
parsing PDF or prose; persistence; fuzzy target resolution; effectivity dates;
partial-repeal scope; automatic re-resolution of `NEEDS_REVIEW` (a later
re-run emits the resolved event under a new id; the earlier `NEEDS_REVIEW` is
never deleted, and projection ignores it).

## 12. Gate

Contract frozen after adversarial review → implementation → every row of §10
passing → lint/types clean → detector fixture derived from real corpus identities
(a synthetic `MENGUBAH` record by PP 33/2026 targeting UU 27/2022, resolved
against an index holding both real keys; not a claim about the real
relationship) →
freeze.

## 13. Decisions

1. **A1:** accepted, with `declared_ref` semantics in §8. Phase 1 is amended and re-frozen before Phase 2 implementation.
2. **PP 33/2026 "implements" UU 27/2022:** outside Phase 2 (Phase 5 lineage). The Phase 2 gate uses a synthetic detector fixture derived from real corpus identities.
3. **`occurred_on = promulgated_on`:** accepted for Phase 2; explicitly not an effectivity claim (§2).
4. **Partial references:** strict policy kept (§3).
5. **Unsupported action:** removed from detector semantics; the closed enum means unsupported values are rejected before detection (§2).
6. **Metadata conflict:** gate before `NEW` (§4); a conflicting record yields `NEEDS_REVIEW` only.
