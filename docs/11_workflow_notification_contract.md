# Regulus — Workflow & Notification Contract

**Phase:** 11 · **Status:** FROZEN

```
Phase 9   Review decisions, gates, audit log                 (review authority)
Phase 10  Presentation of review state
Phase 11  How work reaches a reviewer, and how people are told   (orchestration)
```

> Phase 11 moves work and sends messages. It never decides anything about an
> obligation, never owns a lifecycle, and never makes a message sound like approval.

```
regulatory event ─┬─► deterministic notification  (never waits on AI)
                  │
                  └─► pipeline (documents → … → generation → similarity)
                            │
                            ▼
                      submit_for_review ──► Phase 9 task ──► (Phase 9/10 review)
                            │
                  assignment hint · due dates · reminders · AI-enriched notification
```

## 1. Boundary

| Does | Does not |
|---|---|
| run the pipeline stages for an event, resumably and idempotently | decide relevance, extraction, generation or similarity (earlier phases) |
| `submit_for_review`: hand a verified `GENERATED` obligation to Phase 9 | approve, reject, edit, publish, or change any review state |
| keep assignment hints, due dates and overdue projections | grant authority: a claim and every review action stay Phase 9 |
| queue, send, retry and record notifications | let notification success or failure change review state |
| keep a hash-chained, replayable ledger of what it did | become a second source of truth for obligation status |
| expose read-only projections for Phase 10 | move presentation rules into the workflow |

Infrastructure is behind ports (`Pipeline`, `Notifier`, `Directory`, `Recipients`, `Clock`,
`WorkflowStore`); the contract is testable with in-memory fakes, no Slack, email, cron or queue.

## 2. State ownership

| Fact | Owner |
|---|---|
| obligation status, review log, claims, decisions, snapshots | **Phase 9** (read-only here) |
| `GENERATED → PENDING_REVIEW` | Phase 1 `submit()`, called **only** from `submit_for_review` |
| event/stage progress, assignment hints, due dates, notification queue and attempts | Phase 11 ledger |

Phase 11 writes no obligation field and no Phase 9 log record. The ledger is never
consulted by a Phase 9 gate. Deleting the whole ledger changes no review outcome.

## 3. Ledger

Append-only, hash-chained per stream (same scheme as Phase 9: `GENESIS`, sha256 of
previous hash plus canonical JSON). Streams: `event:{id}`, `task:{id}`, `notification:{key}`.
Every state is a pure projection of its stream (`replay`); the stored state must equal the
replay. A state change and its ledger append are one atomic `WorkflowStore` commit (as in
Phase 9 §7). Records carry: id, stream, kind, subject, idempotency key, principal,
injected time, details, `prev_hash`, `hash`.

## 4. Pipeline orchestration

An event (Phase 2 `RegulatoryEvent`) becomes a **run** keyed `event_id + pipeline_config_version`.

| Stage | Class | Failure |
|---|---|---|
| `DETECTED` notification | deterministic | independent of every later stage |
| `PROCESS` (documents, relevance, lineage) | deterministic | retry, then dead-letter |
| `EXTRACT`, `GENERATE`, `SIMILARITY` | AI-enriched | `PIPELINE_UNAVAILABLE`: retry with backoff, then dead-letter; never silently skipped |
| `SUBMIT` per obligation | hand-off | idempotent, see §5 |

Stage status: `PENDING`, `DONE`, `FAILED_RETRYABLE(next_attempt_at)`, `DEAD_LETTER`.
A run is **complete** only when every stage and every produced obligation is `DONE` or
`DEAD_LETTER` with a visible reason. Partial completion is stored per stage and per
obligation, and a resumed run continues from the ledger without redoing `DONE` work and
without creating a second task. `DEAD_LETTER` is a visible state with a manual requeue by a
principal holding `OPERATOR`; it is never a drop.

## 5. `submit_for_review`

```
submit_for_review(result: GenerationResult, snapshot_inputs, principal, now) -> SubmissionOutcome
```

Preconditions, all checked, each failure a distinct refusal and a ledger record, nothing
else changed:

1. `result.status is GENERATED` and its obligation is `GENERATED` (Phase 1).
2. The Phase 7 evidence and trace are present and re-verified against the owner text
   (the same verification Phase 9 applies at approval). Unverified evidence is **not**
   submitted: it is dead-lettered with `EVIDENCE_INVALID` rather than sent to a reviewer
   as if reviewable.
