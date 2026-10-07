from datetime import timedelta

from rv_engine_helpers import (
    ALICE,
    BOB,
    CAROL,
    DAVE,
    OWNER,
    TEXT,
    World,
    candidate,
    change,
    evidence,
    impact,
    similarity,
)
from rv_helpers import NOW

from regulus.domain import ObligationEvidence, OwnerKind
from regulus.obligations.models import FieldState, FieldStatus
from regulus.obligations.models import ImpactKind as IK
from regulus.review import (
    Action as A,
)
from regulus.review import (
    Disposition,
    MatchDisposition,
    build_snapshot,
    new_task,
    refresh,
)
from regulus.review_ui import Banner, build_queue, build_view
from regulus.similarity import Label

LATER = NOW + timedelta(seconds=5)


def view(w: World, actor=BOB, texts=None):  # type: ignore[no-untyped-def]
    return (
        build_view(w.store, w.task, actor, LATER, texts=None)
        if False
        else build_view(
            w.store, w.task, actor, LATER, owner_texts=w.texts if texts is None else texts
        )
    )


def with_candidate(w: World, cand=None, questions=()) -> World:  # type: ignore[no-untyped-def]
    snap = build_snapshot(
        w.ob,
        [evidence()],
        questions,
        True,
        None,
        permitted_source=TEXT,
        candidate=cand or candidate(),
    )
    w.task = new_task(snap, NOW)
    return w


def test_header_banner_and_ai_label_for_a_clean_task() -> None:
    v = view(World())
    assert (
        v.header.status == "PENDING_REVIEW"
        and v.header.origin == "RULE"
        and v.banner is Banner.VERIFIED
    )
    assert v.header.snapshot_hash and v.header.base_version and v.chain_valid and v.history == ()


def test_ai_label_clears_only_when_published() -> None:
    w = World()
    w.do(BOB, A.APPROVE)
    w.do(CAROL, A.PUBLISH)
    v = view(w, CAROL)
    assert v.header.status == "PUBLISHED" and v.header.published and len(v.history) == 2


def test_edit_shows_generated_vs_current_the_reason_and_history() -> None:
    w = World()
    w.do(
        ALICE,
        A.EDIT,
        reason="add deadline",
        changes=(change("deadline", None, "paling lambat 3 hari"),),
    )
    v = view(w, BOB)
    d = {x.field: x for x in v.diff}
    assert (
        d["deadline"].changed
        and d["deadline"].generated is None
        and d["deadline"].current == "paling lambat 3 hari"
    )
    assert not d["actor"].changed
    assert [e.reason for e in v.edits] == ["add deadline"] and v.edits[0].fields == ("deadline",)
    assert [(h.from_status, h.to_status) for h in v.history] == [
        ("PENDING_REVIEW", "EDITED"),
        ("EDITED", "PENDING_REVIEW"),
    ]
    assert v.history[1].prev_hash == v.history[0].hash and v.chain_valid


def test_text_absent_from_the_source_is_shown_as_divergence() -> None:
    w = World()
    w.do(ALICE, A.EDIT, reason="r", changes=(change("text", TEXT, TEXT + " sesuai kebijakan"),))
    assert view(w, BOB).edits[0].divergence == ("sesuai", "kebijakan")


def test_carried_questions_are_labelled_and_resolution_is_tracked() -> None:
    w = World(questions=("deadline:undelimited trigger",))
    w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "paling lambat 3 hari"),))
    ob, _ = w.store.get("obl-1")
    w.task = refresh(
        w.task, build_snapshot(ob, [evidence()], (), True, None, (), TEXT, w.task.snapshot)
    )
    q = view(w, BOB).questions
    assert len(q) == 1 and q[0].carried and q[0].resolved
    assert q[0].question == "deadline:undelimited trigger"
    open_ = view(World(questions=("actor:comma",))).questions
    assert open_[0].carried is False and open_[0].resolved is False


