# Regulus — Relevance & Sector Contract

**Phase:** 4 · **Status:** FROZEN

Answers one question: **given a regulatory event and the content it touches, is
the change relevant to the configured compliance scope, and which sectors does it
concern?** Nothing else.

```
Phase 2  "What changed?"            RegulatoryEvent
Phase 4  "Is it relevant, which sector?"   RelevanceAssessment      ← this phase
Phase 5  "What is affected, what lineage?"
```

Not in this phase: obligations, lineage or impact, legal applicability,
fetching text, calling an LLM, calibration (Phase 12), review UI (Phase 9).

Stated explicitly so no later phase leans on more than is here:

- relevance ≠ legal applicability; sector ≠ compliance determination;
- an assessment approves or rejects nothing; it routes work to the next stage or to a human;
- uncertainty is a first-class outcome and never collapses to a default.

## 1. Inputs

`assess(context, config, classifier=None, assessed_at) -> AssessmentResult` — a pure function.

`AssessmentContext` keeps provenance to Phases 1–3; there is no raw text blob:

| Field | Source |
|---|---|
| `event` | Phase 2 `RegulatoryEvent` (must not be `NEEDS_REVIEW`) |
| `regulation` | Phase 1 `Regulation` named by `event.regulation_id` (the acting regulation) |
| `target` | Phase 1 `Regulation` named by `event.target_id`, if any |
| `texts` | `(owner_id, text)` pairs from Phase 3 `Article` / `AmendmentUnit`, optional |

`config` (versioned data, loaded and validated at start-up):

- `SectorTaxonomy`: stable `code` + label per sector, with a `version`.
- `ScopeProfile`: `id`, `version`, `sectors_in_scope`, `watchlist` (regulation ids already monitored), `sector_map` (explicit regulation id → sector codes), `exclusions` (regulation ids explicitly out of scope).
- `RuleSet`: `version` + rules (§3).

`NEEDS_REVIEW` events, or a context whose regulation ids do not match the event,
yield `NOT_ASSESSABLE(reason)`: the human resolves those first (Phase 2).

## 2. Sector taxonomy

A deliberately small, public, versioned vocabulary. v1 candidate, driven by the
sectors the local corpus actually covers:

| Code | Label |
|---|---|
| `FINANCIAL_SERVICES` | Financial services |
| `DATA_PROTECTION` | Personal data protection |
| `ENERGY_UTILITIES` | Energy and electricity |
| `ENVIRONMENT` | Environment |
| `LAND_FORESTRY` | Spatial planning, land and forestry |
| `TRANSPORT_AVIATION` | Transport and aviation |
| `GENERAL` | Cross-cutting, no single sector |

Properties: stable codes; assessments may hold **several** sectors; free-form
sector strings are rejected at construction (must be in the taxonomy named by
`taxonomy_version`); serialization is deterministic (sorted codes). It is
authored independently from public vocabulary and carries no employer-specific
terms.

## 3. Evidence and deterministic signals

`Evidence` is one cited fact:

`kind` (`DETERMINISTIC`|`SEMANTIC`), `rule_id`, `strength` (`STRONG`|`MODERATE`|`WEAK`),
`effect` (`SUPPORTS_RELEVANCE`|`CONTRADICTS_RELEVANCE`|`SECTOR_ONLY`), `sector` (code or none),
`source_id` (event, regulation, article or unit id), `span` and `quote` (when the
source is text; `quote == text[span]`, verified like Phase 1 evidence), `detail`
(short, template-generated for rules).

Deterministic rules, in this order, each producing zero or more evidence items:

| Rule | Fires when | Strength | Effect |
|---|---|---|---|
| `EXCLUDED_REGULATION` | actor or target id ∈ `exclusions` | STRONG | contradicts |
| `WATCHLIST_TARGET` | `event.target_id` ∈ `watchlist` | STRONG | supports |
| `SECTOR_MAP` | actor/target id has an explicit `sector_map` entry | STRONG | sector (supports if sector ∈ scope) |
| `ISSUER_SECTOR` | `regulation.issuer` matches an issuer→sector entry | MODERATE | sector (+ supports if in scope) |
| `TITLE_LEXICON` | whole-word, case-folded term of a sector lexicon occurs in the title | MODERATE | sector (+ supports if in scope) |
| `TEXT_LEXICON` | lexicon term occurs in a supplied text | WEAK | sector (+ supports if in scope) |