3. The snapshot is built by Phase 9 `build_snapshot` from the real Phase 6/7/8 outputs
   (candidate included), never constructed by Phase 11.

**Transaction boundary.** Phase 1 `submit()` is a pure function (it returns a new
obligation); nothing is durable until commit. `submit_for_review` therefore *prepares* the
`PENDING_REVIEW` obligation, the Phase 9 task and the submission record, then makes them
durable in **one `WorkflowStore` transaction**: obligation registered as `PENDING_REVIEW`,
Phase 9 task stored, ledger record (which **is** the idempotency record) appended. All
become visible together or not at all. Phase 1 remains the authority for the transition;
Phase 11 only coordinates the transaction that contains it.

A store that cannot provide such a transaction must implement the equivalent recovery
protocol: a durable `SUBMISSION_INTENT` is written first. It carries the **complete prepared
submission**, or immutable references from which exactly that content is recoverable
without re-running any pipeline stage: the key and content hash, the prepared
`PENDING_REVIEW` obligation, the Phase 9 snapshot (candidate and evidence included) and the
task id. A hash alone is never sufficient. The three effects are then applied idempotently,
and recovery **completes** an intent whose effects are partial from that stored payload
(never compensates by un-submitting, never re-prepares from live data). The in-memory reference store implements
the transaction; the recovery rule below holds for both.

Idempotency key: `obligation_id + content_hash(generated)`.

| Repeat or state found | Result |
|---|---|
| same key, complete | `ALREADY_SUBMITTED`: original task returned, no second task, no second transition |
| same key, partial (obligation `PENDING_REVIEW` or intent present, task or record missing) | **completed** to the identical result; never `NOT_SUBMITTABLE` |
| same obligation id, different generated content | `CONFLICT`: refused and recorded; never overwrites or replaces a task |
| obligation not `GENERATED` and no submission of this key | `NOT_SUBMITTABLE` |
| transaction fails | no submission effects become durable (no obligation change, no task, no submission record). A separate `SUBMIT_FAILED` attempt may be recorded when the store is available; failing to record it does not alter the submission outcome. Retryable |

**Submission invariant.** For every successful submission key exactly one lifecycle
transition, one registration, one task and one submission record exist, made visible
atomically. Repeating a submission after any crash point returns the original result or
deterministically completes it; it can never answer `NOT_SUBMITTABLE` while the original
submission lacks a task.

`submit_for_review` has no path to `APPROVED`/`PUBLISHED`, accepts no reviewer, and cannot
pre-fill a disposition, resolution or acknowledgement.

## 6. Assignment

Assignment is a **routing hint**, not a claim. `assigned_to` never changes a Phase 9 gate,
refusal, queue order or claim, and a review action by a non-assignee is judged exactly as
before.

| Rule | |
|---|---|
| who assigns | the system (deterministic strategy) or a principal with `COORDINATOR` |
| eligible | the `Directory` lists the person as an available `REVIEWER`; checked at assignment time; Phase 9 re-checks at action time |
| strategy | fewest open assigned tasks, ties by reviewer id; no randomness |
| none available | task stays `UNASSIGNED(reason=NO_REVIEWER_AVAILABLE)`, visible in the pool, re-evaluated each tick; never dropped |
| reassign | new hint with a required reason; a held claim is untouched (it expires by Phase 9 TTL); both records kept |
| four-eyes | assignment cannot make an editor the approver of their own edit: it may *suggest* them, Phase 9 still denies |
| closed task | assignment to a `DONE` task refused |

## 7. Scheduling

Time is injected. `due_at = created_at + sla(risk_class)`, with `risk_class` and its SLA
from configuration, derived from the Phase 9 snapshot (dangerous match, withdrawn or
changed source, open questions) and not from anything the UI computes. SLA values are
configuration with a stated default; none is a regulatory claim.

`overdue(task, now)` is a **projection**, not a state: it changes no review state and
blocks no action. `tick(now)` is pure: from the ledger and `now` it returns the actions
due (reminder, escalation notification, retry, re-evaluate unassigned); a tick is
idempotent, and each action has the key `(kind, subject, window)`, so running a tick twice
or after a crash produces each action once. The window is fixed per kind:
`TASK_DUE_SOON` = `task_id` + the due-soon threshold crossing (once per task and `due_at`);
`TASK_OVERDUE` = `task_id` + the calendar day (UTC) of the escalation;
`RETRY` = `item_id` + attempt number; `UNASSIGNED` re-evaluation = `task_id` + tick time bucket.
Changing `due_at` (reschedule) starts a new window and is itself a ledger record.

