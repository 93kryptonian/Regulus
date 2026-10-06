from collections import defaultdict
from collections.abc import Iterable, Sequence

from regulus.domain import Regulation
from regulus.domain import RegulationKind as K

from .models import Effect, ImpactItem, IntegrityIssue, IssueCode, LineageRelation, RelationType
from .relations import sha

RANK = {K.UU: 1, K.PERPU: 1, K.PP: 2, K.PERPRES: 3, K.PERMEN: 4, K.POJK: 4, K.OTHER: 4}
WITHDRAWING = {Effect.DELETED, Effect.REPEALED}
CHANGING = {Effect.MODIFIED, Effect.ADDED}


def _issue(code: IssueCode, rel_ids: Iterable[str], detail: str = "") -> IntegrityIssue:
    ids = tuple(sorted(rel_ids))
    return IntegrityIssue(
        id="iss-" + sha(code, *ids, detail)[:16], code=code, relation_ids=ids, detail=detail
    )


def _components(edges: Sequence[tuple[str, str]]) -> list[set[str]]:
    graph: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        graph[a].append(b)
        graph.setdefault(b, [])
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[set[str]] = []
    counter = 0

    def visit(v: str) -> None:
        nonlocal counter
        index[v] = low[v] = counter
        counter += 1
        stack.append(v)
        on.add(v)
        for w in graph[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = set()
            while True:
                w = stack.pop()
                on.discard(w)
                comp.add(w)
                if w == v:
                    break
            if len(comp) >= 2:
                out.append(comp)

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return out


def check_relations(
    relations: Sequence[LineageRelation], regulations: dict[str, Regulation]
) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    by = {(r.type, r.source_id, r.target_id): r for r in relations}
    for r in relations:
        if r.source_id == r.target_id:
            issues.append(_issue(IssueCode.SELF_RELATION, [r.id]))
        tgt = regulations.get(r.target_id)
        if (
            tgt
            and tgt.promulgated_on
            and any(e.occurred_on < tgt.promulgated_on for e in r.evidence)
        ):
            issues.append(_issue(IssueCode.ANACHRONISM, [r.id], f"before {tgt.id}"))
        if r.type is RelationType.IMPLEMENTS:
            s = regulations.get(r.source_id)
            if s and tgt and RANK[s.kind] <= RANK[tgt.kind]:
                issues.append(
                    _issue(IssueCode.HIERARCHY_INVERSION, [r.id], f"{s.kind}->{tgt.kind}")
                )
            for other in (
                RelationType.AMENDS,
                RelationType.REPEALS,
                RelationType.PARTIALLY_REPEALS,
            ):
                if (other, r.source_id, r.target_id) in by:
                    issues.append(
                        _issue(
                            IssueCode.CONFLICTING_DECLARATIONS,
                            [r.id, by[(other, r.source_id, r.target_id)].id],
                        )
                    )
        if (
            r.type is RelationType.REPEALS
            and (RelationType.REPEALS, r.target_id, r.source_id) in by
        ):
            back = by[(RelationType.REPEALS, r.target_id, r.source_id)]
            if r.id < back.id:
                issues.append(_issue(IssueCode.MUTUAL_REPEAL, [r.id, back.id]))
    for kind, min_size in ((RelationType.IMPLEMENTS, 2), (RelationType.REPEALS, 3)):
        rels = [r for r in relations if r.type is kind and r.source_id != r.target_id]
        for comp in _components([(r.source_id, r.target_id) for r in rels]):
            if len(comp) >= min_size:
                ids = [r.id for r in rels if r.source_id in comp and r.target_id in comp]
                issues.append(_issue(IssueCode.HIERARCHY_CYCLE, ids, ",".join(sorted(comp))))
    return issues


def check_operations(impacts: Sequence[ImpactItem]) -> list[IntegrityIssue]:
    groups: dict[tuple[str, str, object], list[ImpactItem]] = defaultdict(list)
    for i in impacts:
        if i.article_number is not None and not i.derived:
            groups[(i.target_regulation_id, i.article_number, i.occurred_on)].append(i)
    out = []
    for (reg, art, _), items in groups.items():
        effects = {i.effect for i in items}
        if effects & WITHDRAWING and effects & CHANGING:
            out.append(
                _issue(
                    IssueCode.CONFLICTING_OPERATIONS, {i.relation_id for i in items}, f"{reg}:{art}"
                )
            )
    return out
