from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from regulus.domain import Obligation
from regulus.domain import ObligationStatus as S
from regulus.obligations.models import FieldStatus, FieldValue
from regulus.review import (
    Action,
    ActionVerdict,
    Gate,
    ReviewConfig,
    ReviewStore,
    ReviewTask,
    TaskStatus,
    obligation_version,
    ordered,
    preflight,
    verify_chain,
)
from regulus.review.gates import DANGEROUS, resolved_questions
from regulus.review.models import (
    SOURCE_CHANGED,
    SOURCE_INCOMPLETE,
    SOURCE_WITHDRAWN,
    ActionRequest,
    Actor,
)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


FIELDS = ("text", "actor", "action", "object", "condition", "deadline", "frequency", "exception")


class Banner(StrEnum):
    VERIFIED = "VERIFIED"
    INCOMPLETE = "INCOMPLETE"
    CHANGED = "CHANGED"
    WITHDRAWN = "WITHDRAWN"


class EvidenceView(Model):
    id: str
    owner_id: str
    span: tuple[int, int]
    quote: str
    verified: bool


class Segment(Model):
    text: str
    evidence: tuple[str, ...] = ()


class SourceView(Model):
    owner_id: str
    available: bool
    segments: tuple[Segment, ...] = ()
    evidence: tuple[EvidenceView, ...] = ()


class ProvenanceView(Model):
    field: str
    state: str
    value: str | None = None
    reason: str | None = None
    owner_id: str | None = None
    span: tuple[int, int] | None = None
    verified: bool | None = None
    questions: tuple[str, ...] = ()


class FieldDiff(Model):
    field: str
    generated: str | None
    current: str | None
    changed: bool


class EditView(Model):
    actor_id: str
    at: datetime
    reason: str | None
    fields: tuple[str, ...]
    divergence: tuple[str, ...] = ()


class QuestionView(Model):
    question: str
    carried: bool
    resolved: bool


class ComparisonView(Model):
    field: str
    query: str | None
    match: str | None
    relation: str


class MatchView(Model):
    match_id: str
    rank: int
    relationship: str
    retrieval_score: float
    score_kind: str
    lineage: str
    comparisons: tuple[ComparisonView, ...]
    needs_disposition: bool
    weak: bool
    recorded_disposition: str | None = None


class HistoryEntry(Model):
    index: int
    from_status: str
    to_status: str
    actor_id: str
    roles: tuple[str, ...]
    at: datetime
    reason: str | None
    hash: str
    prev_hash: str


class HeaderView(Model):
    obligation_id: str
    article_id: str
    status: str
    task_id: str
    task_status: str
    claimed_by: str | None
    claim_expires_at: datetime | None
    snapshot_hash: str
    base_version: str
    origin: str
    published: bool


class ReviewView(Model):
    header: HeaderView
    banner: Banner
    source: SourceView
    provenance_recorded: bool
    provenance: tuple[ProvenanceView, ...]
    diff: tuple[FieldDiff, ...]
    edits: tuple[EditView, ...]
    questions: tuple[QuestionView, ...]
    matches: tuple[MatchView, ...]
    gates: tuple[Gate, ...]
    actions: dict[Action, ActionVerdict]
    history: tuple[HistoryEntry, ...]
    chain_valid: bool


class QueueItem(Model):
    task_id: str
    obligation_id: str
    article_id: str
    status: str
    markers: tuple[str, ...]
    open_questions: int
    age_seconds: int


class QueueView(Model):
    items: tuple[QueueItem, ...]


def banner_of(flags: Sequence[str]) -> Banner:
    for flag, banner in (
        (SOURCE_WITHDRAWN, Banner.WITHDRAWN),
        (SOURCE_CHANGED, Banner.CHANGED),
        (SOURCE_INCOMPLETE, Banner.INCOMPLETE),
    ):
        if flag in flags:
            return banner
    return Banner.VERIFIED


def _source(ob: Obligation, task: ReviewTask, texts: Mapping[str, str]) -> SourceView:
    text = texts.get(ob.source_owner_id)
    evs: list[EvidenceView] = []
    for i, e in enumerate(task.snapshot.evidence, 1):
        ok = (
            e.obligation_id == ob.id
            and e.owner_id == ob.source_owner_id
            and e.matches(e.owner_id, texts.get(e.owner_id, ""))
            and e.owner_id in texts
        )
        evs.append(
            EvidenceView(id=f"ev{i}", owner_id=e.owner_id, span=e.span, quote=e.quote, verified=ok)
        )
    if text is None:
        return SourceView(owner_id=ob.source_owner_id, available=False, evidence=tuple(evs))
    good = [e for e in evs if e.verified]
    cuts = sorted({0, len(text), *(p for e in good for p in e.span)})
    segs = tuple(
        Segment(
            text=text[a:b], evidence=tuple(e.id for e in good if e.span[0] <= a and b <= e.span[1])
        )
        for a, b in zip(cuts, cuts[1:], strict=False)
    )
    return SourceView(
        owner_id=ob.source_owner_id, available=True, segments=segs, evidence=tuple(evs)
    )


def _prov(
    name: str,
    st: str,
    fv: FieldValue | None,
    reason: str | None,
    texts: Mapping[str, str],
    questions: Sequence[str],
) -> ProvenanceView:
    qs = tuple(q for q in questions if q.split(":")[0] == name)
    if fv is None:
        return ProvenanceView(field=name, state=st, reason=reason, questions=qs)
    c = fv.citation
    owner = texts.get(c.owner_id)
    verified = None if owner is None else owner[c.start : c.end] == c.quote
    return ProvenanceView(
        field=name,
        state=st,
        value=fv.value,
        reason=reason,
        owner_id=c.owner_id,
        span=(c.start, c.end),
        verified=verified,
        questions=qs,
    )


