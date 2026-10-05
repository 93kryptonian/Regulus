# Regulus — Domain Contract

**Phase:** 1 · **Status:** FROZEN

Canonical language of the system. Pure Python/Pydantic v2: no DB, API, LLM,
embeddings or orchestration types. An obligation is an obligation whether a
model, a rule or a human produced it.

## 1. Conventions

- All models are immutable (`frozen`), `extra="forbid"`; changes create new values.
- IDs are opaque strings; natural keys are derived, not trusted (§2).
- Timestamps are timezone-aware UTC.
- Invalid states fail at construction (`ValidationError`), never later.
- Serialization round-trips losslessly (`model_dump_json` ↔ `model_validate_json`).

## 2. Entities

| Entity | Meaning | Key fields |
|---|---|---|
| `Regulation` | A legal instrument | `id`, `kind` (UU/PP/PERPRES/PERMEN/POJK/…), `number`, `year`, `title`, `issuer`, `enacted_on`, `promulgated_on`, `source_url`, `status` |
| `RegulatoryEvent` | Something that happened to the corpus | `id`, `type`, `regulation_id`, `target_id`, `occurred_on`, `detected_on`, `basis` |
| `Article` | Source provision | `id`, `regulation_id`, `number`, `parent`, `text`, `page_start`, `page_end`, `text_hash` |
| `Sector` | Controlled vocabulary entry | `code`, `label` |
| `Obligation` | Structured meaning of a provision | `id`, `status`, `current`, `generated`, `origin`, `sectors`, `article_id` |
| `ObligationEvidence` | Why the obligation exists | `obligation_id`, `article_id`, `span`, `quote` |
| `ReviewDecision` | A human decision, append-only | `id`, `obligation_id`, `reviewer`, `at`, `from_status`, `to_status`, `reason`, `changes` |

Regulation natural key: `(kind, number, year)`; `id` is derived from it so the
same regulation ingested twice yields the same identity (idempotency, Phase 2).

## 3. Enums

- `RegulationStatus`: `IN_FORCE`, `AMENDED`, `REPEALED`, `UNKNOWN`
- `EventType`: `NEW`, `AMEND`, `REPEAL`, `PARTIAL_REPEAL`, `NEEDS_REVIEW`
- `ObligationStatus`: `GENERATED`, `PENDING_REVIEW`, `EDITED`, `APPROVED`, `REJECTED`, `PUBLISHED`
- `Origin`: `AI`, `RULE`, `HUMAN`

`NEEDS_REVIEW` is the explicit ambiguity outcome (Phase 0 §12): metadata that
cannot be resolved is never guessed.

## 4. Relationships

```
Regulation 1─* Article 1─* Obligation 1─* ObligationEvidence
Regulation 1─* RegulatoryEvent *─1 Regulation (target)
Obligation 1─* ReviewDecision
Article, Obligation *─* Sector
```

`Article.parent` is an opaque reference for now; its semantics (BAB, Bagian,
Paragraf, ayat, huruf) are defined in Phase 3.

References are by ID, not nesting; consistency across entities is a service
concern, structural validity is a model concern.

## 5. Obligation lifecycle (decision)

One `Obligation` identity with a `status`, not separate candidate/approved
types. Phase 0 requires the original AI output and the edited version to both
survive, so:

- `generated`: frozen snapshot at creation, never changes.
- `current`: the working content (actor, action, object, condition, deadline,
  frequency, exception, text); changes only through an `EDITED` transition.
- Candidate-processing failures (e.g. LLM timeout) are pipeline stage results,
  not obligations; a failed candidate does not exist in the domain.

```
GENERATED ─submit()→ PENDING_REVIEW → APPROVED → PUBLISHED
                │   ↑            
                │   └── EDITED ──┘ (back to PENDING_REVIEW)
                └→ REJECTED
```

Allowed transitions are a closed table; anything else is invalid. Terminal:
`REJECTED`, `PUBLISHED` (recovery is a new obligation, referencing the old).

## 6. Invariants

1. `Article.page_end >= page_start >= 1`; `text` non-empty after strip.
2. `Article.text_hash` equals the hash of `text`.
3. `RegulatoryEvent`: `AMEND`/`REPEAL`/`PARTIAL_REPEAL` require `target_id`; `NEW` forbids it; `target_id != regulation_id`; `detected_on >= occurred_on` is not required, but both are set.
4. `ObligationEvidence.span` lies within `Article.text` and `quote == text[span]`.
5. An obligation with no evidence cannot enter `APPROVED` (provenance gate, Phase 0 §8).
6. `Obligation.origin == AI` requires generation metadata (`model`, `prompt_version`, `generated_at`) on `generated`.
7. `ReviewDecision.from_status → to_status` must be an allowed transition; `reviewer` and `reason` (for `REJECTED`/`EDITED`) are required; `EDITED` carries a non-empty `changes`: a list of `FieldChange(field, before, after)`, not free text.
8. `GENERATED → PENDING_REVIEW` is a system workflow step (`submit()`), not a decision. Only `ReviewDecision` (a human reviewer) moves an obligation out of `PENDING_REVIEW` or `EDITED`; `PUBLISHED` requires a prior `APPROVED`.
9. Evidence passed to `apply_decision` must already be verified with `ObligationEvidence.matches(article)`; the caller filters, `apply_decision` takes no `Article`.

Invariants 5 and 8 span entities, so they are enforced by a pure function
`apply_decision(obligation, decision, evidence) -> Obligation` in the domain
package (no I/O), not by individual model validators.

## 7. Out of scope here

Persistence, API schemas, prompts, embeddings, similarity results, lineage
graph, document pages/paragraphs (Phase 3), `RelevanceAssessment` (Phase 4).

## 8. Gate

Schema validation, round-trip serialization, invalid-state tests for every
invariant above, closed transition table tests, and construction of every
entity from the real corpus (e.g. PP 33/2026 metadata and an article) without
any external service.

## 9. Decisions

1. `Regulation.status` is derived from `RegulatoryEvent` history (Phase 2). The stored value is a cached projection, never authoritative.
2. Article hierarchy stays shallow in Phase 1: `parent` and `number` are structural placeholders. `Paragraph`/`SourceSpan` are defined in Phase 3.
3. Edit history is the append-only `ReviewDecision` chain; `changes` is structured field-level before/after. No `ObligationVersion` entity.

## 10. Amendments

- Phase 1 implementation review: queueing (`GENERATED → PENDING_REVIEW`) removed from `ReviewDecision` so decisions are human-only (invariant 8); evidence verification layering made explicit (invariant 9).