Lexicons are portfolio-original, generic public terms stored as data with a
version; matching is exact and whole-word, no stemming, no fuzzy matching. A
sector outside `sectors_in_scope` is recorded as `SECTOR_ONLY` evidence: it
**never** contradicts relevance. Only an explicit exclusion (or a grounded
semantic negative, §5) can do that.

## 4. Decision procedure (deterministic stage)

| Evidence present | Outcome | Confidence |
|---|---|---|
| ≥ 1 STRONG supports, no STRONG contradicts | `RELEVANT` | `HIGH` |
| ≥ 1 STRONG contradicts, no STRONG supports | `NOT_RELEVANT` | `HIGH` |
| STRONG supports **and** STRONG contradicts | `INSUFFICIENT_EVIDENCE`, `conflict = true` | `NONE` |
| no STRONG; ≥ 1 MODERATE supports | `RELEVANT` | `MEDIUM` |
| no STRONG, no MODERATE supports | undecided → §5 | |

**The table defines only the deterministic-stage outcome.** An undecided result proceeds to §5; the final assessment is the result after the optional semantic stage.

Policy rationale: the costly error is a false `NOT_RELEVANT`, so **only STRONG
evidence can exclude**, and silence is never "not relevant".

Sectors: the union of sector evidence at STRONG or MODERATE strength, sorted by
code. WEAK-only sectors are recorded in `evidence` but not in `sectors`.
`sector_status` is `DETERMINED` or `UNDETERMINED` (empty `sectors`); an empty
sector list is allowed only with `UNDETERMINED`. No default sector is invented.

## 5. Semantic classifier (optional, injected)

```
class RelevanceClassifier(Protocol):
    id: str; version: str
    def classify(self, request: ClassificationRequest) -> ClassificationResult
```

`ClassificationRequest`: event, regulation metadata (kind, number, year, title,
issuer), bounded text excerpts with owner ids, taxonomy, scope. `ClassificationResult`:
`decision` (`RELEVANT`|`NOT_RELEVANT`|`ABSTAIN`), `sectors`, `evidence`, `score`,
`score_kind` (`UNCALIBRATED`|`CALIBRATED_PROBABILITY`).

Invocation policy: only when relevance is undecided, or `RELEVANT` with no
determined sector. Phase 4 ships **no model**: the reference implementation is
rules-only (`classifier=None`), and the interface exists so rules, a trained
model, embeddings or an LLM can be added later without touching this contract.

Rules for accepting a result:

1. **Grounding.** Every semantic evidence item must cite a `source_id`, `span` and `quote` that verify against the supplied text (title or text owner). Unverifiable items are dropped and counted (`dropped_ungrounded`). A decision left with no grounded evidence is treated as `ABSTAIN`.
2. **No override.** A semantic result can only resolve an *undecided* case. It never changes a STRONG or MODERATE deterministic outcome.
3. **Negative needs a clear field.** A semantic `NOT_RELEVANT` is accepted only if no deterministic evidence of any strength supports relevance; otherwise the case is `INSUFFICIENT_EVIDENCE` with `conflict = true`.
4. **Confidence.** A semantic-only decision is `LOW`, regardless of the score. `score` is stored verbatim with its `score_kind` and is never presented as a probability. A calibrated threshold may raise confidence to `MEDIUM` only after Phase 12 evidence, via a versioned config change.
5. **Failure.** A classifier error or timeout records `semantic.status = FAILED`; the assessment falls back to the deterministic result, and an undecided case stays `INSUFFICIENT_EVIDENCE`. **A failure never becomes `NOT_RELEVANT`** (Phase 0 §9).
6. Sectors suggested by the classifier join `sectors` only with grounded evidence, and carry `kind = SEMANTIC`.

