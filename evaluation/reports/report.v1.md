# Regulus evaluation report

Layered evaluation. There is no overall score: each row states its population, numerator and denominator.

Evidence classes present: CORPUS_COVERAGE, MUTATION, PROPERTY, REGRESSION.
Evidence classes absent: GENERALIZATION, PRODUCTION (none exist yet).

## Inputs

- `code`: `d5fd041`
- `corpus:lt4a68050e0766d.pdf`: `e194ac16dac56e6a`
- `corpus:lt4a716646b0a25.pdf`: `c9448f51bbb31b51`
- `corpus:lt4aeaae7b927c0.pdf`: `a49679389d423f12`
- `corpus:lt4b1e12ac0efd3.pdf`: `93e57586341f5f48`
- `corpus:lt4b209de5e2d16.pdf`: `356c4bc1f1a1bef7`
- `corpus:lt4b9763a946cfc.pdf`: `228cfbbaa34c6794`
- `corpus:lt4b976b3d87fd8.pdf`: `225b4b0fb2b59b08`
- `corpus:lt4bcfe5ea78f25.pdf`: `830363b15735bbac`
- `corpus:lt4f32463fb11ee.pdf`: `f5d1426f7c1964c4`
- `corpus:lt4f72ee9aba41a.pdf`: `07062a70f85fe52b`
- `corpus:lt57bac6099aa30.pdf`: `f73b267b0c24a4bf`
- `corpus:lt6a9164bf1e96a.pdf`: `4116ed4f70ae4de1`
- `corpus:pp20_1980.pdf`: `0ede31870c3df082`
- `corpus:uu21_1982.pdf`: `b97cc9b4081df417`
- `gold:detection`: `6caf5a421379276b`
- `gold:documents`: `0cf4e080e781af4d`
- `gold:extraction`: `889d8dc87095919a`
- `gold:generation`: `40d6b94b4f1c714f`
- `gold:lineage`: `f502da4db1c209d4`
- `gold:relevance`: `1d28208a8f3758ac`
- `gold:similarity`: `47844fd078a549dc`

## Detection

Population `detection.gold`: hand-authored source records with expected events, plus status projections; n = 39; built by system author, from the Phase 2 contract with a rationale per case. Limits: synthetic records over a three-regulation index; adversarial by design; not real intake traffic.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| outcome accuracy<br>records with the expected outcome (processed, empty, failed) / gold records | 31/31 = 1.000 (100.0%) (Wilson 95% 89-100%) | REGRESSION |  | OK |  |
| event type accuracy<br>records whose multiset of event types equals the gold's / gold records | 31/31 = 1.000 (100.0%) (Wilson 95% 89-100%) | REGRESSION |  | OK |  |
| target resolution accuracy<br>expected target-bound events produced with the right target / expected target-bound events | 10/10 = 1.000 (100.0%) (Wilson 95% 72-100%) | REGRESSION |  | OK |  |
| false resolution rate<br>target-bound events whose type and target the gold does not expect / target-bound events the system produced | 0/10 = 0.000 (0.0%) (Wilson 95% 0-28%) | REGRESSION | HARD (expect 0): met | OK |  |
| review reason agreement<br>expected review events produced with the expected reason / expected review events | 17/17 = 1.000 (100.0%) (Wilson 95% 82-100%) | REGRESSION |  | OK |  |
| NEEDS_REVIEW case rate<br>records with at least one review event / gold records | 15/31 = 0.484 (48.4%) (Wilson 95% 32-65%) | REGRESSION |  | OK |  |
| status projection accuracy<br>projections with the expected status and anomalies / gold projections | 8/8 = 1.000 (100.0%) (Wilson 95% 68-100%) | REGRESSION |  | OK |  |
| ingestion-order violation rate<br>seeded permutations producing a different event set / seeded permutations | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK | seed 7 |
| replay violation rate<br>records that emit events again when their own events are already seen / gold records | 0/31 = 0.000 (0.0%) (Wilson 95% 0-11%) | PROPERTY | HARD (expect 0): met | OK |  |

## Documents

Population `documents.gold`: hand-authored page snippets with expected structure; n = 23; built by system author, from the Phase 3 contract with a rationale per case. Limits: synthetic snippets, adversarial by design; no real scanned pages; OCR is not evaluated.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| document status accuracy<br>snippets with the expected status / gold snippets | 23/23 = 1.000 (100.0%) (Wilson 95% 86-100%) | REGRESSION |  | OK |  |
| structure recovery accuracy<br>expected articles and amendment units recovered with the exact number and text / expected articles and amendment units | 37/37 = 1.000 (100.0%) (Wilson 95% 91-100%) | REGRESSION |  | OK |  |
| noise removal accuracy<br>snippets whose removed noise is absent from every unit / snippets that list noise to remove | 5/5 = 1.000 (100.0%) (Wilson 95% 57-100%) | REGRESSION |  | OK |  |
| diagnostic agreement<br>snippets whose diagnostic codes equal the gold's / snippets with expected codes | 16/16 = 1.000 (100.0%) (Wilson 95% 81-100%) | REGRESSION |  | OK |  |
| explicit failure rate on unreadable or incomplete input<br>failed or partial snippets reported as failed or partial / gold snippets expected to fail or be partial | 3/3 = 1.000 (100.0%) (Wilson 95% 44-100%) | REGRESSION | HARD (expect 1): met | OK |  |
| provenance round-trip violation rate<br>articles or units whose text is not reconstructible from their spans / articles and units checked | 0/37 = 0.000 (0.0%) (Wilson 95% 0-9%) | PROPERTY | HARD (expect 0): met | OK | self-consistency only |

## Relevance

Population `relevance.gold`: hand-authored relevance cases; n = 40; built by system author, against the rule set's own vocabulary. Limits: authored against the same rules; small; not a recall claim on unseen regulations.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| decided fraction<br>cases labelled RELEVANT or NOT_RELEVANT / all gold cases | 18/40 = 0.450 (45.0%) (Wilson 95% 31-60%) | REGRESSION |  | OK |  |
| abstention rate<br>cases labelled INSUFFICIENT_EVIDENCE / all gold cases | 22/40 = 0.550 (55.0%) (Wilson 95% 40-69%) | REGRESSION |  | OK |  |
| precision of RELEVANT (with decided fraction: 18/40 = 0.450 (45.0%) (Wilson 95% 31-60%))<br>gold-relevant among predicted RELEVANT (TP) / predicted RELEVANT (TP + FP) | 14/16 = 0.875 (87.5%) (Wilson 95% 64-97%) | REGRESSION |  | OK |  |
| recall of RELEVANT (with abstention rate: 22/40 = 0.550 (55.0%) (Wilson 95% 40-69%))<br>predicted RELEVANT among gold-relevant (TP) / gold-relevant cases (TP + FN); an abstained gold-relevant case is a FN | 14/18 = 0.778 (77.8%) (Wilson 95% 55-91%) | REGRESSION |  | OK |  |
| F1 of RELEVANT<br>2 * TP / 2 * TP + FP + FN | 28/34 = 0.824 (82.4%) (Wilson 95% 66-92%) | REGRESSION |  | OK |  |
| false NOT_RELEVANT rate<br>gold-relevant cases predicted NOT_RELEVANT / gold-relevant cases | 0/18 = 0.000 (0.0%) (Wilson 95% 0-18%) | REGRESSION | HARD (expect 0): met | OK |  |
| sector micro F1<br>2 * pooled TP / 2 * pooled TP + FP + FN | 70/78 = 0.897 (89.7%) (Wilson 95% 81-95%) | REGRESSION |  | OK |  |
| sector macro F1<br>sum of per-sector F1 / sectors | 5.53262/6 = 0.922 (92.2%) | REGRESSION |  | OK |  |
| decided assessments without deciding evidence violations<br>decided assessments lacking verifiable evidence / decided assessments | 0/18 = 0.000 (0.0%) (Wilson 95% 0-18%) | PROPERTY | HARD (expect 0): met | OK |  |

## Lineage