def test_field_states_are_worded_as_recorded_with_verified_citations() -> None:
    c = candidate().model_copy(
        update={"deadline": FieldState(status=FieldStatus.UNDETERMINED, reason="enumerated_items")}
    )
    w = with_candidate(World(), c, ("deadline:attachment unclear",))
    v = view(w)
    p = {x.field: x for x in v.provenance}
    assert v.provenance_recorded
    assert (
        p["action"].state == "PRESENT"
        and p["action"].value == "menyimpan"
        and p["action"].verified is True
    )
    assert p["action"].owner_id == OWNER and p["action"].span == (
        TEXT.index("menyimpan"),
        TEXT.index("menyimpan") + 9,
    )
    assert (
        p["actor"].state == "NOT_STATED" and p["actor"].value is None and p["actor"].reason is None
    )
    assert p["deadline"].state == "UNDETERMINED" and p["deadline"].reason == "enumerated_items"
    assert p["deadline"].questions == ("deadline:attachment unclear",)
    assert p["condition"].state == "NOT_STATED" and p["exception"].state == "NOT_STATED"


def test_a_citation_that_does_not_match_the_text_is_not_verified() -> None:
    w = with_candidate(World())
    assert next(x for x in view(w).provenance if x.field == "action").verified is True
    changed = view(w, texts={OWNER: "teks lain yang tidak sama sekali memuat kutipan itu"})
    assert next(x for x in changed.provenance if x.field == "action").verified is False
    gone = view(w, texts={})
    assert next(x for x in gone.provenance if x.field == "action").verified is None


def test_no_candidate_means_no_provenance_is_invented() -> None:
    v = view(World())
    assert not v.provenance_recorded and v.provenance == ()


def test_evidence_spans_are_marked_in_the_source_only_when_verified() -> None:
    v = view(World())
    marked = [s for s in v.source.segments if s.evidence]
    assert "".join(s.text for s in v.source.segments) == TEXT
    assert [s.text for s in marked] == ["wajib menyimpan"] and marked[0].evidence == ("ev1",)
    assert v.source.available and v.source.evidence[0].verified
    bad = view(World(), texts={OWNER: "teks yang berubah sama sekali tanpa kutipan itu"})
    assert not bad.source.evidence[0].verified and all(not s.evidence for s in bad.source.segments)
    missing = view(World(), texts={})
    assert (
        not missing.source.available
        and not missing.source.evidence[0].verified
        and missing.source.segments == ()
    )


def test_overlapping_evidence_spans_nest_without_gaps_or_loss() -> None:
    w = World()
    a = evidence()
    b = ObligationEvidence(
        obligation_id="obl-1",
        owner_id=OWNER,
        owner_kind=OwnerKind.ARTICLE,
        span=(TEXT.index("menyimpan"), len(TEXT)),
        quote=TEXT[TEXT.index("menyimpan") :],
    )
    w.task = new_task(build_snapshot(w.ob, [a, b], (), True, None, permitted_source=TEXT), NOW)
    segs = view(w).source.segments
    assert "".join(s.text for s in segs) == TEXT
    assert [s.evidence for s in segs if s.text == "menyimpan"] == [("ev1", "ev2")]
    assert [s.evidence for s in segs if s.text == " arsip"] == [("ev2",)]


def test_evidence_in_an_amendment_unit_is_checked_against_that_owner_text() -> None:
    amd = "AMD:1:1"
    ob = World().ob.model_copy(update={"source_owner_id": amd})
    w = World()
    w.store.register(ob)
    quote = "wajib menyimpan"
    s = TEXT.index(quote)
    ev = ObligationEvidence(
        obligation_id="obl-1",
        owner_id=amd,
        owner_kind=OwnerKind.AMENDMENT_UNIT,
        span=(s, s + len(quote)),
        quote=quote,
    )
    w.task = new_task(build_snapshot(ob, [ev], (), True, None, permitted_source=TEXT), NOW)
    ok = view(w, texts={amd: TEXT})
    assert ok.source.owner_id == amd and ok.source.evidence[0].verified
    assert not view(w, texts={OWNER: TEXT}).source.evidence[0].verified


def test_the_view_holds_data_not_markup() -> None:
    hostile = '<script>alert(1)</script> & "q"'
    w = World()
    w.texts = {OWNER: hostile + TEXT}
    v = view(w)
    dumped = v.model_dump_json()
    assert "<script>" in "".join(s.text for s in v.source.segments)
    assert "&amp;" not in dumped and "&lt;" not in dumped


