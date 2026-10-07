# Regulus — Evaluation Contract

**Phase:** 12 · **Status:** FROZEN

```
Phases 2–11  each component declares its own contract, gold sets and hard gates
Phase 12     how well does each component perform against its declared contract,
             and how much does each number actually prove?
```

> Phase 12 asks how well each component performs against its declared contract.
> It does not ask for one overall Regulus accuracy, and it never produces one.

The output is a **layered evaluation report**: for every layer, what was measured, on
which population, against which denominator, with what class of evidence, which gates
passed, where the system abstains or fails, and what the numbers cannot support.

## 1. Principles

1. **A metric is valid only with an explicit population and its own denominator.** Every
   reported number is defined by a `MetricDefinition` (population, numerator, denominator,
   formula) and carries the computed `numerator / denominator`. Metrics in the same family
   have different denominators and are defined separately: precision is `TP / (TP + FP)`,
   recall is `TP / (TP + FN)`, F1 is their harmonic mean, and none borrows another's
   denominator. A number without its definition is not emitted.
2. **Evidence classes are never mixed.** Every metric is labelled with exactly one class (§2).
   A number from a weaker class is never presented in the language of a stronger one.
3. **No cross-layer aggregation.** There is no overall score, no weighted mean, no "pipeline
   accuracy". The report schema has no field that could hold one.
4. **Missing observation is not a value.** A metric whose inputs the authoritative records do
   not contain is `NOT_MEASURABLE`; a layer with no gold is `NO_GOLD`. Neither is rendered as
   0, as a pass, or as an inferred number.
5. **Precision never appears without coverage.** For any component that may abstain, the
   decided fraction and the abstention rate are printed with the precision they qualify.
6. **Gates are inherited, not invented.** Hard gates are the ones the earlier contracts
   already state. Phase 12 may add `TARGET` or `REPORT_ONLY` lines, labelled as such, but it may
   not move a gate to make a run pass; changing a gate is a contract amendment.
7. **Known gaps are reported, not hidden.** A recorded known gap (for example the accepted
   generation contradictions) is a counted line in the report.
8. **Small samples say so.** For a proportion over fewer than 100 observations the report shows
   the exact counts and a Wilson 95% interval. The interval describes uncertainty under a
   binomial model for that evaluated population; it is not generalization evidence and never
   upgrades an evidence class.
9. **Reports contain no source or obligation text.** Ids, counts, labels and hashes only.

## 2. Evidence classes

| Class | What it is | What it can support | What it cannot |
|---|---|---|---|
| `REGRESSION` | hand-authored gold, built against the same grammar and lexicon as the system | the component still does what its contract declares on those cases | recall or precision on unseen regulations |
| `MUTATION` | injected faults with a known expected detection | the verifier catches this fault family | catching faults outside the family |
| `PROPERTY` | invariants over seeded random sequences | the invariant held on the sequences tried (seed and count reported) | proof for all inputs |
| `CORPUS_COVERAGE` | the real local corpus, no ground truth | outcome **counts and distributions**: how often the system extracts, abstains, rejects, flags | correctness of any kind; **no precision, recall, accuracy, or "zero errors" claim is made from it** |
| `GENERALIZATION` | independently labelled held-out data by someone other than the system's author | out-of-sample performance | none exists today; reported as `NONE` until one does |
| `PRODUCTION` | measurements from real reviewers and live operation | operational performance | none exists today; reported as `NONE` |

A `PROPERTY` check is an invariant decidable without ground truth, for example "every populated
field equals its cited text". It may run over gold cases, mutated cases or corpus items, and is
reported as "0 violations in N items checked". That wording states self-consistency of the
output, never that the real corpus contains no true errors. A hard correctness gate is
carried by `REGRESSION`, `MUTATION` or `PROPERTY` rows; a `CORPUS_COVERAGE` row beside it
reports only counts.

The report states, at its top and in every layer, which classes it has and which it lacks.

## 3. Report model

```
MetricDefinition(id, layer, name, population_id, numerator_definition,
                 denominator_definition, formula, evidence_class, gate)
MetricResult(definition_id, numerator, denominator, value | None, interval | None,
             status: OK | NOT_MEASURABLE | NO_GOLD | GATE_FAILED,
             gate_passed | None, note)
Population(id, description, source, n, built_by, limitations)
Report(inputs, populations, definitions, results, known_gaps, classes_present,
       classes_absent, limitations)
```

