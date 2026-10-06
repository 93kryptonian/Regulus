# Regulus — Document Processing Contract

**Phase:** 3 · **Status:** FROZEN

Answers one question: **what does this document structurally contain, and
where exactly?** Output is structurally trustworthy source material with
provenance, never interpretation. No relevance, sector, obligation, lineage or
meaning (Phases 4–8); no spelling repair; no LLM.

```
bytes ─▶ [page reader: native | OCR] ─▶ Page[] ─▶ [clean] ─▶ [zone] ─▶ [segment] ─▶ ProcessedDocument
         (adapters, I/O)                         └──────── pure functions of Page[] ────────┘
```

Readers are thin I/O adapters behind a protocol. Everything from `Page[]`
onward is pure, deterministic and testable without a PDF.

## 1. Evidence from the real corpus (drives the design)

Checked against the 12 local PDFs (Aug 2026 copies, 3–172 pages):

- Every page has a native text layer; **no real scanned page exists**. The OCR
  path is therefore exercised by synthetic fixtures only (Phase 0 §13).
- Reading order matters: poppler's default `pdftotext` mode detached the `(1)`
  `(2)` ayat labels from their text on PP 33/2026 p.20. **pdfplumber's
  `extract_text()` (v0.11) keeps each label with its text on that page and
  returns no padding**, so it is the native reader (chosen). Reader contract:
  label-with-text reading order is required, verified on the corpus.
- Pages carry running noise: `PRESIDEN / REPUBLIK INDONESIA` and page labels
  such as `- 20 -`.
- The text layer itself contains OCR-grade glitches (`lnformasi`, `( 1)`,
  `Pasal2`): the pipeline must tolerate marker variants and must not "fix" body
  text.
- The *Penjelasan* (elucidation) repeats `Pasal N` headings (`Pasal 1 / Cukup
  jelas.`). Naive counting double-counts articles (PP 33/2026: 417 `Pasal`
  lines vs ~10 chapters), so **zones are mandatory**.

## 2. Models (package `regulus.documents`; Phase 1 domain unchanged)

| Type | Meaning | Key fields |
|---|---|---|
| `Document` | One source file | `id`, `regulation_id`, `content_hash`, `text_fingerprint`, `page_count` |
| `Page` | One physical page | `number` (1-based), `label` (printed, optional), `source` (`NATIVE`/`OCR`), `status`, `text`, `removed` (`RemovedLine(index, text, kind)`, kind `NOISE`/`CATCHWORD`), `ocr_engine`, `ocr_confidence` |
| `SourceSpan` | A location | `document_id`, `page`, `start`, `end` (offsets into that `Page.text`, end exclusive) |
| `AmendmentUnit` | Roman-numeral body unit of an amending regulation (`Pasal I`, `Pasal II`) | `id` (`f"{regulation_id}:unit-{label}"`), `label`, `text`, `page_start`, `page_end`, `text_hash` |
| `Provision` | Ayat/huruf/angka inside an article or unit | `owner_id`, `level`, `path` (e.g. `("(2)", "b")`), `text`, `span` (owner-relative) |
| `Explanation` | Penjelasan unit | `article_number`, `text`, `fragments` |
| `Diagnostic` | A finding | `code`, `severity`, `page`, `article_number`, `detail` |
| `ProcessedDocument` | The result | `document`, `status`, `pages`, `articles`, `amendment_units`, `provenance`, `provisions`, `explanations`, `diagnostics` |

Articles are the **Phase 1 `Article`**, produced as-is:
`id = f"{regulation_id}:{number}"`, `page_start/page_end` from the fragments,
`text_hash` via `Article.of`. Phase 1 deferred the meaning of `Article.parent`;
it is now fixed: the structural path of enclosing headings joined by `" > "`,
e.g. `"BAB III > Bagian Kedua > Paragraf 1"`, `None` if none.

