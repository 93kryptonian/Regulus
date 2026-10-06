# Relevance gold set (v1)

40 author-labelled cases built from public regulation identities (real titles) plus
synthetic events and synthetic regulations for hard cases. Guideline `g1`, sample
scope: `FINANCIAL_SERVICES` and `DATA_PROTECTION` in scope; a change is relevant if
it concerns an in-scope sector or touches a monitored regulation.

Labels are illustrative portfolio judgements with a written rationale each, not
legal conclusions. Deliberate hard cases: lexicon false positives, vocabulary gaps,
weak text-only evidence, whole-word traps, cross-sector regulations.

Run: `pytest tests/relevance/test_evaluate.py` (metrics are pinned there).
