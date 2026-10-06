# Regulus — Obligation Extraction Contract

**Phase:** 6 · **Status:** FROZEN

```
PHASE 5   What provision changed?                      ChangedProvision / WithdrawnProvision
PHASE 6   What obligation semantics are explicitly stated?   ObligationCandidate   ← this phase
PHASE 7   How are they normalized into a grounded obligation?   Obligation (domain)
```

> **Phase 6 extracts obligation semantics from an already-identified changed
> provision. It does not decide legal applicability, does not resolve lineage, and
> does not author a normalized obligation.**

## 1. Purpose and boundary

Phase 6 answers: *in this provision, which clauses state an obligation or a
prohibition, and which parts of each clause are the actor, the required action,
the object, the condition, the deadline, the frequency and the exception?*

| Phase | Owns | Phase 6 uses it as |
|---|---|---|
| 3 | text, `Provision` structure, provenance | the text and its structure; never re-read from a PDF |
| 4 | relevance | **not an input**; routing is orchestration |
| 5 | `ChangedProvision`, `WithdrawnProvision`, lineage | the only way a provision reaches Phase 6; never re-derived |
| 6 | candidates, extraction result, obligation impact | |
| 7 | normalization, generation, the domain `Obligation` | consumes candidates; Phase 6 never writes a clean obligation sentence |

Core principle, carried from Phases 2–5: **extract only what the text states; if a
part cannot be delimited by a deterministic rule, say so explicitly. Never infer.**

Not in Phase 6: normalized wording, pronoun or defined-term resolution
("Pengendali Data Pribadi" is not expanded from Pasal 1), sector, relevance,
similarity, duplicate detection, legal applicability, approval, effectivity dates.

## 2. Inputs

`extract(input, extractor) -> ExtractionOutput`: pure, no I/O, no clock.

| Field | Meaning |
|---|---|
| `changes` | Phase 5 `ChangedProvision` (`NEW_REGULATION_ARTICLE`, `ADDED`, `MODIFIED`, `TERM_REPLACED`) |
| `withdrawn` | Phase 5 `WithdrawnProvision` |
| `documents` | Phase 3 `ProcessedDocument` per acting regulation; the owner of a `text_ref` is found by its id prefix (`PP-5-2026:unit-I` → `PP-5-2026`) |
| `obligations` | existing Phase 1 `Obligation`s and an `obligations_complete` flag (see §8) |

The analysed region of a change is `owner_text[text_ref.start:text_ref.end]`.
Phase 3 `Provision`s (ayat, huruf, angka) overlapping that region give its
structure. A `TERM_REPLACED` change is **not** analysed for candidates: its text is a
term swap, not a clause (§8).

## 3. The candidate

`ObligationCandidate` (package-local type, not the domain `Obligation`):

| Field | Meaning |
|---|---|
| `id` | `"cand-" + sha256(owner_id, clause span, marker span, modality, extractor id@version)[:16]`; no time in it |
| `change_ref` | the `ChangedProvision` (regulation id, article number, `impact_id`) |
| `clause` | `Citation` of the unit of analysis (§6) |
| `modality` | `OBLIGATION` or `PROHIBITION` |
| `marker` | `FieldValue`: the deontic word itself |
| `actor`, `action`, `object`, `deadline`, `frequency` | `FieldState` |
| `conditions`, `exceptions` | `tuple[FieldValue, ...]` (a clause can carry several) |
| `items` | `tuple[Citation, ...]`: enumerated sub-items under this clause (§6.3), structural only |
| `extractor` | `id@version` |

Permissions (`dapat`, `boleh`, `berhak`) are not obligations and yield no candidate.

### 3.1 Hard invariants

1. **Existence:** a candidate has a `clause`, a `marker` and ≥ 1 citation; no evidence, no candidate.
2. **Field values are verbatim.** A populated field is `FieldValue(value, citation)` with `citation.quote == value == owner_text[span]`. No normalization, no reordering, no added or removed words.
3. **Every populated field cites its own span**, and that span lies inside the candidate's `clause`. **Exception (enumeration-item candidates only, §6.3):** `actor` and applicable `conditions` may cite the item's lead-in clause (recorded as `lead_in` on the candidate); every other populated field must cite a span inside the item's own clause.
4. `action` is required for a candidate; a clause that has a marker but no delimitable action is **not** a candidate and is reported (§11).
5. No field is filled from a neighbouring sentence or clause.

