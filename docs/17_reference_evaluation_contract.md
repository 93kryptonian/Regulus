# Regulus v2 — Reference Corpus & Evaluation Harness Contract

**Phase:** 17 · **Status:** FROZEN

```
v1 (Phases 0–16)  frozen. Evaluation (Phase 12) measured components against self-authored gold sets.
v2 Phase 17       an expert-derived reference becomes the oracle, before any v2 AI component exists.
```

> Phase 17 builds the instrument, not the system under test. It defines what the expert reference
> contains, how it is loaded and reconciled, how a system's output is compared with it, and how
> much each comparison can prove. It contains no model call.

## 1. Question

**What does the expert reference say, in a form precise enough that later phases can be measured
against it and a degraded or fabricated result is detectably worse?**

| Phase 17 does | Phase 17 does not |
|---|---|
| load, validate, normalize and reconcile the reference | call any model or embedding |
| define the reference obligation identity and article linkage | extract, generate or classify anything |
| define the matching and metric interfaces and a deterministic baseline matcher | tune a prompt or policy |
| freeze a dev/test split before any prompt exists | claim any system quality |
| validate the instrument itself (oracle, null and mutated systems) | change a frozen v1 contract |

## 2. Boundary amendment (supersedes Phase 0 §10 for v2 only)

Phase 0 §10 forbids employer material in the repository. v2 amends this, narrowly:

1. The expert reference (`reference/`: spreadsheets and instruction documents) may be used **locally**.
   It is git-ignored (`/reference/`), is never committed, and its rows, texts and instruction content
   never appear in committed documents, tests, fixtures or reports.
2. Committed artifacts may contain **aggregate** facts only (counts, rates, intervals, per-regulation
   metric values keyed by the public regulation id).
3. Reference content **may** be sent to the configured model provider and stored in the configured
   database during v2 experiments; this was authorized by the project owner on 2026-10-08. Any such
   call is recorded as an egress event (provider, purpose, record count, no content) in the run log.
4. Tests run against a deterministic **synthetic stand-in** with the same schema. Tests and report
   rows that need the real reference are marked `reference` and, when the files are absent, report
   `NOT_MEASURABLE`, never a pass.
5. The reference is a local-only dependency. The public repository is reproducible without it, and
   reports say which rows were measured against it.

## 3. Inputs

| Input | What it is | What it is not |
|---|---|---|
| detail workbook | one row per (obligation, article) pairing, with regulation id, article text and sector | not one row per obligation |
| count workbook | declared obligation count per regulation id | not derived from the detail rows |
| sector vocabulary | the closed list of sector labels | not a taxonomy the model may extend |
| regulation PDFs | the public sources; each reference regulation id equals a PDF file stem | not all PDFs have references |
| instruction documents | the expert rules for writing obligations | not machine-readable gold |

### 3.1 Facts the model must respect (measured, aggregate)

- Rows are **article-obligation links**, not obligations. The file has six columns: obligation text,
  regulation id, article, article text, regulation title, sector.
- Article references are **article-level only** (`Pasal N`); there is no paragraph, appendix or
  reference-pointer column. Appendix handling therefore **cannot** be evaluated by this reference.
- One obligation commonly spans several articles, and one article carries several obligations.
- **Repeated identical rows carry meaning.** In PP 33/2026 one obligation text has every link
  repeated exactly twice, and the declared count (156) equals 155 distinct texts plus that one
  repeat. Collapsing identical rows would lose an obligation.
- **A regulation can appear under two titles with identical copies of its rows.** UU 30/2009 has two
  title forms, 138 rows each, and the two copies are identical. The copies are one regulation, not
  two (collapsing by id is required, or its count doubles).
- The multiplicity model reproduces **five of six** declared counts exactly. It gives 94 for UU 30/2009
  against 93 declared: one text has links repeated two and three times, and no consistent reading
  reaches 93. The residual of one is recorded, not forced (§5.4).
