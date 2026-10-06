# Regulus — Lineage & Impact Contract

**Phase:** 5 · **Status:** FROZEN

Two questions, kept separate:

```
LINEAGE   "Which regulations are related, and why?"        regulation ↔ regulation
IMPACT    "Which regulatory objects does this event change?"   event → article → new wording
```

`PP 33/2026 ──IMPLEMENTS──▶ UU 27/2022` is lineage. `PP X ──AMENDS──▶ Pasal 42 of PP Y,
wording changed` is impact. Phase 6 needs both and must never confuse "implements"
with "affects".

Principle carried from Phases 2–4: **if the text cannot be deterministically
interpreted, Phase 5 records an explicit unresolved state; it never invents a
relationship or an impact.**

## 1. Boundaries

| Phase | Owns | Phase 5 uses it as |
|---|---|---|
| 2 | what changed (events, `target_id`, status projection) | the declared relations; never re-derived |
| 3 | document structure, `AmendmentUnit`, `Provision`, provenance | the text to interpret; never re-parsed from PDF |
| 4 | relevance and sector | **not an input**: lineage is a corpus fact, independent of relevance. Relevance routing is an orchestration concern (Phase 11 decides which events get impact analysis, normally `RELEVANT`), never a semantic prerequisite for lineage correctness |
| 5 | lineage graph, article impact, changed-provision pointers | |
| 6 | obligations | consumes `ChangedProvision` / `WithdrawnProvision`; Phase 5 stops at articles |

Not in Phase 5: obligations, relevance, sector, similarity, legal conclusions about
what a changed provision "means", effectivity dates (`berlaku`), inferred
amendments from prose outside the grammar in §4.

## 2. Inputs and outputs

`project(input) -> LineageResult`: a pure function, no I/O, no clock.

`LineageInput`:

| Field | From |
|---|---|
| `events` | Phase 2 `RegulatoryEvent` (`NEW`, `AMEND`, `REPEAL`, `PARTIAL_REPEAL`; `NEEDS_REVIEW` kept as unresolved) |
| `regulations` | Phase 1 `Regulation` index (dates, kind) |
| `declarations` | structured `IMPLEMENTS` declarations from the source adapter (`implementer`, `parent` natural key + raw text), same pattern as Phase 2 `DeclaredRelation` |
| `documents` | Phase 3 `ProcessedDocument` per acting regulation (units, provisions, articles, provenance, status) |
| `target_articles` | Phase 3 articles of the *target* regulations, when available |

`LineageResult`: `relations`, `impacts`, `changed`, `withdrawn`, `unresolved`,
`issues`, `complete`, `incomplete_sources`. A **contributing document** is one required to evaluate the supplied events and declarations (the acting regulation of an analysed event, and any regulation whose units or articles an operation reads). `complete` is false if any contributing document is not `PROCESSED_OK` or is missing; `incomplete_sources` lists exactly which (document id or regulation id, with its status). Unrelated documents in the corpus never affect `complete`.

Events are analysed individually too: `analyze_impact(event, input)` returns the
impacts for one event, so the workflow can run it only for relevant events while
`project` always builds the full graph.

## 3. Lineage model

Nodes are Phase 1 regulation ids. `LineageRelation`:

| Field | Meaning |
|---|---|
| `id` | `"lin-" + sha256(type, source_id, target_id)[:16]` |
| `type` | `AMENDS`, `REPEALS`, `PARTIALLY_REPEALS`, `IMPLEMENTS` |
| `source_id`, `target_id` | acting regulation → affected / parent regulation |
| `evidence` | non-empty ordered set of `RelationEvidence(kind, ref, occurred_on)`: `EVENT` (event id), `DECLARATION`, `UNIT` (unit id + `SourceSpan`). `occurred_on` is the source's promulgation date |
| `integrity` | `OK` or `CONFLICT` (some issue in §7 names this relation) |