Retry schedule is deterministic from the attempt count (`base * 2^n`, capped), with a
maximum; exhaustion moves the item to `DEAD_LETTER` with the last error class (never a
payload, token or URL).

## 8. Notifications

```
NotificationEvent(kind, class, subject, dedupe_key, payload)   class: DETERMINISTIC | AI_ENRICHED
```

| Kind | Class | Source |
|---|---|---|
| `REGULATION_DETECTED`, `AMENDMENT_DETECTED` | DETERMINISTIC | Phase 2/5 facts |
| `OBLIGATIONS_READY` | AI_ENRICHED | counts of potential obligations, similarity candidates |
| `TASK_ASSIGNED`, `TASK_DUE_SOON`, `TASK_OVERDUE` | DETERMINISTIC | ledger, clock |
| `SOURCE_CHANGED`, `SOURCE_WITHDRAWN` on an open task | DETERMINISTIC | Phase 9 snapshot flags |
| `REVIEW_DECIDED` | DETERMINISTIC | **observed** from the Phase 9 log, never produced here |
| `PIPELINE_STAGE_FAILED`, `DEAD_LETTER` | DETERMINISTIC | ledger |

Composition is pure (`compose(event) -> Message`) with these rules:

- `AI_ENRICHED` messages are visibly separated from `DETERMINISTIC` ones and use only
  "potential", "candidate", "unreviewed"; they contain no obligation text.
- No message uses "approved", "compliant", "required" or "valid" except `REVIEW_DECIDED`,
  which quotes the recorded Phase 9 status and its record hash.
- A message carries ids, counts, labels and a link to the Phase 10 page. There is no action
  link (nothing approves from a message).
- Data classes. **Allowed:** opaque staff/reviewer identifiers needed for routing and audit;
  task, obligation and event ids; counts; fixed labels. **Forbidden:** source or obligation
  text; names, email addresses or phone numbers (a delivery adapter may map an opaque id to an
  address at send time inside the adapter, and that address is never stored in the ledger,
  an event or an error); credentials, tokens and secret URLs.
- Channel credentials come from the host; they are never in an event, the ledger or an error.

**Outbox.** A notification is recorded `QUEUED` (dedupe key fixed) **before** any send;
then sent with the dedupe key as the channel idempotency key; then `DELIVERED`,
`FAILED_RETRYABLE` or `FAILED_PERMANENT` is recorded. Delivery is **at-least-once**: a
crash after the send but before the record resends with the same key, and the duplicate is
possible only on a channel that cannot dedupe (stated, not hidden). One logical
notification per dedupe key regardless of attempts. **Recipients are resolved from the `Recipients`
port once, when the notification is queued, and the resolved set is recorded in the `QUEUED`
record; every retry sends to that recorded set.** A later routing change does not alter a
queued notification; to reach a different audience, a new notification with a new dedupe
key (and a `REROUTED` reason, linked to the original) is queued. None resolvable at queue
time → `FAILED_PERMANENT(NO_RECIPIENT)`, visible.

Notification outcome never feeds back: not into the obligation, the task, the queue, or the
pipeline stage that produced it.

## 9. Failure semantics

| Situation | Behaviour |
|---|---|
| Slack/notifier unavailable | `FAILED_RETRYABLE`, backoff, then `DEAD_LETTER`; review and pipeline unaffected |
| AI pipeline unavailable | AI stages `FAILED_RETRYABLE`, then `DEAD_LETTER`; `DETECTED` already sent; no obligation faked |
| duplicate event / duplicate tick | same run key / action key: no second run, task, assignment or message |
| retry after partial run | resumes at the first non-`DONE` unit |
| message sent, ledger commit failed | record stays `QUEUED`; retried with the same key |
| ledger commit succeeded, send failed | `QUEUED` retried; nothing else changed |
| crash at any effect boundary | recovery converges to the same projection as an uninterrupted run |
| store unavailable | the operation is refused as a whole; no partial in-memory state |
| directory/recipients unavailable | assignment stays `UNASSIGNED`; notification `FAILED_RETRYABLE` |
| malformed event | `REJECTED_EVENT` recorded with the reason; not retried |
| clock goes backwards | injected time is validated monotonic per stream; a regression is refused and recorded |

