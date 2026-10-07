from datetime import timedelta

import pytest
from wf_helpers import LATER, NOW, generated, submit_it

from regulus.review import StoreError
from regulus.workflow import (
    SYSTEM,
    ClockRegression,
    InMemoryWorkflowStore,
    IntentWorkflowStore,
    Kind,
    Phase,
    PreparedSubmission,
    make_record,
    obligation_stream,
    submission_state,
    verify_chain,
)

STORES = [InMemoryWorkflowStore, IntentWorkflowStore]


def chain(n: int = 4):  # type: ignore[no-untyped-def]
    recs: list = []  # type: ignore[type-arg]
    for i in range(n):
        recs.append(
            make_record(
                "s", recs, Kind.SUBMIT_FAILED, "system", NOW + timedelta(seconds=i), key=f"k{i}"
            )
        )
    return recs


def test_chain_links_and_is_deterministic() -> None:
    a, b = chain(), chain()
    assert a == b and verify_chain(a) and verify_chain([])
    assert [r.seq for r in a] == [0, 1, 2, 3] and a[1].prev_hash == a[0].hash


def test_modifying_deleting_reordering_or_duplicating_breaks_the_chain() -> None:
    log = chain()
    assert not verify_chain([log[0].model_copy(update={"principal_id": "x"}), *log[1:]])
    assert not verify_chain([*log[:1], *log[2:]])
    assert not verify_chain([log[1], log[0], *log[2:]])
    assert not verify_chain([*log, log[-1]])
    assert not verify_chain(log[1:])


@pytest.mark.parametrize("store_cls", STORES)
def test_streams_verify_and_tampering_is_detected(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    submit_it(s)
    assert s.verify() and s.violations() == []
    stream = obligation_stream("obl-1")
    s.streams[stream] = (
        s.streams[stream][0].model_copy(update={"principal_id": "mallory"}),
        *s.streams[stream][1:],
    )
    assert not s.verify()


@pytest.mark.parametrize("store_cls", STORES)
def test_the_projection_equals_what_the_store_holds(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    out = submit_it(s)
    st = submission_state(s.ledger(obligation_stream("obl-1")))
    assert st.phase is Phase.COMPLETE and st.task_id == out.task.id and st.prepared is None  # type: ignore[union-attr]
    assert s.task(st.task_id) == out.task and s.registered("obl-1")


@pytest.mark.parametrize("store_cls", STORES)
def test_a_clock_regression_is_refused_and_recorded(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    submit_it(s)
    with pytest.raises(ClockRegression):
        s.append(obligation_stream("obl-1"), Kind.SUBMIT_FAILED, SYSTEM, NOW)
    last = s.ledger(obligation_stream("obl-1"))[-1]
    assert (
        last.kind is Kind.CLOCK_REGRESSION
        and last.details["kind"] == "SUBMIT_FAILED"
        and s.verify()
    )


@pytest.mark.parametrize("store_cls", STORES)
def test_a_submission_at_an_earlier_time_than_the_stream_is_refused_and_recorded(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    submit_it(s, at=LATER)
    st = s.submission("obl-1")
    prepared = PreparedSubmission(
        key="k2",
        content_hash="h",
        obligation=s.review.get("obl-1")[0],
        task=s.task(st.task_id),  # type: ignore[arg-type]
    )
    with pytest.raises(ClockRegression):
        s.commit_submission(prepared, SYSTEM, NOW)
    assert s.ledger(obligation_stream("obl-1"))[-1].kind is Kind.CLOCK_REGRESSION and s.verify()


@pytest.mark.parametrize("store_cls", STORES)
def test_an_injected_store_failure_makes_nothing_durable(store_cls) -> None:  # type: ignore[no-untyped-def]
    s = store_cls()
    s.fail_store = 1
    with pytest.raises(StoreError):
        s.append("x", Kind.SUBMIT_FAILED, SYSTEM, NOW)
    assert s.ledger("x") == () and generated().obligation is not None
