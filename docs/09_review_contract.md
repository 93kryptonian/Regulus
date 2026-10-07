# Regulus — Human Review Contract

**Phase:** 9 · **Status:** FROZEN (amendments A1–A2 pending re-freeze)

```
Phase 7  Obligation (GENERATED) + evidence + open_questions
Phase 8  SimilarityResult (possible relationships, with field evidence)
Phase 9  How does a human turn that candidate into a controlled, auditable decision?
Phase 10 The UI that presents it
```

> The UI is never the source of truth. It *presents* the obligation, its exact source
> evidence, the Phase 7 open questions, the Phase 8 matches and the lineage context.
> The **structured review record is the authoritative decision artifact**, and the
> Phase 1 transition engine (`apply_decision`) remains the **lifecycle authority**.

```
source → extraction → generation → similarity evidence → human decision → immutable audit trail
```

## 1. Purpose and boundary

Phase 9 defines the review *workflow contract*: tasks, snapshots, roles, actions, the
audit envelope, concurrency, and the rules that stop an obligation from being
approved while something that needs a human has been ignored.

| Does | Does not |
|---|---|
| create review tasks with an immutable snapshot of what the reviewer sees | render anything (Phase 10) |
| authorize actions by role, with four-eyes | authenticate users (an `Actor` is injected) |
| turn actions into Phase 1 `ReviewDecision`s through `apply_decision` | change Phase 1's transition table or `ReviewDecision` |
| wrap each decision in an append-only, hash-chained `ReviewRecord` | persist to a database (a store protocol, Phase 16) |
| detect stale reviews and changed sources | schedule, notify, or orchestrate (Phase 11) |
| require explicit handling of open questions and duplicate/contradiction suggestions | decide duplicates or merge obligations |

Phase 1 is reused unchanged: states, the closed transition table, `submit()`,
`apply_decision()`, `FieldChange`, the evidence gate.

## 2. Actors, roles, authorization

`Actor(id, roles)`, injected by the caller; Phase 9 never reads credentials.

| Role | May |
|---|---|
| `REVIEWER` | claim tasks, `APPROVE`, `EDIT`, `REJECT` |
| `PUBLISHER` | `PUBLISH` an approved obligation |
| `AUDITOR` | read tasks and the log; no action |

`authorize(actor, action, obligation, log) -> Allow | Deny(reason)` is pure.
Rules beyond the role table:

- **Four-eyes.** The actor who last edited an obligation (from the log) cannot approve it; the actor who approved it cannot publish it. Both are configurable per deployment but default **on**.
- A `Deny` is **not** a decision: it writes nothing to the log and changes no state (§9).
- Identity in a record is the injected `Actor.id`; a record can never name a different reviewer than the actor who acted.

## 3. Review task and snapshot

`ReviewTask`: `id`, `obligation_id`, `base_version`, `status` (`OPEN`, `CLAIMED`, `DONE`, `SUPERSEDED`), `claimed_by`, `claim_expires_at`, `snapshot`, `priority_key`, `created_at`.

`ReviewSnapshot` (immutable, hashed at creation, **what the reviewer saw**):

| Part | Source |
|---|---|
| obligation (`generated`, `current`, `status`) | Phase 1 / 7 |
| evidence (owner, span, quote) with verified quotes | Phase 7 |
| `TransformationTrace` summary and `open_questions` | Phase 7 |
| `source_complete` flag | Phase 7 `GenerationRecord` |
| `SimilarityResult` (id, provider, matches, labels, field comparisons, lineage context) | Phase 8 |
| pending `ObligationImpact` for the obligation's article | Phase 6 |
| `snapshot_hash` | sha256 of the above |

The task is created when an obligation is submitted (`GENERATED → PENDING_REVIEW` via
`submit()`, a Phase 11 step). A task is created only for a `PENDING_REVIEW`
obligation; the snapshot is rebuilt when the obligation changes (§6), never edited.

**`base_version`** is the concurrency token: sha256 of `(obligation id, status, current
content, number of log records for it)`.

## 4. Actions

| Action | Phase 1 effect | Requires |
|---|---|---|
| `APPROVE` | `PENDING_REVIEW → APPROVED` | verified evidence (Phase 1 gate); §5 acknowledgements; four-eyes |
| `REJECT` | `PENDING_REVIEW → REJECTED` | a closed reason code (§4.1) and, for `OTHER`, text |
| `EDIT` | `PENDING_REVIEW → EDITED` **then** `EDITED → PENDING_REVIEW` | structured `FieldChange`s, a reason; produces **two** decisions recorded atomically; the edited obligation needs a **second** reviewer (four-eyes) |
| `PUBLISH` | `APPROVED → PUBLISHED` | role `PUBLISHER`, four-eyes |

