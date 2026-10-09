# Regulus v2 — Extraction Units & Deterministic Signals Contract

**Phase:** 19 · **Status:** FROZEN (amendments A1 applied before freeze)

```
Phase 18  which exact document, and which articles did it contain?        (frozen)
Phase 19  prepare every article for semantic interpretation, losslessly,
          with deterministic evidence attached
Phase 20  decide what constitutes an obligation, group across articles,
          and be measured against the expert reference
```

> **Phase 19 is a lossless structural preparation stage, not a deterministic obligation-recall
> stage.** It does not define deterministic obligation recall as its objective. It guarantees
> article-level input coverage and produces deterministic extraction signals. Obligation recall
> against the expert reference is evaluated only after semantic generation and consolidation in
> Phase 20.

## 1. Profile that shapes this contract (counts only, six benchmark regulations)

| Fact | Observation |
|---|---|
| Phase 6 on real text | runs on all 620 articles, no `FAILED`, no ungrounded drops; 350 candidates in 239 articles |
| Phase 6 article coverage of the reference | 135 of 319 reference articles carry a Phase 6 candidate (about 42 %) |
| Why the rest are missed | 181 of the 184 misses contain **no** closed-lexicon marker word; the reference records implicit obligations (permissions, passive duties) |
| Lexical lift | reference articles are 51 % of all articles; the closed lexicon flags 40 % of articles and catches 43 % of reference articles, about chance; widening it to 86 % recall flags 82 % of articles |
| Reference selectivity | the expert records a subset: one POJK shows candidates in 51 articles against 3 reference articles |
| Obligation span | five regulations: median 1 to 2 articles per obligation; the largest (PP 33/2026): median 22, 94 % multi-article, 2 % consecutive |
| Cross-references | connect only 33 of 216 multi-article obligations (15 %) |
| Size | about 429 000 characters, roughly 107 000 tokens for the six regulations per full pass |

Consequences: a lexical filter would irreversibly drop most expert articles; an article-local view
cannot reproduce multi-article obligations; and cross-references are a weak structural hint, not an
obligation graph.

## 2. Question and boundaries

**Given the Phase 18 article structure of a document, what extraction units does it contain, which
deterministic signals does each carry, and is every article guaranteed to reach Phase 20?**

| Phase 19 does | Phase 19 does not |
|---|---|
| turn every article (and amendment unit) into an extraction unit with provenance | filter, rank away or suppress any article |
| attach deterministic signals as evidence | decide that an article contains no obligation |
| attach Phase 6 explicit-marker results as hints, unchanged | tune any rule toward the expert reference |
| build a cross-reference graph as a structural signal | treat that graph as an obligation graph |
| record what could not be processed (gaps, annexes) | process annex content |
| report signal statistics against the reference | call a model, an embedding or a database; claim obligation quality |

## 3. Input and the no-loss guarantee

Input is a Phase 18 `IngestionResult`. Phase 19 **never reparses a PDF**.

```
IngestionResult → build_package() → ExtractionPackage
```

| Rule | Statement |
|---|---|
| Coverage | every article in the Phase 18 `article_index` becomes exactly one `ExtractionUnit`; every Phase 3 amendment unit becomes exactly one unit of kind `AMENDMENT_UNIT` |
| Presentation | the package exposes every unit; there is no filtered view that downstream stages may use in place of it |
| Carried loss | articles Phase 18 could not recover (reported `ARTICLE_GAP`), failed pages and unprocessed annexes are listed in the package (`missing_articles`, `unprocessed_regions`); a loss is never silent at any stage |
| Failure | an ingestion that `FAILED` or was `REFUSED` produces a `FAILED` package with no units and no claims |
| Scope of the guarantee | it covers every **recoverable** unit in the Phase 18 result. Unrecovered material is represented through inherited issues and `missing_articles` / `unprocessed_regions`, and is never treated as processed |
| Complete hand-over | Phase 20 receives the complete `units` collection. It may use signals as context but must not treat `NO_SIGNAL`, `NO_OBLIGATION` or the graph as grounds to exclude a unit before semantic interpretation |

## 4. Extraction unit

```python
class ExtractionUnit(Model):
    unit_id: str                  # sha256(regulation_id, kind, label, ordinal)[:16]
    kind: UnitKind                # ARTICLE, AMENDMENT_UNIT
    label: str                    # article number or amendment label
    ordinal: int                  # 0-based position among units in document order
    article_id: str | None        # Phase 3 id; required for ARTICLE, None for AMENDMENT_UNIT
    page_start: int
    page_end: int
    text_hash: str                # Phase 3 hash of the unit text
    provision_ids: tuple[str, ...]  # Phase 3 provisions inside the unit
    heading_normalized: bool      # carried from Phase 18
    signals: tuple[Signal, ...]
    phase6: Phase6Hint
```

