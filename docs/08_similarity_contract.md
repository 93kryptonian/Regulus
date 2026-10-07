# Regulus — Similarity & Duplicate Intelligence Contract

**Phase:** 8 · **Status:** FROZEN

```
Phase 7  generated Obligation
Phase 8  Which existing obligations are nearby, and how are they related?   SimilarityResult (top 3)
Phase 9  What does a human decide?
```

Four things that look alike and **must never be conflated**:

```
retrieval similarity   ≠   duplicate   ≠   amends   ≠   related
```

- **Retrieval similarity** is a score from an embedding or lexical model. It answers only *"which existing obligations are nearby?"*. It is infrastructure, never evidence of a relationship.
- **Relationship label** (`POSSIBLE_DUPLICATE`, `VARIANT`, …) is a separate, evidence-backed, deterministic judgement made from the obligations' structured fields. It is a *suggestion for a human*, never a decision.
- **Lineage** (`AMENDS`, same-article chain) belongs to Phase 5. Phase 8 only reads it as context; it never assigns it.
- **Duplicate** is a human conclusion (Phase 9). The system says *possible*.

## 1. Purpose and boundary

For a generated obligation (the query) and a set of existing obligations (the index), Phase 8 returns up to **K = 3** matches, each with a retrieval score, a relationship label, the field-by-field evidence behind the label, and its lineage context.

| Does | Does not |
|---|---|
| represent obligations as comparable text and fields | decide duplicates, merge, delete or approve (Phases 9, 10) |
| retrieve nearby obligations (embedding or lexical) | let the embedding decide any relationship |
| rerank with structured field evidence | create or change an obligation |
| label relationships from field evidence, with the evidence | assign `AMENDS` or lineage (Phase 5) |
| report unavailability explicitly | call a provider other than through the injected interface |

## 2. Inputs and index

`search(query, index, config, providers) -> SimilarityResult`: the orchestration is
pure given the provider's vectors; the provider is injected.

- **Query:** a Phase 7 `GenerationResult` (obligation, its `TransformationTrace`, `open_questions`).
- **Index entries:** existing Phase 1 `Obligation`s with their structured content and, where available, their trace. `IndexConfig.include_statuses` (default `APPROVED`, `PUBLISHED`; evaluation also includes `GENERATED`). The query itself, and every obligation derived from the same candidate, are excluded.
- **Lineage context (optional):** the Phase 5 `LineageResult` relations, used only for the context annotation (§7).

Eligibility: the query must have status `GENERATED` and non-empty content; otherwise
`NOT_SEARCHABLE(reason)`.

## 3. Representation

`Representation` (built deterministically from an obligation):

| Part | Content |
|---|---|
| `text_tokens` | casefolded word tokens of `ObligationContent.text` |
| `fields` | normalized token sets for actor, action, object, deadline, frequency, condition, exception, each with a state `PRESENT` / `NOT_STATED` / `UNDETERMINED` (from the trace; an obligation without a trace has `UNDETERMINED` for fields that are `None`) |
| `modality` | `OBLIGATION` or `PROHIBITION` (from the verbatim marker) |
| `hash` | sha256 of the above, so vectors can be cached and invalidated |

The embedding input text is **only** the obligation text plus its populated field
values, never reviewer notes, status, or anything outside the regulation's text.
Only public regulatory text may be sent to an external provider; no other data
leaves the system through Phase 8.

## 4. Retrieval

```
class EmbeddingProvider(Protocol):
    id: str; version: str; dimension: int
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]
```

`VectorIndex`: `add(obligation_id, representation_hash, vector)`, `search(vector, k)`;
the reference index is in-memory brute force (pgvector is a later adapter).

- **Reference provider (`LexicalEmbedding`)**: offline and deterministic. Sublinear term frequency of word unigrams and bigrams, weighted by an IDF table fitted on the index corpus, hashed into a fixed dimension with signed hashing, L2-normalized. No network, no model.
- **OpenAI provider (later, optional extra):** an adapter implementing the same protocol. Not shipped in Phase 8; when added it changes retrieval only. Provider failures follow §8.
- Retrieval takes the top `K_retrieve` (default 20) by cosine, ties broken by obligation id, so reruns are identical. `score_kind = COSINE_UNCALIBRATED`: the number is **never** shown or used as a probability or a "% similar", and **no threshold is applied at retrieval**.