Population `lineage.gold_ops`: hand-authored amendment operations; n = 38; built by system author, from the declared drafting formulas. Limits: authored against the same grammar; operation parsing only, not target binding.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| operation recognition precision<br>recognized operations the gold also resolves (TP) / recognized operations (TP + FP) | 20/20 = 1.000 (100.0%) (Wilson 95% 84-100%) | REGRESSION |  | OK |  |
| operation recognition recall<br>gold-resolved operations recognized (TP) / gold-resolved operations (TP + FN) | 20/20 = 1.000 (100.0%) (Wilson 95% 84-100%) | REGRESSION |  | OK |  |
| operation kind accuracy<br>correct kind and target level / operations both recognized and gold-resolved | 20/20 = 1.000 (100.0%) (Wilson 95% 84-100%) | REGRESSION |  | OK |  |
| locator accuracy<br>correct locators / operations both recognized and gold-resolved | 20/20 = 1.000 (100.0%) (Wilson 95% 84-100%) | REGRESSION |  | OK |  |
| target binding accuracy<br>correctly bound operations / operations with an expected binding | NO_GOLD | REGRESSION |  | NO_GOLD | the gold records operation parsing only; no expected event-target binding exists |
| false resolution rate<br>operations resolved with a wrong kind, level or locator, or resolved where the gold is unresolved / operations the system resolved | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | REGRESSION | HARD (expect 0): met | OK |  |
| expected-unresolved agreement<br>gold-unresolved operations left unresolved / gold-unresolved operations | 18/18 = 1.000 (100.0%) (Wilson 95% 82-100%) | REGRESSION |  | OK |  |

## Extraction

Population `extraction.gold`: hand-authored extraction cases; n = 38; built by system author, against the extractor's own grammar and lexicon. Limits: authored against the same grammar; regression evidence, not recall on unseen regulations.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| candidate precision<br>predicted candidates matching a gold candidate (TP) / predicted candidates (TP + FP) | 36/36 = 1.000 (100.0%) (Wilson 95% 90-100%) | REGRESSION |  | OK |  |
| candidate recall<br>gold candidates matched (TP) / gold candidates (TP + FN) | 36/38 = 0.947 (94.7%) (Wilson 95% 83-99%) | REGRESSION |  | OK |  |
| candidate F1<br>2 * TP / 2 * TP + FP + FN | 72/74 = 0.973 (97.3%) (Wilson 95% 91-99%) | REGRESSION |  | OK |  |
| field precision<br>populated fields equal to the gold value (TP) / populated fields of matched candidates (TP + FP) | 102/108 = 0.944 (94.4%) | REGRESSION |  | OK |  |
| field recall<br>gold fields recovered (TP) / gold fields of matched candidates (TP + FN) | 102/120 = 0.850 (85.0%) | REGRESSION |  | OK |  |
| NOT_STATED agreement<br>fields reported NOT_STATED where the gold has no value / fields the gold marks without a value | 70/77 = 0.909 (90.9%) (Wilson 95% 82-96%) | REGRESSION |  | OK |  |
| multiplicity agreement<br>cases with the gold's candidate count / gold cases | 36/38 = 0.947 (94.7%) (Wilson 95% 83-99%) | REGRESSION |  | OK |  |
| unsupported claim rate<br>citations whose quoted text is not at their span / citations checked | 0/190 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| silent deontic loss rate<br>marker occurrences with neither candidate nor diagnostic / marker occurrences | 0/38 = 0.000 (0.0%) (Wilson 95% 0-9%) | REGRESSION | HARD (expect 0): met | OK |  |

## Generation

Population `generation.mutations`: applied fault injections; n = 567; built by system author. Limits: covers the listed fault families only.
Population `generation.contradictions`: hand-written contradicting outputs; n = 10; built by system author. Limits: includes enumerated known gaps.
Population `generation.candidates`: candidates produced from the extraction gold; n = 36; built by derived from the extraction gold. Limits: same authorship as the extraction gold.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| undetected mutation rate<br>mutated outputs the verifier accepted / applied mutations | 0/567 = 0.000 (0.0%) | MUTATION | HARD (expect 0): met | OK |  |
| unexpected accepted contradiction rate<br>accepted contradictions not listed as known gaps / contradiction cases | 0/10 = 0.000 (0.0%) (Wilson 95% 0-28%) | MUTATION | HARD (expect 0): met | OK |  |
| accepted known-gap contradiction rate<br>accepted contradictions listed as known gaps / contradiction cases | 2/10 = 0.200 (20.0%) (Wilson 95% 6-51%) | MUTATION |  | OK | gap-deadline-attachment, gap-unfielded-recipients |
| hallucinated token rate<br>tokens of generated text absent from the permitted source / tokens of generated text | 0/565 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| field accounting violation rate<br>trace references that are duplicated or untraced / trace references | 0/272 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| open-question loss rate<br>candidates with an undetermined part and no open question / candidates with an undetermined part | 0/11 = 0.000 (0.0%) (Wilson 95% 0-26%) | PROPERTY | HARD (expect 0): met | OK |  |
| evidence citation violation rate<br>evidence items whose quote is not at their span / evidence items | 0/190 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |

## Similarity

Population `similarity.gold`: labelled query-match pairs; n = 71; built by system author, with a rationale per pair. Limits: synthetic variants derived from generated obligations; 12 queries; includes hard negatives.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| Recall@3<br>queries whose top 3 contain at least one gold match / queries with at least one gold match | 12/12 = 1.000 (100.0%) (Wilson 95% 76-100%) | REGRESSION |  | OK | 0 queries without a gold match excluded |
| Precision@3<br>gold matches among returned top-3 matches, pooled / returned top-3 matches, pooled | 34/36 = 0.944 (94.4%) (Wilson 95% 82-98%) | REGRESSION |  | OK |  |
| MRR<br>sum of reciprocal ranks of the first gold match (0 if absent) / queries with at least one gold match | 12/12 = 1.000 (100.0%) | REGRESSION |  | OK |  |
| relationship label accuracy<br>pairs with the gold label / gold pairs | 71/71 = 1.000 (100.0%) (Wilson 95% 95-100%) | REGRESSION |  | OK |  |
| POSSIBLE_DUPLICATE precision<br>predicted duplicates the gold confirms / predicted POSSIBLE_DUPLICATE | 12/12 = 1.000 (100.0%) (Wilson 95% 76-100%) | REGRESSION |  | OK |  |
| false-duplicate rate<br>POSSIBLE_DUPLICATE returned where the gold is not a duplicate / returned matches that are not gold duplicates | 0/24 = 0.000 (0.0%) (Wilson 95% 0-14%) | REGRESSION | TARGET (expect 0): met | OK |  |
| ceiling and evidence violation rate<br>returned matches breaking a cap or lacking supporting fields / returned matches | 0/36 = 0.000 (0.0%) (Wilson 95% 0-10%) | PROPERTY | HARD (expect 0): met | OK |  |
| provider label disagreement rate<br>pairs labelled differently by the two configurations / pairs returned by both | 0/36 = 0.000 (0.0%) (Wilson 95% 0-10%) | PROPERTY |  | OK | two lexical-embedding configurations (dimension 1024 and 64), not independent model families |

## Review