The unit **references** the Phase 3 article by id, page range and hash; the text itself stays in the
Phase 3 document inside the ingestion result, so provenance cannot drift. A reader reconstructs the
unit text through the existing Phase 3 provenance functions.

### 4.0 Identity
`unit_id` includes the document-order `ordinal`, so repeated or malformed labels cannot collide.
Invariants: `unit_id` is unique within a package; `article_id` is present exactly when `kind` is
`ARTICLE` and is unique among ARTICLE units; a validator rejects a package violating either. Both are
tested with repeated and malformed labels.

### 4.1 Granularity
The unit is the **article**. Provisions (ayat, huruf, angka) are referenced, not split into separate
units: deciding what an obligation is belongs to Phase 20. Multi-article windows and regulation-level
grouping are Phase 20.

## 5. Deterministic signals

A `Signal` is `kind`, `term` (the closed-lexicon entry matched), `start` and `end` and
`signals_version`. **Offset convention:** Python `str` character indices (code points, not bytes) into
the unit text exactly as Phase 3 provides it; `end` is exclusive, so `text[start:end]` equals the
matched surface form, compared case-insensitively to `term`. Multiword phrases are one signal spanning
the whole phrase. Tests cover Unicode Indonesian text and multiword phrases. Signals are **evidence about wording, never a decision
about obligation**.

| Kind | Source |
|---|---|
| `EXPLICIT_OBLIGATION`, `EXPLICIT_PROHIBITION` | the frozen Phase 6 lexicon markers (loaded, not copied) |
| `PERMISSION` | `dapat`, `berhak`, `boleh`, `diperbolehkan`, `diizinkan` |
| `SANCTION` | `sanksi administratif`, `dikenai sanksi`, `dikenakan sanksi`, `dipidana`, `pidana penjara`, `denda` |
| `RESPONSIBILITY` | `bertanggung jawab`, `bertugas`, `berwenang` |
| `DUTY_VERB` | `melakukan`, `menyampaikan`, `memenuhi`, `menyelenggarakan`, `melaporkan`, `menyimpan`, `memberikan`, `menetapkan`, `mengajukan`, `menyediakan`, `memberitahukan`, `menjamin`, `memastikan`, `melindungi`, `menghapus`, `memusnahkan` |
| `PASSIVE_DUTY` | `dilakukan`, `disampaikan`, `dipenuhi`, `diberikan`, `disimpan`, `diajukan`, `ditetapkan`, `dilaporkan`, `diselenggarakan`, `dilaksanakan`, `disediakan`, `diberitahukan` |
| `CONDITION`, `DEADLINE`, `FREQUENCY` | the frozen Phase 6 lexicon triggers and phrases |
| `ENUMERATION` | two or more `HURUF` or `ANGKA` Phase 3 provisions in the unit |
| `DEFINITION` | `yang dimaksud dengan` and the definition form of Pasal 1 |
| `CROSS_REFERENCE` | `Pasal N` mentions (§7) |
| `NO_SIGNAL` | recorded explicitly when a unit carries none of the above, so absence is a fact, not a gap |

Matching is whole-word, case-insensitive on the Phase 3 text, deterministic, and order-stable. There
is no cap on the number of signals. The lexicon is package data (`signals.v1.json`), versioned; a change
is a new version and a new package key.

**Disclosure.** The word lists above were chosen while profiling the reference-linked articles, so
the signal statistics measured against the reference are **not held-out evidence**. They are reported
per Phase 17 role (dev and test) and labelled accordingly.

**No retrospective tuning.** Lexicon v1 is frozen with this contract. It is not tuned against the
reference within Phase 19; any change is a new lexicon version, a new `package_key`, and needs a fresh
evaluation. Whether signals improve Phase 20 generation or routing is not answered by Phase 19
statistics (generation outcomes: Phase 20; routing: Phase 28).

## 6. Phase 6 as a hint, unchanged

For each article unit the frozen Phase 6 `extract` runs exactly as for a new regulation article, and
its result is attached as `Phase6Hint` (status, candidate ids and spans, diagnostics, dropped count).

- Phase 6 is **not modified** and its output is never used to include or exclude a unit.
- A Phase 6 failure on one unit records `PHASE6_FAILED` on that unit only; the unit remains.
- `NO_OBLIGATION` from Phase 6 means "no explicit marker found", never "no obligation".

## 7. Cross-reference graph

Edges are `(from_unit, to_unit, start, end)` for each `Pasal N` mention in a unit's text where `N` is an
article of the same document. Self-references are ignored. A mention of an article that is not in the
document is recorded as `UNRESOLVED_REFERENCE` with its span and is never turned into an edge. The
graph is directed and may be read as undirected.

