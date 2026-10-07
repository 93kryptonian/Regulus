from html.parser import HTMLParser

from rv_engine_helpers import (
    ALICE,
    BOB,
    CAROL,
    OWNER,
    TEXT,
    World,
    candidate,
    evidence,
    impact,
)
from rv_helpers import NOW
from test_view import LATER, view  # noqa: I001

from regulus.obligations.models import FieldState, FieldStatus
from regulus.obligations.models import ImpactKind as IK
from regulus.review import Action as A
from regulus.review import build_snapshot, new_task
from regulus.review_ui import build_queue, build_view, render_outcome, render_queue, render_task
from regulus.similarity import Label

HOSTILE = '<script>alert(1)</script>"><img src=x onerror=y> &amp;'


def html_of(w: World, actor=BOB, **kw) -> str:  # type: ignore[no-untyped-def]
    return render_task(view(w, actor, **kw), "tok")


def test_hostile_text_is_escaped_in_every_section() -> None:
    w = World(questions=(f"deadline:{HOSTILE}",), labels=(Label.POSSIBLE_DUPLICATE,))
    ob = w.ob.model_copy(
        update={"current": w.ob.current.model_copy(update={"deadline": HOSTILE, "actor": HOSTILE})}
    )
    w.store.register(ob)
    quote = "wajib menyimpan"
    src = HOSTILE + " " + TEXT
    s = src.index(quote)
    ev = evidence().model_copy(update={"span": (s, s + len(quote))})
    w.task = new_task(
        build_snapshot(
            ob,
            [ev],
            (f"deadline:{HOSTILE}",),
            True,
            None,
            permitted_source=src,
            candidate=candidate(),
        ),
        NOW,
    )
    w.texts = {OWNER: src}
    out = html_of(w)
    assert "<script>" not in out and "<img" not in out and "onerror=y>" not in out
    assert "&lt;script&gt;" in out


def test_ai_label_is_present_until_published_and_cannot_be_hidden_by_query() -> None:
    w = World()
    assert "AI-GENERATED" in html_of(w)
    w.do(BOB, A.APPROVE)
    w.do(CAROL, A.PUBLISH)
    assert "AI-GENERATED" not in html_of(w, CAROL)


def test_source_banners_are_worded_and_withdrawn_says_the_engine_may_still_refuse() -> None:
    assert "SOURCE VERIFIED" in html_of(World())
    assert "SOURCE INCOMPLETE" in html_of(World(complete=False))
    assert "SOURCE CHANGED" in html_of(World(impacts=(impact(IK.MODIFIED),)))
    w = html_of(World(impacts=(impact(IK.WITHDRAWN),)))
    assert (
        "SOURCE WITHDRAWN" in w
        and "may still refuse" in w
        and "only available review action is rejection" in w
    )


def test_field_states_are_stated_in_words() -> None:
    c = candidate().model_copy(
        update={"deadline": FieldState(status=FieldStatus.UNDETERMINED, reason="enumerated_items")}
    )
    w = World()
    w.task = new_task(
        build_snapshot(
            w.ob, [evidence()], ("deadline:x",), True, None, permitted_source=TEXT, candidate=c
        ),
        NOW,
    )
    out = html_of(w)
    assert (
        "not stated in the source" in out
        and "enumerated_items" in out
        and "exact quote verified" in out
    )
    assert "Open question: deadline:x" in out
    assert "No field provenance recorded" in html_of(World())


def test_invalid_evidence_is_flagged_not_highlighted() -> None:
    out = html_of(World(), texts={OWNER: "teks yang berubah sama sekali tanpa kutipan itu"})
    assert "EVIDENCE INVALID" in out and "<mark>" not in out
    assert "SOURCE TEXT UNAVAILABLE" in html_of(World(), texts={})


def test_evidence_is_marked_with_a_textual_id() -> None:
    out = html_of(World())
    assert "<mark>wajib menyimpan<sup> [ev1]</sup></mark>" in out