No action may produce any other transition. `REJECTED` and `PUBLISHED` are terminal
(Phase 1); recovery is a new obligation referencing the old, never a state reversal.

### 4.1 Reject reasons (closed)

`DUPLICATE_OF(match_id)`, `NOT_AN_OBLIGATION`, `INCORRECT_EXTRACTION`, `OUT_OF_SCOPE`,
`SOURCE_UNCLEAR`, `OTHER` (free text required). `DUPLICATE_OF` must name a match from the
snapshot's `SimilarityResult`. Rejecting as a duplicate links the two obligations;
nothing is merged or deleted.

### 4.2 Edit semantics (human authority, visible divergence)

- `FieldChange(field, before, after)` over `ObligationContent` fields; `before` must equal the current value (Phase 1 stale-edit protection).
- `generated` is never touched; `current` is replaced only through the log.
- `text` must stay non-empty; `source_owner_id` and `article_id` are not editable.
- A human may write words the source does not contain; this is allowed (the human is the authority) but **recorded**: the record carries `divergence`, the tokens of the edited `text` absent from the permitted source (Phase 7 `permitted_source_text`), shown to later reviewers and auditors. Phase 7's generator verifier does not apply to human edits.

## 5. What a reviewer must handle before `APPROVE`

Approval is **refused** unless the `ReviewRecord` carries:

1. **Open questions.** For every Phase 7 `open_question` in the snapshot an `OpenQuestionResolution(question, resolution)` with `RESOLVED_BY_EDIT` (an earlier edit set the field), `ACCEPTED_AS_IS` (explicit acknowledgement) or `NOT_APPLICABLE` plus a short note. None are silently dropped.
2. **Similarity.** For every match in the snapshot labelled `POSSIBLE_DUPLICATE` or `CONTRADICTORY_MODALITY`, a `MatchDisposition(match_id, disposition)`: `NOT_A_DUPLICATE`, `CONFIRMED_RELATED`, `CONFIRMED_VARIANT`, `CONTRADICTION_NOTED`. A match the reviewer judges a duplicate leads to `REJECT(DUPLICATE_OF)`, not to approval. Other matches may be `NOT_REVIEWED`.
3. **Source status.** If `source_complete = false` or a pending `ObligationImpact` marks the source changed, an explicit `ACKNOWLEDGED` flag; otherwise approval is blocked.
4. The evidence gate of Phase 1, with the quotes re-verified against the owner texts supplied by the caller (Phase 9 does the filtering that Phase 1 invariant 9 leaves to the caller).

**Historical completeness.** These obligations are evaluated over the **whole review task history**, not only the latest snapshot. An open question present in *any* snapshot of the task (including superseded ones) stays outstanding until it is (a) resolved by an edit recorded in the history whose `FieldChange` sets the field the question names (`actor:…` names `actor`, `action:enumerated_items` names `action`, `condition:…` names `condition`; the new value must be non-empty), or (b) explicitly resolved or acknowledged in a `ReviewRecord`. Rebuilding a snapshot **carries forward** outstanding questions with their origin snapshot hash and never erases one; a rebuilt snapshot with zero open questions does not make an earlier question disappear. Match dispositions carry forward while the match id and its label are unchanged; source-flag acknowledgements carry forward, but a **new** flag needs a new acknowledgement.

These are checks on the record, not on the UI: an API client cannot bypass them.

## 6. Concurrency and stale reviews

- Every action carries `task_id` and `base_version`. If `base_version` differs from the obligation's current version the action is `STALE` (§9): not applied, nothing recorded as a decision, the task's snapshot is rebuilt and the reviewer must decide again.
- **Claims.** `claim(task, actor, now, ttl)` gives one actor an exclusive claim; a second claim while valid is refused; an expired claim is released. Actions require a valid claim; there is no override role.
- Concurrent edit by two reviewers: the first applied edit bumps the version, the second is `STALE`; the second's `before` values also fail Phase 1's stale-edit check.
- **Source changed.** If Phase 6 reports an `ObligationImpact` `MODIFIED` or `TERM_REPLACED` for the obligation's article while a task is open, the task gets a `SOURCE_CHANGED` flag; approval is blocked until acknowledged (§5.3).
- **Source withdrawn.** For `WITHDRAWN` the task gets `SOURCE_WITHDRAWN`. **A withdrawn source is never approvable, and never publishable, through acknowledgement.** Acknowledgement only records awareness. The reviewer's available action is `REJECT` (typically `OUT_OF_SCOPE`); an already `APPROVED` obligation whose source is withdrawn stays `APPROVED` and unpublishable, flagged, until a recovery path is defined by the governance phase (Phase 15). Phase 1's `REJECTED` stays terminal.

