# Regulus — Generation Contract

**Phase:** 7 · **Status:** FROZEN

```
Regulatory source → Citation → Phase 6 ObligationCandidate → Phase 7 normalization → Domain Obligation
```

Generated text is never the canonical truth. The canonical chain is the one above,
and Regulus must be able to walk it backwards: from a sentence in an `Obligation`
to the candidate field that carries each of its parts, and from there to the exact
source span.

## 1. Purpose and boundary

Phase 7 turns one Phase 6 `ObligationCandidate` into one domain `Obligation`
(status `GENERATED`) plus the evidence and the transformation record that justify it.

| Does | Does not |
|---|---|
| normalize whitespace and punctuation of verbatim fields | re-extract, split or merge candidates (Phase 6) |
| compose the obligation text (reference: extractive) | interpret meaning beyond the candidate |
| record every candidate field's fate | decide applicability, compliance, relevance, sector |
| verify every generator output independently | approve, edit, reject or publish (Phases 9, 10) |
| attach generation metadata | find similar obligations (Phase 8) |

Phase 6 backlog items (passive-voice actors, adverbial lead-ins, object
boundaries, extra deadline phrasings) are **not** pulled into Phase 7: this phase
consumes the frozen candidate semantics as they are.

## 2. Inputs and preconditions

`generate(input, generator, config, generated_at) -> GenerationOutput`: a pure
function; the generator is injected and may be non-deterministic, everything
after it is deterministic.

| Input | Meaning |
|---|---|
| `candidates` | Phase 6 `ObligationCandidate`s, each with its `ChangeRef` |
| `documents` | Phase 3 `ProcessedDocument`s, to re-read the cited owner text |
| `extraction_complete` | per candidate: the Phase 6 `ExtractionResult.complete` flag |
| `config` | generator id, version, model and prompt version (if any), verification config version |

