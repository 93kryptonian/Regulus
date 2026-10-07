# Regulus — Reliability & Failure Semantics Contract

**Phase:** 14 · **Status:** FROZEN

```
Phase 9 / 11   how review and workflow resume after a failure
Phase 13       what happened, where, how long, at what cost
Phase 14       when a dependency or the infrastructure fails, what does Regulus
               guarantee about the resulting state, and is that proven?
```

> Phase 14 is a set of guarantees, a failure matrix that maps each failure to its guarantee
> and its evidence, and the small amount of hardening that matrix exposes. It is not a new
> retry engine: the retry, dead-letter, idempotency and recovery machinery already exists
> (Phases 9 and 11).

**Scope statement.** Phase 14 validates failure semantics under deterministic, seeded fault
injection against in-memory and fake infrastructure. It makes no availability, durability,
disaster-recovery or SLO claim about any real deployment.

## 1. Boundary

| Does | Does not |
|---|---|
| state the safety guarantees Regulus makes when a dependency fails | add a general retry, circuit-breaker or queue framework |
| inject faults deterministically at the existing boundaries | test real disks, networks, databases or clouds |
| prove recovery converges, is idempotent and loses nothing | claim durability beyond what the store port provides |
| name and implement the small hardening the matrix exposes | change any frozen behaviour (additions are additive and listed in §9) |
| report evidence in the Phase 12 report | promote a fault-injection result to a production claim |

Real-infrastructure failure (disk, network, replica, backup and restore) belongs to the
deployment phase (16) and to a real environment; this contract states that boundary rather
than simulating it.

## 2. Fault model

Faults are injected through wrappers around the existing ports and stores, driven by a seeded
`FaultPlan`, so every run is reproducible and every injected fault is listed in the report.

| Fault | Meaning | Injection |
|---|---|---|
| `UNAVAILABLE` | the dependency raises a retryable error | pipeline, directory, channel, store |
| `PERMANENT` | the dependency rejects the request for good | pipeline, channel |
| `TIMEOUT` | the call exceeds its budget; modelled as the injected clock advancing past the budget, then `Timeout` | pipeline, channel |
| `CRASH` | the process dies at a step | existing step points: intent, task, obligation, record, and mid-run points |
| `DUPLICATE` | the same input is delivered twice | event, submission request, review request, notification send, tick |
| `PARTIAL_PERSISTENCE` | a multi-effect write is interrupted after some effects | intent store steps |
| `CORRUPTION` | a stored stream is modified, truncated, reordered or spliced | ledger streams, review logs, the submission intent payload |
| `CLOCK_SKEW` | time goes backwards or jumps | injected clocks |

`Timeout` is classified as `UNAVAILABLE` (retryable). A late result from a timed-out call is
never applied a second time (G10).

## 3. Guarantees

Each guarantee is checked by a named invariant function over the stores and logs after a
fault run, independent of the engines it checks.

| Id | Guarantee |
|---|---|
| **G1** | **No partial lifecycle transition.** An obligation's status changes only by a Phase 1 transition committed together with its audit record; an `EDIT` is both decisions or neither; no `PENDING_REVIEW` obligation exists without its task. |
| **G2** | **No phantom obligation.** Every registered obligation has a submission record and a task; no record or task refers to an obligation that is not registered. The one allowed exception is the in-flight state of an intent-protocol submission (phase `INTENT`, task stored and obligation not yet registered), which recovery completes from the intent payload and which, like any prepared state, is not an observable committed state; the effects are ordered so that a registered obligation never lacks its task. |
| **G3** | **No lost submission.** In every **observable committed state**, every item that reached `GENERATED` and verified is submitted, dead-lettered with a visible reason, or pending with a next attempt; the unaccounted count is 0. Internal transactional or prepared state (between the steps of a transaction or an intent) is not an observable committed state and is not checked. |
| **G4** | **No duplicate logical decision.** Delivering the same review request twice records one decision (the second is `STALE` and changes nothing); decision and record ids are unique; a replayed submission or notification creates no second task or logical notification. |
| **G5** | **No silent corruption.** The corruption classes the integrity scheme covers and the tests exercise (modification of a record, deletion, reordering, truncation of the tail where a later record or tip reference exists, splicing a foreign record) are detected by chain verification, and a store guarded by §6 refuses to write to a stream whose chain fails. The claim is limited to those classes; it is not a statement about every conceivable alteration. |
| **G6** | **Recovery convergence, conditional on fault removal.** After the injected faults are removed and the documented recovery is executed (re-run the same operations; operator requeue of dead letters), the recovered logical state equals the uninterrupted logical state, differing only in retry-attempt history and explicitly recorded dead-letter and recovery history. A fault that remains active may legitimately leave the run retryable or dead-lettered; that is not a convergence failure. |
| **G7** | **Duplicate-input idempotence.** Re-delivering the **same logical input**, identified by its stable idempotency or deduplication key, produces no additional logical effect. Excluded, because they are meant to change state: an operator requeue, a corrected event or new content or version, a new retry window, and an intentionally distinct notification event. |
| **G8** | **Bounded and visible retry.** Every retry loop terminates in at most the configured attempts, ends in a visible dead letter, and a run that is neither complete nor dead always has a `next_attempt_at`; nothing retries forever or silently stops. |
| **G9** | **Degraded operation never weakens review.** A missing dependency may delay a task or send it to a dead letter; it never creates a task whose snapshot looks more complete or more checked than it is (§5). |
| **G10** | **Timeout safety, including the ambiguous case.** A timed-out call is retryable. A timeout can mean the effect never happened (`timeout_before_effect`) or that it committed and only the response was lost (`timeout_after_effect`); the caller cannot tell which. In both cases a retry with the same idempotency, submission or dedupe key yields exactly one logical effect, and a late result is never applied a second time. |