Undecided and no accepted semantic result ⇒ `INSUFFICIENT_EVIDENCE` (confidence
`NONE`), with the weaker evidence retained for the reviewer.

## 6. Output

`AssessmentResult`: `status` (`ASSESSED`|`NOT_ASSESSABLE`), `assessment`, `reason`.

`RelevanceAssessment`:

| Field | Meaning |
|---|---|
| `id` | `"rel-" + sha256(event_id, scope id@version, ruleset version, taxonomy version, classifier id@version or "none")[:16]`; no time in it |
| `event_id`, `regulation_id`, `target_id` | provenance |
| `relevance` | `RELEVANT` / `NOT_RELEVANT` / `INSUFFICIENT_EVIDENCE` |
| `confidence` | `HIGH` / `MEDIUM` / `LOW` / `NONE`, an **ordinal**, derived only by the table in §4/§5, never a free score |
| `sectors`, `sector_status` | §4 |
| `evidence` | all items, deterministic and semantic kept separate by `kind`, in deterministic order |
| `method` | `RULES` (no semantic evidence used), `SEMANTIC` (decided by classifier alone), `HYBRID` |
| `semantic` | `None`, or `{classifier id/version, status OK/FAILED/ABSTAINED, score, score_kind, dropped_ungrounded}` |
| `conflict` | true when evidence was contradictory (§4, §5.3) |
| `summary` | template-generated one-liner from evidence codes; **derived and non-evidential**: downstream must cite `evidence`, never `summary` |
| `basis` | scope/ruleset/taxonomy versions used |
| `assessed_at` | injected timestamp, not part of `id` |

`confidence` is deliberately **not** a number: a rule weight, an uncalibrated
model score, a calibrated probability and a human's certainty are different
things and are not interchangeable. The ordinal states only how strong and how
independent the cited evidence is.

## 7. Downstream routing (the point of the output)

| Assessment | Next step |
|---|---|
| `RELEVANT` | continues to Phase 5+ |
| `INSUFFICIENT_EVIDENCE` | human triage queue; never auto-continues and never auto-drops; `conflict = true` has priority |
| `NOT_RELEVANT` | recorded, not processed further; eligible for audit sampling (Phases 12/15) |
| `NOT_ASSESSABLE` | returned to the producer (e.g. `NEEDS_REVIEW` event unresolved) |

## 8. Determinism and idempotency

Same `(context, config, classifier output, assessed_at)` ⇒ byte-identical
result; same ids ⇒ the store deduplicates. Evidence order is fixed by
`(rule order, source_id, span)`. The classifier is invoked at most once per
assessment, and its output is part of the input of the pure decision step, so
tests replay recorded classifier outputs.

## 9. Evaluation (offline, not part of the runtime decision)

Gold record: `case_id`, the event/regulation facts or ids, `relevance`, `sectors`,
**`rationale`** (required, human-written: why this label), `annotator`,
`guideline_version`. Gold labels are authored for the portfolio's illustrative
scope profile; they are not claims about legal truth, and no real client data is
used. The first gold set is built from the public corpus identities plus
synthetic events and stays small (≈ 40 cases) with deliberately hard cases.

Metrics (pure functions in `regulus.relevance.evaluate`):

- relevance: 3×3 confusion matrix; precision, recall, F1 for `RELEVANT`; **abstention rate** (`INSUFFICIENT_EVIDENCE` share) and recall among decided cases. Abstaining is not scored as wrong, and not hidden either.
- error accounting: false `NOT_RELEVANT` is reported separately and headline-gated (target 0 on the gold set).
- sectors (multi-label): per-sector precision/recall/F1, micro and macro F1, exact-match ratio.
- explainability check: every `RELEVANT`/`NOT_RELEVANT` result has non-empty evidence whose quotes verify.

The evaluation framework itself (datasets, runners, gates) is Phase 12.

## 10. Module layout

