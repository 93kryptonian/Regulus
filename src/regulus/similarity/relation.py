from regulus.obligations import FieldStatus

from .models import (
    CORE,
    FIELDS,
    PARAMS,
    FieldComparison,
    Label,
    Relation,
    RelationConfig,
    Representation,
    Verdict,
)


def jaccard(a: tuple[str, ...], b: tuple[str, ...]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 1.0


def compare(
    name: str, q: Representation, m: Representation, cfg: RelationConfig
) -> FieldComparison:
    a, b = q.fields[name], m.fields[name]
    if FieldStatus.UNDETERMINED in (a.state, b.state):
        rel, j = Relation.UNDETERMINED, None
    elif a.state is FieldStatus.NOT_STATED and b.state is FieldStatus.NOT_STATED:
        rel, j = Relation.BOTH_NOT_STATED, None
    elif FieldStatus.NOT_STATED in (a.state, b.state):
        rel, j = Relation.ONE_MISSING, None
    else:
        j = jaccard(a.tokens, b.tokens)
        rel = (
            Relation.EQUAL
            if a.tokens == b.tokens
            else Relation.OVERLAP
            if j >= cfg.tau_overlap
            else Relation.DIFFERENT
        )
    return FieldComparison(
        field=name, query_value=a.value, match_value=b.value, relation=rel, jaccard=j
    )


def composite(comparisons: dict[str, FieldComparison], cfg: RelationConfig) -> float:
    total = sum(cfg.weights.values()) or 1.0
    score = 0.0
    for name, c in comparisons.items():
        w = cfg.weights.get(name, 0.0)
        if c.relation is Relation.EQUAL:
            score += w
        elif c.relation is Relation.OVERLAP and c.jaccard is not None:
            score += w * c.jaccard
    return round(score / total, 6)


def classify(q: Representation, m: Representation, cfg: RelationConfig | None = None) -> Verdict:
    cfg = cfg or RelationConfig()
    cmp = {name: compare(name, q, m, cfg) for name in FIELDS}
    ordered = tuple(cmp[n] for n in FIELDS)
    caps: list[str] = []
    core_ok = all(
        cmp[n].relation in (Relation.EQUAL, Relation.OVERLAP, Relation.DIFFERENT) for n in CORE
    )
    for n in CORE:
        if cmp[n].relation in (
            Relation.UNDETERMINED,
            Relation.ONE_MISSING,
            Relation.BOTH_NOT_STATED,
        ):
            caps.append(
                f"CAPPED_BY_UNDETERMINED({n})"
                if cmp[n].relation is Relation.UNDETERMINED
                else f"CAPPED_BY_MISSING({n})"
            )
    modality_known = q.modality is not None and m.modality is not None
    if not modality_known:
        caps.append("CAPPED_BY_UNDETERMINED(modality)")
    core_match = core_ok and all(
        cmp[n].relation is Relation.EQUAL
        or (cmp[n].relation is Relation.OVERLAP and (cmp[n].jaccard or 0.0) >= cfg.tau_dup)
        for n in CORE
    )
    supporting = tuple(n for n in FIELDS if cmp[n].relation in (Relation.EQUAL, Relation.OVERLAP))
    score = composite(cmp, cfg)
    if core_match and modality_known:
        if q.modality is not m.modality:
            return Verdict(
                label=Label.CONTRADICTORY_MODALITY,
                comparisons=ordered,
                supporting_fields=supporting,
                composite=score,
            )
        params = [cmp[n] for n in PARAMS]
        if any(
            c.relation in (Relation.DIFFERENT, Relation.ONE_MISSING, Relation.OVERLAP)
            for c in params
        ):
            return Verdict(
                label=Label.VARIANT,
                comparisons=ordered,
                supporting_fields=supporting,
                composite=score,
            )
        undet = [c.field for c in params if c.relation is Relation.UNDETERMINED]
        if undet:
            caps += [f"CAPPED_BY_UNDETERMINED({n})" for n in undet]
            return Verdict(
                label=Label.RELATED,
                comparisons=ordered,
                supporting_fields=supporting,
                cap_reasons=tuple(caps),
                composite=score,
            )
        if all(c.relation in (Relation.EQUAL, Relation.BOTH_NOT_STATED) for c in params):
            return Verdict(
                label=Label.POSSIBLE_DUPLICATE,
                comparisons=ordered,
                supporting_fields=supporting,
                composite=score,
            )
        return Verdict(
            label=Label.RELATED, comparisons=ordered, supporting_fields=supporting, composite=score
        )
    label = Label.RELATED if supporting else Label.SIMILAR_TEXT_ONLY
    return Verdict(
        label=label,
        comparisons=ordered,
        supporting_fields=supporting,
        cap_reasons=tuple(caps),
        composite=score,
    )