- A `MetricResult` references its `MetricDefinition`; it cannot exist without one. Definitions
  are data in the registry, so a formula is written once and reviewed once.
- `populations.v1.json` registers every population; a result naming an unregistered population,
  or whose `n` disagrees with the registry, is an error.
- `inputs` records what could change a result: code reference, gold file hashes, config
  versions, corpus manifest (local PDFs by file name and sha256). `CORPUS_COVERAGE` results are
  comparable only when the manifest matches, otherwise `NOT_COMPARABLE`.
- Output is deterministic JSON plus a rendered Markdown view; time, if any, is injected.

**Baseline.** A committed `baseline.v1.json` holds the last accepted values with the `inputs`
they were computed from. Any metric change is reported as drift and the runner fails.
- Drift with **unchanged inputs** is a defect (nondeterminism) and cannot be baselined.
- Drift with changed inputs may be baselined only in a commit that names which input changed
  (code, gold, config or corpus) and why, after that change has been reviewed. A baseline
  update is never a way to make an unexplained regression pass; a worsened metric must be
  understood first, and a hard gate cannot be baselined at all.
- For deterministic components the tolerance is exact equality.

## 4. Layers

For each layer: the metric, its numerator and denominator, the population, the class and the
gate. "Source" names the existing evaluator reused; "new" means Phase 12 builds it. The
adapters wrap existing evaluators and do not reimplement their metrics.

### 4.1 Change detection (Phase 2)

No gold set or evaluator exists today; the tests are behavioural. Phase 12 builds a small gold
(about 40 cases from public regulation headers, citation formulas and synthetic variants),
each with a written rationale. It must contain adversarial cases, not only happy paths:
metadata conflict, ambiguous target, malformed target, self-reference, contradictory
relations, duplicate relation, no relation (`NEW`), an event after a repeal (anomaly), and
unsupported or invalid structural input. Not one case per item is required, but the set may
not be a representative-only suite.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| event type accuracy | correct type / gold cases | `REGRESSION` | REPORT_ONLY |
| target resolution accuracy | correctly resolved / gold cases with an expected target | `REGRESSION` | REPORT_ONLY |
| **false resolution rate** | resolved to a wrong target / all cases the system resolved | `REGRESSION` | **HARD: 0** |
| `NEEDS_REVIEW` rate and reason mix | `NEEDS_REVIEW` / all gold cases | `REGRESSION` | REPORT_ONLY |
| ingestion-order invariance, idempotent replay | holding runs / seeded permutations | `PROPERTY` | **HARD: all hold** |
| outcome counts on the real corpus | counts by outcome / corpus documents | `CORPUS_COVERAGE` | none |

Until the gold exists, the correctness metrics report `NO_GOLD`.

### 4.2 Document processing (Phase 3)

The new gold (about 30 snippets, written rationale each) must also include adversarial
structure: a standard article, an amending unit, a quoted Arabic `Pasal` inside a Roman
amendment unit, a mixed body form, a catchword, a Unicode-ellipsis catchword, a page
boundary, missing page text, an unreadable PDF and an incomplete source.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| provenance round-trip violations | articles or units whose text is not at its located source span / all articles and units checked | `PROPERTY` over gold and corpus items | **HARD: 0** (self-consistency only) |
| structure recovery accuracy | correctly recovered units / gold units | `REGRESSION` | REPORT_ONLY |
| noise removal accuracy (catchword, header/footer) | correctly cleaned snippets / gold snippets | `REGRESSION` | REPORT_ONLY |
| explicit failure on unreadable or incomplete input | cases failing explicitly / unreadable or incomplete gold cases | `REGRESSION` | **HARD: all** (never silent) |
| article numbering contiguous and unique | documents satisfying it / corpus documents | `CORPUS_COVERAGE` (a proxy, not accuracy) | none |
| OCR path | synthetic only | not claimed on real scans | `NOT_MEASURABLE` on real scans |

### 4.3 Relevance and sector (Phase 4)

