from regulus.domain import RegulatoryEvent

from .impact import Analysis, analyze_event
from .integrity import check_operations, check_relations
from .models import (
    Integrity,
    IntegrityIssue,
    IssueCode,
    LineageInput,
    LineageResult,
)
from .relations import EVENT_RELATION, build_relations, relation_id, sha


def _rel_id(event: RegulatoryEvent) -> str | None:
    t = EVENT_RELATION.get(event.type)
    return relation_id(t, event.regulation_id, event.target_id) if t and event.target_id else None


def _result(an: Analysis) -> dict[str, object]:
    impacts = sorted({i.id: i for i in an.impacts}.values(), key=lambda i: (i.occurred_on, i.id))
    changed = sorted(
        an.changed,
        key=lambda c: (
            c.regulation_id,
            c.article_number,
            c.kind,
            c.text_ref.owner_id,
            c.text_ref.start,
        ),
    )
    withdrawn = sorted(an.withdrawn, key=lambda w: (w.regulation_id, w.article_number, w.impact_id))
    unresolved = sorted(an.unresolved, key=lambda u: (u.event_id, u.owner_id, u.reason, u.detail))
    inc = sorted({x.ref: x for x in an.incomplete}.values(), key=lambda x: x.ref)
    return {
        "impacts": tuple(impacts),
        "changed": tuple(changed),
        "withdrawn": tuple(withdrawn),
        "unresolved_operations": tuple(unresolved),
        "incomplete_sources": tuple(inc),
        "complete": not inc,
    }


def analyze_impact(event: RegulatoryEvent, inp: LineageInput) -> LineageResult:
    an = analyze_event(event, _rel_id(event), inp)
    issues = tuple(sorted({i.id: i for i in an.issues}.values(), key=lambda i: i.id))
    return LineageResult(issues=issues, **_result(an))


def project(inp: LineageInput, analyze: bool = True) -> LineageResult:
    relations, unresolved_rel, dups = build_relations(inp.events, inp.declarations)
    regs = {r.id: r for r in inp.regulations}
    issues: list[IntegrityIssue] = check_relations(relations, regs)
    issues += [
        IntegrityIssue(
            id="iss-" + sha(IssueCode.DUPLICATE_RELATION, d)[:16],
            code=IssueCode.DUPLICATE_RELATION,
            relation_ids=(d,),
        )
        for d in dups
    ]
    total = Analysis()
    if analyze:
        for e in sorted(inp.events, key=lambda e: (e.occurred_on, e.id)):
            an = analyze_event(e, _rel_id(e), inp)
            for field in ("impacts", "changed", "withdrawn", "unresolved", "issues", "incomplete"):
                getattr(total, field).extend(getattr(an, field))
        issues += total.issues + check_operations(total.impacts)
    unique = sorted({i.id: i for i in issues}.values(), key=lambda i: i.id)
    flagged = {
        r for i in unique if i.code is not IssueCode.DUPLICATE_RELATION for r in i.relation_ids
    }
    rels = tuple(
        r.model_copy(update={"integrity": Integrity.CONFLICT}) if r.id in flagged else r
        for r in relations
    )
    return LineageResult(
        relations=rels,
        unresolved_relations=tuple(unresolved_rel),
        issues=tuple(unique),
        **_result(total),
    )