def test_dangerous_matches_need_disposition_and_weak_ones_are_labelled() -> None:
    w = World(
        labels=(
            Label.POSSIBLE_DUPLICATE,
            Label.CONTRADICTORY_MODALITY,
            Label.SIMILAR_TEXT_ONLY,
            Label.RELATED,
        )
    )
    v = view(w)
    by = {m.match_id: m for m in v.matches}
    assert by["m0"].needs_disposition and by["m1"].needs_disposition
    assert not by["m2"].needs_disposition and by["m2"].weak and not by["m3"].needs_disposition
    assert (
        by["m0"].score_kind == "COSINE_UNCALIBRATED"
        and by["m0"].relationship == "POSSIBLE_DUPLICATE"
    )
    assert by["m0"].retrieval_score == 0.5 and by["m0"].lineage == "NONE"
    blockers = {g.id for g in v.gates if not g.ok}
    assert {"DISPOSITION:m0", "DISPOSITION:m1"} <= blockers and "DISPOSITION:m2" not in blockers
    assert not v.actions[A.APPROVE].available


def test_a_recorded_disposition_is_shown_beside_the_match() -> None:
    w = World(labels=(Label.POSSIBLE_DUPLICATE,))
    disp = MatchDisposition(match_id="m0", disposition=Disposition.NOT_A_DUPLICATE)
    w.do(BOB, A.APPROVE, dispositions=(disp,))
    assert view(w, CAROL).matches[0].recorded_disposition == "NOT_A_DUPLICATE"
    assert view(World(labels=(Label.POSSIBLE_DUPLICATE,))).matches[0].recorded_disposition is None


def test_source_banners_follow_the_snapshot_flags() -> None:
    assert view(World(complete=False)).banner is Banner.INCOMPLETE
    assert view(World(impacts=(impact(IK.MODIFIED),))).banner is Banner.CHANGED
    assert (
        view(World(impacts=(impact(IK.MODIFIED), impact(IK.WITHDRAWN)), complete=False)).banner
        is Banner.WITHDRAWN
    )


def test_withdrawn_source_leaves_only_reject_as_an_available_action() -> None:
    w = World(impacts=(impact(IK.WITHDRAWN),))
    w.claim(BOB)
    v = view(w)
    assert (
        v.actions[A.APPROVE].available is False
        and "SOURCE_WITHDRAWN" in v.actions[A.APPROVE].reasons
    )
    assert v.actions[A.REJECT].available and not v.actions[A.PUBLISH].available


def test_editor_sees_four_eyes_and_auditor_sees_role() -> None:
    w = World()
    w.do(ALICE, A.EDIT, reason="r", changes=(change("deadline", None, "x"),))
    w.claim(ALICE)
    own = view(w, ALICE)
    assert "FOUR_EYES" in own.actions[A.APPROVE].reasons
    assert any(g.id == "AUTHORIZATION" and not g.ok and g.detail == "FOUR_EYES" for g in own.gates)
    aud = view(w, DAVE)
    assert all(not a.available and "ROLE" in a.reasons for a in aud.actions.values())


def test_build_view_is_deterministic_and_does_not_mutate() -> None:
    w = World(questions=("q:x",), labels=(Label.POSSIBLE_DUPLICATE,), complete=False)
    before = (w.store.get("obl-1"), w.task)
    a, b = view(w), view(w)
    assert a == b and a.model_dump_json() == b.model_dump_json()
    assert (w.store.get("obl-1"), w.task) == before


def test_queue_follows_phase_9_order_and_marks_risk() -> None:
    contra, plain, many = (
        World(labels=(Label.CONTRADICTORY_MODALITY,)),
        World(),
        World(questions=("a:x", "b:y")),
    )
    tasks = []
    for i, w in enumerate((plain, many, contra)):
        tasks.append(w.task.model_copy(update={"id": f"task-{i}", "obligation_id": "obl-1"}))
    q = build_queue(contra.store, tasks, LATER)
    assert [i.task_id for i in q.items] == ["task-2", "task-1", "task-0"]
    assert "CONTRADICTORY_MODALITY" in q.items[0].markers and q.items[1].open_questions == 2
    assert q.items[2].markers == () and q.items[0].age_seconds == 5
    assert similarity  # helper import kept for parity