Population `review.harness_runs`: seeded random action sequences by scripted reviewers; n = 60; built by evaluation harness. Limits: scripted reviewers and a scripted clock; no real human review data exists; descriptive only.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| approved share of decided tasks<br>tasks ending APPROVED or PUBLISHED / tasks with a terminal decision | 18/60 = 0.300 (30.0%) (Wilson 95% 20-43%) | PROPERTY |  | OK | scripted decisions, not reviewer behaviour |
| rejected share of decided tasks<br>tasks ending REJECTED / tasks with a terminal decision | 42/60 = 0.700 (70.0%) (Wilson 95% 57-80%) | PROPERTY |  | OK | reject reasons: {'INCORRECT_EXTRACTION': 14, 'OUT_OF_SCOPE': 14, 'SOURCE_UNCLEAR': 14} |
| share of decided tasks with at least one edit<br>decided tasks with an EDITED record / tasks with a terminal decision | 20/60 = 0.333 (33.3%) (Wilson 95% 23-46%) | PROPERTY |  | OK |  |
| share of question resolutions accepted as is<br>resolutions recorded ACCEPTED_AS_IS / recorded question resolutions | 22/22 = 1.000 (100.0%) (Wilson 95% 85-100%) | PROPERTY |  | OK |  |
| share of dispositions recorded NOT_A_DUPLICATE<br>dispositions recorded NOT_A_DUPLICATE / recorded dispositions | 21/21 = 1.000 (100.0%) (Wilson 95% 85-100%) | PROPERTY |  | OK |  |
| approvals on flagged sources carrying an acknowledgement<br>such approvals with a recorded acknowledgement / approvals on tasks whose snapshot has a source flag | 6/6 = 1.000 (100.0%) (Wilson 95% 61-100%) | PROPERTY |  | OK |  |
| four-eyes violation rate<br>approvals by the last editor plus publishes by the approver / approvals and publishes | 0/32 = 0.000 (0.0%) (Wilson 95% 0-11%) | PROPERTY | HARD (expect 0): met | OK | log scan independent of the engine |
| replay equality violation rate<br>logs whose replay differs from the stored state or whose chain fails / review logs | 0/60 = 0.000 (0.0%) (Wilson 95% 0-6%) | PROPERTY | HARD (expect 0): met | OK |  |
| stale and denied action rate<br>stale or denied actions / submitted actions | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | failed actions leave no record by design; covered by the property tests only |
| submit-to-decision elapsed seconds (mean)<br>sum of elapsed seconds from task creation to the first terminal decision / decided tasks with both times | 50145/60 = 835.750 (83575.0%) | PROPERTY |  | OK | 0 excluded; scripted clock, elapsed time is not reviewer effort |
| reviewer time per obligation<br>active reviewer time / obligations reviewed | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | claim durations and active time are not recorded, and no real reviewer data exists |

## Workflow

Population `workflow.harness_runs`: seeded fault, crash and retry runs over a fake pipeline, channel and directory; n = 25; built by evaluation harness. Limits: fake infrastructure; describes the orchestration and outbox logic, not a real channel or scheduler.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| unaccounted item rate<br>items with no state after a run returned normally / items observed after runs that neither crashed nor lost the store | 0/1524 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| crash divergence rate<br>fault runs whose final logical state differs from the uninterrupted run / seeded fault runs | 0/25 = 0.000 (0.0%) (Wilson 95% 0-13%) | PROPERTY | HARD (expect 0): met | OK | seeds 777000..777024, both stores; crashes, store faults and pipeline outages; reliable channel |
| duplicate logical notification rate<br>notification streams queued more than once / notification streams | 0/110 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| notifications delivered over a flaky channel<br>notifications in state DELIVERED after ten delivery rounds / notifications queued | 48/50 = 0.960 (96.0%) (Wilson 95% 87-99%) | PROPERTY |  | OK | fake channel failing 30% of sends, at most 3 attempts |
| notifications dead-lettered over a flaky channel<br>notifications in state DEAD_LETTER after ten delivery rounds / notifications queued | 2/50 = 0.040 (4.0%) (Wilson 95% 1-13%) | PROPERTY |  | OK | no operator requeue exists for dead-lettered notifications |
| dead-lettered items in runs with no dead-letter notification<br>dead-lettered items in runs that queued no dead-letter notification / dead-lettered items | 0/2 = 0.000 (0.0%) (Wilson 95% 0-66%) | PROPERTY |  | OK | counted, not gated |
| assignment and notification independence violation rate<br>seeded runs whose review outcome differs with assignment and failing notifications / seeded runs | 0/25 = 0.000 (0.0%) (Wilson 95% 0-13%) | PROPERTY | HARD (expect 0): met | OK |  |

## Observability

Population `observability.harness_runs`: seeded faulty runs observed with injected clocks and failing sinks; n = 20; built by evaluation harness. Limits: fake pipeline, channel and sinks; injected clocks; describes the instrumentation, not any real system's speed.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| non-interference violation rate<br>seeded runs whose outputs differ with observability absent, present or failing / seeded runs | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK | three variants per seed, faults and failing sinks |
| lifecycle violation rate<br>runs with an orphan, double-closed or unresolved-parent span after recovery / seeded runs with injected crashes | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK | 8 open spans abandoned by injected crashes and recovered |
| nondeterminism rate<br>runs whose replayed event stream or metric text differs / seeded runs | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| vocabulary and cardinality violation rate<br>events or metric updates rejected as outside the allow-lists / events emitted | 0/1471 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| sensitive-content hit rate<br>emitted artifacts containing a forbidden pattern or the source text / artifacts scanned | 0/60 = 0.000 (0.0%) (Wilson 95% 0-6%) | PROPERTY | HARD (expect 0): met | OK |  |
| cost arithmetic mismatch rate<br>ledger money totals differing from exact integer recomputation / totals checked | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | REGRESSION | HARD (expect 0): met | OK |  |
| unpriced calls summed into money<br>unpriced models contributing to a money total / unpriced calls | 0/72 = 0.000 (0.0%) (Wilson 95% 0-5%) | REGRESSION | HARD (expect 0): met | OK |  |
| unclassified outcome share<br>non-OK outcomes with error class UNCLASSIFIED / non-OK outcomes | 0/253 = 0.000 (0.0%) | PROPERTY |  | OK | counted, not gated |
| drop accounting violation rate<br>runs where emitted differs from delivered + dropped + buffered / seeded runs with failing sinks | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| sink calls inside a wrapped call<br>sink invocations made while a wrapped call was executing / wrapped calls | 0/328 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| mean ENRICH span duration (ms, injected clock)<br>sum of span durations in the injected clock's milliseconds / finished spans | 385/77 = 5.000 (500.0%) | PROPERTY |  | OK | descriptive only: measures that the measurement works, not how fast the system is |
| mean GENERATE span duration (ms, injected clock)<br>sum of span durations in the injected clock's milliseconds / finished spans | 130/26 = 5.000 (500.0%) | PROPERTY |  | OK | descriptive only: measures that the measurement works, not how fast the system is |
| mean PROCESS span duration (ms, injected clock)<br>sum of span durations in the injected clock's milliseconds / finished spans | 160/32 = 5.000 (500.0%) | PROPERTY |  | OK | descriptive only: measures that the measurement works, not how fast the system is |
| mean SUBMIT span duration (ms, injected clock)<br>sum of span durations in the injected clock's milliseconds / finished spans | 265/53 = 5.000 (500.0%) | PROPERTY |  | OK | descriptive only: measures that the measurement works, not how fast the system is |

## Reliability

Population `reliability.harness_runs`: seeded fault, duplicate, timeout and corruption runs over fake infrastructure; n = 20; built by evaluation harness. Limits: in-memory stores and fakes; describes failure semantics, not any real system's availability or durability.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| state-safety violation rate (G1, G2)<br>fault runs with any state-safety violation after a run round or after recovery / seeded fault runs | 0/40 = 0.000 (0.0%) (Wilson 95% 0-9%) | PROPERTY | HARD (expect 0): met | OK | 1 to 3 faults per run, both stores |
| lost item rate (G3)<br>items with no state after a run returned normally / items observed after normal runs | 0/1176 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| duplicate logical effect rate (G4, G7)<br>extra tasks, notifications or decisions after re-delivery / re-delivered inputs | 0/120 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| undetected corruption rate (G5)<br>injected corruptions neither detected by verification nor refused by a guarded write / injected corruptions | 0/125 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK | modification, deletion, reordering, truncation, splicing on ledger streams and review logs |
| writes accepted on corrupted streams (G5)<br>guarded writes accepted on a corrupted stream or log / guarded writes attempted on corrupted streams | 0/125 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| recovery divergence rate (G6)<br>fault runs whose final logical state differs from the uninterrupted run once faults are removed / seeded fault runs | 0/40 = 0.000 (0.0%) (Wilson 95% 0-9%) | PROPERTY | HARD (expect 0): met | OK |  |
| unbounded or silent retry rate (G8)<br>runs exceeding the attempt bound or retrying without a next attempt / seeded fault runs | 0/40 = 0.000 (0.0%) (Wilson 95% 0-9%) | PROPERTY | HARD (expect 0): met | OK |  |
| weaker-than-shown snapshot rate (G9)<br>tasks from a partial or issue-bearing document built without the incomplete flag / tasks from partial or issue-bearing documents | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | REGRESSION | HARD (expect 0): met | OK |  |
| second effects after a timeout before the effect (G10)<br>second effects / timeout-before-effect cases (channel, submission, review) | 0/60 = 0.000 (0.0%) (Wilson 95% 0-6%) | PROPERTY | HARD (expect 0): met | OK |  |
| second effects after a timeout after the effect (G10)<br>second effects / timeout-after-effect cases (channel, submission, review) | 0/60 = 0.000 (0.0%) (Wilson 95% 0-6%) | PROPERTY | HARD (expect 0): met | OK |  |
| failure matrix coverage<br>matrix rows with at least one existing claiming test / matrix rows | 23/23 = 1.000 (100.0%) (Wilson 95% 86-100%) | REGRESSION | HARD (expect 1): met | OK |  |
| failure matrix integrity violation rate<br>matrix defects (unknown fault, bad guarantee id, missing test, unknown claim) / matrix rows | 0/23 = 0.000 (0.0%) (Wilson 95% 0-14%) | REGRESSION | HARD (expect 0): met | OK |  |
| fault-wrapper transparency violation rate<br>runs whose results differ with the wrappers present and no fault planned / seeded runs | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |

## Governance

Population `governance.harness_runs`: seeded governance runs over the reference stores and the governed review app; n = 20; built by evaluation harness. Limits: reference stores and fakes; demonstrates controls, makes no compliance claim.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| unclassified field rate<br>stored fields without a classification / stored fields | 0/236 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| stale inventory entry rate<br>entries naming a missing field or a model that is not stored / inventory entries | 0/37 = 0.000 (0.0%) (Wilson 95% 0-9%) | REGRESSION | HARD (expect 0): met | OK |  |
| access mismatch rate<br>role, operation and resource-fact combinations where an enforcing component disagrees with the matrix or resource rules / combinations checked | 0/2397 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | authorize, the workflow operator functions, the Phase 9 authorizer and the governed app; BASELINE_UPDATE is enforced by repository review, not code |
| unlisted operations allowed<br>unlisted operations that were allowed / unlisted operations tried | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | PROPERTY | HARD (expect 0): met | OK |  |
| separation property violation rate<br>violated separation properties / separation properties | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| audit accounting violation rate<br>runs where attempted differs from recorded plus gap, a record is missing or duplicated, or the chain fails / seeded request runs | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK | 153 audit gaps injected and counted |
| restricted resources served with the audit failing<br>responses that served a restricted resource / requests with the audit sink failing | 0/200 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| content in audit artifacts<br>audit artifacts containing a forbidden pattern or text / audit artifacts scanned | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| unsafe purge rate<br>purges applied to unexpired, non-terminal or held streams / purge attempts of those kinds | 0/60 = 0.000 (0.0%) (Wilson 95% 0-6%) | PROPERTY | HARD (expect 0): met | OK |  |
| deletions without a purge intent<br>deleted streams with no PURGE_INTENT / deleted streams | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| contradictory purge evidence after a crash<br>crash points where the purge log and the store disagree after recovery / crash points tried | 0/80 = 0.000 (0.0%) (Wilson 95% 0-5%) | PROPERTY | HARD (expect 0): met | OK | before the intent, after the intent, after the delete, after applied |
| identity links surviving erasure<br>resolvable links after erase_identity / erasures | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK | opaque ids remain in historical chains by design and are not claimed anonymous |
| undetected corruption in chained logs<br>injected corruptions verify_all did not report / injected corruptions (access audit, purge log, workflow stream with a tip reference) | 0/300 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| forbidden free text stored<br>rejected-class inputs found stored / rejected-class inputs submitted | 0/100 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| free-text findings in stored records<br>scan findings in stored review records / review records scanned | 0/53 = 0.000 (0.0%) (Wilson 95% 0-7%) | PROPERTY |  | OK | counted by record type, never by value |
| audit gaps on public resources<br>public requests served with an audit gap / public requests with the sink failing | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | no public resource is served through the governed app; the stylesheet is not a review page |

## Deployment

Population `deployment.reference_runs`: seeded reference deployments over temporary state directories; n = 10; built by evaluation harness. Limits: one host, in-memory stores with snapshot persistence, fault injection in process; no availability, capacity or production evidence.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| runtime data files missing from the package<br>data files without a package-data pattern / data files in the tree | 0/9 = 0.000 (0.0%) (Wilson 95% 0-30%) | REGRESSION | HARD (expect 0): met | OK | matched against pyproject package-data; the wheel build is tested separately |
| runtime dependencies missing or mismatched in the lock<br>closure packages missing, extra or at another version / runtime closure packages | 0/13 = 0.000 (0.0%) (Wilson 95% 0-23%) | REGRESSION | HARD (expect 0): met | OK |  |
| invalid configurations accepted<br>accepted / invalid configurations tried | 0/24 = 0.000 (0.0%) (Wilson 95% 0-14%) | PROPERTY | HARD (expect 0): met | OK |  |
| secrets found in outputs, logs, state or errors<br>artifacts containing the secret / artifacts scanned | 0/33 = 0.000 (0.0%) (Wilson 95% 0-10%) | PROPERTY | HARD (expect 0): met | OK |  |
| review routes served without the governed app<br>probes without exactly one access-audit record (or a fail-closed 503) / routes probed | 0/30 = 0.000 (0.0%) (Wilson 95% 0-11%) | PROPERTY | HARD (expect 0): met | OK |  |
| restart divergence<br>restores whose verified content differs from the snapshot / restore cycles | 0/20 = 0.000 (0.0%) (Wilson 95% 0-16%) | PROPERTY | HARD (expect 0): met | OK |  |
| corrupted snapshots accepted at startup<br>accepted / injected corruptions | 0/17 = 0.000 (0.0%) (Wilson 95% 0-18%) | PROPERTY | HARD (expect 0): met | OK |  |
| non-atomic snapshot outcomes<br>crash points leaving a mixed or unverifiable state or a marker naming an incomplete generation / crash points tried | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | PROPERTY | HARD (expect 0): met | OK | controlled in-process fault injection; not power loss |
| misclassified startup state<br>recoverable states refused, or corruption recovered or accepted / classified cases | 0/6 = 0.000 (0.0%) (Wilson 95% 0-39%) | PROPERTY | HARD (expect 0): met | OK |  |
| untruthful readiness<br>injected failures not reflected or not recovered / injected failures | 0/8 = 0.000 (0.0%) (Wilson 95% 0-32%) | PROPERTY | HARD (expect 0): met | OK |  |
| non-content-free probe bodies<br>bodies with content, a secret or a configuration value / bodies scanned | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | PROPERTY | HARD (expect 0): met | OK |  |
| non-deterministic seeded runs<br>differing state hashes or verify reports / paired seed runs | 0/10 = 0.000 (0.0%) (Wilson 95% 0-28%) | PROPERTY | HARD (expect 0): met | OK |  |
| runbook commands that fail or drift<br>failing steps / runbook steps executed | 0/44 = 0.000 (0.0%) (Wilson 95% 0-8%) | REGRESSION | HARD (expect 0): met | OK |  |
| container build and probe<br>built and healthy / attempts | NOT_MEASURABLE | REGRESSION |  | NOT_MEASURABLE | the container client is present but no daemon is reachable |

## Reference

