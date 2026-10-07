from pathlib import Path

from regulus.similarity.evaluate import evaluate, load_gold

from ..builder import EC, HARD0, TARGET0, Builder
from ..models import Formula

L = "similarity"
POP = "similarity.gold"


def evaluate_layer(b: Builder, root: Path) -> None:
    gold = load_gold(root / "similarity" / "gold.v1.json")
    r = evaluate(gold)
    b.population(POP, "labelled query-match pairs", "evaluation/similarity/gold.v1.json", r.pairs, "system author, with a rationale per pair",
                 "synthetic variants derived from generated obligations; 12 queries; includes hard negatives")  # fmt: skip
    m = b.metric
    with_gold = [q for q in r.per_query if q[1] >= 1]
    b.record(m(f"{L}.recall_at_3", L, "Recall@3", POP, "queries whose top 3 contain at least one gold match", "queries with at least one gold match", EC.REGRESSION),
             sum(1 for q in with_gold if q[3] >= 1), len(with_gold), f"{len(r.per_query) - len(with_gold)} queries without a gold match excluded")  # fmt: skip
    b.record(m(f"{L}.precision_at_3", L, "Precision@3", POP, "gold matches among returned top-3 matches, pooled", "returned top-3 matches, pooled", EC.REGRESSION),
             sum(q[3] for q in with_gold), sum(q[2] for q in with_gold))  # fmt: skip
    b.record(m(f"{L}.mrr", L, "MRR", POP, "sum of reciprocal ranks of the first gold match (0 if absent)", "queries with at least one gold match", EC.REGRESSION, formula=Formula.MEAN),
             sum(1 / q[4] for q in with_gold if q[4] > 0), len(with_gold))  # fmt: skip
    cf = r.confusion
    b.record(m(f"{L}.label_accuracy", L, "relationship label accuracy", POP, "pairs with the gold label", "gold pairs", EC.REGRESSION),
             sum(cf[k][k] for k in cf), r.pairs)  # fmt: skip
    b.record(m(f"{L}.duplicate_precision", L, "POSSIBLE_DUPLICATE precision", POP, "predicted duplicates the gold confirms", "predicted POSSIBLE_DUPLICATE", EC.REGRESSION),
             r.duplicates_confirmed, r.duplicates_predicted)  # fmt: skip
    b.record(m(f"{L}.false_duplicate_rate", L, "false-duplicate rate", POP, "POSSIBLE_DUPLICATE returned where the gold is not a duplicate", "returned matches that are not gold duplicates", EC.REGRESSION, TARGET0),
             len(r.false_duplicates), r.returned_matches - r.returned_gold_duplicates)  # fmt: skip
    b.record(m(f"{L}.ceiling_and_evidence_violations", L, "ceiling and evidence violation rate", POP, "returned matches breaking a cap or lacking supporting fields", "returned matches", EC.PROPERTY, HARD0),
             r.cap_violations + r.unevidenced_labels, r.returned_matches)  # fmt: skip
    pd = m(
        f"{L}.provider_label_disagreements",
        L,
        "provider label disagreement rate",
        POP,
        "pairs labelled differently by the two configurations",
        "pairs returned by both",
        EC.PROPERTY,
    )
    b.record(pd, r.provider_disagreements, r.shared_pairs,
             "two lexical-embedding configurations (dimension 1024 and 64), not independent model families")  # fmt: skip
