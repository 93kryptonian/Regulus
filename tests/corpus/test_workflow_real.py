from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from regulus.documents import PdfPlumberReader, process
from regulus.domain import EventType, RegulatoryEvent
from regulus.domain import ObligationStatus as S
from regulus.generation import ExtractiveGenerator, GenerationInput, generate
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.notifications import (
    DeliveryResult,
    DeliveryStatus,
    State,
    deliver_due,
    notification_state,
    queue_emitter,
)
from regulus.obligations import ExtractionInput, RulesExtractor, extract
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    Disposition,
    MatchDisposition,
    OpenQuestionResolution,
    Resolution,
    ReviewConfig,
    Role,
    Status,
    apply,
    claim,
    replay,
    verify_chain,
)
from regulus.review_ui import build_view, render_task
from regulus.similarity import (
    Label,
    LexicalEmbedding,
    SearchConfig,
    SimilarityEntry,
    build_index,
    represent,
    search,
)
from regulus.similarity.representation import embedding_text
from regulus.workflow import (
    SYSTEM,
    InMemoryWorkflowStore,
    ReviewerInfo,
    RunStatus,
    SnapshotInputs,
    current_assignment,
    run_event,
    run_key,
    run_state,
    tick,
    unaccounted,
)

FILES = sorted((Path(__file__).parents[2] / "pdf").glob("lt*.pdf"))
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]
NOW = datetime(2026, 9, 1, tzinfo=UTC)


class Who:
    def resolve(self, e):  # type: ignore[no-untyped-def]
        return ["r1"]


class Dir:
    def reviewers(self, now):  # type: ignore[no-untyped-def]
        return [ReviewerInfo(id="r1"), ReviewerInfo(id="r2")]


class Channel:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    def send(self, message, recipients, idempotency_key):  # type: ignore[no-untyped-def]
        self.keys.add(idempotency_key)
        return DeliveryResult(status=DeliveryStatus.SENT)


class RealPipeline:
    def __init__(self) -> None:
        self.units: dict[str, tuple] = {}  # type: ignore[type-arg]
        self.texts: dict[str, dict[str, str]] = {}
        self.items: dict[str, list[str]] = {}
        self.entries: list[SimilarityEntry] = []
        self.candidates: dict = {}  # type: ignore[type-arg]
        self.docs: dict = {}  # type: ignore[type-arg]
        self.sim = None
        self.complete: dict[str, bool] = {}

    def load(self) -> None:
        for f in FILES:
            reg = "R" + f.stem[-6:]
            doc = process(f.read_bytes(), reg, PdfPlumberReader())
            self.docs[reg] = doc
            self.complete[reg] = doc.status.value == "PROCESSED_OK"
            self.texts[reg] = {a.id: a.text for a in doc.articles}
            changes = tuple(
                ChangedProvision(
                    regulation_id=reg,
                    article_number=a.number,
                    kind=ChangedKind.NEW_REGULATION_ARTICLE,
                    text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
                )
                for a in doc.articles
            )
            ex = extract(ExtractionInput(changes=changes, documents={reg: doc}), RulesExtractor())
            cands = tuple(c for r in ex.results for c in r.candidates)
            self.candidates.update({c.id: c for c in cands})
            gen = generate(
                GenerationInput(candidates=cands, documents={reg: doc}), ExtractiveGenerator()
            )
            self.items[reg] = []
            for r in gen.results:
                if r.obligation is not None:
                    self.units[r.obligation.id] = (reg, r)
                    self.items[reg].append(r.obligation.id)
                    self.entries.append(
                        SimilarityEntry(
                            obligation=r.obligation.model_copy(update={"status": S.APPROVED}),
                            trace=r.trace,
                            candidate_id=r.candidate_id,
                        )
                    )
        cfg = SearchConfig()
        provider = LexicalEmbedding.fit(
            [embedding_text(represent(e.obligation, e.trace)) for e in self.entries]
        )
        self.sim = (build_index(self.entries, provider, cfg), provider, cfg)

    def process(self, event):  # type: ignore[no-untyped-def]
        return event.regulation_id

    def generate(self, event, ref):  # type: ignore[no-untyped-def]
        return list(self.items[ref])

    def result(self, item_id):  # type: ignore[no-untyped-def]
        return self.units[item_id][1]

    def enrich(self, item_id):  # type: ignore[no-untyped-def]
        reg, r = self.units[item_id]
        index, provider, cfg = self.sim
        q = SimilarityEntry(obligation=r.obligation, trace=r.trace, candidate_id=r.candidate_id)
        return SnapshotInputs(
            source_complete=self.complete[reg],
            similarity=search(q, index, provider, cfg),
            candidate=self.candidates[r.candidate_id],
            permitted_source=self.texts[reg][r.obligation.source_owner_id],
        )

    def owner_texts(self, ref):  # type: ignore[no-untyped-def]
        return self.texts[ref]