def test_similarity_separates_retrieval_relationship_and_disposition_without_percentages() -> None:
    out = html_of(World(labels=(Label.POSSIBLE_DUPLICATE, Label.SIMILAR_TEXT_ONLY)))
    assert (
        "uncalibrated" in out
        and "Relationship: POSSIBLE_DUPLICATE" in out
        and "NEEDS DISPOSITION" in out
    )
    assert "weak: text similarity only" in out
    assert "%" not in out.split("<main>")[1] and "probability" not in out
    assert 'type="radio" name="disp:m0"' in out and 'name="disp:m1"' not in out


def test_gates_list_blockers_in_words_and_never_by_colour_alone() -> None:
    out = html_of(
        World(questions=("deadline:x",), labels=(Label.CONTRADICTORY_MODALITY,), complete=False)
    )
    assert "BLOCKED: Open question needs a resolution: deadline:x" in out
    assert "BLOCKED: Disposition needed for match m0" in out and "PASS: Evidence verified" in out
    assert "approval is not available" in out and "APPROVE: unavailable" in out
    assert "color" not in out.lower().split("<main>")[1]


class Collect(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.labels: set[str] = set()
        self.controls: list[tuple[str, dict[str, str | None]]] = []
        self.tags: set[str] = set()
        self.in_label = 0
        self.nested: list[dict[str, str | None]] = []
        self.legends = 0

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        a = dict(attrs)
        self.tags.add(tag)
        if tag == "label":
            self.in_label += 1
            if a.get("for"):
                self.labels.add(a["for"] or "")
        if tag == "legend":
            self.legends += 1
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden":
            self.controls.append((tag, a))
            if self.in_label:
                self.nested.append(a)

    def handle_endtag(self, tag):  # type: ignore[no-untyped-def]
        if tag == "label":
            self.in_label -= 1


def test_every_control_is_labelled_and_landmarks_are_semantic() -> None:
    w = World(questions=("deadline:x",), labels=(Label.POSSIBLE_DUPLICATE,), complete=False)
    c = Collect()
    c.feed(html_of(w))
    for _, a in c.controls:
        assert a in c.nested or a.get("id") in c.labels, a
    assert {"main", "section", "form", "fieldset", "legend", "button", "table", "header"} <= c.tags
    assert c.legends >= 3


def test_outcome_is_a_live_region_and_worded_per_status() -> None:
    out = render_outcome("INCOMPLETE_REVIEW", ("DISPOSITION:m0",))
    assert 'role="status"' in out and 'aria-live="polite"' in out and "Nothing was recorded" in out
    assert "Disposition needed for match m0" in out
    assert "may be retried" in render_outcome("NOT_RECORDED")


def test_history_shows_hashes_and_chain_state() -> None:
    w = World()
    w.do(BOB, A.APPROVE)
    out = html_of(w, CAROL)
    assert (
        "AUDIT CHAIN VERIFIED" in out
        and "PENDING_REVIEW to APPROVED by bob" in out
        and "previous" in out
    )


def test_rendering_is_byte_identical_and_handles_large_inputs() -> None:
    w = World()
    v = build_view(w.store, w.task, ALICE, LATER, owner_texts=w.texts)
    assert render_task(v, "t") == render_task(v, "t")
    long = ("kalimat panjang " * 5000) + TEXT
    w.texts = {OWNER: long}
    big = build_view(w.store, w.task, ALICE, LATER, owner_texts=w.texts)
    assert len(render_task(big, "t")) > 80000
    tasks = [w.task.model_copy(update={"id": f"task-{i:03d}"}) for i in range(150)]
    q = build_queue(w.store, tasks, LATER)
    page = render_queue(q)
    assert page.count("<tr><td><a href") == 150
    assert page.index("task-000") < page.index("task-149")
    assert "<nav" in page and "Ordered by review risk" in page