Mapping from Phase 2: `AMEND→AMENDS`, `REPEAL→REPEALS`, `PARTIAL_REPEAL→PARTIALLY_REPEALS`.
`IMPLEMENTS` has no Phase 2 event; it comes only from a structured declaration
(§15 Q2). A `NEEDS_REVIEW` event yields **no relation**: it yields an
`UnresolvedRelation(event_id, reason, declared_ref)`, kept visible.

A `LineageRelation` is the **timeless** enduring fact "X has amended Y"; all temporal information lives in its evidence. `PP X AMENDS PP Y` in 2020 and again in 2024 is one relation with two evidence entries (two events, two dates), ordered by `(occurred_on, ref)`. A relation is a fact, not a state: relations are never deleted. What is "currently
in force" is a projection (§6).

## 4. Amendment-unit semantics (structure → operations)

Scope: only text inside Phase 3 `AmendmentUnit`s (`Pasal I`, `Pasal II`…), per
numbered point (`Provision` angka) or, if a unit has no points, the unit as one
operation. Quoted amended text, including inner `Pasal 5` headings, is the **new
wording**, never an operation.

**Target binding** (which regulation a unit amends), in order, no guessing:

1. the unit's intro sentence names a regulation (`Undang-Undang|Peraturan … Nomor N Tahun Y`) that matches an index entry by exact natural key (Phase 2 matcher) → that target;
2. else the **event under analysis** names exactly one target (`bind_unit_target(unit, event, index)` takes the event explicitly; a unit never binds against unrelated events in the history) → that target;
3. else `UnresolvedOperation(AMBIGUOUS_UNIT_TARGET)`.

If (1) names a target different from the event's, `UNIT_TARGET_MISMATCH` (§7).

**Closed grammar** (case-insensitive, whitespace-collapsed, exact patterns; v1):

| Operation | Pattern (Indonesian drafting formula) | Effect on target |
|---|---|---|
| `MODIFY` | `Ketentuan <locator> diubah[,] sehingga berbunyi sebagai berikut:` | article `MODIFIED` |
| `INSERT` | `Di antara <anchor> dan <anchor> disisipkan N (…) <unit>, yakni <label>, yang berbunyi sebagai berikut:` | one operation with `target_level` = `ARTICLE` (article `ADDED`), `AYAT` or `HURUF` (article `MODIFIED`, inserted label in `provision_path`); the level is read from `<unit>` (`Pasal`, `ayat`, `huruf`), anything else is unresolved |
| `APPEND` | `<locator> ditambah N (…) <unit>, yakni <label>, yang berbunyi…` | article `MODIFIED` |
| `DELETE` | `<locator> dihapus.` | `DELETED` (whole article) or `MODIFIED` (inside an article) |
| `REPEAL_PROVISION` | `<locator> dicabut[ dan dinyatakan tidak berlaku].` | `REPEALED` (whole article) or `MODIFIED` |
| `REPLACE_TERM` | `Kata\|frasa\|istilah "<x>" dalam <locator> diganti dengan "<y>"` | article `MODIFIED` |

The formula words are exact; the terminating colon after `berikut` may be spaced (` :`) or absent in the source, as in real instruments.

A **locator** is one or more of `Pasal N[A-Z]`, optionally prefixed by `ayat (n)`
and `huruf x` (e.g. `ayat (2) dan ayat (3) Pasal 5`) or suffixed with them (`Pasal 5 ayat (2)`, the equally common order), or a ranged form
`Pasal N sampai dengan Pasal M` (expanded to the integer range, suffixed articles
inside a range are not inferred). A locator naming `BAB`, `Bagian`, `Paragraf`,
`Penjelasan` or `Lampiran` is **recognized and unresolved**
(`UNSUPPORTED_LOCATOR`), because those are outside the article-level model.

Anything that matches no pattern, matches two, or has a locator that does not
parse is `UnresolvedOperation(UNSUPPORTED_OPERATION | LOCATOR_UNPARSEABLE)` carrying
the point's `SourceSpan`. **No fuzzy matching, no stemming, no inference from
similar wording.**