Source: `regulus.relevance.evaluate`, gold 40 cases. Definitions: a *decided* case is one the
system labelled `RELEVANT` or `NOT_RELEVANT`; an *abstained* case is `NEEDS_REVIEW` or
`NOT_ASSESSABLE`; abstentions are not predictions of either class.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| precision of `RELEVANT` | gold-relevant among predicted `RELEVANT` (TP) / predicted `RELEVANT` (TP + FP) | `REGRESSION` | REPORT_ONLY |
| recall of `RELEVANT` | predicted `RELEVANT` among gold-relevant (TP) / gold-relevant cases (TP + FN; an abstained gold-relevant case is a FN) | `REGRESSION` | REPORT_ONLY |
| F1 | harmonic mean of the two above | `REGRESSION` | REPORT_ONLY |
| **decided fraction** and **abstention rate**, printed beside every precision | decided / all cases; abstained / all cases | `REGRESSION` | REPORT_ONLY |
| **false `NOT_RELEVANT`** | gold-relevant predicted `NOT_RELEVANT` / gold-relevant cases | `REGRESSION` | **HARD: 0** |
| sector micro F1, macro F1, per-sector scores | per its own TP, FP, FN over sector-labelled cases (micro pooled; macro mean of per-sector) | `REGRESSION` | REPORT_ONLY |
| decided assessments carry deciding evidence | violations / decided assessments | `PROPERTY` | **HARD: 0** |
| outcome counts on real events | counts by outcome / corpus events | `CORPUS_COVERAGE` | none |

### 4.4 Lineage (Phase 5)

Source: `regulus.lineage.evaluate`, gold 38 operations.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| operation kind accuracy | correct kind / gold operations | `REGRESSION` | REPORT_ONLY |
| locator accuracy | correct locator / operations with an expected locator | `REGRESSION` | REPORT_ONLY |
| target binding accuracy | correct binding / operations with an expected binding | `REGRESSION` | REPORT_ONLY |
| **false resolution rate** | resolved or located wrongly / operations the system resolved | `REGRESSION` | **HARD: 0** |
| expected-unresolved agreement | operations unresolved or ambiguous as the gold expects / operations the gold expects unresolved or ambiguous | `REGRESSION` | REPORT_ONLY |
| outcome counts on the two amending instruments | resolved, unresolved, ambiguous / corpus operations | `CORPUS_COVERAGE` | none |

### 4.5 Obligation extraction (Phase 6)

Source: `regulus.obligations.evaluate`, gold 38 cases. The gold is authored against the
extractor's own grammar; it is regression evidence and is described as such.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| candidate precision | matched candidates (TP) / predicted candidates (TP + FP) | `REGRESSION` | REPORT_ONLY |
| candidate recall | matched candidates (TP) / gold candidates (TP + FN) | `REGRESSION` | REPORT_ONLY |
| candidate F1 | harmonic mean of the two | `REGRESSION` | REPORT_ONLY |
| field precision | correct populated fields / populated fields of matched candidates | `REGRESSION` | REPORT_ONLY |
| field recall | correct populated fields / gold populated fields of matched candidates | `REGRESSION` | REPORT_ONLY |
| `NOT_STATED` and `UNDETERMINED` agreement | fields in the gold's state / fields the gold marks in that state | `REGRESSION` | REPORT_ONLY |
| multiplicity agreement | items correctly counted / gold multi-item fields | `REGRESSION` | REPORT_ONLY |
| **unsupported claims** | populated fields whose value is not the cited text / populated fields checked | `REGRESSION` on gold; `PROPERTY` on corpus items ("0 violations in N") | **HARD: 0** |
| **silent deontic loss** | marker occurrences with neither candidate nor diagnostic / marker occurrences | `REGRESSION` on gold; `PROPERTY` on corpus items | **HARD: 0** |
| candidate, `UNRESOLVED`, `UNEXTRACTED_DEONTIC` counts | counts / corpus regions | `CORPUS_COVERAGE` | none |

### 4.6 Generation (Phase 7)

Source: `regulus.generation.evaluate`.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| **undetected mutations** | accepted mutated outputs / applied mutations | `MUTATION` | **HARD: 0** |
| **unexpected accepted contradictions** | accepted contradictions not listed as known gaps / contradiction cases | `MUTATION` | **HARD: 0** |
| accepted known-gap contradictions, enumerated | accepted known gaps / contradiction cases | `MUTATION` | counted, reported |
| hallucinated-token violations | tokens of accepted outputs absent from the permitted source / tokens of accepted outputs | `PROPERTY` over gold and mutation outputs | **HARD: 0** |
| field accounting violations | populated fields with no traced candidate field / populated fields | `PROPERTY` | **HARD: 0** |
| open-question preservation violations | candidates with an undetermined part lacking its open question / such candidates | `PROPERTY` | **HARD: 0** |
| evidence citation violations | evidence items not matching their source span / evidence items | `PROPERTY` | **HARD: 0** |
| generated, rejected-by-verification counts and reasons | counts / corpus candidates | `CORPUS_COVERAGE` (counts only) | none |