def _provenance(
    task: ReviewTask, texts: Mapping[str, str], questions: Sequence[str]
) -> tuple[ProvenanceView, ...]:
    c = task.snapshot.candidate
    if c is None:
        return ()
    out = [_prov("marker", FieldStatus.PRESENT.value, c.marker, None, texts, questions)]
    for name in ("actor", "action", "object", "deadline", "frequency"):
        fs = getattr(c, name)
        out.append(_prov(name, fs.status.value, fs.value, fs.reason, texts, questions))
    for name, vals in (("condition", c.conditions), ("exception", c.exceptions)):
        if not vals:
            out.append(ProvenanceView(field=name, state=FieldStatus.NOT_STATED.value))
        out += [_prov(name, FieldStatus.PRESENT.value, v, None, texts, questions) for v in vals]
    return tuple(out)


def build_view(
    store: ReviewStore,
    task: ReviewTask,
    actor: Actor,
    now: datetime,
    cfg: ReviewConfig | None = None,
    owner_texts: Mapping[str, str] | None = None,
) -> ReviewView:
    cfg = cfg or ReviewConfig()
    texts = owner_texts or {}
    ob, log = store.get(task.obligation_id)
    snap = task.snapshot
    pf = preflight(store, task, actor, now, cfg, texts)
    bare = ActionRequest(
        action=Action.APPROVE, task_id=task.id, base_version="", actor=actor, at=now
    )
    done = resolved_questions(task, log, bare)
    qs = [(q, False) for q in snap.open_questions] + [(q, True) for q in snap.carried_questions]
    all_q = tuple(q for q, _ in qs)
    recorded = {d.match_id: d.disposition.value for rec in log for d in rec.match_dispositions}
    matches = tuple(
        MatchView(
            match_id=m.obligation_id,
            rank=m.rank,
            relationship=m.verdict.label.value,
            retrieval_score=m.retrieval_score,
            score_kind=m.score_kind,
            lineage=m.lineage_context.value,
            comparisons=tuple(
                ComparisonView(
                    field=c.field,
                    query=c.query_value,
                    match=c.match_value,
                    relation=c.relation.value,
                )
                for c in m.verdict.comparisons
            ),
            needs_disposition=m.verdict.label in DANGEROUS,
            weak=m.verdict.label.value == "SIMILAR_TEXT_ONLY",
            recorded_disposition=recorded.get(m.obligation_id),
        )
        for m in (snap.similarity.matches if snap.similarity else ())
    )
    diff = tuple(
        FieldDiff(
            field=f,
            generated=getattr(ob.generated.content, f),
            current=getattr(ob.current, f),
            changed=getattr(ob.generated.content, f) != getattr(ob.current, f),
        )
        for f in FIELDS
    )
    edits = tuple(
        EditView(
            actor_id=r.actor_id,
            at=r.decision.at,
            reason=r.decision.reason,
            fields=tuple(c.field for c in r.decision.changes),
            divergence=r.divergence,
        )
        for r in log
        if r.decision.to_status is S.EDITED
    )
    history = tuple(
        HistoryEntry(
            index=i,
            from_status=r.decision.from_status.value,
            to_status=r.decision.to_status.value,
            actor_id=r.actor_id,
            roles=tuple(x.value for x in r.actor_roles),
            at=r.decision.at,
            reason=r.decision.reason,
            hash=r.hash,
            prev_hash=r.prev_hash,
        )
        for i, r in enumerate(log)
    )
    return ReviewView(
        header=HeaderView(
            obligation_id=ob.id,
            article_id=ob.article_id,
            status=ob.status.value,
            task_id=task.id,
            task_status=task.status.value,
            claimed_by=task.claimed_by,
            claim_expires_at=task.claim_expires_at,
            snapshot_hash=snap.hash,
            base_version=obligation_version(ob, len(log)),
            origin=ob.origin.value,
            published=ob.status is S.PUBLISHED,
        ),
        banner=banner_of(snap.source_flags),
        source=_source(ob, task, texts),
        provenance_recorded=snap.candidate is not None,
        provenance=_provenance(task, texts, all_q),
        diff=diff,
        edits=edits,
        questions=tuple(QuestionView(question=q, carried=c, resolved=q in done) for q, c in qs),
        matches=matches,
        gates=pf.gates,
        actions=pf.actions,
        history=history,
        chain_valid=verify_chain(log),
    )


def build_queue(store: ReviewStore, tasks: Sequence[ReviewTask], now: datetime) -> QueueView:
    items = []
    for t in ordered(tasks):
        s = t.snapshot
        labels = {m.verdict.label for m in s.similarity.matches} if s.similarity else set()
        markers = tuple(
            [lb.value for lb in sorted(labels & DANGEROUS, key=lambda x: x.value)]
            + list(s.source_flags)
            + (["OPEN_QUESTIONS"] if s.open_questions or s.carried_questions else [])
            + (["CLAIMED"] if t.status is TaskStatus.CLAIMED else [])
        )
        items.append(
            QueueItem(
                task_id=t.id,
                obligation_id=t.obligation_id,
                article_id=s.obligation.article_id,
                status=store.get(t.obligation_id)[0].status.value,
                markers=markers,
                open_questions=len(s.open_questions) + len(s.carried_questions),
                age_seconds=max(0, int((now - t.created_at).total_seconds())),
            )
        )
    return QueueView(items=tuple(items))