## 10. Hard invariants (tested as properties)

1. **No review-state mutation.** The only obligation change Phase 11 causes is Phase 1
   `submit()`, once per idempotency key and only inside the §5 transaction; no Phase 9 log
   record is ever written by it. `PENDING_REVIEW` without a task cannot be observed.
2. **Idempotence.** Replaying any event, submission, tick or delivery result any number of
   times leaves the projection unchanged (no duplicate run, task, assignment, message).
3. **No silent loss.** Every event and obligation is `DONE`, `DEAD_LETTER` or pending with
   a `next_attempt_at`; the unaccounted count is 0.
4. **Replay equality** for every stream, and a tampered ledger fails verification.
5. **Independence.** Deterministic notifications are sent with the pipeline down; review
   outcomes are identical with notifications on, failing or absent.
6. **Assignment is not authority.** Any Phase 9 request has the same outcome with, without,
   or with a different assignment.
7. **Crash safety.** Fault injection at every effect boundary (before/after each store
   commit and each send), then recovery, converges to the same **logical state** as the
   uninterrupted run: the same obligations and statuses, the same Phase 9 tasks, the same
   assignment projection, the same set of logical notifications (by dedupe key) and their
   terminal status, the same submission outcomes, and the same dead-letter set. Only
   additional retry-attempt and `SUBMIT_FAILED` records may differ; the chain of each stream
   must still verify and replay to its stored state.
8. **Determinism.** Same ledger, inputs and clock produce the same actions.
9. **No authority language** outside `REVIEW_DECIDED`. No source or obligation text, credential
   or personal data other than the allowed opaque identifiers (§8) in any message, ledger
   record or error.

## 11. Phase 10 boundary

Phase 11 owns read-only workflow projections (`assignee(task)`, `due_at(task)`,
`overdue(task, now)`, `notification_state(subject)`) and may expose them to future consumers.
**Consuming them in the Phase 10 review UI is out of scope for this phase** and requires an
explicit Phase 10 amendment (with its own contract change and tests); until then the frozen
Phase 10 contract, views and pages are unchanged. When such an amendment is made, assignment
must be labelled a routing hint and must not imply that only the assignee may act.

## 12. Module layout

```
src/regulus/workflow/
├── models.py      Run, Stage, Assignment, Principal, WorkflowRole, results
├── ledger.py      records, chain, replay, projections
├── store.py       WorkflowStore protocol + in-memory reference, atomic commit
├── intake.py      submit_for_review
├── assign.py      directory port, deterministic strategy
├── schedule.py    sla, due, overdue, tick, backoff
└── engine.py      run_event, resume, requeue
src/regulus/notifications/
├── models.py      NotificationEvent, Message, DeliveryResult
├── compose.py     pure composition and wording rules
├── outbox.py      queue, send, record, retry
└── ports.py       Notifier, Recipients
tests/workflow/  tests/notifications/
```

