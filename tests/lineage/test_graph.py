from datetime import date
from itertools import permutations

import pytest
from helpers import ACTOR, OTHER, TARGET, ev, make, reg

from regulus.domain import EventType as T
from regulus.domain import RegulationKind as K
from regulus.lineage import (
    ArticleStatus,
    Declaration,
    Effect,
    IssueCode,
    RelationType,
    lineage_of,
    project,
    project_article_status,
)
from regulus.lineage.models import EvidenceKind, ImpactItem, ImpactStatus, SourceRef

D1, D2, D3 = date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)


def codes(res) -> list[IssueCode]:  # type: ignore[no-untyped-def]
    return sorted(i.code for i in res.issues)


def decl(source, target, on=D2, did=None) -> Declaration:  # type: ignore[no-untyped-def]
    return Declaration(
        id=did or f"d-{source.id}-{target.id}",
        source_id=source.id,
        target_id=target.id,
        raw="melaksanakan",
        occurred_on=on,
    )


def test_event_types_map_to_relations_with_event_evidence() -> None:
    evs = [
        ev(ACTOR, T.AMEND, TARGET),
        ev(ACTOR, T.REPEAL, OTHER),
        ev(ACTOR, T.PARTIAL_REPEAL, reg(K.PP, "12", 2021)),
    ]
    res = project(make(evs, regs=[ACTOR, TARGET, OTHER, reg(K.PP, "12", 2021)]), analyze=False)
    assert sorted(r.type for r in res.relations) == sorted(
        [RelationType.AMENDS, RelationType.REPEALS, RelationType.PARTIALLY_REPEALS]
    )
    assert all(
        r.evidence[0].kind.value == "EVENT" and r.id.startswith("lin-") for r in res.relations
    )


def test_relations_are_timeless_with_dated_evidence() -> None:
    e1 = ev(ACTOR, T.AMEND, TARGET, on=D2, eid="a")
    e2 = ev(ACTOR, T.AMEND, TARGET, on=D3, eid="b")
    (rel,) = project(make([e2, e1]), analyze=False).relations
    assert [(x.ref, x.occurred_on) for x in rel.evidence] == [("a", D2), ("b", D3)]
    assert rel.id == project(make([e1]), analyze=False).relations[0].id


def test_needs_review_yields_unresolved_relation_only() -> None:
    e = ev(ACTOR, T.NEEDS_REVIEW, reason="UNRESOLVED_TARGET", declared_ref="PP 99/1999")
    res = project(make([e]), analyze=False)
    assert res.relations == () and res.unresolved_relations[0].declared_ref == "PP 99/1999"


def test_real_identity_implements_pairs_are_valid() -> None:
    uu27, pp33 = (
        reg(K.UU, "27", 2022, promulgated=date(2022, 10, 17)),
        reg(K.PP, "33", 2026, promulgated=date(2026, 7, 16)),
    )
    uu30, pp14 = (
        reg(K.UU, "30", 2009, promulgated=date(2009, 9, 23)),
        reg(K.PP, "14", 2012, promulgated=date(2012, 2, 16)),
    )
    inp = make(
        [],
        regs=[uu27, pp33, uu30, pp14],
        decl=[decl(pp33, uu27, date(2026, 7, 16)), decl(pp14, uu30, date(2012, 2, 16))],
    )
    res = project(inp, analyze=False)
    assert [r.type for r in res.relations] == [RelationType.IMPLEMENTS] * 2 and res.issues == ()


def test_hierarchy_inversion_is_flagged_but_kept() -> None:
    uu, pp = reg(K.UU, "1", 2000), reg(K.PP, "2", 2001)
    res = project(make([], regs=[uu, pp], decl=[decl(uu, pp)]), analyze=False)
    assert codes(res) == [IssueCode.HIERARCHY_INVERSION] and len(res.relations) == 1
    assert res.relations[0].integrity.value == "CONFLICT"
    same = project(
        make([], regs=[pp, reg(K.PP, "3", 2002)], decl=[decl(pp, reg(K.PP, "3", 2002))]),
        analyze=False,
    )
    assert codes(same) == [IssueCode.HIERARCHY_INVERSION]


def test_implements_cycle_and_self_relation() -> None:
    a, b = reg(K.PERMEN, "1", 2001), reg(K.PERMEN, "2", 2002)
    res = project(make([], regs=[a, b], decl=[decl(a, b), decl(b, a)]), analyze=False)
    assert IssueCode.HIERARCHY_CYCLE in codes(res)
    assert (
        codes(project(make([], regs=[a], decl=[decl(a, a)]), analyze=False)).count(
            IssueCode.SELF_RELATION
        )
        == 1
    )


def test_mutual_repeal_and_three_cycle_of_repeals() -> None:
    a, b, c = reg(K.PP, "1", 2001), reg(K.PP, "2", 2002), reg(K.PP, "3", 2003)
    mutual = project(make([ev(a, T.REPEAL, b), ev(b, T.REPEAL, a)], regs=[a, b]), analyze=False)
    assert codes(mutual) == [IssueCode.MUTUAL_REPEAL]
    cycle = project(
        make([ev(a, T.REPEAL, b), ev(b, T.REPEAL, c), ev(c, T.REPEAL, a)], regs=[a, b, c]),
        analyze=False,
    )
    assert codes(cycle) == [IssueCode.HIERARCHY_CYCLE]


