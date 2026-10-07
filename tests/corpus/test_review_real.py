from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from regulus.documents import PdfPlumberReader, process
from regulus.domain import ObligationStatus as S
from regulus.domain import submit
from regulus.generation import ExtractiveGenerator, GenerationInput, generate
from regulus.lineage import ChangedProvision
from regulus.lineage.models import ChangedKind, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract
from regulus.review import (
    Action,
    ActionRequest,
    Actor,
    InMemoryReviewStore,
    OpenQuestionResolution,
    Resolution,
    ReviewConfig,
    Role,
    Status,
    apply,
    build_snapshot,
    claim,
    new_task,
    replay,
    verify_chain,
)

FILES = sorted((Path(__file__).parents[2] / "pdf").glob("lt*.pdf"))
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]
NOW = datetime(2026, 9, 1, tzinfo=UTC)
REV, REV2 = Actor(id="r1", roles=(Role.REVIEWER,)), Actor(id="r2", roles=(Role.REVIEWER,))
PUB = Actor(id="p1", roles=(Role.PUBLISHER,))
CFG = ReviewConfig()


@pytest.fixture(scope="module", params=FILES, ids=lambda p: p.stem)
def generated(request: pytest.FixtureRequest):  # type: ignore[no-untyped-def]
    doc = process(request.param.read_bytes(), "REG", PdfPlumberReader())
    changes = tuple(
        ChangedProvision(
            regulation_id="REG",
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        for a in doc.articles
    )
    ex = extract(ExtractionInput(changes=changes, documents={"REG": doc}), RulesExtractor())
    cands = tuple(c for r in ex.results for c in r.candidates)
    out = generate(GenerationInput(candidates=cands, documents={"REG": doc}), ExtractiveGenerator())
    return {a.id: a.text for a in doc.articles}, out.results


TOTAL = [0]
CANDS: dict = {}  # type: ignore[type-arg]


def act(store, ob, t, actor, action, **kw):  # type: ignore[no-untyped-def]
    if action is not Action.PUBLISH:
        t = claim(t, actor.id, NOW, CFG.claim_ttl_seconds)
    req = ActionRequest(
        action=action,
        task_id=t.id,
        base_version=store.version(ob.id),
        actor=actor,
        at=NOW + timedelta(seconds=1),
        **kw,
    )
    return apply(store, t, req, CFG, TEXTS[0])


TEXTS: list[dict[str, str]] = [{}]


def test_real_obligations_go_through_submit_review_publish_with_replay_equality(generated) -> None:  # type: ignore[no-untyped-def]
    texts, results = generated
    store, applied = InMemoryReviewStore(), 0
    TEXTS[0] = texts
    for r in results:
        assert r.obligation is not None
        ob = submit(r.obligation)
        store.register(ob)
        task = new_task(
            build_snapshot(
                ob,
                r.evidence,
                r.open_questions,
                True,
                None,
                permitted_source=texts[ob.source_owner_id],
            ),
            NOW,
        )
        res = tuple(
            OpenQuestionResolution(question=q, resolution=Resolution.ACCEPTED_AS_IS, note="n")
            for q in r.open_questions
        )

        out = act(store, ob, task, REV, Action.APPROVE, resolutions=res)
        assert out.status is Status.APPLIED, (ob.id, out.status, out.reasons)
        assert act(store, ob, task, REV, Action.PUBLISH).status is Status.DENIED
        assert act(store, ob, task, PUB, Action.PUBLISH).status is Status.APPLIED
        final, log = store.get(ob.id)
        assert final.status is S.PUBLISHED and verify_chain(log) and replay(ob, log) == final
        assert final.generated == r.obligation.generated
        applied += 1
    assert applied == len(results)
    TOTAL[0] += applied


def test_the_corpus_produced_obligations() -> None:
    assert TOTAL[0] > 0


@pytest.fixture(scope="module")
def corpus():  # type: ignore[no-untyped-def]
    from regulus.domain import ObligationStatus as OS
    from regulus.similarity import (
        LexicalEmbedding,
        SearchConfig,
        SimilarityEntry,
        build_index,
        represent,
    )
    from regulus.similarity.representation import embedding_text

    entries, evidence, texts = [], {}, {}
    for f in FILES:
        reg = "R" + f.stem[-6:]
        doc = process(f.read_bytes(), reg, PdfPlumberReader())
        texts.update({a.id: a.text for a in doc.articles})
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
        CANDS.update({c.id: c for c in cands})
        gen = generate(
            GenerationInput(candidates=cands, documents={reg: doc}), ExtractiveGenerator()
        )
        for r in gen.results:
            if r.obligation is not None:
                evidence[r.obligation.id] = r
                entries.append(
                    SimilarityEntry(
                        obligation=r.obligation.model_copy(update={"status": OS.APPROVED}),
                        trace=r.trace,
                        candidate_id=r.candidate_id,
                    )
                )
    cfg = SearchConfig()
    provider = LexicalEmbedding.fit(
        [embedding_text(represent(e.obligation, e.trace)) for e in entries]
    )
    return entries, evidence, texts, build_index(entries, provider, cfg), provider, cfg


def test_a_real_phase_8_duplicate_match_is_dispositioned_approved_and_published(corpus) -> None:  # type: ignore[no-untyped-def]
    from regulus.review import Disposition, MatchDisposition
    from regulus.similarity import Label, search

    entries, evidence, texts, index, provider, cfg = corpus
    found = None
    for e in entries:
        q = e.model_copy(update={"obligation": evidence[e.obligation.id].obligation})
        sim = search(q, index, provider, cfg)
        if any(m.verdict.label is Label.POSSIBLE_DUPLICATE for m in sim.matches):
            found = (e.obligation.id, sim)
            break
    assert found is not None
    oid, sim = found
    r = evidence[oid]
    assert r.obligation is not None
    ob = submit(r.obligation)
    store = InMemoryReviewStore()
    store.register(ob)
    task = new_task(
        build_snapshot(
            ob, r.evidence, r.open_questions, True, sim, permitted_source=texts[ob.source_owner_id]
        ),
        NOW,
    )
    TEXTS[0] = texts
    res = tuple(
        OpenQuestionResolution(question=q, resolution=Resolution.ACCEPTED_AS_IS, note="n")
        for q in r.open_questions
    )
    dups = [
        m
        for m in sim.matches
        if m.verdict.label in (Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY)
    ]
    blocked = act(store, ob, task, REV, Action.APPROVE, resolutions=res)
    assert blocked.status is Status.INCOMPLETE_REVIEW
    assert blocked.reasons == tuple(f"DISPOSITION:{m.obligation_id}" for m in dups)
    assert store.get(ob.id)[1] == ()
    disp = tuple(
        MatchDisposition(match_id=m.obligation_id, disposition=Disposition.NOT_A_DUPLICATE)
        for m in dups
    )
    approved = act(store, ob, task, REV, Action.APPROVE, resolutions=res, dispositions=disp)
    assert approved.status is Status.APPLIED and approved.records[0].match_dispositions == disp
    assert act(store, ob, task, PUB, Action.PUBLISH).status is Status.APPLIED
    final, log = store.get(ob.id)
    assert final.status is S.PUBLISHED and verify_chain(log) and replay(ob, log) == final
    assert final.generated == r.obligation.generated


def test_a_real_obligation_with_candidate_and_match_is_reviewed_through_the_web_app(corpus) -> None:  # type: ignore[no-untyped-def]
    import io
    from urllib.parse import urlencode

    from regulus.review import Role
    from regulus.review_ui import ReviewApp
    from regulus.similarity import Label, search

    entries, evidence, texts, index, provider, cfg = corpus
    for e in entries:
        r = evidence[e.obligation.id]
        sim = search(e.model_copy(update={"obligation": r.obligation}), index, provider, cfg)
        dups = [
            m
            for m in sim.matches
            if m.verdict.label in (Label.POSSIBLE_DUPLICATE, Label.CONTRADICTORY_MODALITY)
        ]
        if dups and r.candidate_id in CANDS:
            break
    else:
        pytest.fail("no real obligation with a candidate and a dangerous match")
    ob = submit(r.obligation)
    store = InMemoryReviewStore()
    store.register(ob)
    task = new_task(
        build_snapshot(
            ob,
            r.evidence,
            r.open_questions,
            True,
            sim,
            permitted_source=texts[ob.source_owner_id],
            candidate=CANDS[r.candidate_id],
        ),
        NOW,
    )
    actors = {"r1": REV, "p1": PUB}
    app = ReviewApp(
        store,
        {task.id: task},
        lambda env: actors.get(env.get("HTTP_X_ACTOR", "")),
        lambda env: "t",
        texts,
        lambda: NOW + timedelta(seconds=1),
    )

    def call(method: str, path: str, who: str, body: dict | None = None):  # type: ignore[no-untyped-def,type-arg]
        data = urlencode(body or {}, doseq=True).encode()
        out: dict = {}  # type: ignore[type-arg]
        env = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "HTTP_X_ACTOR": who,
            "CONTENT_LENGTH": str(len(data)),
            "wsgi.input": io.BytesIO(data),
        }
        out["body"] = b"".join(app(env, lambda s, h: out.update(status=s))).decode()
        return out

    page = call("GET", f"/tasks/{task.id}", "r1")["body"]
    assert (
        "exact quote verified" in page
        and "NOT VERIFIED" not in page
        and "EVIDENCE INVALID" not in page
    )
    assert "NEEDS DISPOSITION" in page and "<script" not in page.lower() and Role.REVIEWER
    assert call("POST", f"/tasks/{task.id}/claim", "r1", {"csrf": "t"})["status"].startswith("200")

    def post(who: str, action: str, **extra: str):  # type: ignore[no-untyped-def]
        t = app.tasks[task.id]
        body = {
            "csrf": "t",
            "action": action,
            "base_version": store.version(ob.id),
            "snapshot_hash": t.snapshot.hash,
            **extra,
        }
        return call("POST", f"/tasks/{task.id}/action", who, body)

    res = {f"res:{q}": "ACCEPTED_AS_IS" for q in r.open_questions}
    blocked = post("r1", "APPROVE", **res)
    assert (
        blocked["status"].startswith("422")
        and "DISPOSITION:" in blocked["body"]
        and store.get(ob.id)[1] == ()
    )
    disp = {f"disp:{m.obligation_id}": "NOT_A_DUPLICATE" for m in dups}
    assert post("r1", "APPROVE", **res, **disp)["status"].startswith("200")
    assert post("p1", "PUBLISH")["status"].startswith("200")
    final, log = store.get(ob.id)
    assert final.status is S.PUBLISHED and verify_chain(log) and replay(ob, log) == final
    done = call("GET", f"/tasks/{task.id}", "p1")["body"]
    assert "AUDIT CHAIN VERIFIED" in done and "AI-GENERATED" not in done
