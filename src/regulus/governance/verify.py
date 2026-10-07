from regulus.domain.base import Model
from regulus.review import ReplayError, replay, verify_chain
from regulus.workflow import WorkflowStore
from regulus.workflow import verify_chain as verify_workflow

from .chain import ChainLog


class IntegrityReport(Model):
    intact: tuple[str, ...] = ()
    broken: tuple[str, ...] = ()
    unreceipted: tuple[str, ...] = ()


def verify_all(
    store: WorkflowStore,
    access: ChainLog,
    purge: ChainLog,
    anchors: dict[str, tuple[int, str]] | None = None,
) -> IntegrityReport:
    intact: list[str] = []
    broken: list[str] = []
    unreceipted: list[str] = []
    for prefix in ("obligation:", "task:", "notification:", "run:"):
        for s in store.streams_with(prefix):
            recs = store.ledger(s)
            ok = verify_workflow(recs)
            a = (anchors or {}).get(s)
            if ok and a is not None:
                ok = len(recs) > a[0] and recs[a[0]].hash == a[1]
            (intact if ok else broken).append(s)
    for oid in sorted(store.review._initial):
        state, log = store.review.get(oid)
        try:
            ok = verify_chain(log) and replay(store.review._initial[oid], log) == state
        except ReplayError:
            ok = False
        (intact if ok else broken).append(f"review:{oid}")
        if f"obligation:{oid}" not in store.streams_with("obligation:") and not any(
            r.fields.get("stream") == f"review_{oid}" for r in purge.records
        ):
            unreceipted.append(f"obligation:{oid}")
    for chain in (access, purge):
        (intact if chain.verified() else broken).append(f"log:{chain.name}")
    return IntegrityReport(
        intact=tuple(intact), broken=tuple(broken), unreceipted=tuple(unreceipted)
    )