## 5. Reranking

**Relationship classification never uses the retrieval score.** A different provider can change *which* candidates enter the pool, never how a given pair is judged. The retrieval score is permitted only as a deterministic tie-breaker, after relationship tier and field score. For each retrieved pair the reranker computes the field comparisons (§6.1) and
orders the pool by (relationship tier, composite field score, retrieval score as tie-breaker only,
obligation id), highest first; the top `K = 3` are returned. Tier order (strongest
first): `POSSIBLE_DUPLICATE`, `CONTRADICTORY_MODALITY`, `VARIANT`, `RELATED`,
`SIMILAR_TEXT_ONLY`. The composite is a fixed, versioned weighted sum
(`RelationConfig.weights`); it orders results **only within already-classified relationships** and carries no meaning as a probability. A high composite or retrieval score never promotes a pair to a higher label: `POSSIBLE_DUPLICATE` is a conservative conjunction of field conditions (§6.2), not a score band.

## 6. Relationship labels

### 6.1 Evidence: field comparison

For each field in {actor, action, object, deadline, frequency, condition, exception}
and for modality, a `FieldComparison(field, query_value, match_value, relation)` with:

`EQUAL` (identical after normalization), `OVERLAP` (token Jaccard ≥ `τ_overlap` but not equal),
`DIFFERENT`, `ONE_MISSING` (stated in one, `NOT_STATED` in the other), `BOTH_NOT_STATED`,
`UNDETERMINED` (either side undetermined).

The comparison is lexical (normalized tokens, no stemming, no synonyms, no embedding).

### 6.2 Labels (closed, deterministic, evidence required)

| Label | Required evidence | Never when |
|---|---|---|
| `POSSIBLE_DUPLICATE` | same modality; actor, action and object `EQUAL` or `OVERLAP ≥ τ_dup`, all `PRESENT` on both sides; deadline, frequency, condition and exception each `EQUAL` or `BOTH_NOT_STATED` | any of actor/action/object is `UNDETERMINED` or missing on either side; any parameter `DIFFERENT` or `ONE_MISSING` |
| `VARIANT` | same modality; actor, action, object as for a duplicate; at least one of deadline, frequency, condition, exception `DIFFERENT` or `ONE_MISSING` | core fields not matching |
| `CONTRADICTORY_MODALITY` | opposite modality; actor, action, object as for a duplicate | modality equal |
| `RELATED` | at least one field (actor, action, object, deadline, frequency, condition, exception) `PRESENT` on both sides and `EQUAL` or `OVERLAP`, and not enough for the labels above. The result **names the supporting fields**, so a `RELATED` caused by the actor alone is visible as such and the review UI shows those comparisons | no matching field at all |
| `SIMILAR_TEXT_ONLY` | retrieved, but no field evidence | n/a (the default) |

Rules:

1. **A label above `SIMILAR_TEXT_ONLY` needs field evidence, listed in the result.** A high retrieval score alone yields `SIMILAR_TEXT_ONLY`, never a duplicate.
2. **The label depends only on the two obligations' fields and the versioned config**, never on the retrieval score or the provider. Swapping the provider must not change the label of any given pair.
3. **`UNDETERMINED` is an explicit label ceiling** (`label_ceiling`):
   - if any of actor, action or object is not `PRESENT` on **both** sides (`UNDETERMINED`, or missing), or the modality of either side is unknown: `POSSIBLE_DUPLICATE`, `VARIANT` and `CONTRADICTORY_MODALITY` are prohibited; **the maximum label is `RELATED`** (and only if a field-level match exists, else `SIMILAR_TEXT_ONLY`);
   - if the core matches but no parameter (deadline, frequency, condition, exception) is `DIFFERENT` or `ONE_MISSING`, and at least one parameter is `UNDETERMINED` on either side: `POSSIBLE_DUPLICATE` is prohibited and the maximum label is `RELATED` (a proven difference elsewhere still gives `VARIANT`, and an opposite modality still gives `CONTRADICTORY_MODALITY`);
   - the reason is always reported: `CAPPED_BY_UNDETERMINED(<field>)`.
4. Thresholds (`τ_overlap`, `τ_dup`) live in `RelationConfig`, versioned, and are justified by the gold set (§10).
5. The label vocabulary is a suggestion: the output says `POSSIBLE_DUPLICATE`, never `DUPLICATE`; nothing is merged or hidden.

