# Regulus — Review UI Contract

**Phase:** 10 · **Status:** CONTRACT (v3, approved for implementation after the Phase 9 re-freeze)

```
Phase 9  Review engine: tasks, snapshots, gates, audit log   (the authority)
Phase 10 The workbench in which a reviewer inspects the evidence and decides
```

> The review UI must make the system's evidence, uncertainty, provenance and decision
> gates inspectable without making the UI itself authoritative.

The UI holds no state, makes no decision and enforces no rule. Every rule lives in
Phase 9; the UI shows what Phase 9 reports and sends what the reviewer chose. If the UI
and the engine disagree, the engine wins. The UI also says only what the system
recorded: it never invents an explanation (for example "clause inspected ✓") that no
earlier phase produced.

## 1. Boundary

| Does | Does not |
|---|---|
| build a plain-data `ReviewView` from task, store state and owner texts | add review rules or gates, or compute queue priority |
| render it as escaped, semantic, server-side HTML (no JS needed) | decide anything client-side |
| turn one form post into one `ActionRequest` for `apply` | change `ReviewConfig`, roles or transitions |
| show every refusal exactly as the engine reports it | authenticate; sessions, CSRF secret, identity are host-provided |
| make provenance, uncertainty, divergence and blockers visible | compare AI against manual extraction (Phase 12) |

No new runtime dependency and no framework: pure `build_view`, pure `render`, stdlib WSGI.

```
Phase 9 state ──► build_view() ──► ReviewView (data only) ──► render() ──► HTML ──► WSGI adapter
                  pure                                         pure                 routes · CSRF · actor · hash check
```

**Phase 9 amendments (docs/09 §16, re-freeze first):** A1 `preflight` shared with `apply`
and returning the full gate checklist; A2 snapshot carries the Phase 6 candidate for
per-field provenance. Phase 10 implementation starts only after Phase 9 is re-frozen.

## 2. Determinism, split

- `build_view`: same inputs → structurally equal `ReviewView` (clock injected).
- `render`: same `ReviewView` → byte-identical HTML.
- `ReviewView` contains data only, never markup; `render` is the only HTML producer.

## 3. The workbench

```
QUEUE (left)          SOURCE + PROVENANCE (centre)        DECISION (right)
risk-ordered          owner text, evidence marked         origin label
by Phase 9            field → citation → span             blockers, actions

below: OBLIGATION diff · SIMILARITY & LINEAGE · REVIEW GATES · HISTORY
```

| Section | Content | Rules |
|---|---|---|
| Header | obligation, regulation, article, status, task status, claim holder/expiry | |
| Source banner | one of VERIFIED / INCOMPLETE / CHANGED / WITHDRAWN, in words | WITHDRAWN states that approval and publication are unavailable; the only available review action is rejection, subject to normal Phase 9 authorization and transition rules (the engine may still refuse it) |
| Source text | full owner text, evidence spans marked | a span whose quote does not match the text is **EVIDENCE INVALID**, never highlighted |
| Provenance | per field: value, state, `Pasal …, chars a–b`, "exact quote verified ✓/✗" | from the snapshot candidate (A2); the view re-checks each citation against the owner text itself; no candidate → "no field provenance recorded", never fabricated |
| Field state | `PRESENT`, `NOT_STATED` ("the source states no <field>"), `UNDETERMINED` + the recorded reason and any related open question | only what Phase 6/7 recorded |
| Obligation diff | `generated` (AI) vs `current` (human), changed fields marked, editor reason | `generated` read-only everywhere; text not present in the source is flagged **source divergence** with the recorded tokens |
| Open questions | snapshot and carried questions, resolution control each | carried ones labelled |
| Similarity | per match: retrieval score marked **uncalibrated**, relationship label, field comparisons, lineage context, disposition control | retrieval score, relationship and human disposition are three separate labelled items; no "% duplicate" wording; `SIMILAR_TEXT_ONLY` marked weak |
| Gates | the A1 checklist, passing and failing, with a "why can't I approve?" list of blockers | straight from `preflight`; no UI-side conditionals |
| Actions | each `available` or `unavailable(reasons)` | disabled is a convenience; the engine is still called |
| History | timeline: submitted, claimed, edited (what and why), approved, published; per record actor, role, time, hash, previous hash; chain VALID/INVALID | read-only; verification result from `verify_chain` |
| Queue | Phase 9 order, risk markers (dangerous match, open questions, source flag), age, article | the UI renders the order, never recomputes it |

## 4. Requests

| Route | Method | Effect |
|---|---|---|
| `/tasks` | GET | queue |
| `/tasks/{id}` | GET | workbench |
| `/tasks/{id}/claim` | POST | `claim` |
| `/tasks/{id}/action` | POST | one `ActionRequest` → `apply` |

- A supplied `actor` field is rejected (400), never silently discarded: the actor comes only from the host.
- A post carries `base_version`, `snapshot_hash`, the action and its fields. Nothing
  missing is defaulted; the engine returns `INCOMPLETE_REVIEW` for the rest.
- `snapshot_hash` differing from the task's current one → `STALE` from the adapter
  before `apply` (the reviewer is never approving a page they were not shown);
  `base_version` is checked by the engine.
- Outcome is rendered verbatim (status and reasons) in an `aria-live` region, then the
  fresh workbench. `STALE` shows what changed; `NOT_RECORDED` says nothing was recorded.
- GET never changes anything. Every POST needs a valid host CSRF token or is refused
  without calling the engine. Duplicate or unknown fields are errors, not ignored.
- The `Actor` comes only from the host's `identify(request)`; no form field can set it.

## 5. Safety properties

