from datetime import UTC, datetime

from regulus.domain import (
    FieldChange,
    Generated,
    Obligation,
    ObligationContent,
    Origin,
    ReviewDecision,
)
from regulus.domain import (
    ObligationStatus as S,
)
from regulus.review.log import seal, tip
from regulus.review.models import ReviewRecord, Role

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def make_obligation(oid: str = "obl-1", status: S = S.PENDING_REVIEW, **content: str) -> Obligation:
    c = ObligationContent(
        text="Pengendali wajib menyimpan arsip",
        actor="Pengendali",
        action="menyimpan",
        object="arsip",
        **content,
    )
    return Obligation(
        id=oid,
        article_id="R:1",
        source_owner_id="R:1",
        status=status,
        origin=Origin.RULE,
        generated=Generated(content=c),
        current=c,
    )


def record(
    prev: list[ReviewRecord],
    oid: str,
    frm: S,
    to: S,
    actor: str = "alice",
    task: str = "t1",
    changes: tuple[FieldChange, ...] = (),
    reason: str | None = None,
    **kw: object,
) -> ReviewRecord:
    d = ReviewDecision(
        id=f"dec-{len(prev)}",
        obligation_id=oid,
        reviewer=actor,
        at=NOW,
        from_status=frm,
        to_status=to,
        reason=reason,
        changes=changes,
    )
    r = ReviewRecord(
        id=f"rrec-{len(prev)}",
        decision=d,
        task_id=task,
        base_version="v",
        snapshot_hash="h",
        actor_id=actor,
        actor_roles=(Role.REVIEWER,),
        prev_hash=tip(prev),
        **kw,
    )  # type: ignore[arg-type]
    return seal(r)


def chain(oid: str = "obl-1") -> list[ReviewRecord]:
    log: list[ReviewRecord] = []
    log.append(
        record(
            log,
            oid,
            S.PENDING_REVIEW,
            S.EDITED,
            "alice",
            reason="set deadline",
            changes=(FieldChange(field="deadline", before=None, after="paling lambat 3 hari"),),
        )
    )
    log.append(record(log, oid, S.EDITED, S.PENDING_REVIEW, "alice", reason="RESUBMIT"))
    log.append(record(log, oid, S.PENDING_REVIEW, S.APPROVED, "bob"))
    log.append(record(log, oid, S.APPROVED, S.PUBLISHED, "carol"))
    return log