**New wording pointer.** For `MODIFY`, `INSERT`, `APPEND`, the new text is the
region after the operation sentence's terminating colon up to the next sibling
point or the unit end, trimmed, expressed as `TextRef(owner_id, start, end)` into
the owner's text (Phase 3 provenance applies unchanged). `REPLACE_TERM` carries the
quoted old and new terms as the new wording.

## 5. Impact model

`ImpactItem` (one per target article touched by one operation or one event):

| Field | Meaning |
|---|---|
| `id` | `"imp-" + sha256(relation_id, owner_id, op ordinal, target article, effect)[:16]` |
| `relation_id`, `event_id` | lineage link |
| `occurred_on` | promulgation date of the producing event's acting regulation (ordering key) |
| `derived` | true for per-article items projected from a regulation-level relation (§5) |
| `target_regulation_id`, `article_number` | `article_number = None` means a regulation-level effect |
| `provision_path` | e.g. `("(2)", "b")` when the operation addressed a provision inside the article |
| `effect` | `ADDED`, `MODIFIED`, `DELETED`, `REPEALED`, `PARTIALLY_REPEALED`, `UNKNOWN` |
| `source` | `Provenance` to the amending unit / article and the `SourceSpan` of the operation sentence |
| `new_text` | `TextRef` to the new wording, if any |
| `target_check` | `CONFIRMED` (article exists as the operation requires), `MISSING`, `ALREADY_EXISTS`, `NOT_CHECKED` (no target articles supplied) |
| `status` | `RESOLVED` or `UNRESOLVED(reason)` |

Rules:

- Whole-article `DELETE`/`REPEAL_PROVISION` give `DELETED`/`REPEALED`; an operation on an ayat or huruf inside an article gives article-level `MODIFIED` plus `provision_path`.
- `MODIFY`, `DELETE`, `REPEAL_PROVISION`, `REPLACE_TERM` require the article to exist in `target_articles`; if absent: `target_check = MISSING`, status `UNRESOLVED(TARGET_ARTICLE_MISSING)`. `INSERT` requires the new label not to exist (`ALREADY_EXISTS` otherwise) and both anchors to exist. With no `target_articles`: `NOT_CHECKED`, status `RESOLVED` but never silently upgraded.
- A `REPEALS` relation (whole regulation) is a **regulation-level lineage fact**: one regulation-level impact item `REPEALED` (`article_number = None`). When the target's articles are supplied, one `REPEALED` item per article is added as a **derived projection** of that regulation-level relation (`derived = true`); these are not independently sourced lineage relations.
- A `PARTIALLY_REPEALS` relation: see §8.
- A `NEW` event produces no impact items: the new regulation's own articles are its changes (`ChangedProvision`, below).

**Phase 6 interface** (the only *semantic* interface from Phase 5 to Phase 6; pointers only, Phase 5 never extracts obligations; identifiers, provenance and status travel with them):

- `ChangedProvision`: `regulation_id`, `article_number` (or unit label), `kind` (`NEW_REGULATION_ARTICLE`, `ADDED`, `MODIFIED`, `TERM_REPLACED`), `text_ref` (the Article itself, or the new-wording region inside an amending unit), `supersedes` (previous article id when known), `impact_id`.
- `WithdrawnProvision`: `regulation_id`, `article_number`, `effect` (`DELETED`/`REPEALED`), `impact_id`, so downstream can find obligations already tied to that `article_id` (Phase 1 `Obligation.article_id`) that may no longer hold.

## 6. Projection (history → state)

Pure functions over the relation evidence and impact set; impact items carry the `occurred_on` of the event that produced them. Ordered by `(occurred_on, id)`:

- `lineage_of(regulation_id)`: ordered chain of relations in and out.
- `project_article_status(regulation_id, article_number, impacts) -> ArticleProjection(status, anomalies)`:

| History | Status |
|---|---|
| none | `IN_FORCE` |
| `MODIFIED`/`ADDED` only | `AMENDED` (`ADDED` makes it exist from that date) |
| any `DELETED`/`REPEALED` | `WITHDRAWN` (absorbing) |

An impact dated after a `DELETED`/`REPEALED` of the same article is returned in
`anomalies`, not applied. Two conflicting operations on one article on the same date
(e.g. `MODIFIED` and `DELETED`) are an integrity issue (§7), not resolved by id order.

Regulation-level status stays the Phase 2 `project_status`; Phase 5 does not replace it.

## 7. Graph integrity

Issues are returned in `LineageResult.issues` and mark the involved relations
`CONFLICT`; **nothing is dropped or silently resolved.**

| Code | Condition |
|---|---|
| `SELF_RELATION` | source = target (Phase 1 forbids it for events; checked again for declarations) |
| `ANACHRONISM` | an evidence entry is dated before its target's promulgation (both dates known), for every type |
| `MUTUAL_REPEAL` | `A REPEALS B` and `B REPEALS A` |
| `HIERARCHY_CYCLE` | cycle in `IMPLEMENTS` or in `REPEALS` |
| `HIERARCHY_INVERSION` | `IMPLEMENTS` whose source is not strictly lower in the configured v1 norm-rank table (`UU`=`PERPU`=1, `PP`=2, `PERPRES`=3, `PERMEN`=`POJK`=`OTHER`=4). This is a deterministic structural sanity check, not a statement of legal validity: the relation is kept and flagged |
| `UNIT_TARGET_MISMATCH` | unit intro names a different target than the event (§4) |
| `CONFLICTING_OPERATIONS` | same article, same date, incompatible operations |
| `CONFLICTING_DECLARATIONS` | two declarations for the same source/type disagree on the target |
| `DUPLICATE_RELATION` | informational: merged, evidence unioned (no conflict) |

**Cycle policy is per relation type, not generic.** `AMENDS` edges may form a
directed cycle across time (A amended by B in 2020, B amended by A in 2022); that
is valid when each edge respects the time order, and is not an issue. `IMPLEMENTS`
and `REPEALS` cycles are impossible and are `HIERARCHY_CYCLE`. Other relation
combinations are unconstrained until the contract defines them.

## 8. Partial repeal

Phase 2's `PARTIAL_REPEAL` states that part of the target is repealed but not
which part. Phase 5 resolves scope **only from the acting regulation's text**,
by the closed pattern `<scope> <target ref> dicabut[ dan dinyatakan tidak berlaku]`
where `<scope>` is a locator (§4) and `<target ref>` matches the event's target.

- Parsed scope: one `REPEALED` item per article (a ranged locator expands), or `MODIFIED` + `provision_path` for ayat/huruf scope.
- Scope not found or not parseable: one regulation-level item `PARTIALLY_REPEALED`, `article_number = None`, `status = UNRESOLVED(SCOPE_UNRESOLVED)`. "What remains in force" is then **unknown**, never "everything else".
- With `target_articles` and a parsed scope, the in-force set is the articles minus the `REPEALED`/`DELETED` ones, via `project_article_status`.
- Prior amendments do not change this: an article amended and later repealed is `WITHDRAWN`; repealed and later amended is an anomaly.

## 9. Determinism and identity

Same `LineageInput` ⇒ byte-identical `LineageResult`. Ids are derived (§3, §5), never
random, and exclude dates and processing times. Ordering is `(occurred_on, id)`
everywhere. Duplicate relations merge with the union of evidence. The inputs
(event history, documents) are never mutated; re-running is idempotent and the
caller's store dedupes by id.

## 10. Failure and uncertainty

