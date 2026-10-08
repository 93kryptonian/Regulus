# Regulus v2 — Regulatory Document Ingestion Contract

**Phase:** 18 · **Status:** FROZEN

```
Phase 3   what does a document structurally contain, and where?        (frozen, reused unchanged)
Phase 17  what does the expert reference point to?                     (frozen, the oracle)
Phase 18  which exact document was processed, can the same input be recognised,
          and does the recovered article structure cover what the reference points to?
```

> Phase 18 wraps the frozen Phase 3 processor with document identity, version control, one tightly
> constrained normalization of a measured article-heading glitch, and an evaluation against the
> Phase 17 reference. It reads PDFs and never calls a model.

## 1. Profile that shapes this contract (counts only, real PDFs)

| Fact | Observation |
|---|---|
| PDFs | 14 readable, all with a native text layer; 6 have expert reference, 8 do not |
| Phase 3 status on the 6 benchmark PDFs | 5 `PROCESSED_OK`, 1 `PROCESSED_WITH_ISSUES` |
| Reference articles recovered | 318 of 319 (5 regulations complete) |
| The one miss | PP 33/2026, Pasal 92: the text layer reads the heading as `Pasa192` (an `l` rendered as `1`, space lost). Phase 3 reports `ARTICLE_GAP`, so the loss is **flagged, not silent** |
| Articles extracted that the reference does not link | 22 to 104 per regulation: normal, most articles carry no obligation |
| Reference article text versus extracted text | the reference text is **not** a verbatim copy of the PDF text (for the largest regulation only about 17 % of reference texts reach 95 % token containment even against the whole document) |
| Identity already in Phase 3 | `content_hash` (SHA-256 of the bytes), `text_fingerprint`, a content-derived document id, and the regulation id as an input |
| Two non-benchmark PDFs | amendment-style documents: no articles, two amendment units each |

Consequences: Phase 3 is reused unchanged; the reference supports **article-number linkage only** as an
oracle, not article text; and the work in this phase is identity, versioning, one sequence-verified heading normalization,
and the evaluation.

## 2. Question and boundaries

| Phase 18 does | Phase 18 does not |
|---|---|
| give every ingested document a stable identity and a processing key | extract obligations (Phase 19) |
| recognise identical input and flag changed or conflicting input | call a model, an embedding or a database |
| normalize one measured class of article-heading glitch, only under sequence evidence (§5) | repair spelling, repair text, or normalize anything other than that heading class |
| evaluate article-structure recovery against the Phase 17 reference | claim anything about appendix or annex content |
| report documents outside the benchmark as such | treat the reference article text as source truth |

## 3. Identity

| Field | Meaning |
|---|---|
| `regulation_id` | identifies the regulatory document. Source: the file stem by convention, or a manifest entry; never the title |
| `content_hash` | SHA-256 of the exact bytes processed (the Phase 3 field) |
| `text_fingerprint` | Phase 3 hash of the cleaned text; detects a re-rendered PDF with equal text |
| `ingestion_version` | version of this contract's wrapper behaviour |
| `reader_config_hash` | hash of the reader settings (OCR engine, thresholds, heading normalization on or off) |

`processing_key = SHA256(content_hash + "\x1f" + ingestion_version + "\x1f" + reader_config_hash)`.
Later phases extend this material with their own versions (Phase 20: expert policy, model, prompt, and
so on); a key never depends on a file name.

### 3.1 Registry rules (in-memory port, `IngestionRegistry`)

| Situation | Behaviour |
|---|---|
| unseen `regulation_id` and `content_hash` | `NEW`; recorded |
| same id, same hash | `UNCHANGED`; the earlier result is returned, nothing reprocessed |
| same id, different hash | `NEW_VERSION`; both versions kept, the earlier one never overwritten, the change reported |
| same hash, different id | `DUPLICATE_CONTENT`; refused with a diagnostic, not silently aliased |
| same id and text fingerprint, different bytes | `RERENDERED`; recorded as a new version, flagged as text-equal |
| unreadable bytes | `FAILED`; no article claims; never partial success |

Durability of the registry belongs to Phase 20's result store. Phase 18 defines the semantics and an
in-memory implementation.

## 4. Ingestion result

