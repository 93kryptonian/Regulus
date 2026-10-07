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
