# Regulus — Governance Contract

**Phase:** 15 · **Status:** FROZEN

```
Phase 9   decisions are audited (the review log)
Phase 11  workflow facts are audited (the ledger)
Phase 13  behaviour is observable (events and metrics)
Phase 14  failure leaves safe state
Phase 15  what data does Regulus hold, who can reach it, how are access and change
          audited, how long is it kept, and what can the system honestly demonstrate?
```

> Phase 15 states controls and proves they behave as stated. It is not a compliance claim.
> Regulus does not claim to be compliant with UU PDP, ISO 27001, GDPR, OJK rules or any other
> regime; it demonstrates specific controls under specific tests, and leaves the legal and
> compliance judgement to the people who own it.

**Scope statement.** Phase 15 validates governance controls (classification, access, audit,
retention, sensitive-data handling, integrity) against the reference stores and fake
infrastructure under controlled tests. Authentication, transport security, encryption at rest,
backup and restore, and the organisational process around incidents belong to the host and to
the deployment phase.

## 1. Boundary

| Does | Does not |
|---|---|
| inventory and classify every kind of record Regulus stores | decide the lawful basis, retention period or legal hold in any jurisdiction |
| define who may do which read and write operation, and enforce it at the review UI boundary | authenticate (the host supplies identity) |
| audit access and operator actions in a tamper-evident log | collect content or personal data in that log |
| apply retention by purging whole expired streams with a receipt | rewrite or edit records inside a retained hash chain |
| separate identity from records so identity can be erased without touching the chain | encrypt data, manage keys or secure transport |
| verify every chained log in one pass | claim compliance, certification or regulatory approval |

## 2. Data inventory and classification

A committed `governance/data_inventory.v1.json` lists every stored record type. Each entry has:
`record` (the model), `store`, `holds` (field groups), `class`, `personal_data` (`NONE` or
`OPAQUE_ID`), `mutable`, `retention_class`, `deletion` (`WHOLE_STREAM`, `NONE`, `EPHEMERAL`) and
`readers` (operations from §3).

| Class | Meaning | Examples |
|---|---|---|
| `PUBLIC` | derived from public regulation text or synthetic | source documents, articles, provenance, evaluation gold and reports |
| `INTERNAL` | work product, not personal | candidates, generated obligations, evidence, snapshots, workflow items |
| `RESTRICTED` | contains opaque personal identifiers or reviewer free text | review records, review tasks (claim holder), workflow ledger principals, notifications and recipients, access audit |
| `OPERATIONAL` | ids, counts, closed enums, durations | observability events, metrics, usage records |
| `SECRET` | credentials and tokens | never stored by Regulus; host-injected |

- **Opaque identifiers** (reviewer, publisher, operator and recipient ids) are treated as
  personal data of staff, not as anonymous: they are `RESTRICTED`, and their legal status is
  for legal and compliance to confirm.
- **Free text.** Reviewer reasons, question-resolution notes and reject text can hold anything a
  person types. They are `RESTRICTED` and bounded and checked at the boundary (§6).
- **No client or consultation data.** Regulus processes public regulations and synthetic data.
  It has no field for client data, case data or consultation content; if one is ever added the
  inventory test fails until it is classified.

**Inventory completeness is machine-checked.** A test enumerates every stored model's fields by
introspection and fails on a model or field the inventory does not classify, and on an
inventory entry that names a field that does not exist.

## 3. Access model

Authorization has two layers, and both must allow.

1. **Coarse policy: role × operation**, in a committed `governance/access_matrix.v1.json`.
2. **Resource policy: actor × operation × resource**, for the operations that name a resource.
   The deciding function is `authorize(actor, roles, operation, resource_facts)`; the facts are
   data about the resource (status, participants), never about assignment (see below).