1. **Escaping.** Every piece of text from sources, obligations, ids and users is escaped;
   nothing untrusted is placed unescaped in an element, attribute, URL or script.
2. **No unsupported claim as fact.** A value is shown with its state; invalid or
   unverifiable evidence is never presented as support.
3. **Origin visible, never inferred.** The header states the obligation's own `origin`
   (`AI-GENERATED`, `RULE-GENERATED`, `HUMAN-CREATED`); the review warning appears only for `AI`
   origin and only until `PUBLISHED`. Status never decides the label; no form or query parameter
   changes it.
4. **The UI cannot approve what the engine refuses:** a sequence of posts ends in the
   state `apply` alone yields for the same requests.
5. **No mutation by GET; none without CSRF.**
6. **Deterministic** as in §2.
7. **Security headers** on every response: `Content-Security-Policy` (no inline script,
   `frame-ancestors 'none'`), `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
8. **Accessible by default:** `main`/`nav`/`section`/`form`, `fieldset`+`legend` for
   disposition groups, real `button`s, labels bound to controls, visible focus, state
   always stated in text (never colour alone), evidence highlights carry a textual
   citation id, outcome in `aria-live`.

## 6. Failure semantics

| Situation | Behaviour |
|---|---|
| unknown task or obligation | 404, nothing leaked |
| actor with no applicable role | read-only; every action `unavailable(ROLE)` |
| store unreadable | error page; nothing rendered from partial data |
| malformed post (bad enum, duplicate, unknown or actor field) | 400 naming the field; engine not called |
| engine non-`APPLIED` | rendered verbatim; state and log untouched (Phase 9 invariant) |
| owner text missing for evidence/citation | **EVIDENCE INVALID** / "not verifiable"; approve unavailable |

## 7. Module layout

```
src/regulus/review_ui/
├── view.py     ReviewView and build_view (data only)
├── render.py   render_queue, render_task, render_outcome (escaped, semantic)
├── forms.py    parse a post into an ActionRequest or a field error
├── app.py      WSGI adapter: routes, CSRF, identify(), snapshot check, headers
└── text.py     fixed wording per reason code, status and gate
tests/review_ui/
```

## 8. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| **View model** | |
| generated ≠ current, edited field | both shown, field marked, reason shown |
| human text absent from the source | source divergence shown with tokens |
| carried open question | shown and labelled carried |
| `NOT_STATED` / `UNDETERMINED` field | worded as recorded; undetermined shows its reason |
| field citation not matching the text | "not verifiable", no highlight |
| evidence span mismatch, missing owner text | **EVIDENCE INVALID**, approve unavailable |
| overlapping evidence spans | both marked, well-formed nesting |
| evidence in an amendment unit | marked within the right owner text |
| no candidate in the snapshot | "no field provenance recorded" |
| `ReviewView` contents | no markup in any field |
| **Similarity and gates** | |
| `POSSIBLE_DUPLICATE` / `CONTRADICTORY_MODALITY` | needs disposition; blocker listed; approve unavailable |
| multiple dangerous matches | each listed and dispositioned separately |
| retrieval score | labelled uncalibrated, never worded as duplicate probability |
| `SOURCE_WITHDRAWN` | banner, approve/publish unavailable, reject available |
| incomplete / changed source | banner; approval needs acknowledgement |
| editor viewing own edit | approve `unavailable(FOUR_EYES)` in gates |
| auditor | everything `unavailable(ROLE)` |
| **Security** | |
| `<script>`, quotes, `&` in article, obligation, ids | escaped everywhere |
| malicious `snapshot_hash` / obligation id | no injection, no 500 |
| POST without / wrong CSRF | refused, engine not called |
| forged actor field | 400, engine not called |
| duplicate field | 400, engine not called |
| unknown action | 400, engine not called |
| bad enum | 400, engine not called |
| GET with side-effect parameters | no change |
| response headers | CSP, nosniff, referrer policy present |
| **Engine consistency** | |
| preflight available ⇒ apply succeeds; unavailable ⇒ refused | over seeded sequences |
| stale `base_version`; stale `snapshot_hash`; source changed between GET and POST | `STALE`, no state or log change |
| post for an action shown unavailable | engine called, its refusal rendered |
| UI post sequence vs direct `apply` sequence | identical obligation and log |
| **Rendering** | |
| same `ReviewView` twice | byte-identical HTML |
| long article, very long obligation text, 100+ tasks | renders, order preserved |
| every control labelled; no state by colour alone; semantic landmarks; `aria-live` | asserted on HTML |
| keyboard-only review | every action reachable by form controls without JS |
| **Real corpus** | |
| real obligation with a real Phase 8 match | renders; provenance verifies; posts reach `PUBLISHED`; replay equals final |

## 9. Evaluation

Behavioural: the §5 properties as seeded tests, the preflight/apply equivalence, and the
UI-vs-direct differential. No visual or usability study; portfolio screenshots are
produced from the real-corpus render. The AI-vs-manual extraction comparison from the
earlier prototype is Phase 12, not part of the review workbench.

## 10. Decisions

1. Server-rendered HTML, stdlib WSGI, no JS requirement, no new dependency. **Confirmed.**
2. `preflight` shared with `apply` via a narrow Phase 9 amendment (A1), re-frozen first.
3. `snapshot_hash` and `base_version` both checked. **Confirmed.**
4. Authentication, sessions and CSRF secret host-provided. **Confirmed.**
5. Provenance requires the snapshot to carry the Phase 6 candidate (A2).
6. Out of scope: notifications and assignment (Phase 11), AI-vs-manual and review metrics (Phase 12).