- Some article numbers carry more than one distinct article text within one regulation.
- Rows are heavily concentrated: one regulation holds about 88 % of them.
- Only a small subset of the sector vocabulary is observed; every observed sector is in the vocabulary.

### 3.2 What the reference does not contain

There are **no labels** for obligation type (licensing, continuous, periodic, prohibition,
conditional), sanction category, appendix origin, reference pointers, actor, action, modality,
condition, deadline or frequency. The instruction documents define type, sanction, appendix and
pointer rules, but those are **rules, not labelled data**. Consequently:

- type, sanction, appendix and pointer accuracy **cannot** be measured against expert labels;
- style rules that are mechanically checkable (action-verb start, `Dilarang` for prohibitions) are
  measured as **rule compliance**, never as agreement with the expert;
- field-level metrics (actor, action, modality, condition, deadline) can only be computed against
  the source text by the verifier (Phase 21) or against labels a later phase creates.

## 4. Reference model

Three entities, kept separate so that one obligation with several article links is never confused with
several obligations: `ReferenceRegulation`, `ReferenceObligation`, `ReferenceSourceLink`.

Immutable Pydantic models (`frozen`, `extra="forbid"`), in `regulus.reference`.

| Model | Fields | Notes |
|---|---|---|
| `ReferenceRegulation` | `regulation_id`, `labels` (tuple of titles seen), `declared_obligation_count` | identity is the id only |
| `ReferenceObligation` | `obligation_id`, `regulation_id`, `text`, `normalized_text`, `ordinal`, `sectors` (tuple) | one per (normalized text, ordinal) per regulation; `ordinal` numbers identical repeats; never keyed by text alone |
| `ReferenceSourceLink` | `obligation_id`, `regulation_id`, `article` (int), `article_texts` (tuple of distinct texts, sorted), `sector` | one obligation has one or more links; more than one article text is kept and flagged, never merged |
| `ReferenceSector` | `label` | the closed vocabulary |
| `Discrepancy` | `kind`, `regulation_id`, `detail_counts` | kinds in §5.4 |
| `ReferenceCorpus` | regulations, obligations, source links, sectors, discrepancies, `source_digests`, `split` | digests are of the input files, not content |

`obligation_id = sha256(regulation_id + "\x1f" + normalized_text + "\x1f" + ordinal)[:16]`, derived,
never trusted from a file.

## 5. Loading, normalization and reconciliation

### 5.1 Loading
- Spreadsheets are read with the standard library (zip and XML), handling inline and shared strings.
  No spreadsheet dependency is added.
- A missing file, sheet or column is a refusal that names the **field**, not the value.
- No network, no model, no clock.

### 5.2 Normalization (closed, versioned: `normalization_version`)
Unicode NFC, collapse whitespace, strip, casefold for **comparison only**; the original text is kept.
Article reference `Pasal N` parses to an integer; anything else is a `PARSE_ERROR` discrepancy and
the row is excluded, counted, never guessed.

### 5.3 Identity: the multiplicity model
1. **Label copies.** Rows are grouped by regulation id. If a regulation appears under several titles,
   the row multisets of each title are compared; identical copies are kept once (`LABEL_COPIES_IDENTICAL`),
   and non-identical copies are a refusal (`LABEL_COPIES_DIFFER`).
2. **Link.** A link is (article number, article text, sector).
3. **Group.** Within one regulation, links are grouped by normalized obligation text.
4. **Multiplicity.** For each group, the multiplicity of each distinct link is counted. The number of
   reference obligations in the group is the **minimum link multiplicity** (an obligation is only
   counted as repeated if every one of its links repeats). Repeats are numbered by `ordinal`.
5. **Ordinals and residual repeats.** Every ordinal of a group carries the group's distinct links.
   Repeats beyond the minimum add no obligation; the group is flagged `IRREGULAR_MULTIPLICITY`.
   Repeats are never used to invent extra obligations.
