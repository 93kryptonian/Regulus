from datetime import timedelta

import pytest
from test_workflow_real import FILES, NOW, RealPipeline

from regulus.documents import DocStatus, PdfPlumberReader, process
from regulus.review import Action, ActionRequest, Actor, ReviewConfig, Role, apply, claim
from regulus.workflow import source_complete_for

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="local corpus (pdf/) not present"),
]


def test_every_snapshot_from_an_issue_bearing_document_is_marked_incomplete_and_needs_acknowledgement() -> (
    None
):
    from regulus.domain import ObligationStatus as S
    from regulus.review import InMemoryReviewStore, Status, build_snapshot, new_task

    pipe = RealPipeline()
    pipe.load()
    statuses = {
        "R" + f.stem[-6:]: process(f.read_bytes(), "R" + f.stem[-6:], PdfPlumberReader()).status
        for f in FILES
    }
    assert any(s is not DocStatus.PROCESSED_OK for s in statuses.values()), (
        "the local corpus should contain a document processed with issues"
    )
    checked = False
    for oid, (reg, r) in pipe.units.items():
        inputs = pipe.enrich(oid)
        want = source_complete_for(statuses[reg].value)
        assert inputs.source_complete is want
        if not want and not checked:
            ob = r.obligation.model_copy(update={"status": S.PENDING_REVIEW})
            store = InMemoryReviewStore()
            store.register(ob)
            snap = build_snapshot(
                ob,
                r.evidence,
                (),
                inputs.source_complete,
                None,
                permitted_source=inputs.permitted_source,
            )
            assert "SOURCE_INCOMPLETE" in snap.source_flags
            task = claim(new_task(snap, NOW), "r1", NOW, 900)
            req = ActionRequest(
                action=Action.APPROVE,
                task_id=task.id,
                base_version=store.version(oid),
                actor=Actor(id="r1", roles=(Role.REVIEWER,)),
                at=NOW + timedelta(seconds=1),
            )
            out = apply(store, task, req, ReviewConfig(), pipe.texts[reg])
            assert (
                out.status is Status.INCOMPLETE_REVIEW
                and "ACKNOWLEDGE:SOURCE_INCOMPLETE" in out.reasons
            )
            checked = True
    assert checked