## 7. The audit record

`ReviewRecord` wraps (never replaces) a Phase 1 `ReviewDecision`:

`id`, `decision` (Phase 1), `task_id`, `base_version`, `snapshot_hash`, `actor` (id and roles at the time), `open_question_resolutions`, `match_dispositions`, `acknowledged_flags`, `divergence`, `reject_reason`, `prev_hash`, `hash`.

- **Append-only, hash-chained.** `hash = sha256(prev_hash | canonical record)`; the log verifies by recomputing the chain. Any edit, deletion or reordering breaks it.
- **State is derived from the log.** `replay(initial_obligation, records) → obligation` must reproduce the current obligation exactly. There is no state change without a record and no record without a state change.
- **Atomic commit boundary (a store guarantee).** The state transition and its audit-record append are **one atomic commit**: `ReviewStore.commit(obligation_after, records, expected_version)` makes both durable or neither. The store verifies `replay(initial, durable_log + records) == obligation_after` and `expected_version` *before* making anything durable. `NOT_RECORDED` guarantees that replay of the durable log still equals the durable obligation state.
- Records are never updated or deleted; a correction is a new decision.
- `at` comes from an injected clock; `id` is derived from content, not time.

## 8. Queue ordering

`priority_key` is deterministic (descending urgency): any `CONTRADICTORY_MODALITY` match, then `POSSIBLE_DUPLICATE`, then `source_complete = false` or `SOURCE_CHANGED`, then more open questions, then age, then id. It orders work; it never skips a check in §5.

## 9. Failure semantics

| Situation | Result |
|---|---|
| unauthorized actor / four-eyes breach | `DENIED(reason)`: no record, no state change |
| invalid transition | rejected by Phase 1, `INVALID_TRANSITION`: no record |
| stale `base_version` | `STALE`: no record; snapshot rebuilt |
| missing acknowledgements (§5) | `INCOMPLETE_REVIEW(list)`: no record |
| evidence not verifiable | `EVIDENCE_INVALID`: no record |
| `EDIT` fails after its first decision | all-or-nothing: neither decision is recorded |
| store failure | the atomic commit fails as a whole; the caller sees `NOT_RECORDED`; durable state and durable log unchanged and still replay-equal |

A failed action never leaves an obligation in a half-applied state. `NOT_PROCESSED`,
`DENIED` and `APPLIED` are distinct results.

## 10. Hard invariants (tested as properties)

1. Replay of the log equals the current obligation, for every obligation.
2. No obligation reaches `APPROVED` without verified evidence, handled open questions, and dispositions for every `POSSIBLE_DUPLICATE` / `CONTRADICTORY_MODALITY` match.
3. Four-eyes: no actor approves an obligation they last edited, nor publishes one they approved.
4. A stale action is never applied.
5. The log's hash chain detects any modification.
6. `generated` content never changes.
7. A `DENIED` / `STALE` / `INCOMPLETE_REVIEW` result leaves state and log untouched.

## 11. Module layout

```
src/regulus/review/
├── models.py     Actor, Role, ReviewTask, ReviewSnapshot, ReviewRecord, results
├── snapshot.py   build the snapshot and snapshot_hash from Phase 6/7/8 outputs
├── authorize.py  roles and four-eyes (pure)
├── engine.py     apply(action) → Phase 1 apply_decision + record
├── log.py        append, verify chain, replay
├── queue.py      priority_key
└── store.py      ReviewStore protocol (in-memory reference)
tests/review/
```