```
src/regulus/relevance/
├── models.py       Evidence, RelevanceAssessment, AssessmentResult, enums
├── taxonomy.py     SectorTaxonomy, ScopeProfile, loading + validation
├── rules.py        RuleSet, deterministic signals
├── classifier.py   RelevanceClassifier protocol, request/result, grounding check
├── assess.py       assess() decision procedure
├── evaluate.py     metrics (offline)
└── data/           sector_taxonomy.v1.json, ruleset.v1.json, scope_profile.sample.json
evaluation/relevance/gold.v1.json
tests/relevance/
```

## 11. Adversarial cases (each needs a test)

| Case | Expected |
|---|---|
| `NEEDS_REVIEW` event | `NOT_ASSESSABLE` |
| event/regulation id mismatch, missing target for a target event | `NOT_ASSESSABLE` |
| AMEND whose target ∈ watchlist | `RELEVANT`, `HIGH`, STRONG evidence cited |
| Target ∈ exclusions, nothing else | `NOT_RELEVANT`, `HIGH` |
| Target ∈ watchlist **and** ∈ exclusions | `INSUFFICIENT_EVIDENCE`, `conflict` |
| NEW, title hits an in-scope sector lexicon | `RELEVANT`, `MEDIUM`, `method = RULES` |
| NEW, title hits only an out-of-scope sector | not excluded; undecided → `INSUFFICIENT_EVIDENCE` |
| Text-only (WEAK) hit | undecided; sector recorded in evidence, not in `sectors` |
| No signal at all, no classifier | `INSUFFICIENT_EVIDENCE`, `NONE`, `sector_status = UNDETERMINED` |
| Whole-word matching | `data` does not match `database`; case-folded match works |
| Classifier says RELEVANT with grounded evidence, undecided case | `RELEVANT`, `LOW`, `method = SEMANTIC` |
| Classifier evidence quote not in the text | dropped, counted; decision becomes ABSTAIN → `INSUFFICIENT_EVIDENCE` |
| Classifier says `NOT_RELEVANT` but a MODERATE rule supports | not overridden (decided `RELEVANT`, classifier not invoked) |
| Classifier `NOT_RELEVANT` with only WEAK deterministic support | `INSUFFICIENT_EVIDENCE`, `conflict` |
| Classifier raises / times out | fallback to deterministic; undecided stays `INSUFFICIENT_EVIDENCE`, `semantic.status = FAILED`, never `NOT_RELEVANT` |
| Classifier invoked on a STRONG-decided case | never invoked |
| Sector outside the taxonomy (rule data or classifier) | rejected / dropped, never reaches `sectors` |
| Several sectors | all kept, sorted, each with evidence |
| `RELEVANT`, no sector evidence | `sectors = ()`, `sector_status = UNDETERMINED` |
| Same inputs twice / different `assessed_at` | identical content / same `id` |
| Different ruleset or scope version | different `id` |
| Inputs not mutated | unchanged |
| Evidence invariants | every text evidence verifies (`quote == text[span]`) |
| Phase 1/2 compatibility | consumes real `RegulatoryEvent`, `Regulation`, `Article` objects as-is |

## 12. Gate

Contract frozen after adversarial review → implementation module by module with
tests → every §11 case passing → ruff and strict mypy clean → gold set built and
metrics run (reporting abstention and false-`NOT_RELEVANT` counts) → real-corpus
check (events derived from the local corpus identities produce explainable
assessments) → freeze.

## 13. Decisions

1. **Ordinal confidence** (`HIGH/MEDIUM/LOW/NONE`); the classifier score is stored separately with its `score_kind`.
2. **Taxonomy v1:** the seven corpus-driven codes. New sectors arrive as a new taxonomy version only when the corpus supports gold cases.
3. **Watchlist target = STRONG support**: a scope signal, not a legal conclusion.
4. **Only STRONG evidence excludes**; silence is `INSUFFICIENT_EVIDENCE` (human triage).
5. **Classifier policy** as in §5: undecided cases only, no override, grounded evidence, failure never `NOT_RELEVANT`, semantic-only `LOW`. No model ships in Phase 4.
6. **Gold set and metric code in Phase 4**, framework in Phase 12. The 0 false-`NOT_RELEVANT` figure is a safety target on the illustrative gold set, not a claim about real-world false negatives.