6. A row that differs only in sector is a different link, not a duplicate.

This rule is a **hypothesis fitted to the six declared counts**, not a fact about how the expert
produced the file. It is reported as such.

### 5.4 Reconciliation (reported, never forced)

| Discrepancy | Meaning |
|---|---|
| `COUNT_MATCHED` | derived obligation count equals the declared count |
| `COUNT_UNDECLARED` | the regulation has no declared count |
| `DECLARED_COUNT_CONFLICT` | the count file declares different counts for one id |
| `COUNT_EXCEEDS_DECLARED` / `COUNT_BELOW_DECLARED` | derived count differs from the declared count; the difference is recorded |
| `IRREGULAR_MULTIPLICITY` | a text group whose links repeat unevenly |
| `LABEL_COPIES_IDENTICAL` | one regulation under several titles, rows identical |
| `MULTI_TEXT_ARTICLE` | one article number has more than one distinct text |
| `PARSE_ERROR` | an article reference that is not `Pasal N` |
| `UNKNOWN_SECTOR` | a sector outside the vocabulary |

The current reference is expected to give: five regulations `COUNT_MATCHED`, one
(UU 30/2009) `COUNT_EXCEEDS_DECLARED` by 1. A test pins these results, so a change in the data or in the
rule is visible. Obligation-level metrics for an unreconciled regulation are flagged
`COUNT_UNRECONCILED`; the unit is still the derived obligation, and no text is split or merged to
make a number agree.

## 6. Dev/test split (frozen before any prompt exists)

- The unit of splitting is the **regulation**, never the row, article or obligation.
- The split is data (`evaluation/reference_split.v1.json`: regulation ids, role, reason), committed
  with this contract. Changing it is a contract amendment.
- **Frozen assignment:**

| Role | Regulations (by id and public name) | Derived obligations |
|---|---|---|
| dev | PP 33/2026 (`lt6a9164bf1e96a`), PP 40/2012 (`lt4f72ee9aba41a`), POJK 31/POJK.05/2016 (`lt57bac6099aa30`) | 162 |
| test | PP 61/2009 (`lt4b1e12ac0efd3`), PP 14/2012 (`lt4f32463fb11ee`), UU 30/2009 (`lt4b209de5e2d16`) | 165 |

- Reasons: the largest regulation (and the only 2026 document) stays in dev so tuning has enough
  material; test has three regulations with different structure and the one unreconciled count, so
  test results carry that flag; dev (162) and test (165) are close in size.
- Limits stated up front: dev is one newer, one mid-2010s and one small regulation; test is older
  and structurally different, so a gap between dev and test measures **distribution shift as well as
  overfitting**. Neither is generalization evidence.
- Prompts, policies and thresholds may be tuned on **dev only**. The harness refuses to emit a test
  metric from a run whose configuration changed after its last test evaluation without a recorded reason.

## 7. Evaluation harness

### 7.1 Interfaces
```python
class Matcher(Protocol):
    version: str

    def match(self, predicted: str, reference: tuple[ReferenceObligation, ...]) -> MatchResult: ...


class SystemOutput(Model):  # what a system under test returns for one regulation
    regulation_id: str
    obligations: tuple[PredictedObligation, ...]  # text, articles, sector, evidence refs
```
`MatchResult` carries the matched reference ids, a `MatchKind` (`EXACT_NORMALIZED`,
`ARTICLE_OVERLAP`, `NONE`) and the matcher version. The baseline matcher matches a predicted
obligation to a reference obligation **only** on equal normalized text, assigning one reference
obligation per prediction in ordinal order; a further prediction with the same text is a
`duplicate-predicted`. `ARTICLE_OVERLAP` is a **diagnostic, not a match**: the text differs but
the predicted articles overlap reference links, so the report can separate "right place, wrong text"
from "nothing nearby". It is deterministic and offline. A semantic or model
matcher is a later, separately evaluated instrument and is never assumed equal to the baseline.