## 7. Lineage context (separate from the label)

`lineage_context`, taken from the Phase 5 graph when provided, **not** from similarity:

`SAME_ARTICLE` (same `article_id`), `ARTICLE_AMENDED_BY` / `ARTICLE_AMENDS` (a Phase 5 `AMENDS` relation links the two obligations' regulations), `NONE`, `UNKNOWN` (no lineage supplied). It is reported next to the label; it never changes it. Two obligations from successive versions of one article may be `VARIANT` *and* `SAME_ARTICLE`; the reviewer sees both facts.

## 8. Result states and failure semantics

`SimilarityResult`: `query_id`, `status`, `matches`, `provider` (id@version), `index_version`, `config_version`, `retrieved` (pool size), `diagnostics`.

| Status | Meaning |
|---|---|
| `MATCHES` | ≥ 1 match returned |
| `NO_CANDIDATES` | processed, the index had no eligible entry (valid) |
| `UNAVAILABLE(reason)` | provider or index failure; **never** reported as "no similar obligations" |
| `NOT_SEARCHABLE(reason)` | the query is ineligible |

Phase 0 §9: an embedding failure leaves generation untouched and marks similarity
unavailable; the review UI shows "unavailable". Distinguish `NOT_PROCESSED` (no
result), `PROCESSED_EMPTY` (`NO_CANDIDATES`) and `PROCESSED_OK`. A partial index
(some entries failed to embed) reports `diagnostics: INDEX_INCOMPLETE(n)` and the
result is flagged `index_complete = false`, so a missing duplicate cannot be
mistaken for absence.

## 9. Determinism and index lifecycle

- Same `(query, index contents, provider id@version, config)` ⇒ byte-identical result; ties broken by obligation id; no time in ids. `id = "sim-" + sha256(query id, index version, provider id@version, config version)[:16]`.
- Vectors are cached by `(provider id@version, representation hash)`: unchanged text is never re-embedded; a changed text, provider or version invalidates exactly its entries.
- Index updates are add/replace by obligation id; the index records the provider id, version and dimension, and refuses to mix providers or dimensions.
- Inputs are never mutated.

## 10. Evaluation

Gold: `evaluation/similarity/gold.v1.json`: a small obligation corpus (obligations generated from the committed Phase 6 gold excerpts, plus synthetic variants made from them: changed deadline, opposite modality, reworded, unrelated), and labelled query→match pairs with a **written rationale** each (why this label, which fields). The set **must include hard negatives**: pairs with high lexical similarity and different field semantics (swapped actor/recipient, changed action, changed object) whose gold label is `RELATED` or `SIMILAR_TEXT_ONLY`; the false-duplicate metric is only meaningful if the gold stresses that boundary.

| Metric | Gate |
|---|---|
| Recall@3 / Precision@3 / MRR over gold `POSSIBLE_DUPLICATE`, `VARIANT`, `CONTRADICTORY_MODALITY`, `RELATED` | reported |
| duplicate precision, **false-duplicate rate** (`POSSIBLE_DUPLICATE` where gold is not a duplicate) | reported; **0 on the gold set is the target** |
| label confusion matrix (5×5) | reported |
| labels asserted without field evidence | **0** |
| provider independence: same pairs, different provider ⇒ same labels (and relation code never reads a retrieval score) | **100 %** |
| `UNDETERMINED` caps respected | **100 %** |
| determinism: reruns byte-identical | **100 %** |

Reference-provider recall figures are a baseline, not a claim about embedding
quality; they are the baseline an OpenAI provider is later compared against.

## 11. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| identical obligation text and fields | `POSSIBLE_DUPLICATE`, all fields `EQUAL` |
| same core, different deadline | `VARIANT` (deadline `DIFFERENT`) |
| same core, deadline stated on one side only | `VARIANT` (`ONE_MISSING`) |
| same actor/action/object, `wajib` vs `dilarang` | `CONTRADICTORY_MODALITY` |
| reworded text, high retrieval score, different fields | `SIMILAR_TEXT_ONLY` or `RELATED`, never a duplicate |
| identical text, actor `UNDETERMINED` on one side | label capped, `CAPPED_BY_UNDETERMINED(actor)` |
| shared object only | `RELATED` |
| unrelated text | `SIMILAR_TEXT_ONLY` or not retrieved |
| swap provider (reference vs a scripted second provider) | same labels per pair, possibly different pool |
| provider raises / times out | `UNAVAILABLE`, generation untouched, never "no matches" |
| empty index | `NO_CANDIDATES` |
| partial embedding failure | `INDEX_INCOMPLETE`, `index_complete = false` |
| query not `GENERATED` / empty content | `NOT_SEARCHABLE` |
| query itself and same-candidate siblings in the index | excluded |
| ties in score | broken by obligation id, stable |
| same article, successive versions | label from fields; `lineage_context = SAME_ARTICLE` |
| Phase 5 `AMENDS` between the regulations | `ARTICLE_AMENDED_BY` / `ARTICLE_AMENDS`; label unchanged |
| no lineage supplied | `UNKNOWN` |
| mixed providers or dimensions in one index | refused |
| representation changed | vector invalidated and recomputed |
| `K` smaller than the pool | exactly 3, ordered by tier |
| result shows a score | `score_kind = COSINE_UNCALIBRATED`, never labelled a probability |
| inputs unchanged; same input twice | no mutation; byte-identical |
| Phase 1/5/7 compatibility | consumes real `Obligation`, `GenerationResult`, `LineageRelation` |

## 12. Module layout

```
src/regulus/similarity/
├── models.py       Representation, FieldComparison, Match, SimilarityResult, config
├── representation.py   obligation → Representation
├── embedding.py    EmbeddingProvider protocol, LexicalEmbedding (reference)
├── index.py        VectorIndex (in-memory), cache by representation hash
├── relation.py     field comparison and relationship labels (provider-independent)
├── rerank.py       tiering and composite ordering
├── search.py       search(): retrieval → comparison → rerank → top 3
└── evaluate.py     metrics
evaluation/similarity/gold.v1.json
tests/similarity/
```

## 13. Gate

Contract frozen after adversarial review → implementation module by module with
tests (representation and relation labelling first, in isolation, since they carry
the safety properties) → every §11 case passing → ruff and strict mypy clean →
gold metrics with the §10 hard gates → real-corpus run over generated obligations
→ freeze.

## 14. Decisions

1. **Four-way separation** (retrieval ≠ duplicate ≠ amends ≠ related) and the rule that the **label is provider-independent and field-evidence-only** (§6.2 rules 1 and 2).
2. **Closed label set** with `POSSIBLE_DUPLICATE` (never `DUPLICATE`), `VARIANT`, `CONTRADICTORY_MODALITY`, `RELATED`, `SIMILAR_TEXT_ONLY`, and the `UNDETERMINED` cap.
3. **Reranking by structured field evidence**, not by embedding score (§5); the embedding only decides the candidate pool.
4. **Reference retrieval is lexical and offline** (hashed, IDF-weighted unigrams and bigrams); OpenAI embeddings are a later optional adapter behind `EmbeddingProvider`, and only public regulatory text may be sent to it.
5. **No threshold at retrieval; scores are uncalibrated and never shown as probabilities.**
6. **Lineage context is a separate annotation** read from Phase 5 and never changes the label (§7).
7. **Unavailable is not empty** (§8), and a partial index is flagged.
8. **Gold design:** synthetic variants derived from real generated obligations, rationale per pair; false-duplicate target 0.
9. **Review clarifications:** the `UNDETERMINED` ceiling is defined (§6.2 rule 3); retrieval score is a tie-breaker only and never classifies (§5); `POSSIBLE_DUPLICATE` is a conservative conjunction, never a score band; `RELATED` names its supporting fields; gold includes hard negatives (§10).
10. **Implementation order:** representation and relationship labelling first, with no embedding dependency (provider independence proven before any retrieval exists), then embedding, index, reranking, search, evaluation.
11. **Implementation clarification:** a parameter (deadline, frequency, condition, exception) that is `OVERLAP` but not `EQUAL` counts as a difference for `VARIANT` (only `EQUAL` or `BOTH_NOT_STATED` parameters allow `POSSIBLE_DUPLICATE`); a lexical-embedding provider's version includes its dimension and a hash of its fitted IDF table, so two fits are two providers; an index built by one provider cannot be searched by another.
