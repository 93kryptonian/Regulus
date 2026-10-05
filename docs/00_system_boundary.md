# Regulus — System Boundary

**Phase:** 0 · **Status:** FROZEN

## 1. Purpose

Regulus turns regulatory changes into **reviewable, source-traceable obligations**.
It does not decide whether anyone is compliant.

> Regulus detects regulatory changes deterministically, processes the affected
> provisions, uses AI to extract and normalize candidate obligations with
> source-grounded evidence, retrieves similar existing obligations, and routes
> every candidate through human review before anything becomes an approved obligation.

## 2. Problem

Compliance teams must watch for new, amended and repealed regulations, decide
relevance, find affected provisions, extract obligations, compare against what
already exists, and notify stakeholders. Finding documents is cheap. Converting
text into **structured obligations without losing the link to the source
provision** is the expensive part.

## 3. Users

Primary: regulatory/compliance analyst (reviewer). Secondary: compliance
managers, auditors, administrators. Optimized for **reviewer throughput**.

## 4. Three engines, three authorities

| Engine | Question | Authority |
|---|---|---|
| Change Detection | What changed? | Deterministic. No LLM, reproducible, idempotent. |
| Obligation Intelligence | What does it mean? | AI-assisted candidates, grounded in evidence. |
| Review & Decision | Should it become an approved obligation? | Human only. |

```
Regulatory source ─▶ [Change Detection] ─▶ RegulatoryEvent
                                              ├─▶ Notification / monitoring
                                              └─▶ [Document Processing] ─▶ Articles
                                                        ─▶ [Obligation Intelligence]
                                                        ─▶ ObligationCandidate (+ similar existing)
                                                        ─▶ [Human Review] ─▶ Approved obligation
```

Authority never flows backwards:

```
LLM output ≠ regulatory truth      LLM confidence ≠ approval
Similarity score ≠ duplicate       Classification ≠ legal conclusion
```

## 5. Scope

In: ingestion, change detection (NEW / AMEND / REPEAL / PARTIAL_REPEAL),
document processing with OCR fallback, article segmentation with provenance,
relevance and sector classification, lineage and impact, obligation extraction
and generation, similarity top-K, review state machine, notifications,
evaluation, observability, audit.

## 6. Non-goals

- Autonomous approval of obligations.
- Determining legal compliance or replacing legal judgment.
- Treating LLM output as authoritative (the source is).
- Changing approved obligations without review.
- A generic chat-over-PDF tool.
- Reproducing any confidential system (see §10).

## 7. Deterministic vs AI

| Capability | Approach |
|---|---|
| Ingestion, dedup, regulation matching, change type | Deterministic |
| Article segmentation, source citation, audit trail, notification | Deterministic |
| Lineage | Rules + structured extraction |
| Relevance, sector | Hybrid (deterministic evidence stays visible) |
| Obligation extraction / normalization | AI-assisted + validation against source |
| Similarity | Embeddings + retrieval; result is a *relationship*, not a verdict |
| Duplicate decision, final approval | Human |

Authority boundaries are stable; individual techniques may change.

## 8. Provenance

Every candidate links `Regulation → Document → Page → Article → Paragraph/Span`.
A candidate without sufficient provenance is **not eligible for approval**.

## 9. Failure philosophy

> Failure in enrichment must not silently become a valid compliance decision.

Every stage result is one of: `NOT_PROCESSED`, `PROCESSED_EMPTY`,
`PROCESSED_OK`, `FAILED`. These are never conflated. OCR failure → document
FAILED, no generation. LLM timeout → candidate stays `PROCESSING_FAILED`.
Embedding failure → generation continues, similarity marked unavailable.
Notification failure → event stays persisted, delivery retried.

## 10. Confidentiality boundary

Portfolio Regulus uses **public or synthetic data only** and independently
designed contracts. It must not contain proprietary datasets, internal
taxonomies or business rules, prompts, source lists, chat/workspace structures,
spreadsheets, documents, schemas or identifiers from any employer system.
Prior work may inform *domain understanding* only, and lives outside this
repository (git-ignored, to be moved out).

## 11. M1 exit criteria

Phase 0 freezes when: problem, users, scope, non-goals, authority model,
deterministic/AI table, failure philosophy, provenance and confidentiality rules
are written, and the §12 review has no open findings.

M1 itself succeeds when, on synthetic/public inputs, Regulus can: ingest →
normalize → detect NEW/AMEND/REPEAL → identify the affected regulation →
process the document → emit article-level structured output with provenance.
**No LLM involved in M1.**

## 12. Adversarial review (to resolve before freeze)

| Attack | Current answer | Open? |
|---|---|---|
| Is anything secretly assuming an LLM? | M1 has none; Change Detection forbids it. | No |
| Does AI hold too much authority? | Only produces candidates; human approves. | No |
| Is this just generic RAG? | Output is typed, cited obligations + state machine, not answers. | No |
| Is "change" deterministic enough? | Depends on source metadata quality; ambiguous input → `NEEDS_REVIEW`, never guessed. Define in Phase 2. | Phase 2 |
| Is every obligation traceable? | §8 gate. Span-level verification test in Phase 6. | Phase 6 |
| AI unavailable? | §9. | No |
| Ambiguous source? | Explicit ambiguity state; see Phase 2. | Phase 2 |
| Buildable on public/synthetic data only? | Yes, see §13. | No |
| Stronger than a copy of prior work? | Adds contracts, lineage, evaluation, audit, failure semantics. | No |

## 13. Corpus (freeze decision)

Regulus uses a small curated corpus of publicly available Indonesian
regulations (UU, PP, Perpres, Permen, POJK) as its primary development and
evaluation corpus. Official sources are preferred: peraturan.go.id, with JDIHN
as secondary. The corpus is deliberately small and case-driven (NEW, AMEND,
REPEAL, PARTIAL_REPEAL, related regulations, obligation-rich text); it is not
representative of the whole Indonesian regulatory universe.

Synthetic fixtures exist only for pathological conditions public documents do
not reliably provide: OCR degradation, malformed or conflicting metadata,
duplicate ingestion, missing article numbers, broken page boundaries,
incomplete sources. Fixtures are plain files; no database is required before
persistence is needed.

Every committed document records its official source URL. Copies obtained from
third-party hosts are for local development only and are not committed.