## 4. Failure matrix

Each row has a stable id, and a machine-readable copy `evaluation/reliability/matrix.v1.json`
names the test(s) that provide its evidence. A coverage test fails if a row has none.

| Id | Failure domain and fault | Guarantee | Behaviour and recovery | Degraded behaviour |
|---|---|---|---|---|
| R01 | source file unreadable (`PERMANENT`) | G3 | document `FAILED`; run stage dead-letters with a reason; no obligation is created | none: nothing is invented |
| R02 | document with a failed page | G9 | partial document; readable articles continue; **the snapshot is marked source-incomplete** (§5.3) | approval then needs acknowledgement |
| R03 | document processed with issues (gaps, mode conflict) | G9 | continues; snapshot marked source-incomplete | approval needs acknowledgement |
| R04 | extraction raises or yields nothing for a marker | G3 | the marker becomes a diagnostic or an unresolved region; never silent loss | region goes to review, not to "no obligation" |
| R05 | generation fails or is rejected by the verifier | G3 | the candidate is not an obligation; recorded with its reason; retry only for retryable failures | none |
| R06 | similarity or index unavailable (`UNAVAILABLE`) | G9, G8 | the item retries, then dead-letters; **it is not submitted un-enriched** | none; or §5.2 if the item is ever submitted without similarity |
| R07 | store write fails (`UNAVAILABLE`) at each commit step | G1, G2, G6 | nothing durable or complete-and-consistent; retry completes | none |
| R08 | crash at each intent, task, obligation, record step | G1, G2, G6 | transactional store: nothing visible; intent store: recovery completes from the intent payload | none |
| R09 | crash mid review action or mid edit | G1, G4 | state and log unchanged or both decisions committed; re-delivery is `STALE` or applied once | none |
| R10 | notification channel down, then up | G3, G6 | `QUEUED`, retry with backoff, then delivered or dead-lettered; review unaffected; a dead-lettered notification can be requeued by an operator (§9) | none |
| R11 | duplicate event | G7 | same run key; nothing duplicated | none |
| R12 | duplicate submission | G4, G7 | `ALREADY_SUBMITTED`; one task | none |
| R13 | duplicate review request | G4 | one decision, the repeat is `STALE` | none |
| R14 | duplicate notification send (crash after send) | G10 | resend with the same dedupe key; one logical notification | duplicates only on a channel that cannot dedupe, stated |
| R15a | dependency timeout before the effect | G10, G8 | treated as `UNAVAILABLE`; the retry produces one effect | none |
| R15b | dependency timeout after the effect committed (response lost) | G10 | treated as `UNAVAILABLE`; the retry with the same key produces no second effect | none |
| R16 | corrupted ledger stream (modify, delete, reorder, truncate, splice) | G5 | detected by verification; the guarded store refuses writes to that stream | operation refused as a whole, not repaired silently |
| R17 | corrupted review log | G5 | detected by chain verification and replay; the review engine refuses to apply on it | refused |
| R18 | corrupted or altered submission intent payload | G5 | the intent hash/chain fails; recovery refuses to complete from it | refused and surfaced |
| R19 | clock goes backwards | G5, G8 | a regression is recorded and the operation refused; durations clamp | operation retried later |
| R20 | one to three faults in one run (outage, crash, store fault, duplicate), seeded | G6 | after the faults are removed, recovery converges to the uninterrupted logical state | none |
| R21 | directory unavailable | G9 | task stays unassigned and visible; review is not blocked | assignment is a hint only |
| R22 | observability sink failing | G1 | no effect on any result (Phase 13) | events buffered or dropped, counted |