Invariants 2–3 make "unsupported claim" mechanically checkable: a claim is unsupported
if its value is not exactly the cited text.

## 4. Field states

Each of `actor`, `action`, `object`, `deadline`, `frequency` is one of:

| State | Meaning |
|---|---|
| `PRESENT(value, citation)` | the rules delimited the field |
| `NOT_STATED` | the extractor completed and found no stated value (no trigger in the clause) |
| `UNDETERMINED(reason)` | a trigger was found but the rule could not delimit the span (e.g. `kecuali` with nothing after it) |

`NOT_STATED` is a valid, successful outcome: a clause need not have a deadline, a
frequency or a condition. It is **not** an extraction failure, and it is not
`UNDETERMINED`. Evaluation scores them differently (§13).

`conditions` and `exceptions` are empty when `NOT_STATED`; an undelimited trigger
is recorded as a clause-level `UNDETERMINED` note on that field.

## 5. Evidence and citation

`Citation(owner_id, start, end, quote)`: `owner_id` is a Phase 3 `Article.id` or
`AmendmentUnit.id`, offsets index that owner's text (so Phase 3 `locate()` turns any
citation into page-level spans). `quote == owner_text[start:end]` is verified
before a candidate leaves Phase 6 (§9). A citation that does not verify is dropped.