| Operation | Roles (coarse) |
|---|---|
| `READ_QUEUE`, `READ_TASK`, `READ_HISTORY` | REVIEWER, PUBLISHER, AUDITOR (then the resource rules below) |
| `READ_ACCESS_AUDIT` | AUDITOR |
| `READ_EVALUATION` | any identified role |
| `CLAIM`, `EDIT`, `APPROVE`, `REJECT` | REVIEWER (Phase 9 rules and four-eyes still apply) |
| `PUBLISH` | PUBLISHER (and not the approver) |
| `ASSIGN`, `RESCHEDULE` | COORDINATOR |
| `REQUEUE`, `PURGE`, `HOLD`, `RELEASE_HOLD`, `BASELINE_UPDATE`, `ERASE_IDENTITY` | OPERATOR |
| `SUBMIT`, `RUN_PIPELINE`, `TICK` | SYSTEM or OPERATOR |

**Resource facts** for a task: obligation status, whether it is terminal (`PUBLISHED` or
`REJECTED`), and `participants` (every actor id that appears in its review log, derived from the
log, never from a request).

**Resource rules (need to know).** A task page, its history and its queue entry are readable when:

| Rule | Who | Which tasks |
|---|---|---|
| R1 | AUDITOR | any task and its history (read-only) |
| R2 | REVIEWER | every non-terminal task, and terminal tasks the actor participated in |
| R3 | PUBLISHER | tasks awaiting publication (`APPROVED`), and terminal tasks the actor participated in |
| R4 | any other role, or no role | none |

- `READ_QUEUE` returns only the entries the actor may read under R1 to R3.
- A write operation on a task also requires that the actor may read that task: nobody acts on
  a task they cannot see.
- **Assignment is deliberately not part of the read scope.** Phase 11 guarantees that an
  assignment is a routing hint and that every Phase 9 request has the same outcome with, without
  or with a different assignment; a governance rule keyed on assignment would break that at the
  governed boundary. Read scope is data classification and participation, not routing.
- Terminal decision history, which carries reviewer ids, is therefore not browsable by reviewers
  who did not take part; this is the need-to-know boundary Phase 15 adds.
- An identified actor with **no role** has no read access: the pages answer 403 and the denial
  is audited. Mounting under `GovernedApp` is how a deployment turns the policy on, so no frozen
  Phase 10 behaviour is edited.
- **Least privilege and separation** are tested as properties:
  - `AUDITOR` holds no write operation;
  - `OPERATOR`, `COORDINATOR` and `SYSTEM` hold no review operation: a Phase 11 role never
    implies a Phase 9 role, even when one person holds both in a host application;
  - the Phase 9 four-eyes rules are unchanged;
  - an operation absent from the matrix, and a resource the rules do not name, is denied, never
    allowed by default.
- The matrix and the resource rules are the single source: `GovernedApp`, the workflow operator
  functions and the review authorizer are each checked against them by a conformance test over
  every role, operation and resource-fact combination.

## 4. Audit