### 7.2 Metric families (each with explicit population, numerator and denominator)

| Family | Examples | Evidence class |
|---|---|---|
| reference integrity | rows loaded, discrepancies by kind, duplicates collapsed | REGRESSION |
| coverage | reference articles covered, regulations covered | EXPERT_REFERENCE |
| count | predicted vs declared vs distinct count, reported side by side | EXPERT_REFERENCE |
| matching | matched, missing, over-generated, duplicate-predicted (per matcher version) | EXPERT_REFERENCE |
| sector | agreement per regulation against the closed vocabulary | EXPERT_REFERENCE |
| style rules | action-verb start, prohibition wording (rule compliance, not expert agreement) | RULE_COMPLIANCE |
| field | actor, action, modality, condition, deadline: only against source text via the verifier, or against labels a later phase creates | PROPERTY |

Rules inherited from Phase 12: no overall score, no pooled number across regulations without the
per-regulation rows beside it, `NOT_MEASURABLE` instead of zero, Wilson intervals below 100
observations, one denominator per metric, the largest regulation never allowed to dominate a
headline (pooled rows are labelled and shown with per-regulation rows).

### 7.3 Validating the instrument (hard gates)

| Check | Expected |
|---|---|
| **oracle** system output built from the reference | matching recall and precision 1.0 |
| **null** system (empty output) | recall 0, nothing over-generated |
| **mutated oracle** (drop, duplicate, alter modality, shift article) | each mutation lowers exactly the metrics it should and no other |
| **shuffled** article links | article coverage drops |
| same inputs twice | byte-identical report |

A metric that cannot tell the oracle from the null system does not ship.

## 8. Failure semantics

| Situation | Behaviour |
|---|---|
| reference files absent | all reference rows `NOT_MEASURABLE`; synthetic-stand-in rows still run |
| missing column or sheet | refusal naming the field; nothing partially loaded |
| unparseable article reference | counted as `PARSE_ERROR`; row excluded; never guessed |
| regulation id with no PDF | recorded; coverage metrics `NOT_MEASURABLE` for it |
| count and distinct texts disagree | reported, flagged `COUNT_UNRECONCILED`, never forced |
| report would include row content | build fails (content scan over every artifact) |

## 9. Hard invariants

1. **Identity.** Regulation identity is the id; titles never key anything.
2. **No forced reconciliation.** A discrepancy is reported, never silently resolved.
3. **No content leak.** No committed artifact or report contains reference rows, texts or
   instruction content; a scan test enforces it on the synthetic stand-in and on real reports.
4. **Split integrity.** The split is by regulation, committed, and a test fails if a regulation is in
   both roles.
5. **Instrument validity.** Oracle, null, mutated and shuffled checks pass on every build.
6. **Determinism.** Same inputs, same report bytes.
7. **Local only.** Nothing under `reference/` is tracked; a test fails if `git ls-files reference`
   returns anything.
8. **Honest evidence class.** Test numbers are never labelled generalization.
9. **Counts reproduced as measured.** Five declared counts are reproduced exactly and one is off by
   one, and a test pins both facts; the harness never edits data to improve agreement.
10. **No unlabeled dimension is scored.** Type, sanction, appendix and pointer accuracy are reported
    `NOT_MEASURABLE` with the reason that the reference has no labels for them.

## 10. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| every link of a text repeated twice | two ordinals; counts as two obligations |
| uneven repeats within one text | minimum multiplicity counts; `IRREGULAR_MULTIPLICITY` flagged |
| one regulation under two titles, identical rows | kept once; `LABEL_COPIES_IDENTICAL` |
| one regulation under two titles, rows differ | refusal `LABEL_COPIES_DIFFER` |
| request for type, sanction or appendix accuracy | refused; no label exists |
| same obligation and article, different sector | one obligation, two sectors |
| article with two distinct texts | `MULTI_TEXT_ARTICLE`; both kept |
| declared count above or below distinct texts | discrepancy; metrics flagged |
| article reference not `Pasal N` | `PARSE_ERROR`; excluded and counted |
| sector outside vocabulary | `UNKNOWN_SECTOR` |
| missing column | refusal naming the field |
| reference absent | rows `NOT_MEASURABLE`; stand-in rows run |
| oracle, null, mutated, shuffled systems | per §7.3 |
| regulation in both split roles | build fails |
| row text placed into a report | content scan fails the build |
| `reference/` staged in git | invariant 7 fails |
| report built twice | identical bytes |
| pooled metric dominated by one regulation | per-regulation rows shown beside it; label present |

