from datetime import timedelta

from rv_helpers import NOW, make_obligation

from regulus.domain import FieldChange, ObligationEvidence, OwnerKind
from regulus.obligations import ObligationImpact
from regulus.obligations.models import ImpactKind
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    InMemoryReviewStore,
    ReviewConfig,
    ReviewTask,
    Role,
    apply,
    build_snapshot,
    claim,
    new_task,
)
from regulus.similarity import Label, LineageContext, Match, SearchStatus, SimilarityResult, Verdict

TEXT = "Pengendali wajib menyimpan arsip"
OWNER = "R:1"
ALICE, BOB = Actor(id="alice", roles=(Role.REVIEWER,)), Actor(id="bob", roles=(Role.REVIEWER,))
CAROL, DAVE = Actor(id="carol", roles=(Role.PUBLISHER,)), Actor(id="dave", roles=(Role.AUDITOR,))
CFG = ReviewConfig()


def similarity(*labels: Label) -> SimilarityResult:
    ms = tuple(
        Match(
            obligation_id=f"m{i}",
            rank=i + 1,
            retrieval_score=0.5,
            verdict=Verdict(label=lb, comparisons=()),
            lineage_context=LineageContext.NONE,
            article_id="X:1",
        )
        for i, lb in enumerate(labels)
    )
    return SimilarityResult(id="sim-1", query_id="obl-1", status=SearchStatus.MATCHES, matches=ms)


def evidence(oid: str = "obl-1") -> ObligationEvidence:
    quote = "wajib menyimpan"
    s = TEXT.index(quote)
    return ObligationEvidence(
        obligation_id=oid,
        owner_id=OWNER,
        owner_kind=OwnerKind.ARTICLE,
        span=(s, s + len(quote)),
        quote=quote,
    )


def impact(kind: ImpactKind) -> ObligationImpact:
    return ObligationImpact(
        id="oim-1",
        kind=kind,
        regulation_id="R",
        article_number="1",
        article_id="R:1",
        affected_obligation_ids=("obl-1",),
        review_required=True,
        store_complete=True,
    )


class World:
    def __init__(
        self,
        questions: tuple[str, ...] = (),
        labels: tuple[Label, ...] = (),
        complete: bool = True,
        impacts: tuple[ObligationImpact, ...] = (),
        with_evidence: bool = True,
    ) -> None:
        self.store = InMemoryReviewStore()
        self.ob = make_obligation()
        self.store.register(self.ob)
        self.texts = {OWNER: TEXT}
        snap = build_snapshot(
            self.ob,
            [evidence()] if with_evidence else [],
            questions,
            complete,
            similarity(*labels) if labels else None,
            impacts,
            permitted_source=TEXT,
        )
        self.task: ReviewTask = new_task(snap, NOW)
        self.clock = NOW

    def claim(self, actor: Actor) -> None:
        self.task = claim(self.task, actor.id, self.clock, CFG.claim_ttl_seconds)

    def req(self, actor: Actor, action: Action, **kw: object) -> ActionRequest:
        return ActionRequest(
            action=action,
            task_id=self.task.id,
            base_version=self.store.version("obl-1"),
            actor=actor,
            at=self.clock + timedelta(seconds=1),
            **kw,
        )  # type: ignore[arg-type]

    def do(self, actor: Actor, action: Action, claim_first: bool = True, **kw: object):  # type: ignore[no-untyped-def]
        if claim_first and action is not Action.PUBLISH and self.task.claimed_by != actor.id:
            self.task = self.task.model_copy(
                update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
            )
            self.claim(actor)
        out = apply(self.store, self.task, self.req(actor, action, **kw), CFG, self.texts)
        if out.task is not None:
            self.task = out.task
        return out


def change(field: str, before: str | None, after: str | None) -> FieldChange:
    return FieldChange(field=field, before=before, after=after)