def test_amends_cycle_across_time_is_valid() -> None:
    a, b = (
        reg(K.PP, "1", 2001, promulgated=date(2001, 1, 1)),
        reg(K.PP, "2", 2002, promulgated=date(2002, 1, 1)),
    )
    res = project(
        make([ev(b, T.AMEND, a, on=D1), ev(a, T.AMEND, b, on=D2)], regs=[a, b]), analyze=False
    )
    assert res.issues == () and len(res.relations) == 2


def test_anachronism() -> None:
    late_target = reg(K.PP, "10", 2020, promulgated=date(2030, 1, 1))
    res = project(make([ev(ACTOR, T.AMEND, late_target)], regs=[ACTOR, late_target]), analyze=False)
    assert codes(res) == [IssueCode.ANACHRONISM] and res.relations[0].integrity.value == "CONFLICT"
    ok = project(make([ev(ACTOR, T.AMEND, TARGET)]), analyze=False)
    assert ok.issues == ()


def test_conflicting_declaration_against_event_for_the_same_pair() -> None:
    res = project(make([ev(ACTOR, T.REPEAL, TARGET)], decl=[decl(ACTOR, TARGET)]), analyze=False)
    assert IssueCode.CONFLICTING_DECLARATIONS in codes(res)


def test_duplicate_inputs_are_merged_and_reported_informationally() -> None:
    e = ev(ACTOR, T.AMEND, TARGET, eid="same")
    res = project(make([e, e]), analyze=False)
    assert len(res.relations) == 1 and codes(res) == [IssueCode.DUPLICATE_RELATION]
    assert res.relations[0].integrity.value == "OK"


def impact(on, effect, article="5", rid="r", iid=None, status=ImpactStatus.RESOLVED):  # type: ignore[no-untyped-def]
    return ImpactItem(
        id=iid or f"i-{effect}-{on}",
        relation_id=rid,
        event_id="e",
        occurred_on=on,
        target_regulation_id="T",
        article_number=article,
        effect=effect,
        source=SourceRef(kind=EvidenceKind.EVENT, ref="e"),
        status=status,
    )


def test_article_status_chain_and_order_independence() -> None:
    items = [impact(D1, Effect.MODIFIED), impact(D2, Effect.MODIFIED), impact(D3, Effect.REPEALED)]
    outs = {project_article_status(p, "T", "5").model_dump_json() for p in permutations(items)}
    assert len(outs) == 1
    assert project_article_status(items, "T", "5").status is ArticleStatus.WITHDRAWN
    assert project_article_status(items[:2], "T", "5").status is ArticleStatus.AMENDED
    assert project_article_status([], "T", "5").status is ArticleStatus.IN_FORCE
    assert project_article_status(items, "T", "6").status is ArticleStatus.IN_FORCE


def test_amendment_after_withdrawal_is_an_anomaly() -> None:
    items = [impact(D1, Effect.DELETED), impact(D3, Effect.MODIFIED, iid="late")]
    out = project_article_status(items, "T", "5")
    assert out.status is ArticleStatus.WITHDRAWN and out.anomalies == ("late",)


def test_unresolved_impacts_do_not_change_status() -> None:
    items = [impact(D1, Effect.DELETED, status=ImpactStatus.UNRESOLVED)]
    assert project_article_status(items, "T", "5").status is ArticleStatus.IN_FORCE


def test_same_day_conflicting_operations() -> None:
    from helpers import amending, doc, target_articles

    pts = (
        "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut: x",
        "2. Pasal 5 dihapus.",
    )
    from helpers import INTRO

    e = ev(ACTOR, T.AMEND, TARGET)
    inp = make(
        [e], {ACTOR.id: doc(ACTOR, amending(INTRO, *pts))}, {TARGET.id: target_articles("5")}
    )
    res = project(inp)
    assert (
        IssueCode.CONFLICTING_OPERATIONS in codes(res)
        and res.relations[0].integrity.value == "CONFLICT"
    )


def test_lineage_of_orders_by_first_evidence() -> None:
    e1, e2 = ev(ACTOR, T.AMEND, TARGET, on=D3), ev(OTHER, T.AMEND, TARGET, on=D1)
    rels = project(make([e1, e2]), analyze=False).relations
    assert [r.source_id for r in lineage_of(rels, TARGET.id)] == [OTHER.id, ACTOR.id]
    assert lineage_of(rels, "nobody") == ()


def test_project_is_deterministic_under_shuffled_input_and_pure() -> None:
    from helpers import INTRO, amending, doc, target_articles

    evs = [ev(ACTOR, T.AMEND, TARGET), ev(OTHER, T.AMEND, TARGET, on=D1), ev(ACTOR, T.NEW)]
    docs = {ACTOR.id: doc(ACTOR, amending(INTRO, "1. Pasal 7 dihapus."))}
    outs = set()
    for p in permutations(evs):
        inp = make(list(p), docs, {TARGET.id: target_articles("7")})
        snap = inp.model_dump_json()
        outs.add(project(inp).model_dump_json())
        assert inp.model_dump_json() == snap
    assert len(outs) == 1


def test_analyze_false_builds_the_graph_without_requiring_documents() -> None:
    res = project(make([ev(ACTOR, T.AMEND, TARGET)]), analyze=False)
    assert res.complete and res.impacts == () and len(res.relations) == 1
    assert not project(make([ev(ACTOR, T.AMEND, TARGET)])).complete


@pytest.mark.parametrize("n", [0, 1])
def test_empty_input(n: int) -> None:
    assert project(make([])).relations == () and project(make([])).complete
