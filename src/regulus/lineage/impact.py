import re
from dataclasses import dataclass, field

from regulus.documents import DocStatus, ProcessedDocument, locate
from regulus.documents.models import Provision
from regulus.domain import EventType, RegulatoryEvent, regulation_id

from .amendment import (
    Locator,
    Operation,
    OpKind,
    TargetLevel,
    Unresolved,
    _LocatorError,
    parse_locator,
    parse_operation,
)
from .models import (
    ChangedKind,
    ChangedProvision,
    Effect,
    EvidenceKind,
    ImpactItem,
    ImpactStatus,
    IncompleteSource,
    IntegrityIssue,
    IssueCode,
    LineageInput,
    SourceRef,
    TargetCheck,
    TextRef,
    UnresolvedOperation,
    WithdrawnProvision,
)
from .relations import sha

_REF = re.compile(
    r"(?P<kind>Undang-undang|Peraturan\s+Pemerintah\s+Pengganti\s+Undang-undang|Peraturan\s+Pemerintah|"
    r"Peraturan\s+Presiden|Peraturan\s+Otoritas\s+Jasa\s+Keuangan)\s+Nomor\s+(?P<num>\d+)\s+Tahun\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
_KIND = {
    "undang-undang": "UU",
    "peraturan pemerintah pengganti undang-undang": "PERPU",
    "peraturan pemerintah": "PP",
    "peraturan presiden": "PERPRES",
    "peraturan otoritas jasa keuangan": "POJK",
}
_FORMAL = re.compile(
    r"^[^.]{0,200}?\bini\b[^.]{0,250}?\bmulai\s+berlaku\b", re.IGNORECASE | re.DOTALL
)
_TAIL = re.compile(
    r"^[^.;]{0,300}?\s*,?\s+dicabut(?:\s+dan\s+dinyatakan\s+tidak\s+berlaku)?",
    re.IGNORECASE | re.DOTALL,
)
_LOC_START = re.compile(r"\b(?:Pasal|ayat|huruf)\b", re.IGNORECASE)


def scope_matches(text: str) -> list[tuple[str, str, int, int]]:
    out = []
    for m in _REF.finditer(text):
        tail = _TAIL.match(text[m.end() :])
        if not tail:
            continue
        window = text[max(0, m.start() - 160) : m.start()]
        for start in _LOC_START.finditer(window):
            candidate = window[start.start() :].strip()
            try:
                parse_locator(candidate)
            except _LocatorError:
                continue
            base = max(0, m.start() - 160) + start.start()
            out.append((candidate, m.group(0), base, m.end() + tail.end()))
            break
    return out


def referenced_ids(text: str) -> list[str]:
    from regulus.domain import RegulationKind

    out: list[str] = []
    for m in _REF.finditer(text):
        kind = _KIND[" ".join(m.group("kind").lower().split())]
        rid = regulation_id(RegulationKind(kind), m.group("num"), int(m.group("year")))
        if rid not in out:
            out.append(rid)
    return out


@dataclass
class Analysis:
    impacts: list[ImpactItem] = field(default_factory=list)
    changed: list[ChangedProvision] = field(default_factory=list)
    withdrawn: list[WithdrawnProvision] = field(default_factory=list)
    unresolved: list[UnresolvedOperation] = field(default_factory=list)
    issues: list[IntegrityIssue] = field(default_factory=list)
    incomplete: list[IncompleteSource] = field(default_factory=list)


def _points(unit_text: str, provisions: list[Provision]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    last = 0
    for p in sorted(provisions, key=lambda p: p.span):
        label = int(p.path[-1]) if p.path and p.path[-1].isdigit() else -1
        if label == last + 1:
            spans.append(p.span)
            last = label
        elif spans:
            spans[-1] = (spans[-1][0], max(spans[-1][1], p.span[1]))
    return spans or [(unit_text.find("\n") + 1 if "\n" in unit_text else 0, len(unit_text))]


def _effect(op: Operation, loc: Locator) -> Effect:
    whole = not loc.path
    match op.kind:
        case OpKind.INSERT:
            return Effect.ADDED if op.target_level is TargetLevel.ARTICLE else Effect.MODIFIED
        case OpKind.DELETE:
            return Effect.DELETED if whole else Effect.MODIFIED
        case OpKind.REPEAL_PROVISION:
            return Effect.REPEALED if whole else Effect.MODIFIED
        case _:
            return Effect.MODIFIED


def _check(
    op: Operation, loc: Locator, existing: set[str] | None
) -> tuple[TargetCheck, str | None]:
    if existing is None:
        return TargetCheck.NOT_CHECKED, None
    if op.kind is OpKind.INSERT and op.target_level is TargetLevel.ARTICLE:
        if loc.article in existing:
            return TargetCheck.ALREADY_EXISTS, "ARTICLE_ALREADY_EXISTS"
        if any(a.article not in existing for a in op.anchors):
            return TargetCheck.MISSING, "ANCHOR_MISSING"
        return TargetCheck.CONFIRMED, None
    if loc.article in existing:
        return TargetCheck.CONFIRMED, None
    return TargetCheck.MISSING, "TARGET_ARTICLE_MISSING"


def _flag(analysis: Analysis, ref: str, status: DocStatus | str) -> None:
    s = str(status)
    if not any(x.ref == ref for x in analysis.incomplete):
        analysis.incomplete.append(IncompleteSource(ref=ref, status=s))


def _unit_analysis(
    event: RegulatoryEvent, rel_id: str, doc: ProcessedDocument, inp: LineageInput, out: Analysis
) -> None:
    ta = inp.target_articles.get(event.target_id or "")
    existing = {a.number for a in ta.articles} if ta else None
    if ta and ta.status is not DocStatus.PROCESSED_OK:
        _flag(out, event.target_id or "", ta.status)
    if not doc.amendment_units:
        out.unresolved.append(
            UnresolvedOperation(
                event_id=event.id, owner_id=doc.document.id, reason="NO_AMENDMENT_UNITS"
            )
        )
        return
    for unit in doc.amendment_units:
        frags = doc.provenance[unit.id]
        provs = [p for p in doc.provisions if p.owner_id == unit.id]
        body = unit.text.split("\n", 1)[1] if "\n" in unit.text else ""
        if not provs and _FORMAL.match(" ".join(body.split())):
            continue
        first = min((p.span[0] for p in provs), default=len(unit.text))
        refs = referenced_ids(unit.text[:first])
        if len(refs) >= 2:
            out.unresolved.append(
                UnresolvedOperation(
                    event_id=event.id,
                    owner_id=unit.id,
                    reason="AMBIGUOUS_UNIT_TARGET",
                    detail=",".join(refs),
                )
            )
            continue
        if refs and refs[0] != event.target_id:
            out.issues.append(
                IntegrityIssue(
                    id="iss-" + sha("UNIT_TARGET_MISMATCH", event.id, unit.id)[:16],
                    code=IssueCode.UNIT_TARGET_MISMATCH,
                    relation_ids=(rel_id,),
                    detail=f"{unit.id} names {refs[0]}, event targets {event.target_id}",
                )
            )
            out.unresolved.append(
                UnresolvedOperation(
                    event_id=event.id,
                    owner_id=unit.id,
                    reason="UNIT_TARGET_MISMATCH",
                    detail=refs[0],
                )
            )
            continue
        for ordinal, (ps, pe) in enumerate(_points(unit.text, provs), 1):
            text = unit.text[ps:pe]
            parsed = parse_operation(text)
            spans = locate(frags, ps, max(pe, ps + 1)) if pe > ps else ()
            if isinstance(parsed, Unresolved):
                out.unresolved.append(
                    UnresolvedOperation(
                        event_id=event.id,
                        owner_id=unit.id,
                        reason=parsed.reason,
                        detail=parsed.detail,
                        spans=spans,
                    )
                )
                continue
            sent = locate(
                frags, ps + parsed.sentence[0], ps + max(parsed.sentence[1], parsed.sentence[0] + 1)
            )
            region = parsed.new_text or (
                parsed.sentence if parsed.kind is OpKind.REPLACE_TERM else None
            )
            new = (
                TextRef(owner_id=unit.id, start=ps + region[0], end=ps + region[1])
                if region
                else None
            )
            for loc in parsed.locators:
                check, why = _check(parsed, loc, existing)
                effect = _effect(parsed, loc)
                number = loc.article
                path = loc.path if effect is not Effect.ADDED else ()
                item = ImpactItem(
                    id="imp-"
                    + sha(rel_id, unit.id, str(ordinal), number, "/".join(path), effect)[:16],
                    relation_id=rel_id,
                    event_id=event.id,
                    occurred_on=event.occurred_on,
                    target_regulation_id=event.target_id or "",
                    article_number=number,
                    provision_path=path,
                    effect=effect,
                    source=SourceRef(kind=EvidenceKind.UNIT, ref=unit.id, spans=sent),
                    new_text=new,
                    target_check=check,
                    status=ImpactStatus.UNRESOLVED if why else ImpactStatus.RESOLVED,
                    unresolved_reason=why,
                    source_status=None if doc.status is DocStatus.PROCESSED_OK else str(doc.status),
                )
                out.impacts.append(item)
                if why:
                    continue
                _emit_downstream(out, item, parsed)


def _emit_downstream(out: Analysis, item: ImpactItem, op: Operation) -> None:
    number = item.article_number or ""
    if item.effect in (Effect.DELETED, Effect.REPEALED):
        out.withdrawn.append(
            WithdrawnProvision(
                regulation_id=item.target_regulation_id,
                article_number=number,
                effect=item.effect,
                impact_id=item.id,
            )
        )
        return
    if item.new_text is None:
        return
    kind = (
        ChangedKind.TERM_REPLACED
        if op.kind is OpKind.REPLACE_TERM
        else ChangedKind.ADDED
        if item.effect is Effect.ADDED
        else ChangedKind.MODIFIED
    )
    sup = None
    if item.effect is not Effect.ADDED and item.target_check is TargetCheck.CONFIRMED:
        sup = f"{item.target_regulation_id}:{number}"
    out.changed.append(
        ChangedProvision(
            regulation_id=item.target_regulation_id,
            article_number=number,
            kind=kind,
            text_ref=item.new_text,
            supersedes=sup,
            impact_id=item.id,
        )
    )


def _repeal(event: RegulatoryEvent, rel_id: str, inp: LineageInput, out: Analysis) -> None:
    target = event.target_id or ""
    src = SourceRef(kind=EvidenceKind.EVENT, ref=event.id)

    def item(key: str, article: str | None, derived: bool, check: TargetCheck) -> ImpactItem:
        return ImpactItem(
            id="imp-" + sha(rel_id, key, Effect.REPEALED)[:16],
            relation_id=rel_id,
            event_id=event.id,
            occurred_on=event.occurred_on,
            target_regulation_id=target,
            article_number=article,
            effect=Effect.REPEALED,
            source=src,
            target_check=check,
            derived=derived,
        )

    out.impacts.append(item("regulation", None, False, TargetCheck.NOT_CHECKED))
    ta = inp.target_articles.get(target)
    if ta is None:
        return
    if ta.status is not DocStatus.PROCESSED_OK:
        _flag(out, target, ta.status)
    for a in ta.articles:
        derived = item(a.number, a.number, True, TargetCheck.CONFIRMED)
        out.impacts.append(derived)
        out.withdrawn.append(
            WithdrawnProvision(
                regulation_id=target,
                article_number=a.number,
                effect=Effect.REPEALED,
                impact_id=derived.id,
            )
        )


def _partial(
    event: RegulatoryEvent,
    rel_id: str,
    doc: ProcessedDocument | None,
    inp: LineageInput,
    out: Analysis,
) -> None:
    target = event.target_id or ""
    texts = (
        ([(a.id, a.text) for a in doc.articles] + [(u.id, u.text) for u in doc.amendment_units])
        if doc
        else []
    )
    ta = inp.target_articles.get(target)
    existing = {a.number for a in ta.articles} if ta else None
    for owner, text in texts:
        for loc_text, ref_text, start, end in scope_matches(text):
            if referenced_ids(ref_text) != [target]:
                continue
            locs = parse_locator(loc_text)
            frags = doc.provenance[owner] if doc and owner in doc.provenance else ()
            spans = locate(frags, start, end) if frags else ()
            for loc in locs:
                effect = Effect.REPEALED if not loc.path else Effect.MODIFIED
                check = (
                    TargetCheck.NOT_CHECKED
                    if existing is None
                    else (TargetCheck.CONFIRMED if loc.article in existing else TargetCheck.MISSING)
                )
                item = ImpactItem(
                    id="imp-" + sha(rel_id, owner, loc.article, "/".join(loc.path), effect)[:16],
                    relation_id=rel_id,
                    event_id=event.id,
                    occurred_on=event.occurred_on,
                    target_regulation_id=target,
                    article_number=loc.article,
                    provision_path=loc.path,
                    effect=effect,
                    source=SourceRef(kind=EvidenceKind.UNIT, ref=owner, spans=spans),
                    target_check=check,
                    status=ImpactStatus.UNRESOLVED
                    if check is TargetCheck.MISSING
                    else ImpactStatus.RESOLVED,
                    unresolved_reason="TARGET_ARTICLE_MISSING"
                    if check is TargetCheck.MISSING
                    else None,
                )
                out.impacts.append(item)
                if effect is Effect.REPEALED and item.status is ImpactStatus.RESOLVED:
                    out.withdrawn.append(
                        WithdrawnProvision(
                            regulation_id=target,
                            article_number=loc.article,
                            effect=effect,
                            impact_id=item.id,
                        )
                    )
    if any(i.relation_id == rel_id for i in out.impacts):
        return
    out.impacts.append(
        ImpactItem(
            id="imp-" + sha(rel_id, "scope", Effect.PARTIALLY_REPEALED)[:16],
            relation_id=rel_id,
            event_id=event.id,
            occurred_on=event.occurred_on,
            target_regulation_id=target,
            effect=Effect.PARTIALLY_REPEALED,
            source=SourceRef(kind=EvidenceKind.EVENT, ref=event.id),
            status=ImpactStatus.UNRESOLVED,
            unresolved_reason="SCOPE_UNRESOLVED",
        )
    )


def analyze_event(event: RegulatoryEvent, rel_id: str | None, inp: LineageInput) -> Analysis:
    out = Analysis()
    doc = inp.documents.get(event.regulation_id)
    if event.type is EventType.NEW:
        if doc is None:
            _flag(out, event.regulation_id, "MISSING")
            return out
        if doc.status is not DocStatus.PROCESSED_OK:
            _flag(out, doc.document.id, doc.status)
        for a in doc.articles:
            out.changed.append(
                ChangedProvision(
                    regulation_id=event.regulation_id,
                    article_number=a.number,
                    kind=ChangedKind.NEW_REGULATION_ARTICLE,
                    text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
                )
            )
        return out
    if event.type is EventType.NEEDS_REVIEW or rel_id is None:
        return out
    if event.type is EventType.REPEAL:
        _repeal(event, rel_id, inp, out)
        return out
    if doc is None:
        _flag(out, event.regulation_id, "MISSING")
    elif doc.status is not DocStatus.PROCESSED_OK:
        _flag(out, doc.document.id, doc.status)
    if event.type is EventType.PARTIAL_REPEAL:
        _partial(event, rel_id, doc, inp, out)
    elif doc is not None:
        _unit_analysis(event, rel_id, doc, inp, out)
    return out