Population `reference.synthetic_standin`: deterministic synthetic stand-in with the reference schema; n = 9; built by evaluation harness. Limits: synthetic rows built to exercise every reconciliation kind; says nothing about the expert reference.
Population `reference_real.regulations`: the six expert-reference regulations (local, uncommitted); n = 6; built by project expert. Limits: expert reference, not held out, not generalization evidence; absent on machines without the local files.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| instrument failures on the stand-in<br>failed oracle, null and mutation checks / regulations times instrument checks | 0/24 = 0.000 (0.0%) (Wilson 95% 0-14%) | PROPERTY | HARD (expect 0): met | OK |  |
| non-deterministic corpus builds<br>builds from shuffled rows that differ / shuffled builds | 0/10 = 0.000 (0.0%) (Wilson 95% 0-28%) | PROPERTY | HARD (expect 0): met | OK |  |
| split structure violations<br>violated structural rules / structural rules | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | REGRESSION | HARD (expect 0): met | OK |  |
| instrument failures on the reference<br>failed oracle, null and mutation checks / regulations times instrument checks | 0/48 = 0.000 (0.0%) (Wilson 95% 0-7%) | PROPERTY | HARD (expect 0): met | OK |  |
| split violations against the reference<br>violated split rules / split rules checked | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | REGRESSION | HARD (expect 0): met | OK |  |
| committed artifacts containing expert content<br>files with expert-authored text / text files scanned | 0/323 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | public statute wording is excluded; 6 of 6 source PDFs available |
| reference files tracked by git<br>tracked files under reference/ / files under reference/ | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | PROPERTY | HARD (expect 0): met | OK |  |
| rows with a sector outside the vocabulary<br>unknown-sector rows / rows read | 0/3491 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| rows with an unparseable article reference<br>excluded rows / rows read | 0/3491 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| regulations whose derived count differs from the declared count<br>regulations with a count discrepancy / regulations | 1/6 = 0.167 (16.7%) (Wilson 95% 3-56%) | CORPUS_COVERAGE |  | OK | reported, never forced; the pinned expectation is five matched and one over by one |
| obligation type accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| sanction category accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| appendix-derived obligation accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| reference pointer accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |

## Ingestion

Population `ingestion.synthetic_documents`: generated documents exercising identity, registry, normalization and failure; n = 12; built by evaluation harness. Limits: synthetic text pages through a text reader; PDF byte parsing is covered by the unit tests, not here.
Population `ingestion_real.benchmark`: the six expert-reference regulations, ingested from the local PDFs; n = 6; built by project expert, system ingestion. Limits: article-number recovery only; the reference article text is not a source copy; not generalization evidence; absent without the local files.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| identity errors<br>wrong registry outcome / registry scenarios | 0/8 = 0.000 (0.0%) (Wilson 95% 0-32%) | PROPERTY | HARD (expect 0): met | OK |  |
| processing-key instability<br>keys equal for different inputs or different for equal inputs / key scenarios | 0/4 = 0.000 (0.0%) (Wilson 95% 0-49%) | PROPERTY | HARD (expect 0): met | OK |  |
| non-deterministic ingestion<br>documents with differing results on repeat / documents repeated | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | PROPERTY | HARD (expect 0): met | OK |  |
| divergence from Phase 3 with normalization off<br>documents whose result differs from the Phase 3 output / documents compared | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | REGRESSION | HARD (expect 0): met | OK |  |
| unreadable inputs reported as ingested<br>such inputs / unreadable inputs tried | 0/4 = 0.000 (0.0%) (Wilson 95% 0-49%) | PROPERTY | HARD (expect 0): met | OK |  |
| normalizations violating a condition<br>normalizations failing re-verification or missing / normalizations expected | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | PROPERTY | HARD (expect 0): met | OK |  |
| false normalizations<br>negative cases that were normalized / negative cases tried | 0/6 = 0.000 (0.0%) (Wilson 95% 0-39%) | PROPERTY | HARD (expect 0): met | OK |  |
| reference articles recovered, lt4b1e12ac<br>reference articles present in the result / reference articles of this regulation | 64/64 = 1.000 (100.0%) (Wilson 95% 94-100%) | CORPUS_COVERAGE |  | OK |  |
| reference articles recovered, lt4b209de5<br>reference articles present in the result / reference articles of this regulation | 15/15 = 1.000 (100.0%) (Wilson 95% 80-100%) | CORPUS_COVERAGE |  | OK |  |
| reference articles recovered, lt4f32463f<br>reference articles present in the result / reference articles of this regulation | 27/27 = 1.000 (100.0%) (Wilson 95% 88-100%) | CORPUS_COVERAGE |  | OK |  |
| reference articles recovered, lt4f72ee9a<br>reference articles present in the result / reference articles of this regulation | 7/7 = 1.000 (100.0%) (Wilson 95% 65-100%) | CORPUS_COVERAGE |  | OK |  |
| reference articles recovered, lt57bac609<br>reference articles present in the result / reference articles of this regulation | 3/3 = 1.000 (100.0%) (Wilson 95% 44-100%) | CORPUS_COVERAGE |  | OK |  |
| reference articles recovered, lt6a9164bf<br>reference articles present in the result / reference articles of this regulation | 203/203 = 1.000 (100.0%) | CORPUS_COVERAGE |  | OK |  |
| reference articles not recovered<br>reference articles absent from the result / reference articles | 0/319 = 0.000 (0.0%) | REGRESSION | TARGET (expect 0): met | OK | pooled; per-regulation rows are listed beside it |
| silent article loss<br>absent reference articles with no ARTICLE_GAP or failure issue / reference articles | 0/319 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| benchmark documents with an unresolved ARTICLE_GAP<br>such documents / benchmark documents | 0/6 = 0.000 (0.0%) (Wilson 95% 0-39%) | REGRESSION | TARGET (expect 0): met | OK |  |
| reference text agreement (not an oracle)<br>reference texts with at least 95 percent token containment in the extracted article / reference texts | 332/3352 = 0.099 (9.9%) | CORPUS_COVERAGE |  | OK | the reference text is not a verbatim source copy; reported, never an oracle |
| non-benchmark PDFs ingested without failure<br>PDFs ingested / non-benchmark PDFs | 8/8 = 1.000 (100.0%) (Wilson 95% 68-100%) | CORPUS_COVERAGE |  | OK | robustness only; no quality claim |

## Extraction_units

