from pathlib import Path

from regulus.generation.evaluate import (
    candidates_for,
    load_contradictions,
    run_contradictions,
    run_generation,
    run_mutations,
)
from regulus.obligations.evaluate import load_gold

from ..builder import EC, HARD0, Builder

L = "generation"


def evaluate(b: Builder, root: Path) -> None:
    pairs = candidates_for(load_gold(root / "obligations" / "gold.v1.json"))
    g = run_generation(pairs)
    mut = run_mutations(pairs)
    con = run_contradictions(load_contradictions(root / "generation" / "contradictions.v1.json"))
    n_mut = sum(mut.applicable.values())
    b.population("generation.candidates", "candidates produced from the extraction gold", "evaluation/obligations/gold.v1.json", len(pairs),
                 "derived from the extraction gold", "same authorship as the extraction gold")  # fmt: skip
    b.population("generation.mutations", "applied fault injections", "regulus.generation.evaluate.MUTATIONS", n_mut,
                 "system author", "covers the listed fault families only")  # fmt: skip
    b.population("generation.contradictions", "hand-written contradicting outputs", "evaluation/generation/contradictions.v1.json", con.total,
                 "system author", "includes enumerated known gaps")  # fmt: skip
    m = b.metric
    b.record(m(f"{L}.undetected_mutations", L, "undetected mutation rate", "generation.mutations", "mutated outputs the verifier accepted", "applied mutations", EC.MUTATION, HARD0),
             n_mut - sum(mut.detected.values()), n_mut)  # fmt: skip
    b.record(m(f"{L}.unexpected_accepted_contradictions", L, "unexpected accepted contradiction rate", "generation.contradictions", "accepted contradictions not listed as known gaps", "contradiction cases", EC.MUTATION, HARD0),
             len(con.accepted_unexpected), con.total)  # fmt: skip
    b.record(m(f"{L}.accepted_known_gap_contradictions", L, "accepted known-gap contradiction rate", "generation.contradictions", "accepted contradictions listed as known gaps", "contradiction cases", EC.MUTATION),
             len(con.accepted_known_gaps), con.total, ", ".join(con.accepted_known_gaps))  # fmt: skip
    b.known_gaps.extend(
        f"generation: accepted known-gap contradiction {c}" for c in con.accepted_known_gaps
    )
    p = "generation.candidates"
    b.record(
        m(
            f"{L}.hallucinated_tokens",
            L,
            "hallucinated token rate",
            p,
            "tokens of generated text absent from the permitted source",
            "tokens of generated text",
            EC.PROPERTY,
            HARD0,
        ),
        g.hallucinated_tokens,
        g.tokens_checked,
    )
    b.record(
        m(
            f"{L}.field_accounting",
            L,
            "field accounting violation rate",
            p,
            "trace references that are duplicated or untraced",
            "trace references",
            EC.PROPERTY,
            HARD0,
        ),
        g.unaccounted_fields,
        g.trace_refs,
    )
    b.record(
        m(
            f"{L}.open_question_preservation",
            L,
            "open-question loss rate",
            p,
            "candidates with an undetermined part and no open question",
            "candidates with an undetermined part",
            EC.PROPERTY,
            HARD0,
        ),
        g.open_question_missing,
        g.undetermined_candidates,
    )
    b.record(
        m(
            f"{L}.evidence_citation",
            L,
            "evidence citation violation rate",
            p,
            "evidence items whose quote is not at their span",
            "evidence items",
            EC.PROPERTY,
            HARD0,
        ),
        g.citation_failures,
        g.evidence_checked,
    )
