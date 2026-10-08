# Regulus evaluation report

Layered evaluation. There is no overall score: each row states its population, numerator and denominator.

Evidence classes present: CORPUS_COVERAGE, MUTATION, PROPERTY, REGRESSION.
Evidence classes absent: GENERALIZATION, PRODUCTION (none exist yet).

## Inputs

- `code`: `b226dee`
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
| runtime data files missing from the package<br>data files without a package-data pattern / data files in the tree | 0/8 = 0.000 (0.0%) (Wilson 95% 0-32%) | REGRESSION | HARD (expect 0): met | OK | matched against pyproject package-data; the wheel build is tested separately |
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
| committed artifacts containing expert content<br>files with expert-authored text / text files scanned | 0/293 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK | public statute wording is excluded; 6 of 6 source PDFs available |
| reference files tracked by git<br>tracked files under reference/ / files under reference/ | 0/5 = 0.000 (0.0%) (Wilson 95% 0-43%) | PROPERTY | HARD (expect 0): met | OK |  |
| rows with a sector outside the vocabulary<br>unknown-sector rows / rows read | 0/3491 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| rows with an unparseable article reference<br>excluded rows / rows read | 0/3491 = 0.000 (0.0%) | PROPERTY | HARD (expect 0): met | OK |  |
| regulations whose derived count differs from the declared count<br>regulations with a count discrepancy / regulations | 1/6 = 0.167 (16.7%) (Wilson 95% 3-56%) | CORPUS_COVERAGE |  | OK | reported, never forced; the pinned expectation is five matched and one over by one |
| obligation type accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| sanction category accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| appendix-derived obligation accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |
| reference pointer accuracy<br>reference obligations whose label agrees / reference obligations with a label | NOT_MEASURABLE | PROPERTY |  | NOT_MEASURABLE | the reference carries no labels for this dimension; the rules exist only in the instruction documents |

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