## 11. Module layout

```
src/regulus/reference/
├── models.py       reference models, MatchResult, SystemOutput
├── xlsx.py         stdlib spreadsheet reader
├── normalize.py    normalization (versioned) and article parsing
├── load.py         ReferenceCorpus build and reconciliation
├── split.py        split loading and validation
├── matching.py     Matcher protocol, baseline matcher
├── metrics.py      metric families, mutations
└── synthetic.py    deterministic stand-in with the same schema
src/regulus/evaluation/layers/reference.py    Phase 12 layer
evaluation/reference_split.v1.json
tests/reference/
```
No new runtime dependency. `python-dotenv`, `psycopg` and an OpenAI client belong to later phases.

## 12. Claims

Allowed: "the harness loads and reconciles the expert reference deterministically", "the instrument
distinguishes an oracle, a null and mutated systems", "results are per regulation against an
expert reference of six regulations, with intervals".

Not allowed: any system quality claim, "accuracy" without its denominator, any generalization claim,
any statement about appendix handling, any statement that the declared counts and distinct texts
agree, and any reproduction of reference content.

## 13. Decisions (confirmed by the project owner, 2026-10-08)

1. The multiplicity model (§5.3) is the obligation identity. UU 30/2009 is `COUNT_EXCEEDS_DECLARED`
   by 1 and is **never forced**; the freeze does not wait for an expert explanation.
2. The dev/test split in §6.
3. The baseline matcher of §7.1; semantic matching is a later instrument.
4. Stdlib spreadsheet reading, isolated under the Phase 17 boundary.
5. Appendix, paragraph, type and sanction evaluation are out of scope for this reference (§3.2) and
   reported `NOT_MEASURABLE`.
6. The reference model has the three entities of §4. Code lives in `src/regulus/reference/` and the
   contract in `docs/`, not in a separate `v2` tree.
7. Egress events are logged without content (§2.3).

## 14. Boundaries set for later phases (recorded, not implemented here)

- **Roadmap:** 17 Reference Corpus and Harness, 18 Ingestion, 19 Extraction, 20 Expert LLM, 21 Grounding
  and Verification, 22 Sector, 23 Embedding and pgvector, 24 Similarity, 25 Workbench v2, 26 Human
  Feedback, 27 Model/Prompt/Policy Evaluation, 28 Routing and Optimization, 29 Release Gate.
- **Result reuse is cross-cutting.** Durable, versioned result identity and reuse belong to each
  processing contract from Phase 18 (document fingerprint) and Phase 20 (durable result store with
  provenance, key over document hash and every version that affects output). PostgreSQL is
  authoritative. Redis, if used, is an optional cache and lock adapter and never the system of
  record; whether it is mandatory is decided in Phase 28 from measurements.
- **The workbench** consumes governed results and implements no caching or processing of its own.
- **The existing demo UI** is a feature-parity reference only, never an implementation source.
- **The reference is an evaluation oracle**, never a runtime source of truth for regulatory interpretation.

## 15. Amendments

- **A1 (implementation):** the derived obligation totals under the multiplicity model are 162 (dev) and
  165 (test), 327 in all, not 161 each: the earlier figures counted distinct texts. The assignment of
  regulations to roles is unchanged. The declared counts sum to 326; the derived total is 327 because
  UU 30/2009 is over by 1.