Eligibility, checked before the generator is called (**defence in depth**: Phase 7 does
not trust the candidate's own claim of validity):

- every citation of the candidate re-verifies (`quote == owner_text[span]`) against the owner text; otherwise `NOT_GENERABLE(CITATION_MISMATCH)`;
- the owner text is available; otherwise `NOT_GENERABLE(SOURCE_MISSING)`;
- the candidate satisfies the Phase 6 invariants (present action, or the closed `enumerated_items` exception).

Phase 6 results that produced no candidate (`UNRESOLVED`, `NOT_EXTRACTABLE`, `FAILED`, `NO_OBLIGATION`)
yield nothing here by construction; Phase 7 does not read them as obligations. A
candidate from an incomplete extraction is generated **and flagged**
(`source_complete = false`); it is never silently treated as complete.

## 3. Evidence owner: mandatory design decision

Phase 1 `ObligationEvidence` is article-bound (`article_id`, span in `Article.text`).
A candidate born from an amendment cites an `AmendmentUnit`: the new wording exists
only inside that unit's text. Two options:

- **A. Generalize the evidence owner (chosen).** Evidence cites `owner_id` + `owner_kind` (`ARTICLE` or `AMENDMENT_UNIT`) + `span` + `quote`.
- **B. Map the unit citation onto the changed article (rejected).** The new wording is not part of any stored `Article` of the target regulation (it is a quotation inside the amending unit), so the span cannot be mapped without losing the exact wording and its provenance, which Phases 3 to 6 preserve deliberately.

**Phase 1 amendment A2** (applied and re-frozen before any Phase 7 code):

1. `ObligationEvidence(obligation_id, owner_id, owner_kind, span, quote)`; `article_id` is replaced by `owner_id`. `matches(owner_id, owner_text)` verifies `owner_id` and `quote == owner_text[span]` (callers still own textual verification, Phase 1 invariant 9).
2. `Obligation` gains `source_owner_id`: the owner whose text the evidence cites. `article_id` keeps its meaning (the article the obligation belongs to): for an article-sourced obligation `source_owner_id == article_id`; for an amendment-sourced one `article_id` is the changed target article (`regulation:article`, the key Phase 6 `ObligationImpact` uses) and `source_owner_id` is the unit.
3. `apply_decision`'s provenance gate becomes: approval needs ≥ 1 evidence whose `obligation_id == obligation.id` and `owner_id == obligation.source_owner_id`.
4. Existing Phase 1 tests and the PP 33/2026 corpus test are updated; invariants 1 to 11 otherwise unchanged. The original `owner_id + span + quote` stays recoverable permanently.

## 4. Normalization contract

Four layers, kept separate:

| Layer | Allowed | Where it lives |
|---|---|---|
| **Semantic preservation** | nothing may change meaning | the verifier (§7) |
| **Textual normalization** | collapse whitespace and line breaks to single spaces; strip surrounding punctuation of a field value | field values (closed steps) |
| **Field normalization** | map candidate fields to `ObligationContent` slots; join several conditions / exceptions | field values (closed steps) |
| **Obligation text** | one sentence-like text carrying the whole clause | `ObligationContent.text` (verified, §7) |

**Closed transformation steps** for field values: `PRESERVE`, `WHITESPACE_COLLAPSE`,
`TRIM_PUNCTUATION`, `JOIN` (several conditions or exceptions joined with `"; "`,
the originals kept in the trace). No other step may touch a field value.

Prohibited, always: inventing a requirement; changing the actor; changing modality
(`wajib` ↔ `dilarang`, obligation ↔ permission); dropping a condition, exception,
deadline or frequency; expanding or defining a term (`Pengendali Data Pribadi` is
not expanded); converting durations into dates or other units (`3 x 24 jam` stays);
adding an applicability or compliance conclusion; adding any word absent from the
source clause.

`ObligationContent` mapping: `actor`, `action`, `object`, `deadline`, `frequency`
from the candidate field; `condition` = the joined conditions; `exception` = the
joined exceptions; a field whose state is `NOT_STATED` or `UNDETERMINED` is `None`
(the distinction is kept in the trace, §5); `text` per §6.

## 5. Traceability: the transformation record

```
Candidate field → step(s) → Obligation field → Source evidence
```

`TransformationTrace` lists one `FieldTrace` per candidate field and per
`ObligationContent` field:

- Candidate side (`marker`, `actor`, `action`, `object`, `deadline`, `frequency`, each condition, each exception, each item, the clause): **every candidate field ends in exactly one disposition**:
  - `PRESERVED` or `NORMALIZED(steps)`: carried to a named content field or into `text`;
  - `ABSENT(NOT_STATED)` or `ABSENT(UNDETERMINED, reason)`: no value existed; the reason is kept (never collapsed into one `None`);
  - `DROPPED(reason)` with a **closed** reason (`DUPLICATE` only in v1: a value identical to another carried value). Dropping an actor, marker, action, object, deadline, frequency, condition or exception for any other reason is a verification failure, not an accounting entry.
- Content side: **every populated `ObligationContent` field points back to ≥ 1 candidate field**, with the steps applied; `text` points to the clause and every non-absent candidate field.
- `open_questions`: the candidate fields in `UNDETERMINED` (including `action = enumerated_items`), surfaced to the reviewer UI. An undetermined field is a question for a human, not a blank.

The trace is recomputed by the verifier from the candidate; a generator-supplied
trace is only compared against it (§7: forged traceability fails).

## 6. Generator boundary

```
Candidate → Generator → RawGenerated → Independent verification → Domain Obligation
```

```
class ObligationGenerator(Protocol):
    id: str; version: str; model: str | None; prompt_version: str | None
    def generate(self, request: GenerationRequest) -> RawGenerated
```

`GenerationRequest`: the candidate, its `permitted_source_text` (§7) and the config. `RawGenerated`: `text`, content fields, trace.

**Reference implementation (`ExtractiveGenerator`)**: deterministic, no model.
`text` is the clause with whitespace collapsed (for an enumeration: the lead-in
clause followed by its items in source order). It adds no word, reorders nothing and
cannot reverse anything. Field values are the candidate's, with the closed steps
applied. A model-based generator may later rephrase `text`, but only within the
verifier's limits (§7); no model dependency belongs to this contract or to Phase 7's
shipped code.

Origin: the reference generator gives `Origin.RULE` (no `GenerationMetadata`
required by Phase 1); any model-assisted generator gives `Origin.AI`, which requires
`generated.meta` (model, prompt version, timestamp). One candidate gives exactly
one obligation: Phase 7 never merges or splits.

## 7. Independent verification (hard invariants, not metrics)

`verify(candidate, owner_text, raw) -> Verification(violations)` runs after the
generator, shares no code path with it, and any violation means **no Obligation**.
Matching is on casefolded word tokens (letters and digits) with whitespace collapsed.

**`permitted_source_text`** is defined once and is the only vocabulary V1 to V5 refer to:
`candidate.clause ∪ candidate.lead_in ∪ candidate.items` (the lead-in only for
enumeration-item candidates, the items only for candidates that carry them), each
re-read from the owner text, never taken from the candidate's own copy. Text outside it
(the rest of the article, other clauses) is not permitted vocabulary.

| # | Invariant | Violation code |
|---|---|---|
| V1 | **No new lexical token, multiplicity included:** every token *occurrence* in `text` is supported by an occurrence in `permitted_source_text`, so a token cannot appear more often than in the permitted text (`A wajib wajib melakukan X` fails against `A wajib melakukan X`), unless a closed normalization step permits it. The function-word allowlist is **empty** in v1 (even `dan`/`atau` cannot be added; widening it is a versioned config change) | `NEW_WORD` |
| V2 | **Completeness by state:** every candidate field in state `PRESENT` (actor, marker, action, object, deadline, frequency, every condition, every exception, every item) occurs in `text` as a contiguous token sequence. A `NOT_STATED` field has no value to preserve. An `UNDETERMINED` field has no reliable value to preserve: its state and reason must survive in the trace and in `open_questions` (for `action = enumerated_items`, the **items** must be in `text`, there is no action wording to preserve) | `FIELD_LOST` |
| V3 | **Core order:** in `text`, actor, then marker, then action, then object occur in that order (when present), so actor and recipient cannot be swapped | `ORDER_CHANGED` |
| V4 | **Modality:** the candidate's marker occurs, no other lexicon marker occurs, and no negation token (`tidak`, `bukan`, `jangan`, `tanpa`) occurs unless it is in the source clause | `MODALITY_CHANGED` |
| V5 | **Numbers:** every number or duration token in `text` is in the source, and every one in a candidate field is in `text` (no invented or converted figure) | `NUMBER_CHANGED` |
| V6 | **Field values:** each `ObligationContent` value equals the candidate field with only closed steps applied | `FIELD_ALTERED` |
| V7 | **Trace:** the trace equals the recomputed one: every candidate field has exactly one disposition, every populated content field points back | `TRACE_INVALID` |
| V8 | **Evidence:** evidence is built from the candidate's own citations only; each re-verifies against the owner text | `CITATION_MISMATCH` |
| V9 | **Required fields:** `text` non-empty, `action` present or the `enumerated_items` exception, marker present | `REQUIRED_MISSING` |
| V10 | **Lifecycle:** status is `GENERATED`; metadata present iff `Origin.AI` | `LIFECYCLE_INVALID` |

**Stated limit.** V1 to V5 are lexical and order-sensitive checks. They are
necessary, not sufficient: a rephrasing built only from source words could still
change meaning in ways they do not see. That is why a model-assisted generator is
constrained to the source vocabulary and why semantic contradiction is measured on
an adversarial set (§10), with any accepted contradiction recorded as a verifier
gap rather than hidden.

## 8. Generation metadata (distinct from review metadata)

`GenerationRecord`: `generator` (id@version), `config_version`, `candidate_id`,
`lexicon_version` (Phase 6), `model` and `prompt_version` (if any), `generated_at`
(injected clock), `source_complete`. For `Origin.AI` the Phase 1
`GenerationMetadata(model, prompt_version, generated_at)` is filled from it.

Generation metadata says **how the text was produced**. Review metadata
(`ReviewDecision`: reviewer, time, from/to status, reason, field changes) says **what
a human decided**; Phase 7 writes none of it and never reads it. The two are never
merged.

`obligation.id = "obl-" + sha256(candidate.id, generator id@version, config_version)[:16]`,
no time in it; a different generator version gives a different obligation.

## 9. Review boundary and lifecycle

Generated is not approved. Phase 7 outputs only `status = GENERATED`, with
`current == generated.content` (Phase 1 invariant 10). It never emits `EDITED`,
`APPROVED`, `REJECTED` or `PUBLISHED`. Moving to `PENDING_REVIEW` is the Phase 1
`submit()` workflow step (Phase 11); an obligation with `source_complete = false`
or non-empty `open_questions` is routed there with those facts attached, never hidden.
The output is labelled generated for the UI (`origin`, `generation` record).

## 10. Failure semantics

| Situation | Result |
|---|---|
| ineligible candidate (citation mismatch, source missing) | `NOT_GENERABLE(reason)`: no `Obligation` |
| generator raises / times out / returns malformed output | `GENERATOR_FAILED`: no `Obligation`, never an empty one |
| verification fails (any V1 to V10 violation) | `REJECTED_BY_VERIFICATION(violations)`: **no `Obligation`**; the raw output is kept in the result for audit, never promoted |
| unsupported transformation (a step outside the closed set) | `REJECTED_BY_VERIFICATION(FIELD_ALTERED)` |
| partial output (a candidate field neither carried nor accounted for) | `REJECTED_BY_VERIFICATION(FIELD_LOST` or `TRACE_INVALID)`; partial output never becomes a complete obligation |
| missing provenance | `NOT_GENERABLE`; there is no "obligation without evidence" |
| generation succeeded, extraction incomplete | `GENERATED` with `source_complete = false` |

A generated obligation always carries at least the clause evidence; there is no path
from a failure to a valid-looking `Obligation`.

## 11. Evaluation (hard gates)

| Metric | Gate |
|---|---|
| groundedness: tokens of `text` not in the source (hallucinated words) | **0** |
| citation correctness: evidence quotes equal their source text | **100 %** |
| completeness: candidate field values present in `text` | **100 %** |
| candidate-field accounting: fields with exactly one disposition | **100 %** |
| explicit-drop accounting: every `DROPPED` has a closed reason | **100 %** |
| **mutation detection**: each mutated output (§12) is rejected | **100 %** |
| **semantic contradiction accepted**: contradictory outputs that pass the verifier | **0 on the adversarial set; any accepted case is listed as a verifier gap** |

Datasets: the Phase 6 gold candidates and the real-corpus candidates (generation
pass rate, unresolved-field surfacing), plus `evaluation/generation/mutations.v1.json`:
a closed set of mutations applied to verified outputs, with a rationale each.

## 12. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| drop a condition / exception / deadline / frequency | `FIELD_LOST` |
| replace the actor (also swap actor and recipient) | `NEW_WORD` or `ORDER_CHANGED` |
| reverse modality (`wajib` → `dilarang`, add `tidak`) | `MODALITY_CHANGED` |
| invent a requirement / a deadline / an exception | `NEW_WORD` |
| change `3 x 24 jam` to `3 hari` / a date | `NUMBER_CHANGED` / `NEW_WORD` |
| expand a defined term | `NEW_WORD` |
| reorder so the object precedes the action | `ORDER_CHANGED` |
| content field altered beyond closed steps | `FIELD_ALTERED` |
| field dropped with a reason outside the closed set | `TRACE_INVALID` |
| field dropped for `DUPLICATE` | accepted, accounted |
| forged trace (claims a source field that does not exist, or omits one) | `TRACE_INVALID` |
| trace claims a field but the text lacks its words | `FIELD_LOST` |
| evidence citing text that does not contain the claim | `CITATION_MISMATCH` |
| evidence not from the candidate's citations | `CITATION_MISMATCH` |
| empty `text` / missing marker / missing action | `REQUIRED_MISSING` |
| `UNDETERMINED("enumerated_items")` | obligation generated, `open_questions` lists `action`, items in `text` |
| `NOT_STATED` field | `None`, trace `ABSENT(NOT_STATED)` |
| `UNDETERMINED` actor | `None`, trace `ABSENT(UNDETERMINED, reason)`, listed in `open_questions` |
| several conditions | joined with `"; "`, `JOIN` step, originals in the trace |
| amendment-unit candidate | evidence owner is the unit, `article_id` is the target article, `source_owner_id` the unit |
| multiple candidate fields feed one content field | one `FieldTrace` with several sources |
| generator raises / times out / malformed output | `GENERATOR_FAILED`, no obligation |
| malformed generator output (wrong types, missing keys) | `GENERATOR_FAILED` |
| status other than `GENERATED` | `LIFECYCLE_INVALID` |
| `Origin.AI` without metadata / `RULE` with metadata mismatch | `LIFECYCLE_INVALID` |
| incomplete extraction | `GENERATED`, `source_complete = false` |
| candidate whose citation no longer matches the text | `NOT_GENERABLE(CITATION_MISMATCH)` |
| same input twice / different generator version | identical / different ids |
| inputs unchanged | no mutation |
| Phase 1/3/6 compatibility | produces valid Phase 1 `Obligation` / `ObligationEvidence` objects |

## 13. Module layout

```
src/regulus/generation/
├── models.py      GenerationRequest, RawGenerated, FieldTrace, GenerationRecord, outputs
├── trace.py       recompute the transformation trace from a candidate
├── verify.py      V1 to V10 (independent of generators)
├── reference.py   ExtractiveGenerator
├── generate.py    eligibility, generator call, verification, obligation assembly
└── evaluate.py    metrics and mutation runner
evaluation/generation/mutations.v1.json
tests/generation/
```

## 14. Gate and freeze

Contract frozen after adversarial review → **Phase 1 amendment A2 implemented and
re-frozen** → implementation module by module (trace and verifier first, in
isolation) → every §12 case passing → ruff and strict mypy clean → gold, mutation
and real-corpus evaluation with the §11 hard gates → freeze.

## 15. Decisions

1. **Evidence owner: option A** and Phase 1 amendment A2 (§3), including `Obligation.source_owner_id`.
2. **Closed normalization steps** for field values; free composition only in `text`, under the verifier (§4).
3. **Strict verification:** no new word (empty allowlist), order-sensitive core, numbers and modality checks; stated limit and the mutation/contradiction gates (§7, §11).
4. **One candidate → one obligation**; no merge or split (§6).
5. **Reference generator is extractive**; model-assisted generators are an injected option, `Origin.AI` with metadata (§6, §8).
6. **Drops:** only the closed `DUPLICATE` reason; every other loss is a verification failure (§5).
7. **UNDETERMINED fields surface as `open_questions`**, never as plain blanks (§5).
8. **Lifecycle:** Phase 7 emits only `GENERATED`; `submit()` is orchestration (§9).
9. **Verifier clarifications (review):** token multiplicity in V1, completeness by field state in V2, and one `permitted_source_text` definition (§7).