### 4.1 Matrix integrity

Every row in `matrix.v1.json` has a unique stable id, a valid fault kind, one or more valid
guarantee ids, a declared recovery behaviour, a declared degraded behaviour (or "none"), and at
least one existing test reference. Conversely, a reliability test may claim coverage only for a
row that exists; a claim for an unknown row, or a row nothing claims, fails the matrix test.
Multi-fault rows use a bounded number of faults per run (one to three) with deterministic seeds,
never an exhaustive enumeration of fault combinations.

## 5. Degraded operation

1. **A dependency failure may delay, never weaken.** The allowed responses are retry, dead
   letter, or an explicit refusal. No response silently lowers a review gate.
2. **"Not evaluated" is not "no matches".** A snapshot without a similarity result means
   similarity was not evaluated. The Phase 10 view must say so ("similarity not evaluated"),
   not "No matches". The reference pipeline never submits without enrichment; the view rule
   covers any adapter or direct caller that does (§9, amendment B).
3. **Source completeness follows the document.** A document whose status is `PARTIAL` or
   `PROCESSED_WITH_ISSUES` yields `source_complete = false` in every snapshot built from it, so
   approval needs the existing acknowledgement. The reference pipeline adapter sets this (§9,
   amendment C).
4. **Deterministic first.** A regulatory event's deterministic notification does not wait for
   any AI stage (Phase 11); a failing AI path never suppresses it.

## 6. Integrity guard

