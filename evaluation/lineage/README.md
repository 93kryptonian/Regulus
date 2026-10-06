# Lineage gold set (v1)

`gold_ops.v1.json`: 38 operation sentences (20 resolved, 18 unresolved by design),
each with a written rationale. Sources: synthetic standard drafting formulas,
and sentences from two real amending instruments (official BPK copies kept local):
PP 20/1980 (LN 1980/30) and UU 21/1982 (LN 1982/52, TLN 3235).

The set was authored together with the grammar, so perfect agreement is a regression
check, not a coverage claim. The coverage evidence is the real-instrument run
(`pytest -m corpus`): 0 false resolutions, unsupported formulas surfaced as unresolved.

Run: `pytest tests/lineage/test_lineage_evaluate.py` (metrics pinned there).

## Grammar v1.1 backlog (not implemented)

1. `Pada Pasal N, ditambahkan dengan ketentuan …`
2. `perkataan "X" diubah menjadi "Y"`
3. compound points with a context line (`Pada Pasal 6 :` + lettered sub-operations)
4. title amendments (`Pada judul … diubah`)
5. `Ditambah ayat baru menjadi ayat (n)`
6. target named inside the operation sentence for units that name several laws

Each needs its own semantics, tests and a contract amendment before implementation.