The `PROPERTY` rows are also run on the real-corpus outputs and reported as "0 violations in N
items checked"; the corpus row beside them states counts only and claims nothing about
correctness.

### 4.7 Similarity (Phase 8)

Source: `regulus.similarity.evaluate`, gold 12 queries and 71 pairs. Queries with no gold
match are excluded from the retrieval denominators and counted.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| Recall@3 | queries whose top 3 contain at least one gold match / queries with at least one gold match | `REGRESSION` | REPORT_ONLY |
| Precision@3 | gold matches among returned top-3 matches, pooled over queries / returned top-3 matches, pooled | `REGRESSION` | REPORT_ONLY |
| MRR | sum of reciprocal ranks of the first gold match (0 if absent from the returned list) / queries with at least one gold match; a mean, not a proportion | `REGRESSION` | REPORT_ONLY |
| relationship label accuracy and confusion matrix | correct label / gold pairs | `REGRESSION` | REPORT_ONLY |
| `POSSIBLE_DUPLICATE` precision | predicted duplicates the gold confirms / predicted `POSSIBLE_DUPLICATE` | `REGRESSION` | REPORT_ONLY |
| **false-duplicate rate** | `POSSIBLE_DUPLICATE` where the gold is not a duplicate / gold non-duplicate pairs | `REGRESSION` | **TARGET: 0**, reported |
| ceiling and evidence violations | returned matches violating a cap or lacking evidence / returned matches | `PROPERTY` | **HARD: 0** |
| provider label disagreements | pairs labelled differently by two providers / pairs returned by both | only when two providers were run | else `NOT_MEASURABLE` |
| `POSSIBLE_DUPLICATE` suggestion counts | counts / corpus queries (suggestions, not confirmed duplicates) | `CORPUS_COVERAGE` | none |

### 4.8 Human review workflow (Phase 9)

Only what the authoritative review records contain is measured. A record carries decision,
actor, roles, decision time, open-question resolutions, dispositions, acknowledgements,
divergence and reject reason. It does not carry claim times, failed actions or active-work
duration.

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| outcome mix: approved, rejected (by reason) | tasks per outcome / tasks with a terminal decision | harness runs | REPORT_ONLY |
| edit rate | tasks with at least one `EDIT` / tasks with a terminal decision | harness runs | REPORT_ONLY |
| open-question resolution mix | resolutions per kind / resolutions | harness runs | REPORT_ONLY |
| dangerous-match disposition mix | dispositions per kind / dispositions | harness runs | REPORT_ONLY |
| source acknowledgements | approvals carrying an acknowledgement / approvals on tasks with a source flag | harness runs | REPORT_ONLY |
| four-eyes violations | editors who approved plus approvers who published / approvals and publishes | `PROPERTY` and log scan | **HARD: 0** |
| replay equality violations | logs whose replay differs from stored state / review logs | `PROPERTY` | **HARD: 0** |
| stale and denied actions | none recorded | not recorded by design | `NOT_MEASURABLE` from records; covered only by property tests |
| submit-to-decision **elapsed latency** | decisions with both submission and decision times (others excluded and counted) | harness runs | REPORT_ONLY |
| reviewer time per obligation or per regulation | claim durations and active time are not recorded | none | **`NOT_MEASURABLE`** |

There is no real human review data yet; harness runs use scripted reviewers. These numbers
describe the workflow's behaviour under scripted decisions and are never described as
reviewer performance. Elapsed latency is not effort. The business metric "reviewer time per
obligation" stays `NOT_MEASURABLE` until a separate Phase 9 amendment records claim and active
times and a real reviewer study produces data.

### 4.9 Workflow and notification (Phase 11)

| Metric | Numerator / denominator (population) | Class | Gate |
|---|---|---|---|
| unaccounted items | items neither `DONE`, `DEAD_LETTER` nor pending with a next attempt / run items | `PROPERTY` and harness | **HARD: 0** |
| crash divergence | fault runs whose final logical state differs from the uninterrupted run / seeded fault runs (seeds and count reported) | `PROPERTY` | **HARD: 0** |
| duplicate logical notifications | dedupe keys with more than one logical event / dedupe keys | `PROPERTY` | **HARD: 0** |
| delivery state mix | notifications per state / notifications | harness runs | REPORT_ONLY |
| dead-lettered items with no queued dead-letter notification | such items / dead-lettered items | harness runs | REPORT_ONLY, counted |
| assignment and notification independence violations | runs whose review outcome differs / seeded runs | `PROPERTY` | **HARD: 0** |