A thin wrapper, `GuardedStore`, verifies the chain of the stream a write is about to extend
and refuses with `IntegrityError` if it fails; reads and `verify()` are unchanged. It is
opt-in, wraps the existing store ports, and does not edit them. **Limit:** it is a pre-write
integrity check within the reference store model; it does not claim atomic integrity under
concurrent external writers or real distributed storage (a check-then-write gap exists there),
which is a deployment concern. The same guard exists for the
review store (verify the obligation's log before `commit`). A refusal is classified for
Phase 13 as `STORE` with a distinct `INTEGRITY` attr, so it is visible.

## 7. Evaluation (a Phase 12 layer)

A `reliability` layer joins the report. Evidence class `PROPERTY` (seeded fault runs) unless
stated; no row claims production reliability.

| Metric | Numerator / denominator | Gate |
|---|---|---|
| state-safety violations (G1, G2) | runs with any violation after faults / seeded fault runs | **HARD: 0** |
| lost items (G3) | unaccounted items / items observed | **HARD: 0** |
| duplicate logical decisions or tasks (G4, G7) | duplicates / re-delivered inputs | **HARD: 0** |
| undetected corruption (G5) | injected corruptions not detected / injected corruptions (`REGRESSION`) | **HARD: 0** |
| writes accepted on a corrupted stream (guarded store) | accepted writes / attempted writes on corrupted streams (`REGRESSION`) | **HARD: 0** |
| recovery divergence (G6) | fault runs whose final logical state differs from the uninterrupted run / seeded fault runs (multi-fault) | **HARD: 0** |
| unbounded or silent retry (G8) | runs exceeding the attempt bound or stopped without a visible state / seeded runs | **HARD: 0** |
| weaker-than-shown snapshots (G9) | tasks from a partial or issue-bearing document without the incomplete flag / such tasks | **HARD: 0** |
| second effects after a timeout (G10) | second effects / timeout cases, `before_effect` and `after_effect` counted separately | **HARD: 0** |
| matrix coverage | rows with at least one named, existing test / matrix rows | **HARD: all** |
| matrix integrity | rows violating the rules in §4.1 / matrix rows and test claims | **HARD: 0** |
| fault-injection transparency | runs whose results differ with the wrappers present and no fault planned / runs | **HARD: 0** |

A metric whose population is empty in a run (for example no timeout case was generated) is
`NOT_MEASURABLE`, never `0 / 0`. The matrix rows, the injected faults per run, and the seeds are
listed in the report.

## 8. Module layout

```
src/regulus/reliability/
├── faults.py       FaultKind, FaultPlan (seeded schedule), Timeout, fault log
├── wrappers.py     FaultyPipeline, FaultyChannel, FaultyDirectory, DuplicatingDelivery, corruption helpers
├── guard.py        GuardedStore, GuardedReviewStore, IntegrityError
├── invariants.py   independent checkers for G1 to G10
└── matrix.py       load and validate the failure matrix against the test suite
evaluation/reliability/matrix.v1.json
src/regulus/evaluation/layers/reliability.py
tests/reliability/
```

## 9. Hardening this contract introduces (all additive)

| Id | Change | Why (the matrix row that exposed it) |
|---|---|---|
| A | `requeue_notification(store, key, principal, reason, now)` in the notifications package. **Operator role only; only `DEAD_LETTER → QUEUED`** (every other state refuses, including `DELIVERED`, `FAILED_PERMANENT`, `QUEUED` and `RETRYING`). It appends a recorded `REQUEUED` fact with the actor and a required reason, keeps the same logical notification and dedupe key, and starts a new attempt window so the requeue is never mistaken for the original attempt in the ledger or in Phase 13 events | R10; the Phase 12 report lists this gap |
| B | the Phase 10 view and renderer show "similarity not evaluated" when the snapshot has no similarity result, instead of "No matches" | R06, G9; the current page cannot tell the two apart |
| C | the reference corpus pipeline adapter sets `source_complete = false` for `PARTIAL` and `PROCESSED_WITH_ISSUES` documents | R02, R03, G9; two of the twelve corpus documents are processed with issues and their snapshots currently say complete |
| D | `GuardedStore` and `GuardedReviewStore` | R16 to R18, G5 |

B changes a frozen Phase 10 surface (one wording and its test) and is therefore proposed as a
Phase 10 amendment for your approval; A, C and D add behaviour without altering any frozen one.

## 10. Adversarial matrix for the Phase 14 machinery

| Case | Expected |
|---|---|
| a fault plan with a seed, run twice | identical injected faults and results |
| no fault planned, wrappers present | results identical to unwrapped |
| each fault kind at each boundary | the §4 row's guarantee holds |
| two faults in one operation (store fault during recovery of a crash) | convergence after repeated recovery |
| crash during recovery | recovery is itself re-runnable |
| timeout before the effect, then retry | one effect |
| timeout after the effect (response lost), then retry with the same key | exactly one effect |
| fault still active after the retry bound | run stays retryable or dead-lettered; not a convergence failure |
| duplicate of the same input versus a corrected or new input | the duplicate is a no-op; the corrected input is a new effect |
| a requeue of a dead-lettered notification | allowed once for the operator, recorded, new attempt window; every other state refuses |
| each corruption mode on a ledger, a review log, an intent | detected; guarded write refused |
| guard on an intact stream | writes pass, behaviour unchanged |
| requeue of a non-dead-lettered notification | refused, nothing changes |
| requeue by a non-operator | refused |
| snapshot from a partial document | `source_complete = false`; approval needs acknowledgement |
| snapshot without similarity | the view says not evaluated |
| matrix row with no test | coverage test fails |
| report contains no fault payload text, only ids, kinds and counts | scan clean |

## 11. Gate

Contract frozen after review, then: the fault plan and wrappers, the invariant checkers (each
shown to detect an injected violation), the guard, hardening A, C and D (B after its Phase 10
amendment), the matrix file and its coverage test, every row's tests, the seeded multi-fault
properties, the Phase 12 `reliability` layer with baseline, ruff and strict mypy clean, the
full real-corpus check of hardening C, then freeze.

## 12. Decisions to confirm

1. Phase 14 is guarantees, a failure matrix and evidence, not a new retry framework.
2. Faults are injected at the existing ports and stores through wrappers; real infrastructure
   failure is out of scope and deferred to deployment (16).
3. Hardening A, C, D are additive; B is a Phase 10 amendment, approved and not deferred.
4. Corruption is detected and refused, never silently repaired.
5. Missing enrichment delays or dead-letters an item; it never yields a task that looks more
   checked than it is.
6. The failure matrix is a committed data file with a coverage test, so a row cannot exist
   without evidence.
7. A `reliability` layer joins the Phase 12 report; no availability or durability claim.