## 12. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| approve with all gates satisfied | `APPROVED`, one record, chain valid |
| approve without evidence / forged quote | `EVIDENCE_INVALID` |
| approve with an unhandled open question | `INCOMPLETE_REVIEW` |
| approve with a `POSSIBLE_DUPLICATE` match and no disposition | `INCOMPLETE_REVIEW` |
| approve with a `CONTRADICTORY_MODALITY` match and no disposition | `INCOMPLETE_REVIEW` |
| `NOT_REVIEWED` on a `RELATED` match | allowed |
| `source_complete = false` without acknowledgement | `INCOMPLETE_REVIEW` |
| `SOURCE_CHANGED` task approved without acknowledgement | `INCOMPLETE_REVIEW` |
| reject with each closed reason; `OTHER` without text | accepted / `INCOMPLETE_REVIEW` |
| `DUPLICATE_OF` naming a match not in the snapshot | `INCOMPLETE_REVIEW` |
| edit then resubmit | two decisions, one atomic append; version bumped |
| editor tries to approve own edit | `DENIED(FOUR_EYES)` |
| approver tries to publish | `DENIED(FOUR_EYES)` |
| edit with `before` not matching | stale-edit error, nothing recorded |
| edit that empties `text` | rejected |
| edit adding new words | applied; `divergence` recorded |
| two reviewers act on the same version | first applied, second `STALE` |
| action without a valid claim / second claim while valid / expired claim | refused / refused / released |
| approve twice / approve after reject / publish before approve | Phase 1 `INVALID_TRANSITION` |
| `AUDITOR` attempts an action | `DENIED(ROLE)` |
| record claims a different reviewer than the actor | rejected |
| tamper with a record / delete / reorder | chain verification fails |
| replay of a long history | equals the current obligation |
| failure between the two decisions of an edit | neither recorded |
| store failure on append | `NOT_RECORDED`, state unchanged |
| same inputs twice | byte-identical records (injected clock) |
| source `WITHDRAWN` while task open | approval blocked even with acknowledgement; publish blocked; `REJECT` allowed |
| edit removes an open question, snapshot rebuilt with none | the original question stays outstanding unless resolved by a recorded edit of the named field or explicitly resolved |
| edit sets the field a question names | `RESOLVED_BY_EDIT` derived from the history |
| store commit fails after transition computed | `NOT_RECORDED`, replay of durable log equals durable state |
| queue ordering with ties | deterministic, stable |
| Phase 1/6/7/8 compatibility | consumes real `Obligation`, `GenerationResult`, `SimilarityResult`, `ObligationImpact` |

## 13. Evaluation

Behavioural, not statistical: the §10 invariants run as property tests over generated
action sequences (random but seeded: approvals, edits, stale attempts, tamper attempts).
Review-time metrics (reviewer time per obligation, edit and rejection rates) belong to
Phase 12; Phase 9 only guarantees the records those metrics will be computed from.

## 14. Gate

Contract frozen after adversarial review → implementation module by module (log and
replay first, since every other guarantee depends on them) → every §12 case → the §10
property tests → ruff and strict mypy clean → a full run over the real-corpus
obligations (submit, review, publish) with replay equality → freeze.

## 15. Decisions

1. **Wrapper, not a Phase 1 change:** `ReviewRecord` envelopes the unchanged `ReviewDecision` (§7).
2. **Snapshot of what the reviewer saw**, hashed and immutable (§3).
3. **Acknowledgement gates for approval:** open questions, duplicate/contradiction dispositions, source status (§5).
4. **`EDIT` = two atomic decisions and needs a second reviewer** (four-eyes) (§4).
5. **Human edits are allowed to diverge from the source, but divergence is recorded** (§4.2).
6. **Append-only hash-chained log; state derivable by replay** as the central invariant (§7, §10).
7. **Optimistic concurrency by `base_version`** plus exclusive claims (§6).
8. **Closed reject reasons**, `DUPLICATE_OF` linking without merging (§4.1).
9. **Roles:** `REVIEWER`, `PUBLISHER`, `AUDITOR`; authentication is out of scope (§2).
10. **Review amendments:** open-question completeness is historical across the task (§5); the state transition and audit append are one atomic store commit (§7); a withdrawn source is never approvable or publishable through acknowledgement (§6).

## 16. Amendments (for Phase 10; no change to any frozen behaviour)

**A1 — `preflight`.** A pure `preflight(task, obligation, log, actor, cfg, now, owner_texts)`
returns, without committing or recording anything:

- `actions`: for each `Action`, `available` or `unavailable(reasons)`, with every failing
  reason (not only the first) in the engine's own codes;
- `gates`: the full checklist for approval, each `Gate(id, ok, detail)`: evidence verified,
  source complete, each open question, each dangerous match, each source flag, four-eyes,
  claim held.

`apply` is refactored to call the same gate evaluation, so the verdicts cannot diverge.
Tests also assert non-mutation: obligation, log, task, claim state and store version are identical before and after `preflight`.
Invariant: for the checks both cover, `preflight` available ⇔ `apply` not refused with
`DENIED`/`INCOMPLETE_REVIEW`/`EVIDENCE_INVALID`/`INVALID_TRANSITION`; `preflight` never
mutates the store or the task. `apply` outcomes and every §12 row are unchanged.

**A2 — snapshot carries the Phase 6 candidate.** `ReviewSnapshot` gains an optional
`candidate: ObligationCandidate | None` (covered by `snapshot_hash`; `None` for
obligations without one, e.g. hand-created) so a reviewer can be shown, per field, the
recorded state (`PRESENT` / `NOT_STATED` / `UNDETERMINED` + reason) and its citation.
It is display data: no gate reads it.

Both amendments are re-verified by the existing Phase 9 suite (unchanged, green), new
tests for the `preflight`/`apply` equivalence over the seeded sequences, and one
snapshot-hash test; Phase 9 is re-frozen before Phase 10 implementation starts.