def test_real_events_flow_through_submission_routing_notification_and_a_real_review() -> None:
    pipe = RealPipeline()
    pipe.load()
    store, chan = InMemoryWorkflowStore(), Channel()
    total = 0
    for i, reg in enumerate(sorted(pipe.items)):
        ev = RegulatoryEvent(
            id=f"evt-{i}",
            type=EventType.NEW,
            regulation_id=reg,
            occurred_on=date(2026, 8, 1),
            detected_on=date(2026, 8, 2),
            basis="local corpus",
        )
        emit = queue_emitter(store, Who(), SYSTEM, NOW)
        rep = run_event(store, pipe, ev, SYSTEM, NOW, emit)
        want = len(pipe.items[reg])
        assert rep.status is RunStatus.COMPLETE and rep.submitted == want, (reg, rep)
        assert run_state(store, run_key(ev.id, "1")).status is RunStatus.COMPLETE
        total += want
    assert total > 0 and len(store.tasks) == total and unaccounted(store) == []
    assert store.violations() == [] and store.verify()

    again = run_event(
        store,
        pipe,
        RegulatoryEvent(
            id="evt-0",
            type=EventType.NEW,
            regulation_id=sorted(pipe.items)[0],
            occurred_on=date(2026, 8, 1),
            detected_on=date(2026, 8, 2),
            basis="local corpus",
        ),
        SYSTEM,
        NOW + timedelta(hours=1),
        queue_emitter(store, Who(), SYSTEM, NOW),
    )
    assert again.submitted == 0 and len(store.tasks) == total

    tick(store, NOW + timedelta(minutes=1), Dir(), SYSTEM)
    assert all(current_assignment(store, t).assignee in ("r1", "r2") for t in store.tasks)
    sent = deliver_due(store, chan, SYSTEM, NOW + timedelta(minutes=2))
    assert sent and all(d.state is State.DELIVERED for d in sent)
    assert all(notification_state(store, k).state is State.DELIVERED for k in chan.keys)  # type: ignore[union-attr]

    pick = next(
        (
            t
            for t in store.tasks.values()
            if t.snapshot.similarity
            and any(
                m.verdict.label in (Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY)
                for m in t.snapshot.similarity.matches
            )
        ),
        next(iter(store.tasks.values())),
    )
    oid = pick.obligation_id
    reg = pipe.units[oid][0]
    r1 = Actor(id="r1", roles=(Role.REVIEWER,))
    p1 = Actor(id="p1", roles=(Role.PUBLISHER,))
    t = claim(pick, "r1", NOW + timedelta(minutes=3), 900)
    res = tuple(
        OpenQuestionResolution(question=q, resolution=Resolution.ACCEPTED_AS_IS, note="n")
        for q in (*pick.snapshot.open_questions, *pick.snapshot.carried_questions)
    )
    disp = tuple(
        MatchDisposition(match_id=m.obligation_id, disposition=Disposition.NOT_A_DUPLICATE)
        for m in (pick.snapshot.similarity.matches if pick.snapshot.similarity else ())
        if m.verdict.label in (Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY)
    )
    view = build_view(store.review, t, r1, NOW + timedelta(minutes=3), owner_texts=pipe.texts[reg])
    assert "exact quote verified" in render_task(view, "tok") and view.provenance_recorded
    req = ActionRequest(
        action=Action.APPROVE,
        task_id=t.id,
        base_version=store.review.version(oid),
        actor=r1,
        at=NOW + timedelta(minutes=4),
        resolutions=res,
        dispositions=disp,
    )
    assert apply(store.review, t, req, ReviewConfig(), pipe.texts[reg]).status is Status.APPLIED
    pub = ActionRequest(
        action=Action.PUBLISH,
        task_id=t.id,
        base_version=store.review.version(oid),
        actor=p1,
        at=NOW + timedelta(minutes=5),
    )
    assert apply(store.review, t, pub, ReviewConfig(), pipe.texts[reg]).status is Status.APPLIED
    final, log = store.review.get(oid)
    initial = store.submission(oid).task_id
    assert initial == pick.id and final.status is S.PUBLISHED and verify_chain(log)
    assert replay(store.review._initial[oid], log) == final