**Mandatory Phase 7 design decision** (Phase 6 does not choose, and Phase 1 is not modified for Phase 6's convenience): the Phase 1
`ObligationEvidence` is article-bound (`article_id`, span in `Article.text`), while
an obligation introduced by an amendment cites an `AmendmentUnit`. Phase 7 must explicitly choose between (A) generalizing the evidence owner and (B) mapping the unit citation onto the changed article, and define how the original unit source span stays recoverable.

## 6. Extraction semantics

### 6.1 Clause and marker (the unit of analysis)

Deterministic markers (closed, case-insensitive, whole word):

| Modality | Markers |
|---|---|
| `OBLIGATION` | `wajib`, `berkewajiban`, `diwajibkan`, `harus` |
| `PROHIBITION` | `dilarang`, `tidak boleh`, `tidak diperbolehkan` |

A **clause** is the sentence (or, for an ayat/huruf/angka provision, the provision's
own text) that contains the marker, from its start to its terminating boundary.
Sentence boundary: `.`, `;` or `:` followed by whitespace, not inside parentheses and
not after a closed abbreviation list (`No`, `Nomor`, `dll`, `dsb`, `dst`, `s.d`,
`a.n`). Structural provisions are boundaries too: an ayat never merges with the next.

Negated forms take precedence over the positive markers (`tidak wajib` is never read as `wajib`). `tidak wajib`, `tidak harus` (negated obligation) is **not** a marker: it yields no
candidate and an informational `NEGATED_MARKER` diagnostic (it is an exemption, not
a duty, and must not become either).

### 6.2 Multiplicity (when several candidates arise from one provision)

| Situation | Result |
|---|---|
| one marker in one clause | one candidate |
| two clauses (two sentences / two provisions), each with a marker | two candidates; conditions, deadlines, exceptions never cross the boundary (`A wajib X apabila C. B wajib Y paling lambat T.` gives two) |
| the marker is repeated in one sentence (`A wajib X dan wajib Y`) | two candidates, same actor span cited by both |
| coordinated predicates under **one** marker (`A wajib X dan Y`) | **one** candidate; `action`/`object` span the coordination. Splitting needs linguistic analysis that would infer structure, so it is not done; Phase 7 or the reviewer decides |
| marker with a modality change in one sentence (`A wajib X dan dilarang Y`) | two candidates |

### 6.3 Enumerations

`A wajib: a. … ; b. …` has a lead-in clause (with the marker) and items from the
Phase 3 `Provision` structure. The items may be separate duties (`a. menyampaikan
laporan; b. menyimpan dokumen`) or the object itself (`wajib memuat: a. nama; b.
alamat`); that distinction needs reading the items, so **enumerations are never
split by Phase 6.** One candidate carries the lead-in fields and `items` (structural
citations of each item), with `object` `NOT_STATED` or `UNDETERMINED`.
If an item itself contains a marker, that item is analysed as its own clause
(its `actor` and `conditions` may be cited from the lead-in, and only from it).

### 6.4 Field rules (deterministic, closed triggers; reference implementation)

| Field | Rule |
|---|---|
| `actor` | the noun phrase before the marker, from the clause start (after removing a leading condition clause) |
| `action` | the first verb token after the marker (affixed verb forms `me-/mem-/men-/meng-/meny-/ber-/di-`) up to the object boundary |
| `object` | the phrase after the action up to the next boundary trigger (`kepada`, `dengan`, `sesuai`, `paling`, `setiap`, `dalam`, `untuk`, `,`, `;`, `.`) |
| `condition` | a clause introduced by `dalam hal`, `apabila`, `jika`, `sepanjang`, `sebelum`, `setelah`, `pada saat`, either leading (up to the comma before the main clause) or trailing |
| `exception` | a phrase introduced by `kecuali` or `dikecualikan` up to the clause end |
| `deadline` | `paling lambat`, `paling lama`, `selambat-lambatnya`, `dalam jangka waktu`, `dalam waktu`, `paling singkat` followed by a duration (`N (…) hari/bulan/tahun/jam`, `N x 24 jam`) or a date expression |
| `frequency` | `setiap` + (`N`)? unit (`hari`, `minggu`, `bulan`, `tahun`, `triwulan`, `semester`), `secara berkala`, `secara berkelanjutan` |

**If a field rule meets several structurally plausible spans and no deterministic precedence rule selects exactly one, the field is `UNDETERMINED`; the extractor must not choose by linguistic plausibility** (e.g. an actor phrase containing a comma, two leading adjuncts of the same kind, an object phrase containing a comma). Precedence rules that do exist: a trigger's segment runs from the trigger to the next trigger or the clause end; leftmost trigger first; a deadline expression absorbs its own relative phrase (`setelah …`). Rules that cannot delimit a field give `UNDETERMINED`, never a guess. **No
inference:** `wajib menyampaikan laporan` states no frequency, so `frequency =
NOT_STATED` even though a domain might expect quarterly; `wajib melapor` states no
deadline, so none is produced.

## 7. Extraction versus generation

Phase 6 output is a set of **verbatim spans with roles**. It never produces: a
rewritten sentence, a pronoun or abbreviation resolved, a defined term expanded, a
duration converted (`3 x 24 jam` stays `3 x 24 jam`), a reordering, a merged or split
predicate. Every such operation is Phase 7, which must also record that it
happened. The example output of a clause:

```
actor      "Pengendali Data Pribadi"
marker     "wajib"            (OBLIGATION)
action     "memberitahukan"
object     "kegagalan Pelindungan Data Pribadi"
condition  "dalam hal terjadi kegagalan Pelindungan Data Pribadi"
deadline   "paling lambat 3 x 24 jam"
```

is the whole product; the sentence "Pengendali Data Pribadi wajib memberitahukan …
kepada …" is not Phase 6's to write.

## 8. Existing obligations: `ObligationImpact`

A changed or withdrawn provision may affect obligations already in the store.
Phase 6 reports it **without** reading a withdrawal as "no obligations":

`ObligationImpact(kind, regulation_id, article_number, article_id, affected_obligation_ids, review_required, store_complete, impact_id)`:

- `kind`: `WITHDRAWN` (from `WithdrawnProvision`), `MODIFIED` (from a `MODIFIED` change), `TERM_REPLACED`.
- `affected_obligation_ids`: ids of Phase 1 `Obligation`s whose `article_id` equals `"{regulation_id}:{article_number}"`.
- `review_required` is true if any affected obligation exists **or** `obligations_complete` is false (an empty answer from an incomplete store is unknown, not "none").
- `ADDED` and `NEW_REGULATION_ARTICLE` changes need no impact record: nothing existing can be affected.

`ObligationImpact` never edits, retires or approves an obligation; that is Phase 9.

## 9. Extractor interface

```
class ObligationExtractor(Protocol):
    id: str; version: str
    def extract(self, request: ExtractionRequest) -> tuple[RawCandidate, ...]
```

`ExtractionRequest`: the region text, its owner id and offset, the structural
provisions, the marker lexicon. `RawCandidate` carries the same shape as a candidate
with offsets only; **everything an extractor returns is re-verified** by the Phase 6
`ground()` step: quotes must equal the cited text, fields must lie inside the
clause, the marker must be in the lexicon, `action` must be present. Failing
fields/candidates are dropped and counted (`dropped_ungrounded`). So a learned or
LLM extractor can be plugged in later without being able to introduce a claim the
text does not carry. Phase 6 ships **no model**: the reference implementation is
`RulesExtractor` (§6.4).

## 10. Rules-only reference implementation

`regulus.obligations.rules.RulesExtractor` implements §6 with the closed lexicons in
versioned data (`data/lexicon.v1.json`): markers, abbreviations, condition /
exception / deadline / frequency triggers, duration units. Matching is exact and
whole-word; no stemming, no fuzzy matching. The v1 lexicon is closed and is not extended opportunistically: adding `mewajibkan`, `mengharuskan`, `berkewajiban untuk`… is a deliberate contract and lexicon version change (v1.1), decided on gold and corpus evidence. Recall is bounded by the lexicon by
design (a duty phrased without a marker, e.g. `mewajibkan`, is not found and is not
reported; the gold set measures this).

## 11. Result, failure and abstention

`ExtractionResult` per change: `status`, `candidates`, `diagnostics`, `dropped_ungrounded`, `complete`.

| Status | Meaning |
|---|---|
| `EXTRACTED` | ≥ 1 candidate |
| `NO_OBLIGATION` | processed, no marker-bearing clause: a **valid success** (definitions, authority, procedure) |
| `FAILED` | the extractor raised; no candidates; never reported as `NO_OBLIGATION` |
| `UNRESOLVED` | no candidate was formed, but ≥ 1 marker occurrence exists (`UNEXTRACTED_DEONTIC`): the region is **never** `NO_OBLIGATION`; it goes to review |
| `NOT_EXTRACTABLE` | the owner text or document is missing / unusable |

Diagnostics (never silent loss):

- `UNEXTRACTED_DEONTIC` (error): a lexicon marker occurs in the region but no candidate was formed (no delimitable action, or all fields dropped as ungrounded). **Every marker occurrence ends as a candidate or as this diagnostic.** Gate: zero silent loss.
- `NEGATED_MARKER` (info), `UNDETERMINED_FIELD` (warning), `ENUMERATION_ITEM_MARKER` (info), `INCOMPLETE_SOURCE` (error).

`complete = false` when the acting document is not `PROCESSED_OK` (Phase 3 statuses),
as in Phase 5: an empty result from an incomplete document is not "no obligation".

## 12. Determinism and provenance

Same `(input, extractor, lexicon)` ⇒ byte-identical output; candidate ids are
derived, include the extractor id@version and exclude time. Order is
`(owner_id, clause start, marker start)`. Inputs are never mutated. Every candidate
traces: `ChangedProvision` → owner (article or unit) → span → page (via Phase 3
`locate`) → document hash.

## 13. Evaluation

Gold file `evaluation/obligations/gold.v1.json`: provisions (short excerpts of real
public regulation text with their gazette citation, plus synthetic edge cases), each with
the expected candidates as field spans, the expected field states, and a written
rationale; provisions without any marker are included, to measure false candidates. Metrics (pure functions):

| Metric | Level | Gate |
|---|---|---|
| candidate precision / recall / F1 | clause match | reported |
| actor, action, object, condition, deadline, frequency, exception precision / recall / F1 | field value (exact span match) | reported |
| `NOT_STATED` accuracy | field state | reported, scored apart from extraction failure |
| citation correctness | every cited quote equals its text | **100 %** |
| unsupported-claim count | populated fields whose value is not the cited text | **0 (hard gate)** |
| silent deontic loss | marker occurrences with neither candidate nor diagnostic | **0 (hard gate)** |
| multiplicity accuracy | candidates per provision | reported |
| false `NO_OBLIGATION` | provisions with a gold obligation reported as none | reported, listed |

Gold authored with the lexicon is a regression suite; recall on provisions not
written for it (real articles from the local corpus) is the coverage evidence.

## 14. Module layout

```
src/regulus/obligations/
├── models.py     Citation, FieldValue, FieldState, ObligationCandidate, results
├── segment.py    regions, clauses, sentence boundaries, enumerations (pure)
├── rules.py      RulesExtractor + lexicon loading
├── ground.py     citation / field / marker verification
├── extract.py    extract() orchestration
├── impact.py     ObligationImpact
├── evaluate.py   metrics
└── data/lexicon.v1.json
evaluation/obligations/gold.v1.json
tests/obligations/
```

## 15. Adversarial matrix (each needs a test)

| Case | Expected |
|---|---|
| `X wajib menyampaikan laporan` | candidate with actor, marker, action, object; deadline, frequency, condition, exception `NOT_STATED` |
| `… setiap 3 bulan` | `frequency = "setiap 3 bulan"`; without it `NOT_STATED` (no inference) |
| `… paling lambat 3 x 24 jam` | `deadline` verbatim, not converted |
| `Dalam hal …, X wajib …` | leading condition cited, actor after the comma |
| trailing `apabila …` | trailing condition |
| `… kecuali …` | exception |
| `kecuali` with nothing after | exception `UNDETERMINED` |
| `X dilarang …` | `PROHIBITION` |
| `X dapat …` / `berhak` | no candidate, no diagnostic |
| `X tidak wajib …` | no candidate, `NEGATED_MARKER` |
| two sentences, two markers | two candidates; no field crosses |
| `A wajib X dan wajib Y` | two candidates |
| `A wajib X dan Y` | one candidate, coordination kept |
| `A wajib X dan dilarang Y` | two candidates, two modalities |
| `A wajib: a. …; b. …` | one candidate with two items, nothing split |
| enumeration item carrying its own marker | that item is its own candidate, actor from the lead-in |
| marker present, no delimitable action | `UNEXTRACTED_DEONTIC` |
| definitions / authority provision | `NO_OBLIGATION` (valid) |
| marker only inside a cross-reference phrase | still a marker occurrence: candidate or `UNEXTRACTED_DEONTIC` |
| `mewajibkan` (not in lexicon) | nothing, documented recall limit |
| `TERM_REPLACED` change | no candidates; `ObligationImpact(TERM_REPLACED)` |
| `MODIFIED` change, existing obligations on the article | candidates from the new wording + `ObligationImpact(MODIFIED)` listing them |
| `WITHDRAWN` provision, obligations exist | `ObligationImpact(WITHDRAWN)`, `review_required` |
| `WITHDRAWN`, store incomplete, no obligations known | `review_required = true` |
| `WITHDRAWN`, store complete, none | `review_required = false` |
| amending-unit region | candidates cite the unit; owner resolves via the id prefix |
| document not `PROCESSED_OK` | `complete = false`, items flagged |
| extractor fabricates a field value | dropped, counted; marker clause → `UNEXTRACTED_DEONTIC` |
| extractor field outside the clause | dropped |
| extractor returns marker not in lexicon | candidate dropped |
| extractor raises / times out | `FAILED`, never `NO_OBLIGATION` |
| same input twice / different extractor version | identical / different ids |
| inputs unchanged | no mutation |
| every candidate | `quote == owner_text[span]` for each citation; page spans resolve via `locate` |
| Phase 3/5 compatibility | real `ProcessedDocument`, `ChangedProvision` consumed as-is |

## 16. Gate

Contract frozen after adversarial review → implementation module by module with
tests (segmentation and the field rules first, in isolation) → every §15 case
passing → ruff and strict mypy clean → gold metrics with **unsupported claims 0
and silent loss 0** → real-corpus run on local articles (PP 33/2026 and others)
→ freeze.

## 17. Decisions

1. **Verbatim, citation-equals-value fields** (§3.1): fields cannot contain anything the text does not. Grounding is a structural invariant.
2. **Three field states** (`PRESENT` / `NOT_STATED` / `UNDETERMINED`); `NOT_STATED` is a success (§4).
3. **Multiplicity** per §6.2: coordination and enumerations are not split; enumeration-item candidates may cite actor and conditions from the lead-in (§3.1).
4. **`ObligationImpact`** in Phase 6 (§8), with the incomplete-store rule; it never edits an obligation (Phase 9).
5. **Prohibitions in scope**, permissions out; negated forms take precedence.
6. **Extractor injectable, every output re-verified** (§9); rules-only reference, no model; v1 lexicon closed.
7. **Hard gates:** unsupported claims 0, silent deontic loss 0, citation correctness 100 % (§13).
8. **Evidence-owner mismatch** is a mandatory Phase 7 design decision (§5).
9. **Ambiguity ⇒ `UNDETERMINED`** (§6.4); a region with marker occurrences and no candidate is `UNRESOLVED`, never `NO_OBLIGATION` (§11).
