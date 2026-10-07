import pytest
from rv_helpers import chain, make_obligation, record

from regulus.domain import FieldChange
from regulus.domain import ObligationStatus as S
from regulus.review.log import (
    GENESIS,
    ReplayError,
    canonical,
    obligation_version,
    replay,
    seal,
    tip,
    verify_chain,
)
from regulus.review.store import InMemoryReviewStore, StaleCommit, StoreError


def test_chain_hashes_link_and_verify() -> None:
    log = chain()
    assert verify_chain(log) and log[0].prev_hash == GENESIS and log[1].prev_hash == log[0].hash
    assert verify_chain([]) and tip([]) == GENESIS and tip(log) == log[-1].hash
    assert len({r.hash for r in log}) == 4


def test_hash_is_deterministic_and_covers_every_field() -> None:
    a, b = chain(), chain()
    assert [r.hash for r in a] == [r.hash for r in b]
    base = a[2]
    for update in (
        {"actor_id": "mallory"},
        {"snapshot_hash": "x"},
        {"divergence": ("tok",)},
        {"task_id": "t2"},
        {"base_version": "v2"},
    ):
        tampered = base.model_copy(update=update)
        assert seal(tampered).hash != base.hash and '"hash":' not in canonical(base)


def test_any_tampering_deletion_or_reordering_breaks_the_chain() -> None:
    log = chain()
    assert not verify_chain([log[0].model_copy(update={"actor_id": "mallory"}), *log[1:]])
    assert not verify_chain([*log[:1], *log[2:]])
    assert not verify_chain([log[1], log[0], *log[2:]])
    assert not verify_chain([*log[:3], log[3].model_copy(update={"hash": "0" * 64})])
    assert not verify_chain([log[0].model_copy(update={"prev_hash": "other"}), *log[1:]])


def test_replay_reproduces_the_final_state_and_generated_never_changes() -> None:
    ob = make_obligation()
    out = replay(ob, chain())
    assert out.status is S.PUBLISHED and out.current.deadline == "paling lambat 3 hari"
    assert out.generated == ob.generated and ob.current.deadline is None
    assert replay(ob, []) == ob


def test_replay_rejects_inconsistent_logs() -> None:
    ob = make_obligation()
    log = chain()
    with pytest.raises(ReplayError):
        replay(ob, [log[1], *log[2:]])
    with pytest.raises(ReplayError):
        replay(make_obligation(status=S.APPROVED), log)
    with pytest.raises(ReplayError):
        replay(ob, [log[0].model_copy(update={"actor_id": "x"}), *log[1:]])
    stale = [
        record(
            [],
            "obl-1",
            S.PENDING_REVIEW,
            S.EDITED,
            changes=(FieldChange(field="actor", before="Lain", after="Y"),),
            reason="r",
        )
    ]
    with pytest.raises(ReplayError):
        replay(ob, stale)
    other = [record([], "other", S.PENDING_REVIEW, S.APPROVED)]
    with pytest.raises(ReplayError):
        replay(ob, other)


def test_version_changes_with_state_and_log_length() -> None:
    ob = make_obligation()
    assert obligation_version(ob, 0) != obligation_version(ob, 1)
    assert obligation_version(ob, 0) != obligation_version(replay(ob, chain()[:2]), 0)
    assert obligation_version(ob, 0) == obligation_version(make_obligation(), 0)


def store_with() -> tuple[InMemoryReviewStore, str]:
    s = InMemoryReviewStore()
    s.register(make_obligation())
    return s, s.version("obl-1")


def test_commit_makes_state_and_log_durable_together() -> None:
    s, v = store_with()
    log = chain()[:2]
    after = replay(make_obligation(), log)
    s.commit("obl-1", after, log, v)
    ob, durable = s.get("obl-1")
    assert ob == after and durable == tuple(log) and replay(make_obligation(), durable) == ob
    assert s.version("obl-1") != v


def test_store_failure_leaves_state_and_log_unchanged_and_replay_equal() -> None:
    s, v = store_with()
    s.fail_next = 1
    log = chain()[:2]
    with pytest.raises(StoreError):
        s.commit("obl-1", replay(make_obligation(), log), log, v)
    ob, durable = s.get("obl-1")
    assert ob == make_obligation() and durable == () and replay(make_obligation(), durable) == ob
    s.commit("obl-1", replay(make_obligation(), log), log, v)
    assert len(s.get("obl-1")[1]) == 2


def test_commit_refuses_stale_version_and_inconsistent_state_or_log() -> None:
    s, v = store_with()
    log = chain()[:2]
    good = replay(make_obligation(), log)
    s.commit("obl-1", good, log, v)
    with pytest.raises(StaleCommit):
        s.commit("obl-1", good, [], v)
    s2, v2 = store_with()
    wrong_state = replay(make_obligation(), chain()[:1])
    with pytest.raises(StoreError):
        s2.commit("obl-1", wrong_state, log, v2)
    with pytest.raises(StoreError):
        s2.commit("obl-1", good, [log[1]], v2)
    assert s2.get("obl-1")[1] == ()
    s3, v3 = store_with()
    broken = [log[0].model_copy(update={"actor_id": "x"}), log[1]]
    with pytest.raises((StoreError, ReplayError)):
        s3.commit("obl-1", good, broken, v3)
    assert s3.get("obl-1")[1] == ()
