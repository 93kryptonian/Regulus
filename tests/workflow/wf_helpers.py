from datetime import timedelta

from rv_engine_helpers import OWNER, TEXT, evidence, similarity
from rv_helpers import NOW, make_obligation

from regulus.domain import Generated, ObligationContent, ObligationEvidence
from regulus.domain import ObligationStatus as S
from regulus.generation import GenerationResult
from regulus.generation import Status as GS
from regulus.generation.models import TransformationTrace
from regulus.workflow import SYSTEM, SnapshotInputs, WorkflowStore, submit_for_review

LATER = NOW + timedelta(seconds=5)
TRACE = TransformationTrace(candidate=(), content=())
__all__ = ["OWNER", "TEXT", "similarity"]


def generated(
    oid: str = "obl-1", deadline: str | None = None, status: GS = GS.GENERATED
) -> GenerationResult:
    content = ObligationContent(
        text=TEXT, actor="Pengendali", action="menyimpan", object="arsip", deadline=deadline
    )
    ob = make_obligation(oid, S.GENERATED).model_copy(
        update={"generated": Generated(content=content), "current": content}
    )
    ev: ObligationEvidence = evidence(oid)
    return GenerationResult(
        candidate_id=f"cand-{oid}",
        status=status,
        obligation=ob if status is GS.GENERATED else None,
        evidence=(ev,),
        trace=TRACE,
        open_questions=("deadline:x",),
    )


def inputs(**kw: object) -> SnapshotInputs:
    return SnapshotInputs(permitted_source=TEXT, **kw)  # type: ignore[arg-type]


def submit_it(
    store: WorkflowStore, result: GenerationResult | None = None, at=LATER, texts=None, **kw
):  # type: ignore[no-untyped-def]
    return submit_for_review(
        store,
        result or generated(),
        inputs(**kw),
        SYSTEM,
        at,
        {OWNER: TEXT} if texts is None else texts,
    )