> The cross-reference graph is a **structural signal**. It is not an obligation graph: it connects only
> 15 % of the reference's multi-article obligations, and Phase 20 must not rely on it for grouping.

## 8. Extraction package

```python
class ExtractionPackage(Model):
    package_key: str
    identity: DocumentIdentity       # from Phase 18, unchanged
    status: PackageStatus            # PACKAGED, PACKAGED_WITH_ISSUES, FAILED
    units: tuple[ExtractionUnit, ...]
    graph: CrossReferenceGraph
    missing_articles: tuple[str, ...]
    unprocessed_regions: tuple[Region, ...]
    inherited_issues: tuple[Issue, ...]
    versions: PackageVersions        # signals, Phase 6 extractor and lexicon, contract
```

`package_key = SHA256(ingestion processing_key + signals_version + phase6 extractor version +
phase6 lexicon version + phase19 version)`. Versions are read from the running code, not typed in:
the Phase 6 extractor version and lexicon version from the loaded `lexicon.v1.json` and the
extractor's own version constant, the signals version from `signals.v1.json`, the Phase 19 version
from this package. Every output-affecting version is therefore represented; a test changes each in
turn and asserts a different key. Phase 20 extends this material with its own versions.
Units are ordered by document order; the package is a pure function of the ingestion result.

## 9. Evaluation (a Phase 12 layer, `extraction_units`)

### 9.1 Hard gates (`PROPERTY` / `REGRESSION`)

| Metric | Numerator / denominator | Gate |
|---|---|---|
| **silent unit drop** | articles in the Phase 18 index without a unit / articles in the index | **HARD: 0** |
| reference articles absent from the units without a reported cause | such articles / mapped reference articles | **HARD: 0** |
| unit count differs from article plus amendment-unit count | packages violating / packages | **HARD: 0** |
| provenance loss | units whose article id, pages or hash do not reconstruct the Phase 3 text / units | **HARD: 0** |
| signal span errors | signals whose offsets do not select their term / signals | **HARD: 0** |
| heading-normalization flag lost | normalized articles whose unit lacks the flag / normalized articles | **HARD: 0** |
| Phase 6 divergence | hints differing from a direct Phase 6 run / units | **HARD: 0** |
| non-deterministic packages | differing bytes on repeat / repeats | **HARD: 0** |
| cross-reference errors | edges or unresolved references violating §7 / mentions | **HARD: 0** |
| model, network or database use | detected imports / modules scanned | **HARD: 0** |

**Reference mapping (structural coverage only).** A reference article `(regulation_id, article number)`
maps to a Phase 18 article when the regulation id matches the ingested file and the normalized article
number equals an index label. Outcomes: `MAPPED` (has a unit), `MISSING_REPORTED` (absent but named in
`missing_articles` or an inherited issue), `UNMAPPED_NUMBER` (no index label of that number and no
reported cause; classified as a numbering or source-alignment mismatch, listed in the report, **not**
counted as a missing unit). Only an article that maps and still lacks a unit, or is absent with no
reported cause where a unit should exist, is a gate violation. This is a structural check, not an
obligation-quality metric.

### 9.2 Report-only (`CORPUS_COVERAGE`, never gated, never a target)

Per regulation and per Phase 17 role, with the pooled figure beside them:

- Phase 6 article coverage of the reference-linked articles (currently about 42 %);
- articles flagged by each signal kind, and the **exploratory reference association** of each (rate among
  reference-linked articles against the rate among all articles; the formula is lexical lift, always
  shown with the not-held-out disclosure);
- candidate distribution, and the `EXTRACTED` / `NO_OBLIGATION` / `UNRESOLVED` distribution;
- cross-reference connectivity of the reference's multi-article obligations;
- multi-article span statistics;
- reference-linked versus non-reference articles flagged;
- unit count, signal count and character totals (for the Phase 20 cost projection).

> **Candidate articles not linked by the reference are not errors.** The reference is selective, so
> non-membership is not a false positive. The 42 % figure is a description, never a target.

Reference rows need the local reference and PDFs; otherwise they are `NOT_MEASURABLE` and the synthetic
suite still runs.

## 10. Hard invariants

1. **Lossless.** Every article and amendment unit reaches the package; nothing is filtered.
2. **Provenance survives.** Every unit and signal maps back to Phase 3 text through Phase 18.
3. **Deterministic.** Same ingestion result, same signals lexicon, same package bytes.
4. **Phase 6 unchanged.** Hints equal a direct Phase 6 run; a Phase 6 result never gates a unit.
5. **Signals are evidence.** No code path uses a signal, a hint or the graph to drop or reorder a unit.
6. **Losses stay visible.** Gaps, failed pages and annexes are listed; none is silent.
7. **No model, no network, no database.**
8. **No obligation-quality claim.** Obligation recall is evaluated only after Phase 20.
9. **Complete hand-over.** Phase 20 receives all units; no exclusion before semantic interpretation.
10. **Unique identity.** `unit_id` unique per package; `article_id` unique and present only for ARTICLE.