## 13. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| **Submission** | |
| valid `GENERATED` result | one task, `PENDING_REVIEW`, one ledger record, atomic |
| same result submitted twice | `ALREADY_SUBMITTED`, one task |
| same id, different content | `CONFLICT`, existing task untouched |
| obligation already reviewed | `NOT_SUBMITTABLE` |
| evidence not re-verifiable | dead-lettered `EVIDENCE_INVALID`, no task |
| result not `GENERATED` | refused |
| commit fails mid-submit | no obligation, no task; retry succeeds once |
| submit then immediate Phase 9 approve attempt by anyone | judged by Phase 9 only |
| crash after the transition, before the task | not observable (transaction), or completed on retry; never `PENDING_REVIEW` without a task |
| crash after task, before the submission record | completed on retry to the identical result |
| retry of a half-done submission | returns the original success, never `NOT_SUBMITTABLE` |
| submission record without a task | impossible by the transaction; detected and completed if a store reports it |
| intent-and-complete store, crash after the intent | recovery rebuilds the exact obligation, snapshot and task from the intent payload, not from live data or a re-run |
| `SUBMIT_FAILED` cannot be written | submission outcome unchanged; no effects durable |
| **Pipeline** | |
| AI pipeline unavailable | `DETECTED` sent; AI stages retry then `DEAD_LETTER`; no fake obligation |
| duplicate event | same run, no duplicates |
| failure after k of n obligations | resume continues at k+1; no duplicate tasks |
| deterministic stage fails | retry then dead-letter, visible |
| config version changes | new run key; old run untouched |
| **Assignment** | |
| no available reviewer | `UNASSIGNED(NO_REVIEWER_AVAILABLE)`, re-evaluated on tick |
| tie in load | lowest reviewer id |
| reassign while claimed | hint changes, claim untouched, reason required |
| assign non-reviewer / unavailable / closed task | refused |
| editor suggested as approver | allowed hint; Phase 9 still `FOUR_EYES` |
| request outcome with vs without assignment | identical |
| **Scheduling** | |
| task becomes overdue | projection only; no state change; actions still allowed |
| tick twice / tick after crash | each action once |
| retry schedule | deterministic `base*2^n`, capped; exhaustion → `DEAD_LETTER` |
| clock regression | refused and recorded |
| **Notifications** | |
| Slack unavailable | `FAILED_RETRYABLE`, review untouched |
| sent, ledger commit failed | `QUEUED`, resend with the same key |
| ledger committed, send failed | retried; no other change |
| same dedupe key twice | one logical notification |
| no recipient | `FAILED_PERMANENT(NO_RECIPIENT)` |
| routing changes between queue and retry | retry uses the recorded recipient set; new audience = new notification, linked, with reason |
| `TASK_OVERDUE` window | one per task per UTC day; reschedule opens a new window |
| names, addresses, secrets in payload, ledger, error | rejected by compose / absent from stored records |
| AI-enriched message | labelled separately; "potential/unreviewed"; no obligation text |
| authority words in a non-`REVIEW_DECIDED` message | rejected by compose |
| payload scanned | no source/obligation text, token, URL secret, personal data |
| `REVIEW_DECIDED` | quotes the Phase 9 record status and hash; produced only from the log |
| **Ledger and crash** | |
| tamper, delete, reorder | chain fails |
| replay of a long run | equals stored projection |
| crash at every effect boundary (seeded) | converges to the uninterrupted logical state (§10.7); only retry records differ |
| notifications on / failing / absent | identical review outcomes |
| **Real corpus** | |
| real events → real obligations → submit → assign → notify (fake channel) | one task each, accounted = 100%, then a Phase 9/10 review reaches `PUBLISHED` with replay equality; the claim stays "Phase 11 orchestration exercised on the real corpus through submission, routing and notification", not production readiness |

## 14. Evaluation

Behavioural: the §10 invariants as seeded properties over event, tick, failure and crash
sequences, plus the master-plan gate scenarios: Slack unavailable, AI pipeline unavailable,
duplicate event, retry, partial completion, notification sent but database update failed,
database update succeeded but Slack failed. No latency or delivery-rate claims; those are
Phase 13/14.

## 15. Security and data protection

- Notification content is minimised (§8). Recipient identifiers are staff ids supplied by
  the host. Staff identifiers are personal data under UU PDP: the lawful basis and retention
  of the notification and ledger records need confirmation with the internal legal/compliance
  team; the article numbers are not asserted here.
- Secrets (channel tokens, webhook URLs) are host-injected and never persisted or logged.
- Relevant ISO 27001:2022 Annex A controls (logging and monitoring, protection of
  information in transit, handling of credentials) are mapped by the GRC team; exact control
  numbers are to be confirmed with them, not asserted here.

## 16. Decisions to confirm

1. Phase 11 owns **no** lifecycle: only `submit()` via `submit_for_review`, and only for verified results.
2. Assignment is a hint; claim and authority stay Phase 9.
3. `overdue` is a projection, never a state.
4. At-least-once delivery with an outbox, dedupe keys and a recipient set fixed at queue time; duplicates only on channels that cannot dedupe, and stated.
5. Dead-letter is a visible state with manual requeue, never a drop.
6. `REVIEW_DECIDED` is observed from Phase 9, never generated here.
7. Roles local to Phase 11 (`COORDINATOR`, `OPERATOR`, system principal); Phase 9 roles unchanged. A Phase 11 role never grants or implies a Phase 9 role (`OPERATOR` is not `REVIEWER`, `COORDINATOR` is not `PUBLISHER`), even when one person holds both in a host application.
8. SLA values and backoff are configuration with documented defaults.
9. Submission is one store transaction (or an equivalent intent-and-complete protocol); a retry completes, never reports `NOT_SUBMITTABLE` for its own half-done submission.
10. Phase 10 consumption of workflow projections is deferred to a future Phase 10 amendment.