Existing audit sources stay as they are, and Phase 15 names them precisely (this contract never
says just "the audit log"): the review log (decisions),
the workflow ledger (submissions, assignments, requeues, purges' receipts reference), and the
Phase 13 events. Phase 15 adds one thing they lack: **who looked at what, and who was refused.**

`AccessAudit` is an append-only, hash-chained log (the same scheme as the review log) of:

`ACCESS_ALLOWED`, `ACCESS_DENIED`, `OPERATOR_ACTION`, `INTEGRITY_REFUSAL`, `POLICY_CHANGE`,
`PURGE`, `HOLD`, `RELEASE_HOLD`, `IDENTITY_ERASED`.

Each record carries: id, kind, operation (closed enum), resource type and id (opaque), opaque
actor id and roles, outcome, injected time, `prev_hash`, `hash`. **No content**: no obligation
text, source text, reasons, notes or request bodies, and no name or address.

- Every request through `GovernedApp` to a review page produces exactly one **audit attempt**. If
  the append succeeds there is exactly one corresponding `AccessAudit` record, allowed or denied.
  If the append fails there is no record, and the failure is an **audit gap**.
- **Fail closed.** If the access record cannot be appended, a request for a `RESTRICTED`
  resource is denied (503, nothing rendered) rather than served unaudited. Public resources
  (the evaluation report) may be served and the gap is counted.
- **Accounting.** An independent counter, separate from the `AccessAudit` store and also emitted
  as a Phase 13 point event, holds `audit_attempted`, `audit_recorded` and `audit_gap`, with
  `attempted = recorded + gap`. A gap is never claimed as a record, and it is surfaced even when
  the audit store is the thing that failed.
- Operator actions (requeue, purge, hold, baseline update) record who and why; the reason is
  bounded free text under §6.
- Audit records are `RESTRICTED`, retained longer than the records they describe (§5), and
  readable only under `READ_ACCESS_AUDIT`.

## 5. Retention and deletion

Retention is configuration, not law: `governance/retention_policy.v1.json` states, per
retention class, a number of days or "retain", and ships **illustrative** values marked as such.
The repository asserts no legal retention period; the owners set them.

| Retention class | Applies to | Deletion |
|---|---|---|
| `REVIEW_RECORD` | review logs, tasks, snapshots of a closed obligation | whole stream, after the period, only if the obligation is terminal and not on hold |
| `WORKFLOW` | submission, run, assignment and notification streams | whole stream |
| `ACCESS_AUDIT` | the access audit log | whole segment after its (longer) period, with a receipt |
| `OPERATIONAL` | observability events and usage records | dropped by age; metrics are aggregate |
| `EVALUATION` | gold sets, reports, baseline | retained (public or synthetic) |

**Why whole streams.** A hash chain cannot have a record edited or removed without breaking
verification. Regulus therefore does not offer partial erasure inside a retained chain; it
purges **entire expired streams** and keeps a receipt. This is a design trade-off stated
openly: where law or policy requires erasing one record inside a retained chain, that needs an
owner decision (for example, shorter retention, or a redaction scheme with its own authority)
and is out of scope here.

**Purge** is policy-enforced deletion of **complete streams**, not general-purpose record-level
erasure: it cannot remove one person's single record. `purge(stream, principal, reason, now)` is
operator-only. It refuses a stream that is not expired, belongs to a non-terminal obligation, or is
under a **legal hold**, and it runs as a recorded protocol in the chained `PurgeLog`:

```
PURGE_INTENT   (stream id, retention class, record count, final chain tip hash, reason, actor, time; no content)
      ↓
check eligibility and hold again, then delete the whole stream (atomic in the reference store)
      ↓
PURGE_APPLIED  (references the intent; the stream is absent)
          or
PURGE_CANCELLED (references the intent; the stream is present and the reason is recorded)
```

Receipts are never edited. The states can never contradict the store:

- `PURGE_APPLIED` implies the stream is absent; `PURGE_CANCELLED` implies it is present.
- An `INTENT` with neither is an **interrupted purge**. `recover_purges()` resolves it: stream
  absent, append `PURGE_APPLIED` (marked recovered); stream present and still eligible and not
  held, complete the deletion and append `PURGE_APPLIED`; otherwise append `PURGE_CANCELLED`.
  Recovery is re-runnable.
- A hold placed between the intent and the delete is honoured by the second check; the purge
  then ends `PURGE_CANCELLED`.
- A purge with no intent, or a deletion with no intent, cannot occur; an intent that is lost
  with its stream already deleted is detectable because the purge log chain and the tip hash it
  recorded for other intents still verify, and the missing stream is reported as `UNRECEIPTED`
  by `verify_all`.

**Legal hold.** An operator can place and release a hold with a reason; a held stream is never
purged. Holds are audited.

**Identity erasure.** Opaque ids are linked to people only in an `IdentityMap` held outside every
ledger and log. `erase_identity(opaque_id)` deletes the `opaque_id → person` mapping that Regulus
holds and audits the erasure. Historical opaque identifiers **remain** in the chained records and
are not claimed to be anonymous or globally unlinkable; what is claimed is that nothing Regulus
can resolve maps the id to a person. Free text that a person typed into a reason is not reached
by it (§6).

## 6. Sensitive-data handling

- **Boundary policy.** `GovernedApp` applies a `FreeTextPolicy` to the free-text request fields
  (`reason`, question notes, `reject_text`): maximum length, and rejection of email addresses,
  phone numbers, URLs and credential patterns. A rejection is a 400 naming the field, never the
  value, and is audited as `ACCESS_DENIED` with the reason class.
- **Store scan.** A governance scan runs the Phase 13 pattern scan over every stored record's
  free-text fields; findings are reported by record type and count, never by value.
- **No secrets.** `SECRET` is not a stored class: the control is rejection at the boundary and
  detection by scan, so that nothing is persisted. Nothing in the stores, logs, reports or errors
  may match the credential patterns; a test seeds one and expects detection.
- A rejected value is **never** echoed: not in an exception message, an audit or purge record, a
  log, a metric or the HTTP response.
- Regulus makes no claim that free text is free of personal data: the policy reduces it and the
  scan measures it.

## 7. Integrity

`verify_all(stores)` walks every chained log (workflow streams, review logs, the access audit,
the purge log) and returns a report of intact, broken and unverifiable-by-design streams. A
failure is surfaced as `INTEGRITY_REFUSAL` and never repaired (Phase 14). The hash chains give
tamper evidence; they are not encryption, not signatures by a trusted key, and not proof of
authorship.

## 8. Governance failure semantics

| Situation | Behaviour |
|---|---|
| role lookup or policy file unavailable or malformed | deny, audited if possible |
| operation not in the matrix | deny |
| audit append fails for a restricted resource | deny (503), nothing served |
| audit append fails for a public resource | serve, count `audit_gap` |
| retention policy missing a class | nothing of that class is purged |
| purge fails midway | the stream stays intact; receipt `NOT_APPLIED` |
| purge requested on a held, non-terminal or unexpired stream | refused, audited |
| identity map unavailable | erasure refused and audited; reads unaffected |
| access audit chain broken | writes refused; reads of restricted resources denied until an operator investigates (never auto-repaired) |

## 9. Hard invariants (tested as properties)

1. **Inventory completeness.** Every stored model and field is classified; no stale entry.
2. **Access conformance.** For every role, operation and resource-fact combination, `GovernedApp`,
   the workflow operator functions and the review authorizer agree with the matrix and the
   resource rules; an unlisted operation or resource is denied; read scope never depends on
   assignment.
3. **Separation.** The §3 separation properties hold over the matrix.
4. **Audit accounting.** Every request to a review page makes exactly one audit attempt;
   `attempted = recorded + gap`; each recorded attempt has exactly one `AccessAudit` record
   (none lost, none duplicated); a gap never appears as a record; the `AccessAudit` chain verifies.
5. **Fail closed.** With the audit sink failing, no restricted resource is served.
6. **No content in audit.** A scan of the access audit and the purge log finds no source or
   obligation text, free text, name, address or credential.
7. **Retention safety.** No unexpired, non-terminal or held stream is purged; every deletion is
   preceded by its `PURGE_INTENT`; `PURGE_APPLIED` implies the stream is absent and
   `PURGE_CANCELLED` implies it is present; after a crash at any step, recovery leaves no
   contradictory evidence; a failed purge changes nothing.
8. **Erasure of the link.** After `erase_identity`, nothing Regulus can resolve maps the id to a
   person; the opaque id still appears in historical chains (it is not claimed to disappear); the
   chains still verify.
9. **Integrity coverage.** `verify_all` detects each corruption class of Phase 14 in every
   chained log, including the new ones.
10. **Free-text policy.** Each forbidden pattern and over-length value is rejected at the
    boundary and none is stored.

## 10. Evidence and the Phase 12 layer

A `governance` layer joins the report. Evidence is `PROPERTY` or `REGRESSION`; there is no
corpus row and no compliance row.

| Metric | Numerator / denominator | Gate |
|---|---|---|
| unclassified fields | stored fields without a classification / stored fields | **HARD: 0** |
| stale inventory entries | entries naming a missing model or field / entries | **HARD: 0** |
| access mismatches | role, operation and resource-fact combinations where an enforcing component disagrees with the matrix or resource rules / combinations checked | **HARD: 0** |
| assignment-dependent reads | read decisions that change with the assignment alone / read decisions compared | **HARD: 0** |
| unlisted operations allowed | allowed unlisted operations / unlisted operations tried | **HARD: 0** |
| separation violations | violated separation properties / properties | **HARD: 0** |
| audit accounting violations | requests where `attempted ≠ recorded + gap`, or a record is missing or duplicated for a recorded attempt, or a gap appears as a record / requests | **HARD: 0** |
| restricted resources served with audit failing | served / requests with the audit sink failing | **HARD: 0** |
| content in audit artifacts | artifacts with forbidden content / artifacts scanned | **HARD: 0** |
| unsafe purges | purges of unexpired, non-terminal or held streams / purge attempts of those kinds | **HARD: 0** |
| purges without a prior intent | deletions with no `PURGE_INTENT` / deletions | **HARD: 0** |
| contradictory purge evidence after a crash | crash points (before intent, after intent, after delete, after applied) where the log and the store disagree after recovery / crash points tried | **HARD: 0** |
| identity links surviving erasure | resolvable links after erasure / erasures | **HARD: 0** |
| undetected corruption in chained logs | corruptions not found by `verify_all` / injected, per log type | **HARD: 0** |
| forbidden free text stored | rejected-class inputs found stored / rejected-class inputs submitted | **HARD: 0** |
| free-text findings in stored records | scan findings / records scanned | REPORT_ONLY, counted |
| `audit_gap` counts for public resources | gaps / public requests with the sink failing | REPORT_ONLY |

## 11. Claim discipline

- Allowed: "under these tests, these roles could do these operations", "these records are
  chained and verifiable", "this stream was purged under policy X with receipt Y".
- Not allowed: "compliant", "certified", "GDPR/UU PDP/ISO 27001 ready", "secure", "encrypted",
  "anonymised" (opaque ids are not anonymous), or any statement that a retention value is legal.
- `governance/controls_map.v1.json` lists each Regulus control with the ISO 27001:2022 Annex A
  areas it may inform (candidates: A.5.15 access control, A.5.18 access rights, A.5.33
  protection of records, A.5.34 privacy and protection of PII, A.8.2 privileged access rights,
  A.8.3 information access restriction, A.8.10 information deletion, A.8.11 data masking,
  A.8.15 logging, A.8.16 monitoring activities) and the UU PDP principles it relates to
  (purpose and minimisation, access, correction, deletion, security, record of processing).
  The map is **candidate input for the GRC team, not an assertion of conformance**; control
  numbers and any UU PDP article numbers are to be confirmed with the internal GRC and legal
  teams.
- Staff identifiers are personal data processed for the purpose of review accountability; the
  lawful basis and the retention for them are for legal to confirm. The system helps an
  organisation meet an incident-notification duty by providing integrity refusals and the audit
  log as inputs; the notification process itself is organisational and is not implemented.

## 12. Module layout

```
src/regulus/governance/
├── inventory.py   load the inventory; introspect stored models; completeness checks
├── access.py      roles, operations, the matrix, authorize(role, operation)
├── audit.py       AccessAudit (chained), record kinds, fail-closed helper
├── policy.py      FreeTextPolicy and boundary checks
├── retention.py   RetentionPolicy, expiry, hold, purge with receipts, PurgeLog
├── identity.py    IdentityMap and erase_identity
├── verify.py      verify_all over every chained log
├── scan.py        stored-record free-text scan (reuses the Phase 13 patterns)
└── app.py         GovernedApp WSGI middleware over the Phase 10 app
governance/data_inventory.v1.json  access_matrix.v1.json  retention_policy.v1.json  controls_map.v1.json
src/regulus/evaluation/layers/governance.py
tests/governance/
```

## 13. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| a stored model with a field missing from the inventory | inventory test fails |
| an inventory entry for a removed field | inventory test fails |
| every role by every operation | matches the matrix in the app, the operator functions and the authorizer |
| operation absent from the matrix | denied |
| actor with no role requesting a task page | 403, `ACCESS_DENIED` audited |
| auditor attempting any write | denied |
| operator or coordinator attempting a review action | denied by Phase 9 and by the matrix |
| a request through `GovernedApp` | one audit attempt; one record when the append succeeds; the chain verifies |
| reviewer reading a terminal task they did not participate in | 403, audited |
| reviewer reading a non-terminal task | allowed, however it is assigned; the decision is identical with and without an assignment |
| publisher reading a task not awaiting publication and not theirs | 403 |
| auditor reading any task | allowed, read-only |
| a role with no rule naming the resource | denied |
| acting on a task the actor cannot read | denied |
| audit sink failing, restricted page | 503, nothing rendered, no content leaked, `audit_gap` counted, `attempted = recorded + gap` |
| audit sink failing, public report | served, `audit_gap` counted |
| tampered access audit | `verify_all` finds it; restricted reads denied; writes refused |
| access record scanned | no content, name, address or credential |
| reason containing an email, URL, phone or credential pattern | 400 naming the field; nothing stored |
| over-length reason | 400; nothing stored |
| purge of an unexpired stream | refused, audited |
| purge of a non-terminal obligation's streams | refused |
| purge of a held stream | refused; release then purge succeeds |
| purge success | `PURGE_INTENT` with the final tip hash, then the stream gone, then `PURGE_APPLIED`; the log verifies |
| crash before the intent | nothing changed, nothing recorded |
| crash after the intent, before the delete | `recover_purges` completes it or ends it `PURGE_CANCELLED` per eligibility and hold; never `APPLIED` with the stream present |
| crash after the delete, before `PURGE_APPLIED` | `recover_purges` appends `PURGE_APPLIED` marked recovered |
| crash after `PURGE_APPLIED` | nothing to recover |
| a hold placed between intent and delete | second check refuses; `PURGE_CANCELLED` |
| a stream missing with no intent | `verify_all` reports it `UNRECEIPTED` |
| recovery run twice | the same end state |
| purge by a non-operator | denied |
| purge of a missing retention class | nothing purged |
| identity erasure | mapping gone; the opaque id still appears in historical chains; chains verify; nothing resolvable maps it to a person; erasure audited |
| each Phase 14 corruption class on each chained log | `verify_all` detects it |
| secret seeded into a stored free-text field | scan detects it |
| controls map | every control id exists in the matrix or invariants; no sentence asserts compliance |
| claim check over the governance report text | no forbidden claim phrasing |
| Phase 10 mounted without governance | frozen behaviour unchanged |

## 14. Gate

Contract frozen after review, then: inventory introspection and completeness, the access matrix
and its conformance tests, the audit log, `GovernedApp`, the free-text policy, retention with
receipts, hold and purge, identity erasure, `verify_all`, the scan, every §13 row, the §9
properties, the Phase 12 `governance` layer with baseline, ruff and strict mypy clean, then
freeze.

## 15. Decisions to confirm

1. Governance is policy plus verification, never a compliance claim; the claim discipline in §11
   is part of the contract.
2. Read access control is enforced by a `GovernedApp` middleware, so frozen Phase 10 is not
   edited; an actor with no role has no read access when governance is mounted. The policy is
   role-and-resource aware (need to know: participation and terminal status), and is deliberately
   independent of assignment.
3. Access is audited in a chained, content-free `AccessAudit`, with an independent
   attempted, recorded and gap accounting, and **fails closed** for restricted resources.
4. Retention is by whole-stream purge through a crash-safe intent, applied and cancelled
   protocol, plus legal hold; record-level erasure inside a retained chain is not offered and is
   flagged as an owner decision.
5. Erasure of identity is erasure of the mapping outside the chains; opaque ids are not
   anonymous.
6. Retention periods are configuration with illustrative defaults; the repository asserts no
   legal period.
7. The controls map is candidate input for GRC and legal, with numbers to be confirmed.
8. A `governance` layer joins the Phase 12 report.