```python
class IngestionResult(Model):
    identity: DocumentIdentity
    status: IngestionStatus      # INGESTED, INGESTED_WITH_ISSUES, FAILED
    registry: RegistryOutcome    # §3.1
    processed: ProcessedDocument # the frozen Phase 3 value, unchanged
    normalizations: tuple[HeadingNormalization, ...]
    article_index: dict[int, ArticleRef]   # number -> id, pages, span
    issues: tuple[Issue, ...]
```

`ingest(data, regulation_id, reader, registry, normalize_headings=True)` is a pure function of its arguments and
the registry state. Status derives from Phase 3 status and the normalizations: a document with unresolved
`ARTICLE_GAP` is `INGESTED_WITH_ISSUES`, never `INGESTED`.

## 5. Sequence-verified normalization of a measured article-heading glitch

> This is **not** a spelling-repair or text-repair capability, and Regulus cannot repair malformed
> regulatory text. It recognises **one narrowly defined class of malformed article heading** under five
> evidence conditions and reconstructs the expected heading **solely for structural processing**. The
> original line stays on record as provenance.

Measured defect: a text-layer glitch (`Pasa192`) hides one article. Phase 3 forbids spelling repair, and
that stays true. The normalization lives in the reader wrapper, before Phase 3 runs, and every
condition is required:

1. a line matches a closed glitch pattern for the word `Pasal` followed by digits (`l`, `1`, `I`, `|`
   substitutions, missing space);
2. the unmodified Phase 3 run reports an `ARTICLE_GAP` with exactly one missing integer `n`;
3. the digits read from the line equal `n`;
4. the line lies between the text of article `n-1` and article `n+1` in page order;
5. no other line satisfies conditions 1 to 4 for `n`.

Only then is that heading line normalized to `Pasal n` for processing. The original line, page and
position are stored in a `HeadingNormalization` record, the result is `INGESTED_WITH_ISSUES` with an
issue `HEADING_NORMALIZED`, and the article carries the flag downstream (Phase 21 treats it as lower
certainty). A glitch that fails any condition is left alone and the gap stays reported. Passing
`normalize_headings=False` yields exactly the Phase 3 behaviour.

Provenance: spans refer to the processed text. The normalized heading differs from the original by at
most two characters; the record states the original so a reader can reconcile.

## 6. Evaluation (a Phase 12 layer, `ingestion`)

### 6.1 Scope
The benchmark is the **six** regulations with a Phase 17 reference. The other PDFs are ingested for
robustness (status, determinism, no crash) and are **not** part of any quality claim.

### 6.2 Metrics

| Metric | Numerator / denominator | Gate |
|---|---|---|
| reference articles not recovered | reference articles absent from the result / reference articles | `TARGET: 0` |
| **silent article loss** | reference articles absent **and** not accompanied by an `ARTICLE_GAP` or failure diagnostic / reference articles | **HARD: 0** |
| unresolved ARTICLE_GAP on a benchmark document | such documents / benchmark documents | `TARGET: 0` |
| normalizations violating a condition of §5 | normalizations failing re-verification / normalizations made | **HARD: 0** |
| non-deterministic ingestion | differing results on repeat / repeats | **HARD: 0** |
| identity errors | wrong registry outcome / registry scenarios | **HARD: 0** |
| processing-key instability | key differs for equal inputs, or equal for different inputs / key scenarios | **HARD: 0** |
| unreadable inputs reported as ingested | such / unreadable inputs tried | **HARD: 0** |
| extracted articles not linked by the reference | count per regulation | `REPORT_ONLY` (never an error) |
| reference text agreement | reference texts with ≥ 95 % token containment in the extracted article / reference texts | `REPORT_ONLY`, labelled "the reference text is not a verbatim source copy; not an oracle" |
| ingestion time per regulation | seconds | `REPORT_ONLY` |

Reference rows need the local reference and PDFs; otherwise they are `NOT_MEASURABLE`, and a synthetic
PDF suite exercises identity, registry, heading normalization and failure behaviour regardless. Per-regulation rows
always accompany pooled rows. Evidence class: `PROPERTY` and `REGRESSION`, plus `EXPERT_REFERENCE` for
the article-recovery rows. Results are not generalization evidence.

## 7. Hard invariants