`regulation_id` is **supplied by the caller**. Document processing never decides
which regulation a file is (that is Phase 2's identity).

## 3. Provenance (the most important property)

`provenance[owner_id]` (article or amendment unit) is an ordered tuple of
`SourceSpan` fragments, one contiguous slice per page the owner touches.

**Exact text construction (no other normalization exists):**

1. `Page.text` is the reader output with line endings normalized (`\r\n`, `\r` → `\n`), noise lines deleted (each whole line including its terminating `\n`), and nothing else: no whitespace collapsing, no hyphen joining, no Unicode normalization, no spelling repair.
2. An owner's region on a page runs from its marker line (or the page start, for a continuation) up to the line before the next boundary, on line boundaries.
3. **Boundary trimming** moves `start` forward and `end` backward over leading/trailing characters for which `str.isspace()` is true, **before** the offsets are recorded. Recorded offsets therefore already exclude trimmed whitespace. A fragment that trims to empty is dropped.
4. `owner.text = "\n".join(page.text[f.start:f.end] for f in fragments)`, built directly with no further strip (Phase 1 `Article.of` stripping must therefore be a no-op, asserted). The `"\n"` between fragments belongs to no page.

Invariants:

1. `owner.text == reconstruct(fragments, pages)` where `reconstruct` is exactly the expression in (4). One definition, no "approximately".
2. `page_start/page_end` equal the first/last fragment page.
3. Offsets index into `Page.text` (the cleaned text); removed lines are kept in `Page.removed` with line index, text and kind, so nothing is silently lost.
4. `locate(owner_id, start, end) -> tuple[SourceSpan, ...]` maps any span in `owner.text` (e.g. a Phase 1 `ObligationEvidence.span`) to page-level spans. `locate` of the full text returns the fragments; a round-trip test must hold for every owner in the corpus.

So any later obligation answers: document id → page → article → character span.

## 4. Page reading

`PageReader(bytes) -> tuple[Page | PageFailure, ...]`, one entry per physical page. The native adapter is **pdfplumber** (pure Python, no system binary); pages sent to OCR are rasterized through pdfplumber's page image (`page.to_image`).

- **Per-page** decision (a file may be native, scanned, native): a page is `NATIVE` if its pdfplumber text has ≥ 50 non-whitespace characters, else it goes to the injected `OcrEngine`. The threshold is a documented constant, checked against the corpus (no real page falls below it).
- OCR output records `ocr_engine` (id + version) and `ocr_confidence` (if provided). Determinism is relative to the pinned engine; tests use a fake engine.
- OCR is **never guessed back to correctness**: `Pasal I` for `Pasal 1`, `ada1ah` stay as read. A mis-read structural marker surfaces as a diagnostic (§6), exactly as Phase 2 refuses to guess a target.
- **Selection rule when OCR is attempted:** the OCR result is used only if its non-whitespace character count is at least the native extraction's; otherwise the native text is kept (`source = NATIVE`). OCR never replaces better native text.
- **No engine configured:** a page with no text and with images is `FAILED` (`no text layer and no OCR engine`, never silently empty); a page with no text and no images is a legitimately blank `EMPTY` page; a short native page (< 50 characters but non-empty) is kept as native.
- A page with no text from either path is `EMPTY`; an engine error/timeout/unreadable page is `FAILED`.
- Unreadable file (corrupt, encrypted, zero pages): `FAILED` document, no pages, with the document-level `UNREADABLE_DOCUMENT` (ERROR) diagnostic. `PAGE_FAILED` means a physical page could not be processed; `UNREADABLE_DOCUMENT` means the file could not be opened as a page sequence.
- U+FFFD or control characters in text ⇒ `ENCODING_ISSUE` warning on that page; text is kept verbatim.

## 5. Cleaning, zones, segmentation (pure)

**Noise.** A line is noise if it matches the page-label form `^-\s*\d+\s*-$`, or if the same normalized line appears in the first 6 or last 4 lines of ≥ 50 % of pages (minimum 4 pages). Removed lines are recorded (§3.3).

**Catchword noise.** Gazette copies print, at the bottom of a page, the opening
words of the next page followed by an ellipsis tail (`14. Kesepakatan . . .`,
`Pasal 2 ...`, `(4) Pemasangan ...`, `Bagian ...`), and the next page then starts
with the full line. Evidence (12 corpus PDFs): ~160 such lines in PP 33/2026
alone, across every structural form, not only numbered ones. They contaminate
`Article.text` and can seed a provision with the pointer instead of the real
line. A line is a catchword, and is removed with `kind = CATCHWORD`, only if
**all** hold:

1. it is among the last 4 non-empty lines of a page, after noise removal;
2. it ends with an ellipsis tail of ≥ 2 dots (spaces allowed between), and the text before the tail contains a letter or digit;
3. the next physical page is read (not `FAILED`/`EMPTY`) and one of its first 6 non-empty lines, normalized (whitespace collapsed, case-folded), **starts with** the normalized text before the tail (position + adjacency + prefix repetition).

Not sufficient on their own: repetition (a legitimate line may repeat), or the
ellipsis alone. A bottom-edge ellipsis line whose continuation is not found stays
in the text (conservative; known limitation, e.g. when the continuation line has
a text-layer glitch). Removal happens in `clean`, before offsets exist, so it
changes no article numbering, provision numbering or provenance semantics, and
the removed line stays in `Page.removed`.

**Zones** (first match wins, in order): `PREAMBLE` (title, Menimbang, Mengingat) → `BODY` (from the first `BAB`/`Pasal 1` after `MEMUTUSKAN`/`Menetapkan`) → `CLOSING` (`Ditetapkan di …`) → `EXPLANATION` (line `PENJELASAN`) → `ANNEX` (`LAMPIRAN`). **Only `BODY` produces articles.** `EXPLANATION` produces `Explanation` units keyed by article number. `ANNEX` is not processed and always emits `ANNEX_NOT_PROCESSED` (known limitation, never silent).

**Markers** (whole-line forms; no mid-line splitting):

| Level | Form |
|---|---|
| BAB | `BAB <roman>` + following title line(s) |
| Bagian | `Bagian <Kesatu…|ke-n>` |
| Paragraf | `Paragraf <n>` |
| Pasal | `Pasal <n>[A-Z]` (tolerates `Pasal2`); amending form `Pasal <roman>` |
| Ayat | `(n)` at line start (tolerates `( 1)`) |
| Huruf | `x.` (single letter) |
| Angka | `n.` |

**Sequence rule (the false-positive guard).** A marker opens a boundary only if
it is the expected successor: first ayat `(1)`, first huruf `a.`, first angka
`1.`, next = successor; Pasal `n` after `m` accepted when `n = m+1` or `n = m`
with a letter suffix progression (`5`, `5A`). Otherwise:

- number > expected (a gap): accepted as a boundary **and** `ARTICLE_GAP` (ERROR) names the missing numbers;
- number ≤ already seen (duplicate/backward): treated as text, `DUPLICATE_ARTICLE` (ERROR);
- out-of-sequence ayat/huruf/angka: treated as text, `MARKER_OUT_OF_SEQUENCE` (WARNING).

This makes a stray line such as `b. …` inside a sentence harmless.

**Nesting.** Provision rank: ayat 1 > huruf 2 > angka 3; a marker pops the stack to ranks above it. An angka list directly under a Pasal (the definitions article) has path `("1",)`. Provisions are descriptive units over article text; the **Article is the authority** for evidence.

**Continuation.** A page break never closes an article. Text before the first marker on a page attaches to the open article; a marker as the last line of a page opens an article whose first fragment is that line and whose text continues on the next page.

**Amending regulations (structure only).** `Pasal I`, `Pasal II`, … are
recognized as `AmendmentUnit`s, in sequence by Roman value (same gap/duplicate
rules, e.g. `ARTICLE_GAP` naming the missing labels). Phase 3 preserves their
text, provenance and provisions (numbered points `1.`, `2.`) and does **not**
interpret them: what a unit amends, replaces or inserts is Phase 5 lineage.

- **Body mode** follows the first `Pasal` marker's form (Roman ⇒ amending, Arabic ⇒ standard).
- In amending mode only Roman markers open boundaries. `Pasal 5` lines inside a unit are **quoted amended text**, not articles, and stay inside the unit.
- Cross-check: if the title zone contains `PERUBAHAN` and the mode is standard, or the title lacks it and the mode is amending, emit `BODY_MODE_CONFLICT` (ERROR). This is the guard against an OCR-misread first marker silently flipping the mode.
- Once the first `Pasal` marker fixes the mode, a later marker of the opposite form is handled by that mode. **Standard mode:** a Roman `Pasal I`-style line is not a boundary; it stays text and emits `MIXED_BODY_FORMS` (ERROR). **Amending mode:** Arabic `Pasal n` lines inside a Roman unit are quoted amendment text; they open no article or unit and emit nothing.

## 6. Statuses and failure semantics

Page: `OK`, `EMPTY`, `FAILED`. Document `status`:

| Status | Condition |
|---|---|
| `FAILED` | file unreadable, or every page `FAILED` |
| `PARTIAL` | ≥ 1 page `FAILED` and ≥ 1 page read; `PAGE_FAILED` (ERROR) per page |
| `PROCESSED_EMPTY` | all pages read, zero body units (no articles and no amendment units) in `BODY` (`NO_BODY_UNITS` diagnostic). Says nothing about whether the PDF had text: pages and text are still returned |
| `PROCESSED_WITH_ISSUES` | all pages read, ≥ 1 body unit, ≥ 1 ERROR diagnostic (gap, duplicate, mode conflict…) |
| `PROCESSED_OK` | all pages read, ≥ 1 body unit, no ERROR diagnostic (warnings allowed) |

`NOT_PROCESSED` is the absence of a result. **Only `PROCESSED_OK` is eligible
for downstream extraction without human acknowledgement.** Acknowledgement never rewrites the status: the processing fact is immutable, and a human acceptance is a separate record (`status = PARTIAL`, `acknowledged = true`), defined in the review/audit phases. `PARTIAL` is never
silently usable: a failed page could hold an article or an ayat, and a missing
obligation must not read as "no obligation" (Phase 0 §9). Articles from readable
pages of a `PARTIAL` document are still returned, marked by the status, for
inspection. No retries inside this phase; retry policy is workflow (Phase 11/14).

Diagnostic codes: `PAGE_FAILED`, `ARTICLE_GAP`, `DUPLICATE_ARTICLE`,
`BODY_MODE_CONFLICT`, `MIXED_BODY_FORMS`, `NO_BODY_UNITS`, `UNREADABLE_DOCUMENT` (ERROR); `MARKER_OUT_OF_SEQUENCE`,
`PAGE_EMPTY`, `LOW_OCR_CONFIDENCE`, `ENCODING_ISSUE`, `ANNEX_NOT_PROCESSED`,
`DUPLICATE_CONTENT` (WARNING).

## 7. Identity and idempotency

- `content_hash` = SHA-256 of the **raw file bytes**; `Document.id = "doc-" + content_hash[:16]`. Identity is the file.
- `text_fingerprint` = SHA-256 of the cleaned page texts joined by `"\n"`. Informational only, never identity: the same regulation from two sources has different bytes but equal fingerprints, flagged `DUPLICATE_CONTENT` by the caller's store, not decided here.
- Same bytes + same engine ⇒ byte-identical `ProcessedDocument` (stable ordering, no timestamps in the result). Reprocessing is idempotent; same bytes means same document id, so the store deduplicates.

## 8. Interfaces and module layout

```
src/regulus/documents/
├── models.py       Document, Page, SourceSpan, Provision, Explanation, Diagnostic, ProcessedDocument
├── clean.py        noise removal (pure)
├── segment.py      zones, markers, sequence rule, provisions (pure)
├── provenance.py   fragments, reconstruct, locate (pure)
├── reader.py       PageReader / OcrEngine protocols, pdfplumber native adapter
└── processor.py    process(bytes, regulation_id, reader) -> ProcessedDocument
tests/documents/
```

`process` is the only orchestrating function; it does no I/O besides calling the
injected reader.

## 9. Adversarial cases (each needs a test)

| Case | Expected |
|---|---|
| Clean native text PDF | `PROCESSED_OK`; articles contiguous; provenance reconstructs |
| Scanned page (synthetic image + fake OCR) | page `OCR`, text matches fake output |
| Mixed native / scan / native | per-page source recorded; one document |
| OCR misreads `Pasal 1` as `Pasal I` (title has no `PERUBAHAN`) | no guess; `BODY_MODE_CONFLICT`; `PROCESSED_WITH_ISSUES` |
| One page OCR fails | `PARTIAL`, `PAGE_FAILED`, others returned, not eligible |
| All pages fail / corrupt / encrypted / zero pages | `FAILED`, no articles |
| Blank page | `EMPTY` page, `PAGE_EMPTY`, status unaffected |
| Gap (5 → 7) / duplicate / backward numbering | `ARTICLE_GAP` / `DUPLICATE_ARTICLE`, `PROCESSED_WITH_ISSUES` |
| Stray `b.` mid-sentence, ayat out of order | stays text, warning |
| Article crossing a page break; marker as last line of a page | single article, two fragments |
| Running header/footer and page labels | removed from `Page.text`, kept in `Page.removed` |
| Catchword at page bottom, continuation at next page top | removed (`CATCHWORD`), recorded; article text and provenance exclude it |
| Same ellipsis line, continuation absent / next page differs | retained |
| Ellipsis line mid-page (not in bottom edge) | retained |
| Line without ellipsis tail at page bottom (e.g. a real `14.` provision) | retained |
| Next page `EMPTY`/`FAILED` | catchword retained (no adjacency evidence) |
| Numbered catchword across pages | list continues: `14.` accepted once, no `MARKER_OUT_OF_SEQUENCE` |
| Penjelasan repeating `Pasal N` | explanations only, no extra articles |
| Annex present | `ANNEX_NOT_PROCESSED` |
| `Pasal I`/`II` body (amending regulation, title `PERUBAHAN`) | `AmendmentUnit`s, text and provenance preserved, no semantics; `PROCESSED_OK` |
| Quoted `Pasal 5` inside `Pasal I` | stays inside the unit, no article created |
| Roman and Arabic body markers mixed | `MIXED_BODY_FORMS`, later form treated as text |
| Roman unit gap (`I` → `III`) | `ARTICLE_GAP` naming `II` |
| Trimming | offsets exclude trimmed whitespace; `reconstruct` equals `article.text` byte for byte; whitespace-only fragment dropped |
| No `Pasal` at all (non-conforming file) | `PROCESSED_EMPTY`, pages and text still present |
| U+FFFD / bad encoding | `ENCODING_ISSUE`, text verbatim |
| Same bytes twice | same id, identical result |
| Same text, different bytes | different id, same fingerprint |
| Reprocess | byte-identical JSON |
| `locate` round-trip for every article | spans reconstruct the quoted text |
| Phase 1 compatibility | every produced `Article` validates (hash, pages) |

## 10. Non-goals

Meaning, relevance, sector, obligations, lineage, cross-reference resolution;
what an amendment unit amends or inserts (Phase 5); tables, figures, signatures,
annexes; language/spelling correction; layout analysis beyond what
pdfplumber's text extraction gives (tables are out of scope); language detection; persistence; retries.

## 11. Gate

Contract frozen after adversarial review → implementation module by module with
tests → every §9 case passing → ruff/mypy strict clean → real-corpus check →
freeze.

**Real-corpus check:** committed tests never contain a third-party PDF. They use
(a) short public-law excerpts with LN/TLN citation turned into synthetic PDFs at
test time, and (b) a local-only suite, skipped when `pdf/` is absent, that
asserts properties on the real corpus: contiguous body article numbers, zero
`PROCESSED_OK` documents with errors, `locate` round-trip for every article, and
that no `EXPLANATION` text is in any article.

## 12. Decisions

1. **Five statuses kept**; `PROCESSED_WITH_ISSUES` and `PARTIAL` stay distinct.
2. **`PARTIAL` returns readable articles**, never silently usable; acknowledgement is a separate record and never rewrites the processing status (§6).
3. **OCR:** `PageReader` and `OcrEngine` are protocols; pdfplumber is the native adapter; Tesseract (`ind`, optional extra) is an adapter only, skipped in CI when absent.
4. **Fixtures:** ReportLab (dev/test dependency) generates synthetic PDFs at test time; no binaries committed.
5. **Amending regulations:** structurally supported now as `AmendmentUnit`s (§5); semantics stay in Phase 5.
6. **Penjelasan:** modelled as `Explanation` units, separate from `Article`.
7. **`PROCESSED_EMPTY`** means no body units were found, not that the file had no text (§6).
8. **Text construction** is the single definition in §3; there is no other normalization.
9. **Catchword noise** is removed deterministically (§5): bottom-edge ellipsis line whose prefix is repeated at the next page's top; recorded as `CATCHWORD` in `Page.removed`. Evidence showed catchwords in every structural form, so the rule is not limited to numbered lines; adjacency and prefix repetition keep it conservative.
10. **`MIXED_BODY_FORMS`** applies only in standard mode; Arabic markers inside an amendment unit are quoted text (§5).
11. **OCR selection:** OCR is used only when not shorter than native text; no-engine behavior is defined in §4.
12. **`UNREADABLE_DOCUMENT`** is an ERROR diagnostic for files that cannot be opened (§4, §6).
