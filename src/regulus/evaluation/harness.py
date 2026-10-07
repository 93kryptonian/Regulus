import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from regulus.domain import (
    FieldChange,
    Generated,
    Obligation,
    ObligationContent,
    ObligationEvidence,
    Origin,
    OwnerKind,
)
from regulus.domain import ObligationStatus as S
from regulus.generation import GenerationResult
from regulus.generation import Status as GS
from regulus.generation.models import TransformationTrace
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    Disposition,
    InMemoryReviewStore,
    MatchDisposition,
    OpenQuestionResolution,
    RejectCode,
    RejectReason,
    Resolution,
    ReviewConfig,
    ReviewRecord,
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
NOW = datetime(2026, 9, 1, tzinfo=UTC)
ACTORS = (
    Actor(id="r1", roles=(Role.REVIEWER,)),
    Actor(id="r2", roles=(Role.REVIEWER,)),
    Actor(id="p1", roles=(Role.PUBLISHER,)),
    Actor(id="a1", roles=(Role.AUDITOR,)),
    Actor(id="rp", roles=(Role.REVIEWER, Role.PUBLISHER)),
)
QUESTIONS = ("deadline:undelimited trigger", "actor:comma inside the actor phrase")


def evidence(oid: str) -> ObligationEvidence:
    q = "wajib menyimpan"
    s = TEXT.index(q)
    return ObligationEvidence(
        obligation_id=oid,
        owner_id=OWNER,
        owner_kind=OwnerKind.ARTICLE,
        span=(s, s + len(q)),
        quote=q,
    )


def obligation(oid: str, status: S = S.PENDING_REVIEW, deadline: str | None = None) -> Obligation:
    c = ObligationContent(
        text=TEXT, actor="Pengendali", action="menyimpan", object="arsip", deadline=deadline
    )
    return Obligation(id=oid, article_id=OWNER, source_owner_id=OWNER, status=status, origin=Origin.RULE,
                      generated=Generated(content=c), current=c)  # fmt: skip


def generation_result(
    oid: str, deadline: str | None = None, evidence_ok: bool = True
) -> GenerationResult:
    return GenerationResult(candidate_id=f"cand-{oid}", status=GS.GENERATED, obligation=obligation(oid, S.GENERATED, deadline),
                            evidence=(evidence(oid),) if evidence_ok else (), trace=TransformationTrace(candidate=(), content=()),
                            open_questions=("deadline:x",))  # fmt: skip


def similarity(oid: str, *labels: Label) -> SimilarityResult:
    ms = tuple(
        Match(obligation_id=f"m{i}", rank=i + 1, retrieval_score=0.5, verdict=Verdict(label=lb, comparisons=()),
              lineage_context=LineageContext.NONE, article_id="X:1")
        for i, lb in enumerate(labels)
    )  # fmt: skip
    return SimilarityResult(id="sim", query_id=oid, status=SearchStatus.MATCHES, matches=ms)


class ReviewRun:
    def __init__(self, oid: str, rng: random.Random) -> None:
        self.rng, self.oid = rng, oid
        self.store = InMemoryReviewStore()
        self.ob = obligation(oid)
        self.store.register(self.ob)
        labels = tuple(
            rng.choice((Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY, Label.RELATED))
            for _ in range(rng.randint(0, 2))
        )
        qs = tuple(rng.sample(QUESTIONS, rng.randint(0, 2)))
        snap = build_snapshot(
            self.ob,
            [evidence(oid)],
            qs,
            rng.random() < 0.8,
            similarity(oid, *labels) if labels else None,
            (),
            TEXT,
        )
        self.created = NOW
        self.task: ReviewTask = new_task(snap, NOW)
        self.clock = NOW
        self.cfg = ReviewConfig()
        self.texts = {OWNER: TEXT}

    def step(self) -> None:
        rng = self.rng
        self.clock += timedelta(seconds=rng.choice((5, 30, 600)))
        actor, action = rng.choice(ACTORS), rng.choice(list(Action))
        if rng.random() < 0.85 and action is not Action.PUBLISH:
            self.task = self.task.model_copy(
                update={"status": "OPEN", "claimed_by": None, "claim_expires_at": None}
            )
            self.task = claim(self.task, actor.id, self.clock, self.cfg.claim_ttl_seconds)
        snap = self.task.snapshot
        ob = self.store.get(self.oid)[0]
        kw: dict[str, object] = {}
        if action is Action.APPROVE and rng.random() < 0.8:
            kw["resolutions"] = tuple(
                OpenQuestionResolution(question=q, resolution=Resolution.ACCEPTED_AS_IS, note="n")
                for q in snap.open_questions
            )
            kw["dispositions"] = tuple(
                MatchDisposition(match_id=m.obligation_id, disposition=Disposition.NOT_A_DUPLICATE)
                for m in (snap.similarity.matches if snap.similarity else ())
            )
            kw["acknowledged_flags"] = tuple(snap.source_flags)
        elif action is Action.REJECT:
            kw["reject_reason"] = RejectReason(
                code=rng.choice(
                    [
                        RejectCode.OUT_OF_SCOPE,
                        RejectCode.INCORRECT_EXTRACTION,
                        RejectCode.SOURCE_UNCLEAR,
                    ]
                )
            )
        elif action is Action.EDIT:
            new = f"paling lambat {rng.randint(1, 9)} hari"
            if new != ob.current.deadline:
                kw["changes"] = (
                    FieldChange(field="deadline", before=ob.current.deadline, after=new),
                )
                kw["reason"] = "scripted edit"
        req = ActionRequest(
            action=action,
            task_id=self.task.id,
            base_version=self.store.version(self.oid),
            actor=actor,
            at=self.clock,
            **kw,
        )
        out = apply(self.store, self.task, req, self.cfg, self.texts)
        if out.task is not None:
            self.task = out.task

    def log(self) -> Sequence[ReviewRecord]:
        return self.store.get(self.oid)[1]


class FakeChannel:
    def __init__(self, rng: random.Random, fail: float) -> None:
        self.rng, self.fail, self.keys = rng, fail, set()  # type: ignore[var-annotated]

    def send(self, message, recipients, idempotency_key):  # type: ignore[no-untyped-def]
        from regulus.notifications import DeliveryResult, DeliveryStatus

        if self.rng.random() < self.fail:
            return DeliveryResult(status=DeliveryStatus.FAILED_RETRYABLE, error_class="Unavailable")
        self.keys.add(idempotency_key)
        return DeliveryResult(status=DeliveryStatus.SENT)


class Everyone:
    def resolve(self, event):  # type: ignore[no-untyped-def]
        return ["r1"]


class FakePipeline:
    def __init__(self, n: int, rng: random.Random | None = None, fail: float = 0.0) -> None:
        self.items = {f"obl-{i}": generation_result(f"obl-{i}") for i in range(n)}
        self.rng, self.fail = rng, fail

    def _maybe(self) -> None:
        from regulus.workflow import Unavailable

        if self.rng is not None and self.rng.random() < self.fail:
            raise Unavailable()

    def process(self, event):  # type: ignore[no-untyped-def]
        self._maybe()
        return "ref"

    def generate(self, event, ref):  # type: ignore[no-untyped-def]
        self._maybe()
        return list(self.items)

    def result(self, item_id):  # type: ignore[no-untyped-def]
        return self.items[item_id]

    def enrich(self, item_id):  # type: ignore[no-untyped-def]
        from regulus.workflow import SnapshotInputs

        self._maybe()
        return SnapshotInputs(permitted_source=TEXT)

    def owner_texts(self, ref):  # type: ignore[no-untyped-def]
        return {OWNER: TEXT}