The channel, directory and pipeline are fakes; delivery metrics describe the outbox logic, not
any real channel.

### 4.10 End to end

Reported in its own section, separate from the layers, as a **funnel with a separate
denominator at every stage**: events, processed documents, candidates, generated obligations,
verified submissions, reviewable tasks, with abstentions, rejections and dead-letters at each
step. Source: the real local corpus, class `CORPUS_COVERAGE`. It states that no end-to-end
precision or recall is computed, because no end-to-end ground truth exists.

## 5. What the report may and may not say

- Allowed phrasing names the population: "on the 38-case extraction regression set, field
  recall was 31/36 (86%, Wilson 95% 71–94%)".
- Not allowed: "Regulus accuracy", "production ready", an unqualified recall or precision, a
  comparison between layers' numbers, or a corpus coverage rate described as accuracy.
- Every report ends with a fixed limitations block: gold authored by the system's author,
  small samples, a single local corpus, no generalization or production evidence, scripted
  reviewers, fake infrastructure.

## 6. Failure semantics

| Situation | Behaviour |
|---|---|
| denominator 0 | `value = None`, `NOT_MEASURABLE`; never 0, 1 or NaN |
| gold file missing or its hash differs from the registry | `NO_GOLD` or error; never silently skipped |
| a HARD gate fails | the layer is `GATE_FAILED`; the runner exits non-zero; no flag overrides it |
| baseline drift | reported and the runner fails until the baseline is committed with a reason |
| corpus absent | `CORPUS_COVERAGE` sections are `NOT_MEASURABLE`, layer results from gold still run |
| corpus manifest differs | corpus results marked `NOT_COMPARABLE` |
| a component raises during evaluation | recorded as an evaluation error for that layer; other layers still run |

## 7. Module layout

```
src/regulus/evaluation/
├── models.py       MetricResult, Population, Report
├── stats.py        ratio, Wilson interval
├── populations.py  registry load and checks
├── layers/         one adapter per layer, wrapping the existing evaluate modules
├── review.py       log-derived workflow metrics, NOT_MEASURABLE rules
├── funnel.py       end-to-end funnel
├── baseline.py     drift check
├── claims.py       allowed phrasing checks
├── report.py       deterministic JSON and Markdown rendering
└── runner.py       run all layers, exit status
evaluation/populations.v1.json
evaluation/baseline.v1.json
evaluation/change_detection/gold.v1.json      (new)
evaluation/documents/gold.v1.json             (new)
evaluation/reports/                            (committed aggregate output)
tests/evaluation/
```

## 8. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| zero denominator | `None`, `NOT_MEASURABLE`, not 0 or NaN |
| result without a `MetricDefinition` | rejected |
| precision, recall and F1 | computed from their own numerators and denominators, checked against hand-computed confusion counts |
| MRR | numerator is the sum of reciprocal ranks, denominator the queries with a gold match |
| abstained gold-relevant case | counted as a false negative for recall, not as a prediction |
| layer with no gold | `NO_GOLD`, not a pass |
| result without population or evidence class | rejected |
| population `n` disagrees with the registry | error |
| report schema | no overall or cross-layer field exists |
| precision printed without coverage | rejected by the renderer |
| proportion with n under 100 | exact counts and Wilson interval present; interval wording never says generalization |
| a `CORPUS_COVERAGE` row asserting correctness or "zero errors" | rejected by the claim check |
| `PROPERTY` check over corpus items | worded "0 violations in N items checked", not as a correctness claim |
| a HARD gate fails | `GATE_FAILED`, non-zero exit, no override |
| gate values vs earlier contracts | equal to the contract constants; editing one fails a test |
| baseline unchanged | passes |
| metric change with unchanged inputs | defect; fails; cannot be baselined |
| metric change with changed inputs | fails until a baseline commit names the changed input and reason |
| baseline update that lowers a hard-gate metric | refused |
| two runs, same inputs | byte-identical report |
| degrade a component (for example drop a marker from the extractor) | its layer metric or gate fails |
| degrade the verifier | undetected-mutation gate fails |
| seeded property metric | reports seed list and count |
| review latency with a missing timestamp | excluded and counted, not imputed |
| reviewer time per obligation | `NOT_MEASURABLE` |
| stale or denied actions | `NOT_MEASURABLE` from records |
| four-eyes scan over a log with an injected violation | detected |
| replay scan over a tampered log | detected |
| report text scanned | no source or obligation text, no credential, no personal data |
| corpus manifest hash differs | `NOT_COMPARABLE` |
| corpus absent | corpus sections `NOT_MEASURABLE`, others run |
| known-gap contradictions | counted and enumerated in the report |
| provider independence with one provider | `NOT_MEASURABLE` |
| end-to-end section | has no precision or recall field |
| claim phrasing check | "accuracy of Regulus" and unqualified recall rejected |
| a layer's component raises | error recorded for that layer; others complete |
| gold sets for layers 1 and 2 | contain the adversarial cases listed in 4.1 and 4.2, checked by a coverage test |
| real corpus | full report generated; every layer present; classes present and absent stated |