## 11. Failure semantics

| Situation | Behaviour |
|---|---|
| ingestion `FAILED` or `REFUSED` | `FAILED` package, no units |
| ingestion with an `ARTICLE_GAP` | units for what exists, `missing_articles` lists the rest, status `PACKAGED_WITH_ISSUES` |
| Phase 6 fails on one article | that unit carries `PHASE6_FAILED`; all other units unaffected |
| article with no signals | still a unit, carrying `NO_SIGNAL` |
| amendment-style document | units of kind `AMENDMENT_UNIT`; no article claims |
| annex content present | listed in `unprocessed_regions`; not processed |
| reference mention of a missing article | `UNRESOLVED_REFERENCE`, not an edge |
| signals lexicon missing or invalid | refusal naming the file; no partial package |

## 12. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| article with no signal words | unit present with `NO_SIGNAL` |
| article with every signal kind | all recorded with correct offsets |
| negated marker (`tidak wajib`) | Phase 6 negation preserved; hint unchanged |
| permission, sanction, passive-duty wording | recorded as signals, never as obligations |
| heading-normalized article | unit flagged |
| ingestion gap | unit list excludes the gap; `missing_articles` names it |
| ingestion `FAILED`, `REFUSED` | `FAILED` package |
| Phase 6 raising on one article | that unit flagged, others intact |
| `Pasal N` to an existing article | edge with exact span |
| `Pasal N` to a missing article | `UNRESOLVED_REFERENCE` |
| self-reference | ignored |
| `Pasal N ayat (k)` | article-level edge, span covers the mention |
| amendment-style document | `AMENDMENT_UNIT` units, no article units |
| very long article | one unit, all signals, no truncation |
| same input twice | byte-identical package |
| signals lexicon version change | different `package_key` |
| unit text reconstruction | equals the Phase 3 article text |
| repeated or malformed labels | distinct `unit_id`s; package validator rejects duplicates |
| AMENDMENT_UNIT with and without article id | `None` accepted only for AMENDMENT_UNIT; ARTICLE without id rejected |
| Unicode Indonesian text, multiword phrase | offsets are code-point indices, `end` exclusive, span selects the phrase |
| each version input changed in turn | different `package_key` each time |
| reference number with no index label | `UNMAPPED_NUMBER`, not a missing unit |
| import scan | no model, network or database module |
| reference present, real PDFs | report-only rows per regulation and role |
| reference absent | reference rows `NOT_MEASURABLE`; synthetic suite runs |

## 13. Module layout

```
src/regulus/extraction/
├── models.py      ExtractionUnit, Signal, Phase6Hint, CrossReferenceGraph, ExtractionPackage
├── lexicon.py     signals lexicon loader (package data), versions
├── data/signals.v1.json
├── signals.py     deterministic signal matching
├── crossrefs.py   graph construction
├── package.py     build_package(), package_key
src/regulus/evaluation/layers/extraction_units.py     Phase 12 layer
tests/extraction/
```
No new dependency. `regulus.extraction` does not import `regulus.reference`; only the evaluation layer does.

## 14. Claims

Allowed: "every article of an ingested document is presented to the next stage with provenance",
"deterministic signals are attached as evidence and never used as a filter", "Phase 6 explicit-marker
extraction covers about 42 % of the reference-linked articles and is reported, not targeted".

Not allowed: any obligation-recall or obligation-quality claim, any statement that a unit without
signals contains no obligation, any use of the cross-reference graph as an obligation graph, and any
presentation of the signal statistics as held-out generalization evidence.

## 15. Decisions (confirmed)

1. **Signals lexicon v1** as listed in §5, frozen, with the disclosure and no retrospective tuning.
2. **Unit granularity** is the article, with provisions referenced and not split.
3. **Amendment units** are first-class units (`article_id` is `None`); annexes are listed, not processed.
4. **Phase 6** is unchanged and is a hint only.
5. **Package key** composition of §8, with versions read from code.
6. **Gates:** the hard list in §9.1; everything reference-related is report-only.
7. **Location:** `src/regulus/extraction/`, not a separate `v2` tree.

## Amendment A1 (before freeze)

Clarifications from review: unit identity with ordinal and the `article_id` schema (§4.0); precise
no-loss scope and complete hand-over (§3, invariants 9–10); operational reference mapping (§9.1);
package-key version sources and signal offset convention (§5, §8); "lift" relabelled as exploratory
reference association (§9.2).