1. **Reuse.** Phase 3 is called unchanged; `ingest(..., normalize_headings=False)` equals Phase 3 output.
2. **Identity.** `content_hash` always equals the SHA-256 of the bytes; `regulation_id` is never a title.
3. **Idempotence.** Equal inputs and registry state give equal results; a repeat returns `UNCHANGED`.
4. **No silent loss.** An article the document contains is either in the index or covered by a
   diagnostic. A normalization never hides a gap it did not fill.
5. **Normalization is evidence-bound.** Every normalization record re-verifies against conditions 1
   to 5; a failed re-verification is an error.
6. **No reference dependency.** No module under `regulus.ingestion` imports `regulus.reference`; only
   the evaluation layer does.
7. **Failure is explicit.** Unreadable input is `FAILED` with no articles.
8. **No model, no network, no database.**

## 8. Failure semantics

| Situation | Behaviour |
|---|---|
| unreadable or corrupt PDF | `FAILED`; registry unchanged |
| a page fails | Phase 3 `PARTIAL` carried through as `INGESTED_WITH_ISSUES` |
| no articles (amendment-style document) | status from Phase 3; the amendment units are reported; no article claims |
| two candidate lines for one missing article | no normalization; gap stays reported |
| same bytes under two ids | `DUPLICATE_CONTENT` |
| annex content present | Phase 3 `ANNEX_NOT_PROCESSED` is carried through; annex obligations are out of scope |

## 9. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| glitched heading, number equals the single gap, in position | normalized; issue and record present |
| glitched heading, number does not equal the gap | not normalized |
| glitched heading, no gap | not normalized |
| glitched heading, two candidates for one gap | not normalized |
| glitched heading out of position | not normalized |
| glitch pattern in running text (a cross-reference) | not normalized |
| `normalize_headings=False` | identical to Phase 3 |
| same bytes twice | `UNCHANGED`, no reprocessing |
| same id, new bytes | `NEW_VERSION`, both kept |
| same bytes, new id | `DUPLICATE_CONTENT` |
| re-rendered PDF with equal text | `RERENDERED` |
| unreadable bytes | `FAILED`, no articles |
| processing key for equal inputs | equal |
| processing key when one version or setting changes | different |
| amendment-style document | no articles; units reported |
| real benchmark PDFs, reference present | per-regulation recovery rows |
| reference absent | reference rows `NOT_MEASURABLE`; synthetic suite runs |
| import scan | no `regulus.reference` import under `regulus.ingestion` |

## 10. Module layout

```
src/regulus/ingestion/
├── models.py     DocumentIdentity, IngestionResult, HeadingNormalization, ArticleRef, Issue, statuses
├── identity.py   fingerprints, processing_key
├── registry.py   IngestionRegistry port and in-memory implementation
├── headings.py   glitch pattern, sequence verification, re-verification
├── ingest.py     ingest(), the wrapper over Phase 3
└── synthetic.py  generated PDFs for tests
src/regulus/evaluation/layers/ingestion.py     Phase 12 layer
tests/ingestion/
```
No new dependency (PDF generation for tests uses what v1 tests already use).

## 11. Claims

Allowed: "documents are identified by content, identical input is recognised, a changed document is
versioned rather than overwritten", "article recovery is measured per regulation against the expert
reference's article numbers", "a normalized heading is flagged, evidence-bound and traceable to its original line".

Not allowed: any claim about article **text** fidelity to the reference, appendix or annex handling,
obligation quality, or generalization beyond the six benchmark regulations.

## 12. Decisions (confirmed by the project owner)

1. **Heading normalization (§5)** is included with its five conditions. Its terminology is
   "sequence-verified normalization of a measured article-heading glitch", never "repair" or "recovery"
   of text. The 318-of-319 figure is not the headline result.
2. **Registry** is in-memory with defined semantics; durability waits for Phase 20.
3. **`regulation_id`** is the file stem by convention, with a manifest override. The hierarchy is
   `regulation_id` (logical identity), `content_hash` (exact bytes), `text_fingerprint` (same extracted
   text across different bytes), `processing_key` (exact processing configuration).
4. **Annex and appendix content** stays out of scope and is carried only as a Phase 3 diagnostic.
5. **Gates:** silent loss is a hard gate; plain non-recovery is a target.
6. **Reference text** is `REPORT_ONLY` and never an oracle; reference article **numbers** are the oracle.
7. The Phase 3 `process` call stays unchanged.