| Situation | Result |
|---|---|
| `NEEDS_REVIEW` event | `UnresolvedRelation`, no relation |
| operation matches no pattern / ambiguous / bad locator | `UnresolvedOperation` with span |
| unit target ambiguous | `UnresolvedOperation(AMBIGUOUS_UNIT_TARGET)` |
| target article missing / already exists | item `UNRESOLVED` |
| acting document `PARTIAL`, `PROCESSED_WITH_ISSUES`, `FAILED`, or missing | items flagged `source_status`; `complete = false`; an absent unit is never read as "no amendment" |
| partial-repeal scope not parseable | `SCOPE_UNRESOLVED` |

`complete = false` is how an incomplete or unreadable amending document stays
visible: an empty impact list from a non-`PROCESSED_OK` document is *not* "no impact".

## 11. Evaluation

- **Synthetic fixtures** written from the modern standard drafting formulas (grammar unit tests).
- **Real amending instruments** from the official BPK JDIH database, kept local (`pdf/`, git-ignored) with short excerpts committed as fixtures, each with its gazette citation (checked against the BPK record):
  - **PP 20/1980**, amends PP 21/1967 (amateur radio), promulgated 23 June 1980, LN 1980/30. Uses formulas like `Pada Pasal 1, ditambahkan dengan ketentuan huruf d, e, dan f` and `Ditambah ayat baru menjadi ayat (6)`.
  - **UU 21/1982**, amends UU 11/1966 and UU 4/1967 (press), promulgated 20 September 1982, LN 1982/52, TLN 3235. Uses `Pada Pasal 6 diadakan perubahan sebagai berikut`, `Ayat (2) diubah sehingga berbunyi`, `Ketentuan Pasal 7 ayat (3) dihapus`, and has two targets.
  - **The grammar is not widened to fit them.** Historical formulas the v1 grammar does not recognize must come out as `UnresolvedOperation`; the measured unresolved-rate on these instruments is the evidence for a possible grammar v1.1 (an amendment, decided on that evidence).
- **Lineage cases from real identities:** `PP 33/2026 → UU 27/2022`, `PP 14/2012 → UU 30/2009` (both `IMPLEMENTS`, hierarchy valid under the v1 rank table).
- **Gold file** `evaluation/lineage/gold.v1.json`: per case the operations and impacts expected, with rationale. Metrics: operation recognition precision/recall, locator accuracy, effect accuracy, **unresolved-rate and false-resolution count** (an operation resolved to a wrong article is the dangerous error; target 0 on the gold set), integrity-issue recall.