## 9. Gate

Contract frozen after adversarial review, then: layer adapters over the existing evaluators,
the two new gold sets with written rationales, review and workflow metrics from real logs,
the funnel, baseline and drift check, the report and its claim checks, every §8 row, ruff and
strict mypy clean, a full run on the real corpus with the committed report and baseline,
then freeze.

## 10. Decisions to confirm

1. No overall score, ever; the schema has no field for one.
2. Six evidence classes; `GENERALIZATION` and `PRODUCTION` are reported as `NONE` today.
3. Gates are inherited from earlier contracts; Phase 12 adds no new HARD gate except where an
   earlier contract states an invariant without measuring it (for example four-eyes on the log).
4. Layers 1 and 2 get new small gold sets in this phase, adversarial as well as representative; until built they report `NO_GOLD`.
5. Reviewer time per obligation stays `NOT_MEASURABLE`; adding claim and active-time records
   is a separate Phase 9 amendment, not part of this phase.
6. Wilson intervals for proportions under 100 (an interval of the evaluated population, not generalization); exact equality for deterministic baselines; a baseline cannot absorb an unexplained regression or a hard-gate failure.
7. A committed aggregate report and baseline; the corpus stays uncommitted and is identified
   by manifest hashes.

## 11. Implementation notes (deviations and findings, recorded)

1. **Abstention term.** Phase 4's abstention label is `INSUFFICIENT_EVIDENCE`; §4.3 says "abstained"
   and the adapters use that label. Abstentions count as false negatives for recall.
2. **Unsupported-claim denominator** is the number of **citations checked**, not populated fields:
   the Phase 6 evaluator checks every cited span (clause, marker, items and field values).
3. **Retrieval metrics** follow §4.7 exactly (hit-rate recall over queries with a gold match,
   pooled precision, MRR as a mean). They differ from the per-query averages in Phase 8's own
   report, which also divides by all queries; the Phase 8 evaluator was extended only with raw
   counts, its behaviour unchanged.
4. **Additive counts.** The Phase 5, 6, 7 and 8 evaluators gained raw count fields (numerators and
   denominators) so the adapters need not re-derive them; no metric or gate changed.
5. **Gold sizes as built.** Change detection: 31 records and 8 status projections (population
   39). Documents: 23 snippets. Both carry rationales and the adversarial cases §4.1 and §4.2
   require (checked by tests). Two expectations first written for them were wrong about the
   contract (a record without a title fails by design; a misread first marker opens amendment
   mode); the gold was corrected, the system was not changed.
6. **Target binding accuracy** is `NO_GOLD`: the Phase 5 gold records operation parsing only, with
   no expected event-target binding.
7. **Harness rows.** Review and workflow rows come from seeded scripted runs; they are labelled
   `PROPERTY` and described as scripted. The crash-divergence property covers crashes, store
   faults and pipeline outages with a reliable channel; channel failure is measured separately
   (delivery and dead-letter shares).
8. **Finding.** A dead-lettered notification has no operator requeue (items and stages do). It is
   listed as a known gap, not fixed here.
9. **Corpus property rows** (provenance round trip, citation self-consistency, marker accounting,
   generation self-consistency) are `PROPERTY` checks over corpus items, worded "0 violations in
   N items checked"; the corpus coverage rows beside them are counts only.
10. **Report as committed.** `evaluation/reports/report.v1.{json,md}` is generated by
    `python -m regulus.evaluation`; `baseline.v1.json` holds the accepted values with a history of
    reasons; `populations.v1.json` is the population registry.