Population `extraction_units.synthetic_documents`: generated documents exercising coverage, signals, hints, graph, normalization and failure; n = 7; built by evaluation harness. Limits: synthetic text pages through a text reader; says nothing about the expert reference or obligation quality.
Population `extraction_units_real.regulations`: the six expert-reference regulations, packaged from the local PDFs; n = 6; built by project expert, system ingestion. Limits: structural coverage and exploratory signal association only; the signal lists were chosen while viewing the reference, so these figures are not held-out evidence and say nothing about obligation quality; absent without the local files.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| silent unit drop<br>indexed articles without a unit / indexed articles | 0/34 = 0.000 (0.0%) (Wilson 95% 0-10%) | PROPERTY | HARD (expect 0): met | OK |  |
| unit count differs from articles plus amendment units<br>packages violating / packages | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | PROPERTY | HARD (expect 0): met | OK |  |
| units whose provenance does not reconstruct the Phase 3 text<br>such units / units | 0/34 = 0.000 (0.0%) (Wilson 95% 0-10%) | PROPERTY | HARD (expect 0): met | OK |  |
| signals whose offsets do not select their term<br>such signals / signals | 0/82 = 0.000 (0.0%) (Wilson 95% 0-4%) | PROPERTY | HARD (expect 0): met | OK |  |
| heading normalizations missing from the units<br>normalized articles without the flag / normalized articles | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | PROPERTY | HARD (expect 0): met | OK |  |
| hints differing from a direct Phase 6 run<br>units whose hint differs / article units | 0/34 = 0.000 (0.0%) (Wilson 95% 0-10%) | REGRESSION | HARD (expect 0): met | OK |  |
| non-deterministic packages<br>repeat builds with differing bytes / repeat builds | 0/14 = 0.000 (0.0%) (Wilson 95% 0-22%) | PROPERTY | HARD (expect 0): met | OK |  |
| cross-reference edges or unresolved references violating the contract<br>mismatches against the planted references / planted mentions | 0/9 = 0.000 (0.0%) (Wilson 95% 0-30%) | PROPERTY | HARD (expect 0): met | OK |  |
| model, network, database or reference imports<br>detected imports / modules scanned | 0/6 = 0.000 (0.0%) (Wilson 95% 0-39%) | PROPERTY | HARD (expect 0): met | OK |  |
| silent unit drop on the real documents<br>indexed articles without a unit / indexed articles | 0/620 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| provenance loss on the real documents<br>such units / units | 0/620 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| signal span errors on the real documents<br>such signals / signals | 0/3619 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| hints differing from a direct Phase 6 run on the real documents<br>units whose hint differs / article units | 0/620 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| mapped reference articles without a unit<br>mapped reference articles lacking a unit / mapped reference articles | 0/319 = 0.000 (0.0%) | REGRESSION | HARD (expect 0): met | OK |  |
| reference articles carrying a Phase 6 candidate, pooled<br>mapped reference articles with a candidate / mapped reference articles | 135/319 = 0.423 (42.3%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, pooled<br>obligations whose articles form one connected group / obligations spanning two or more articles | 33/216 = 0.153 (15.3%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 137/319 = 0.429 (42.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, pooled<br>articles carrying the signal / articles | 240/620 = 0.387 (38.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 2/319 = 0.006 (0.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, pooled<br>articles carrying the signal / articles | 11/620 = 0.018 (1.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 139/319 = 0.436 (43.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, pooled<br>articles carrying the signal / articles | 211/620 = 0.340 (34.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 16/319 = 0.050 (5.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, pooled<br>articles carrying the signal / articles | 29/620 = 0.047 (4.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 17/319 = 0.053 (5.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, pooled<br>articles carrying the signal / articles | 42/620 = 0.068 (6.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 171/319 = 0.536 (53.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, pooled<br>articles carrying the signal / articles | 306/620 = 0.494 (49.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 176/319 = 0.552 (55.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, pooled<br>articles carrying the signal / articles | 339/620 = 0.547 (54.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 128/319 = 0.401 (40.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, pooled<br>articles carrying the signal / articles | 220/620 = 0.355 (35.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 28/319 = 0.088 (8.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, pooled<br>articles carrying the signal / articles | 77/620 = 0.124 (12.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 9/319 = 0.028 (2.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, pooled<br>articles carrying the signal / articles | 21/620 = 0.034 (3.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 170/319 = 0.533 (53.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, pooled<br>articles carrying the signal / articles | 304/620 = 0.490 (49.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 1/319 = 0.003 (0.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, pooled<br>articles carrying the signal / articles | 6/620 = 0.010 (1.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 160/319 = 0.502 (50.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, pooled<br>articles carrying the signal / articles | 298/620 = 0.481 (48.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, pooled<br>reference-linked articles carrying the signal / reference-linked articles | 16/319 = 0.050 (5.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, pooled<br>articles carrying the signal / articles | 41/620 = 0.066 (6.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, dev<br>mapped reference articles with a candidate / mapped reference articles | 101/213 = 0.474 (47.4%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, dev<br>obligations whose articles form one connected group / obligations spanning two or more articles | 2/149 = 0.013 (1.3%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 101/213 = 0.474 (47.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, dev<br>articles carrying the signal / articles | 161/339 = 0.475 (47.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 2/213 = 0.009 (0.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, dev<br>articles carrying the signal / articles | 9/339 = 0.027 (2.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 100/213 = 0.469 (46.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, dev<br>articles carrying the signal / articles | 136/339 = 0.401 (40.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 12/213 = 0.056 (5.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, dev<br>articles carrying the signal / articles | 17/339 = 0.050 (5.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 15/213 = 0.070 (7.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, dev<br>articles carrying the signal / articles | 30/339 = 0.088 (8.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 128/213 = 0.601 (60.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, dev<br>articles carrying the signal / articles | 191/339 = 0.563 (56.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 113/213 = 0.531 (53.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, dev<br>articles carrying the signal / articles | 182/339 = 0.537 (53.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 97/213 = 0.455 (45.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, dev<br>articles carrying the signal / articles | 140/339 = 0.413 (41.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 18/213 = 0.085 (8.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, dev<br>articles carrying the signal / articles | 45/339 = 0.133 (13.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 5/213 = 0.023 (2.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, dev<br>articles carrying the signal / articles | 10/339 = 0.029 (2.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 112/213 = 0.526 (52.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, dev<br>articles carrying the signal / articles | 173/339 = 0.510 (51.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 1/213 = 0.005 (0.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, dev<br>articles carrying the signal / articles | 3/339 = 0.009 (0.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 107/213 = 0.502 (50.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, dev<br>articles carrying the signal / articles | 164/339 = 0.484 (48.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, dev<br>reference-linked articles carrying the signal / reference-linked articles | 14/213 = 0.066 (6.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, dev<br>articles carrying the signal / articles | 15/339 = 0.044 (4.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, test<br>mapped reference articles with a candidate / mapped reference articles | 34/106 = 0.321 (32.1%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, test<br>obligations whose articles form one connected group / obligations spanning two or more articles | 31/67 = 0.463 (46.3%) (Wilson 95% 35-58%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 36/106 = 0.340 (34.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, test<br>articles carrying the signal / articles | 79/281 = 0.281 (28.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 0/106 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, test<br>articles carrying the signal / articles | 2/281 = 0.007 (0.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 39/106 = 0.368 (36.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, test<br>articles carrying the signal / articles | 75/281 = 0.267 (26.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 4/106 = 0.038 (3.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, test<br>articles carrying the signal / articles | 12/281 = 0.043 (4.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 2/106 = 0.019 (1.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, test<br>articles carrying the signal / articles | 12/281 = 0.043 (4.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 43/106 = 0.406 (40.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, test<br>articles carrying the signal / articles | 115/281 = 0.409 (40.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 63/106 = 0.594 (59.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, test<br>articles carrying the signal / articles | 157/281 = 0.559 (55.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 31/106 = 0.292 (29.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, test<br>articles carrying the signal / articles | 80/281 = 0.285 (28.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 10/106 = 0.094 (9.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, test<br>articles carrying the signal / articles | 32/281 = 0.114 (11.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 4/106 = 0.038 (3.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, test<br>articles carrying the signal / articles | 11/281 = 0.039 (3.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 58/106 = 0.547 (54.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, test<br>articles carrying the signal / articles | 131/281 = 0.466 (46.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 0/106 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, test<br>articles carrying the signal / articles | 3/281 = 0.011 (1.1%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 53/106 = 0.500 (50.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, test<br>articles carrying the signal / articles | 134/281 = 0.477 (47.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, test<br>reference-linked articles carrying the signal / reference-linked articles | 2/106 = 0.019 (1.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, test<br>articles carrying the signal / articles | 26/281 = 0.093 (9.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt4b1e12ac (TEST)<br>mapped reference articles with a candidate / mapped reference articles | 15/64 = 0.234 (23.4%) (Wilson 95% 15-35%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt4b1e12ac (TEST)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 2/13 = 0.154 (15.4%) (Wilson 95% 4-42%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 17/64 = 0.266 (26.6%) (Wilson 95% 17-38%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 47/168 = 0.280 (28.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/64 = 0.000 (0.0%) (Wilson 95% 0-6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 0/168 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 23/64 = 0.359 (35.9%) (Wilson 95% 25-48%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 43/168 = 0.256 (25.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/64 = 0.000 (0.0%) (Wilson 95% 0-6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 0/168 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/64 = 0.000 (0.0%) (Wilson 95% 0-6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 8/168 = 0.048 (4.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 21/64 = 0.328 (32.8%) (Wilson 95% 23-45%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 66/168 = 0.393 (39.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 40/64 = 0.625 (62.5%) (Wilson 95% 50-73%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 95/168 = 0.565 (56.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 15/64 = 0.234 (23.4%) (Wilson 95% 15-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 44/168 = 0.262 (26.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 5/64 = 0.078 (7.8%) (Wilson 95% 3-17%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 20/168 = 0.119 (11.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 4/64 = 0.062 (6.2%) (Wilson 95% 2-15%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 10/168 = 0.060 (6.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 37/64 = 0.578 (57.8%) (Wilson 95% 46-69%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 89/168 = 0.530 (53.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/64 = 0.000 (0.0%) (Wilson 95% 0-6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 1/168 = 0.006 (0.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 32/64 = 0.500 (50.0%) (Wilson 95% 38-62%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 80/168 = 0.476 (47.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt4b1e12ac (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 2/64 = 0.031 (3.1%) (Wilson 95% 1-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt4b1e12ac (TEST)<br>articles carrying the signal / articles | 20/168 = 0.119 (11.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt4b209de5 (TEST)<br>mapped reference articles with a candidate / mapped reference articles | 5/15 = 0.333 (33.3%) (Wilson 95% 15-58%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt4b209de5 (TEST)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 17/31 = 0.548 (54.8%) (Wilson 95% 38-71%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 5/15 = 0.333 (33.3%) (Wilson 95% 15-58%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 14/58 = 0.241 (24.1%) (Wilson 95% 15-37%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/15 = 0.000 (0.0%) (Wilson 95% 0-20%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 2/58 = 0.034 (3.4%) (Wilson 95% 1-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 4/15 = 0.267 (26.7%) (Wilson 95% 11-52%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 14/58 = 0.241 (24.1%) (Wilson 95% 15-37%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 2/15 = 0.133 (13.3%) (Wilson 95% 4-38%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 10/58 = 0.172 (17.2%) (Wilson 95% 10-29%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/15 = 0.000 (0.0%) (Wilson 95% 0-20%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 2/58 = 0.034 (3.4%) (Wilson 95% 1-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 6/15 = 0.400 (40.0%) (Wilson 95% 20-64%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 25/58 = 0.431 (43.1%) (Wilson 95% 31-56%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 7/15 = 0.467 (46.7%) (Wilson 95% 25-70%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 31/58 = 0.534 (53.4%) (Wilson 95% 41-66%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 4/15 = 0.267 (26.7%) (Wilson 95% 11-52%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 16/58 = 0.276 (27.6%) (Wilson 95% 18-40%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 1/15 = 0.067 (6.7%) (Wilson 95% 1-30%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 8/58 = 0.138 (13.8%) (Wilson 95% 7-25%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/15 = 0.000 (0.0%) (Wilson 95% 0-20%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 0/58 = 0.000 (0.0%) (Wilson 95% 0-6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 9/15 = 0.600 (60.0%) (Wilson 95% 36-80%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 23/58 = 0.397 (39.7%) (Wilson 95% 28-53%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/15 = 0.000 (0.0%) (Wilson 95% 0-20%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 1/58 = 0.017 (1.7%) (Wilson 95% 0-9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 10/15 = 0.667 (66.7%) (Wilson 95% 42-85%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 32/58 = 0.552 (55.2%) (Wilson 95% 42-67%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt4b209de5 (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/15 = 0.000 (0.0%) (Wilson 95% 0-20%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt4b209de5 (TEST)<br>articles carrying the signal / articles | 3/58 = 0.052 (5.2%) (Wilson 95% 2-14%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt4f32463f (TEST)<br>mapped reference articles with a candidate / mapped reference articles | 14/27 = 0.519 (51.9%) (Wilson 95% 34-69%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt4f32463f (TEST)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 12/23 = 0.522 (52.2%) (Wilson 95% 33-71%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 14/27 = 0.519 (51.9%) (Wilson 95% 34-69%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 18/55 = 0.327 (32.7%) (Wilson 95% 22-46%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/27 = 0.000 (0.0%) (Wilson 95% 0-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 0/55 = 0.000 (0.0%) (Wilson 95% 0-7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 12/27 = 0.444 (44.4%) (Wilson 95% 28-63%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 18/55 = 0.327 (32.7%) (Wilson 95% 22-46%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 2/27 = 0.074 (7.4%) (Wilson 95% 2-23%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 2/55 = 0.036 (3.6%) (Wilson 95% 1-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 2/27 = 0.074 (7.4%) (Wilson 95% 2-23%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 2/55 = 0.036 (3.6%) (Wilson 95% 1-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 16/27 = 0.593 (59.3%) (Wilson 95% 41-75%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 24/55 = 0.436 (43.6%) (Wilson 95% 31-57%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 16/27 = 0.593 (59.3%) (Wilson 95% 41-75%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 31/55 = 0.564 (56.4%) (Wilson 95% 43-69%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 12/27 = 0.444 (44.4%) (Wilson 95% 28-63%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 20/55 = 0.364 (36.4%) (Wilson 95% 25-50%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 4/27 = 0.148 (14.8%) (Wilson 95% 6-32%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 4/55 = 0.073 (7.3%) (Wilson 95% 3-17%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/27 = 0.000 (0.0%) (Wilson 95% 0-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 1/55 = 0.018 (1.8%) (Wilson 95% 0-10%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 12/27 = 0.444 (44.4%) (Wilson 95% 28-63%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 19/55 = 0.345 (34.5%) (Wilson 95% 23-48%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/27 = 0.000 (0.0%) (Wilson 95% 0-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 1/55 = 0.018 (1.8%) (Wilson 95% 0-10%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 11/27 = 0.407 (40.7%) (Wilson 95% 25-59%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 22/55 = 0.400 (40.0%) (Wilson 95% 28-53%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt4f32463f (TEST)<br>reference-linked articles carrying the signal / reference-linked articles | 0/27 = 0.000 (0.0%) (Wilson 95% 0-12%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt4f32463f (TEST)<br>articles carrying the signal / articles | 3/55 = 0.055 (5.5%) (Wilson 95% 2-15%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt4f72ee9a (DEV)<br>mapped reference articles with a candidate / mapped reference articles | 4/7 = 0.571 (57.1%) (Wilson 95% 25-84%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt4f72ee9a (DEV)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 0/1 = 0.000 (0.0%) (Wilson 95% 0-79%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 4/7 = 0.571 (57.1%) (Wilson 95% 25-84%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 14/49 = 0.286 (28.6%) (Wilson 95% 18-42%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 1/49 = 0.020 (2.0%) (Wilson 95% 0-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 13/49 = 0.265 (26.5%) (Wilson 95% 16-40%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 1/49 = 0.020 (2.0%) (Wilson 95% 0-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 1/49 = 0.020 (2.0%) (Wilson 95% 0-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 3/7 = 0.429 (42.9%) (Wilson 95% 16-75%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 9/49 = 0.184 (18.4%) (Wilson 95% 10-31%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 4/7 = 0.571 (57.1%) (Wilson 95% 25-84%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 23/49 = 0.469 (46.9%) (Wilson 95% 34-61%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/7 = 0.143 (14.3%) (Wilson 95% 3-51%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 13/49 = 0.265 (26.5%) (Wilson 95% 16-40%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 4/49 = 0.082 (8.2%) (Wilson 95% 3-19%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 1/49 = 0.020 (2.0%) (Wilson 95% 0-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 3/7 = 0.429 (42.9%) (Wilson 95% 16-75%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 19/49 = 0.388 (38.8%) (Wilson 95% 26-53%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 1/49 = 0.020 (2.0%) (Wilson 95% 0-11%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/7 = 0.286 (28.6%) (Wilson 95% 8-64%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 27/49 = 0.551 (55.1%) (Wilson 95% 41-68%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt4f72ee9a (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/7 = 0.000 (0.0%) (Wilson 95% 0-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt4f72ee9a (DEV)<br>articles carrying the signal / articles | 0/49 = 0.000 (0.0%) (Wilson 95% 0-7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt57bac609 (DEV)<br>mapped reference articles with a candidate / mapped reference articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt57bac609 (DEV)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 1/1 = 1.000 (100.0%) (Wilson 95% 21-100%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/3 = 0.333 (33.3%) (Wilson 95% 6-79%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 48/65 = 0.738 (73.8%) (Wilson 95% 62-83%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/3 = 0.333 (33.3%) (Wilson 95% 6-79%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 7/65 = 0.108 (10.8%) (Wilson 95% 5-21%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/3 = 0.333 (33.3%) (Wilson 95% 6-79%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 15/65 = 0.231 (23.1%) (Wilson 95% 15-35%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/3 = 0.333 (33.3%) (Wilson 95% 6-79%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 4/65 = 0.062 (6.2%) (Wilson 95% 2-15%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 10/65 = 0.154 (15.4%) (Wilson 95% 9-26%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 44/65 = 0.677 (67.7%) (Wilson 95% 56-78%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 39/65 = 0.600 (60.0%) (Wilson 95% 48-71%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 28/65 = 0.431 (43.1%) (Wilson 95% 32-55%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/3 = 0.333 (33.3%) (Wilson 95% 6-79%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 24/65 = 0.369 (36.9%) (Wilson 95% 26-49%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 4/65 = 0.062 (6.2%) (Wilson 95% 2-15%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 40/65 = 0.615 (61.5%) (Wilson 95% 49-72%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 1/65 = 0.015 (1.5%) (Wilson 95% 0-8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 2/3 = 0.667 (66.7%) (Wilson 95% 21-94%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 25/65 = 0.385 (38.5%) (Wilson 95% 28-51%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt57bac609 (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 0/3 = 0.000 (0.0%) (Wilson 95% 0-56%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt57bac609 (DEV)<br>articles carrying the signal / articles | 1/65 = 0.015 (1.5%) (Wilson 95% 0-8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| reference articles carrying a Phase 6 candidate, lt6a9164bf (DEV)<br>mapped reference articles with a candidate / mapped reference articles | 95/203 = 0.468 (46.8%) | CORPUS_COVERAGE |  | OK | descriptive, never a target |
| multi-article reference obligations connected by cross-references, lt6a9164bf (DEV)<br>obligations whose articles form one connected group / obligations spanning two or more articles | 1/147 = 0.007 (0.7%) | CORPUS_COVERAGE |  | OK | the graph is a structural signal, not an obligation graph |
| EXPLICIT_OBLIGATION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 96/203 = 0.473 (47.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_OBLIGATION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 99/225 = 0.440 (44.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/203 = 0.005 (0.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| EXPLICIT_PROHIBITION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 1/225 = 0.004 (0.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 99/203 = 0.488 (48.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PERMISSION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 108/225 = 0.480 (48.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 11/203 = 0.054 (5.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| SANCTION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 12/225 = 0.053 (5.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 15/203 = 0.074 (7.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| RESPONSIBILITY among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 19/225 = 0.084 (8.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 123/203 = 0.606 (60.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DUTY_VERB among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 138/225 = 0.613 (61.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 107/203 = 0.527 (52.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| PASSIVE_DUTY among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 120/225 = 0.533 (53.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 94/203 = 0.463 (46.3%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CONDITION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 99/225 = 0.440 (44.0%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 17/203 = 0.084 (8.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEADLINE among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 17/225 = 0.076 (7.6%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 5/203 = 0.025 (2.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| FREQUENCY among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 5/225 = 0.022 (2.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 107/203 = 0.527 (52.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| ENUMERATION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 114/225 = 0.507 (50.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 1/203 = 0.005 (0.5%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| DEFINITION among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 1/225 = 0.004 (0.4%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 103/203 = 0.507 (50.7%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| CROSS_REFERENCE among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 112/225 = 0.498 (49.8%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among reference-linked articles, lt6a9164bf (DEV)<br>reference-linked articles carrying the signal / reference-linked articles | 14/203 = 0.069 (6.9%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| NO_SIGNAL among all articles, lt6a9164bf (DEV)<br>articles carrying the signal / articles | 14/225 = 0.062 (6.2%) | CORPUS_COVERAGE |  | OK | exploratory reference association; signal lists were chosen while viewing the reference, not held-out evidence |
| units with Phase 6 status EXTRACTED<br>units with this status / units | 239/620 = 0.385 (38.5%) | CORPUS_COVERAGE |  | OK | NO_OBLIGATION means no explicit marker, never no obligation |
| units with Phase 6 status NO_OBLIGATION<br>units with this status / units | 373/620 = 0.602 (60.2%) | CORPUS_COVERAGE |  | OK | NO_OBLIGATION means no explicit marker, never no obligation |
| units with Phase 6 status UNRESOLVED<br>units with this status / units | 8/620 = 0.013 (1.3%) | CORPUS_COVERAGE |  | OK | NO_OBLIGATION means no explicit marker, never no obligation |
| reference articles that map to a Phase 18 article<br>mapped / reference articles | 319/319 = 1.000 (100.0%) | CORPUS_COVERAGE |  | OK | structural mapping only |
| reference articles absent with a reported cause<br>absent with a reported cause / reference articles | 0/319 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK |  |
| reference articles with no matching article number and no reported cause<br>unmapped numbers / reference articles | 0/319 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK | a numbering or source-alignment mismatch, not a missing unit |
| units carrying at least one signal<br>units with a lexical or structural signal / units | 579/620 = 0.934 (93.4%) | CORPUS_COVERAGE |  | OK | totals for cost projection: 620 units, 3619 signals, 429158 characters |

## Corpus

Population `corpus.documents`: standard regulation PDFs; n = 12; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.articles`: articles recovered from the corpus; n = 952; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.candidates`: extracted candidates; n = 432; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.regions`: extraction regions (articles); n = 952; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.generated`: generated obligations; n = 432; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| documents processed without issues<br>documents with status PROCESSED_OK / corpus documents | 10/12 = 0.833 (83.3%) (Wilson 95% 55-95%) | CORPUS_COVERAGE |  | OK |  |
| documents with contiguous article numbering<br>documents whose articles are numbered 1..n without gaps / corpus documents | 10/12 = 0.833 (83.3%) (Wilson 95% 55-95%) | CORPUS_COVERAGE |  | OK |  |
| provenance round-trip violation rate<br>articles whose text is not reconstructible from its source spans / articles checked | 0/952 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| citation self-consistency violation rate<br>cited spans whose quote is not at the span / citations checked | 0/2544 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| marker accounting violation rate<br>marker occurrences with neither candidate nor diagnostic / marker occurrences | 0/480 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| regions left unresolved<br>regions with status UNRESOLVED / extraction regions | 15/952 = 0.016 (1.6%) | CORPUS_COVERAGE |  | OK |  |
| candidates per region<br>candidates produced / extraction regions | 432/952 = 0.454 (45.4%) | CORPUS_COVERAGE |  | OK |  |
| candidates turned into obligations<br>obligations generated and verified / candidates | 432/432 = 1.000 (100.0%) | CORPUS_COVERAGE |  | OK | 0 candidates rejected by verification |
| generated-token violation rate<br>tokens of generated text absent from the permitted source / tokens of generated text | 0/17004 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| generation evidence citation violation rate<br>evidence items whose quote is not at its span / evidence items | 0/2544 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| generation field accounting violation rate<br>trace references duplicated or untraced / trace references | 0/3629 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | 0 violations in N items checked: self-consistency, not correctness |
| queries with a duplicate suggestion<br>queries with at least one POSSIBLE_DUPLICATE suggestion (a suggestion, not a confirmed duplicate) / similarity queries | 22/432 = 0.051 (5.1%) | CORPUS_COVERAGE |  | OK | 39 duplicate suggestions over 1296 returned matches |

## End-to-end funnel (separate denominator at every stage; no end-to-end precision or recall exists)

Population `corpus.generated`: generated obligations; n = 432; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.tasks`: submitted review tasks; n = 432; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.
Population `corpus.documents`: standard regulation PDFs; n = 12; built by n/a: real regulations, no labels. Limits: no ground truth; one local set of Indonesian regulations; counts and invariants only.

| Metric | Result | Class | Gate | Status | Note |
|---|---|---|---|---|---|
| generated obligations submitted for review<br>review tasks created / generated obligations | 432/432 = 1.000 (100.0%) | CORPUS_COVERAGE |  | OK |  |
| tasks reviewable with verified evidence<br>tasks pending review with verified evidence / review tasks | 432/432 = 1.000 (100.0%) | CORPUS_COVERAGE |  | OK |  |
| event runs completed<br>runs with status COMPLETE / event runs | 12/12 = 1.000 (100.0%) (Wilson 95% 76-100%) | CORPUS_COVERAGE |  | OK |  |
| items dead-lettered<br>items dead-lettered / generated obligations | 0/432 = 0.000 (0.0%) | CORPUS_COVERAGE |  | OK |  |

## Known gaps

- generation: accepted known-gap contradiction gap-deadline-attachment
- generation: accepted known-gap contradiction gap-unfielded-recipients
- workflow: a dead-lettered notification has no operator requeue (items and stages do)

## Limitations

- Gold sets were authored by the system's author against the system's own contracts: they are regression evidence, not recall or precision on unseen regulations.
- Samples are small; intervals describe uncertainty for the evaluated population only and are not generalization evidence.
- One local corpus of Indonesian regulations without labels: corpus rows are counts and self-consistency checks, never correctness.
- No independent held-out data and no production data exist; those evidence classes are reported as none.
- Review and workflow rows come from scripted reviewers and fake infrastructure; they describe the logic, not reviewer or channel performance.