## 12. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| `AMEND` event, unit "Ketentuan Pasal 5 diubah sehingga berbunyi…" | `MODIFIED` Pasal 5, new-wording `TextRef` verifies |
| inserted `Pasal 5A` between 5 and 6 | `ADDED`, anchors checked |
| `ayat (2) Pasal 5` modified | article `MODIFIED`, `provision_path = ("(2)",)` |
| `Pasal 7 dihapus.` / `dicabut` | `DELETED` / `REPEALED` |
| range `Pasal 5 sampai dengan Pasal 8 dicabut` | four `REPEALED` items |
| term replacement | `MODIFIED`, old/new quoted terms kept |
| quoted `Pasal 5` heading inside the new wording | not an operation, not an impact |
| unknown formula ("diperbaiki seperlunya") | `UnresolvedOperation`, nothing inferred |
| locator `BAB II`, `Penjelasan`, `Lampiran` | recognized, `UNSUPPORTED_LOCATOR` |
| two patterns match one sentence | unresolved, not first-wins |
| omnibus: unit names target X, event target Y | `UNIT_TARGET_MISMATCH` |
| omnibus: two targets, unit names none | `AMBIGUOUS_UNIT_TARGET` |
| unit names target resolving via exact key | bound |
| article missing in target | `UNRESOLVED(TARGET_ARTICLE_MISSING)` |
| inserted label already exists | `ALREADY_EXISTS` |
| no `target_articles` | `NOT_CHECKED`, still `RESOLVED` |
| acting document `PARTIAL` | `complete = false`, items flagged |
| empty impact list from a non-OK document | `complete = false`, not "no impact" |
| `PARTIAL_REPEAL` with parsable scope | per-article `REPEALED` |
| `PARTIAL_REPEAL` without scope | `PARTIALLY_REPEALED`, `SCOPE_UNRESOLVED` |
| `REPEALS` whole regulation, articles supplied | regulation-level + per-article items |
| chain: amend, amend, repeal article | status `WITHDRAWN`; order independent of ingestion |
| repeal then later amend | `WITHDRAWN`, anomaly |
| same-day `MODIFIED` and `DELETED` of one article | `CONFLICTING_OPERATIONS` |
| `A REPEALS B`, `B REPEALS A` | `MUTUAL_REPEAL` |
| `IMPLEMENTS` cycle / `REPEALS` cycle | `HIERARCHY_CYCLE` |
| `AMENDS` cycle respecting time order | no issue |
| `PP IMPLEMENTS UU` | valid, no issue |
| `UU IMPLEMENTS PP` | `HIERARCHY_INVERSION` |
| amendment dated before its target | `ANACHRONISM` |
| `IMPLEMENTS` self | `SELF_RELATION` |
| same relation from event and declaration | one relation, evidence unioned |
| same pair amended in 2020 and 2024 | one relation, two evidence entries, ordered by date |
| `INSERT` of an ayat / huruf | `target_level` `AYAT`/`HURUF`, article `MODIFIED`, label in `provision_path` |
| `INSERT` whose unit is none of `Pasal`/`ayat`/`huruf` | unresolved |
| unit with no named target, event names one target | bound to it |
| unit with no named target, history holds other events with other targets | bound only against the analysed event |
| unrelated failed document in the corpus | `complete` stays true |
| derived per-article repeal items | `derived = true`, not independent relations |
| `NEEDS_REVIEW` event | `UnresolvedRelation` only |
| identical input twice, shuffled event order | byte-identical result |
| inputs unchanged after `project` | no mutation |
| Phase 1/2/3 compatibility | consumes real `RegulatoryEvent`, `Regulation`, `ProcessedDocument` as-is |

## 13. Module layout

```
src/regulus/lineage/
├── models.py       relations, impacts, TextRef, unresolved, issues, results
├── amendment.py    closed grammar: locator + operation parsing (pure)
├── relations.py    event/declaration → LineageRelation
├── impact.py       operations → ImpactItem, ChangedProvision, WithdrawnProvision
├── integrity.py    graph integrity rules
├── status.py       article status projection, lineage_of
├── project.py      project(), analyze_impact()
└── evaluate.py     metrics
evaluation/lineage/gold.v1.json
tests/lineage/
```

## 14. Gate

Contract frozen after adversarial review → implementation per module with tests
(grammar first, in isolation) → every §12 case passing → ruff and strict mypy
clean → gold set metrics, false-resolution count 0 → real-identity check (the two
`IMPLEMENTS` pairs) → freeze.

## 15. Decisions

1. **Phase 4 is not an input.** Relevance routing is an orchestration concern.
2. **`IMPLEMENTS` from structured declarations only**; preamble extraction is a later additive amendment (Phase 3 `Preamble` output).
3. **Article-level impact** with `provision_path`; no ayat-level lifecycle.
4. **Unit→target binding:** unit's named target, else the single target of the event under analysis, else unresolved; mismatch is an integrity issue.
5. **`ChangedProvision` / `WithdrawnProvision`** are the only semantic Phase 5→6 interface.
6. **Cycle policy per relation type;** the norm-rank table is a v1 structural sanity check, not legal validity.
7. **Grammar v1** as in §4, validated additionally against two real instruments (§11) without widening it to fit them.
8. **Relations are timeless; evidence carries dates** (§3).
9. **`complete`** is defined over contributing documents, with `incomplete_sources` (§2).
10. **`REPEALS` is lineage; per-article repeal items are derived impact projections** (§5).
11. **`INSERT`** is one operation with `target_level` (§4).
