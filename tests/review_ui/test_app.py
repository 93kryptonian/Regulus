import pytest
from rv_engine_helpers import BOB, World, change
from ui_helpers import TOKEN, call, form, make_app

from regulus.review import Action as A
from regulus.review_ui import app as app_module
from regulus.similarity import Label


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    seen: list[object] = []
    real = app_module.apply

    def spy(*a, **k):  # type: ignore[no-untyped-def]
        seen.append(a[2])
        return real(*a, **k)

    monkeypatch.setattr(app_module, "apply", spy)
    return seen


def claim(app, w, actor="bob"):  # type: ignore[no-untyped-def]
    r = call(app, "POST", f"/tasks/{w.task.id}/claim", actor, {"csrf": TOKEN})
    assert r["status"].startswith("200"), r["body"][:300]


def test_pages_carry_security_headers() -> None:
    w = World()
    r = call(make_app(w), "GET", f"/tasks/{w.task.id}")
    h = r["headers"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"] and "script" not in h[
        "Content-Security-Policy"
    ].replace("'none'", "")
    assert h["X-Content-Type-Options"] == "nosniff" and h["Referrer-Policy"] == "no-referrer"
    assert (
        call(make_app(w), "GET", "/static/review.css")["headers"]["X-Content-Type-Options"]
        == "nosniff"
    )


def test_get_never_changes_anything_even_with_side_effect_parameters() -> None:
    w = World()
    app = make_app(w)
    before = (w.store.get("obl-1"), dict(app.tasks))
    for path in (
        f"/tasks/{w.task.id}?action=APPROVE&actor=bob",
        "/tasks?action=APPROVE",
        f"/tasks/{w.task.id}/action",
        f"/tasks/{w.task.id}/claim",
    ):
        call(app, "GET", path)
    assert (w.store.get("obl-1"), dict(app.tasks)) == before


def test_unknown_and_malicious_paths_are_404_without_detail() -> None:
    w = World()
    app = make_app(w)
    for p in ("/tasks/nope", "/tasks/<script>", "/tasks/../etc", "/elsewhere"):
        r = call(app, "GET", p)
        assert (
            r["status"].startswith("404")
            and "nope" not in r["body"]
            and "<script>" not in r["body"]
        )
    assert call(app, "GET", "/tasks", actor="stranger")["status"].startswith("401")


def test_posts_without_a_valid_csrf_token_never_reach_the_engine(calls: list[object]) -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    for body in (
        {k: v for k, v in form(w, app, "APPROVE").items() if k != "csrf"},
        {**form(w, app, "APPROVE"), "csrf": "wrong"},
    ):
        assert call(app, "POST", f"/tasks/{w.task.id}/action", "bob", body)["status"].startswith(
            "403"
        )
    assert calls == [] and w.store.get("obl-1")[1] == ()


@pytest.mark.parametrize(
    "extra",
    [{"actor": "mallory"}, {"actor_id": "mallory"}, {"roles": "PUBLISHER"}, {"surprise": "1"}],
)
def test_forged_or_unknown_fields_are_400_and_the_engine_is_not_called(
    extra: dict[str, str], calls: list[object]
) -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    r = call(app, "POST", f"/tasks/{w.task.id}/action", "bob", {**form(w, app, "APPROVE"), **extra})
    assert r["status"].startswith("400") and next(iter(extra)) in r["body"]
    assert calls == [] and w.store.get("obl-1")[1] == ()


def test_duplicate_fields_unknown_actions_and_bad_enums_are_400(calls: list[object]) -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    base = form(w, app, "APPROVE")
    url = f"/tasks/{w.task.id}/action"
    dup = "&".join(f"{k}={v}" for k, v in base.items()) + "&action=REJECT"
    assert call(app, "POST", url, "bob", raw=dup)["status"].startswith("400")
    assert call(app, "POST", url, "bob", {**base, "action": "DELETE"})["status"].startswith("400")
    assert call(app, "POST", url, "bob", {**base, "reject_code": "WHATEVER"})["status"].startswith(
        "400"
    )
    assert call(app, "POST", url, "bob", {**base, "disp:m0": "MAYBE"})["status"].startswith("400")
    assert call(app, "POST", url, "bob", {k: v for k, v in base.items() if k != "action"})[
        "status"
    ].startswith("400")
    assert calls == [] and w.store.get("obl-1")[1] == ()


def test_a_stale_snapshot_hash_is_answered_before_the_engine(calls: list[object]) -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    body = {**form(w, app, "APPROVE"), "snapshot_hash": '"><script>alert(1)</script>'}
    r = call(app, "POST", f"/tasks/{w.task.id}/action", "bob", body)
    assert (
        r["status"].startswith("409") and "STALE" in r["body"] and "<script>alert" not in r["body"]
    )
    assert calls == [] and w.store.get("obl-1")[1] == ()


def test_a_stale_base_version_is_refused_by_the_engine(calls: list[object]) -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    r = call(
        app,
        "POST",
        f"/tasks/{w.task.id}/action",
        "bob",
        {**form(w, app, "APPROVE"), "base_version": "old"},
    )
    assert r["status"].startswith("409") and "STALE" in r["body"] and len(calls) == 1
    assert w.store.get("obl-1")[1] == ()


def test_an_action_shown_unavailable_still_reaches_the_engine_which_refuses(
    calls: list[object],
) -> None:
    w = World()
    app = make_app(w)
    r = call(app, "POST", f"/tasks/{w.task.id}/action", "carol", form(w, app, "PUBLISH"))
    assert len(calls) == 1 and r["status"].startswith("422") and "INVALID_TRANSITION" in r["body"]
    assert w.store.get("obl-1")[1] == ()


def test_roles_and_claims_over_http() -> None:
    w = World()
    app = make_app(w)
    assert call(app, "POST", f"/tasks/{w.task.id}/claim", "dave", {"csrf": TOKEN})[
        "status"
    ].startswith("403")
    claim(app, w, "alice")
    assert call(app, "POST", f"/tasks/{w.task.id}/claim", "bob", {"csrf": TOKEN})[
        "status"
    ].startswith("409")
    r = call(app, "POST", f"/tasks/{w.task.id}/action", "dave", form(w, app, "APPROVE"))
    assert r["status"].startswith("403") and "ROLE" in r["body"]
    page = call(app, "GET", f"/tasks/{w.task.id}", "dave")
    assert page["status"].startswith("200") and "APPROVE: unavailable" in page["body"]


def test_incomplete_review_is_rendered_with_the_engine_reasons() -> None:
    w = World(labels=(Label.POSSIBLE_DUPLICATE,))
    app = make_app(w)
    claim(app, w)
    r = call(app, "POST", f"/tasks/{w.task.id}/action", "bob", form(w, app, "APPROVE"))
    assert (
        r["status"].startswith("422")
        and "DISPOSITION:m0" in r["body"]
        and "Nothing was recorded" in r["body"]
    )
    ok = call(
        app,
        "POST",
        f"/tasks/{w.task.id}/action",
        "bob",
        form(w, app, "APPROVE", **{"disp:m0": "NOT_A_DUPLICATE"}),
    )
    assert ok["status"].startswith("200") and w.store.get("obl-1")[0].status.value == "APPROVED"


def test_ui_driven_sequence_equals_the_direct_engine_sequence() -> None:
    ui, direct = World(questions=("deadline:x",)), World(questions=("deadline:x",))
    app = make_app(ui)
    claim(app, ui, "alice")
    edit = form(
        ui,
        app,
        "EDIT",
        reason="set deadline",
        **{"edit:deadline": "paling lambat 3 hari", "before:deadline": ""},
    )
    assert call(app, "POST", f"/tasks/{ui.task.id}/action", "alice", edit)["status"].startswith(
        "200"
    )
    claim(app, ui, "bob")
    assert call(app, "POST", f"/tasks/{ui.task.id}/action", "bob", form(ui, app, "APPROVE"))[
        "status"
    ].startswith("200")
    assert call(app, "POST", f"/tasks/{ui.task.id}/action", "carol", form(ui, app, "PUBLISH"))[
        "status"
    ].startswith("200")

    direct.clock = ui.clock
    direct.do(
        __import__("rv_engine_helpers").ALICE,
        A.EDIT,
        reason="set deadline",
        changes=(change("deadline", None, "paling lambat 3 hari"),),
    )
    direct.do(BOB, A.APPROVE)
    direct.do(__import__("rv_engine_helpers").CAROL, A.PUBLISH)
    assert ui.store.get("obl-1")[0] == direct.store.get("obl-1")[0]
    assert ui.store.get("obl-1")[1] == direct.store.get("obl-1")[1]


def test_the_page_a_reviewer_was_shown_is_the_page_the_engine_judges() -> None:
    w = World()
    app = make_app(w)
    claim(app, w)
    shown = call(app, "GET", f"/tasks/{w.task.id}")["body"]
    assert (
        f'value="{w.store.version("obl-1")}"' in shown
        and f'value="{app.tasks[w.task.id].snapshot.hash}"' in shown
    )
    assert 'name="csrf"' in shown and 'name="actor' not in shown


QUESTIONS = ("deadline:undelimited trigger", "actor:comma inside the actor phrase")


@pytest.mark.parametrize("seed", range(25))
def test_random_http_sequences_match_direct_engine_calls(seed: int) -> None:
    import random

    from rv_engine_helpers import CFG
    from ui_helpers import ACTORS, CLOCK

    from regulus.review import (
        ActionRequest,
        ClaimError,
        Disposition,
        MatchDisposition,
        OpenQuestionResolution,
        RejectCode,
        RejectReason,
        Resolution,
        apply,
        claim,
    )

    rng = random.Random(seed)
    kw = {
        "questions": QUESTIONS[: rng.randint(0, 2)],
        "labels": (Label.POSSIBLE_DUPLICATE,) * rng.randint(0, 1),
    }
    ui, direct = World(**kw), World(**kw)
    app, task = make_app(ui), direct.task
    for _ in range(20):
        who = rng.choice(["alice", "bob", "carol"])
        actor = ACTORS[who]
        if rng.random() < 0.7:
            r = call(app, "POST", f"/tasks/{ui.task.id}/claim", who, {"csrf": TOKEN})
            if who == "carol":
                assert r["status"].startswith("403")
            else:
                try:
                    task = claim(task, who, CLOCK, CFG.claim_ttl_seconds)
                    assert r["status"].startswith("200")
                except ClaimError:
                    assert r["status"].startswith("409")
        action = rng.choice(list(A))
        extra: dict[str, str] = {}
        req_kw: dict[str, object] = {}
        if action is A.APPROVE:
            ok = rng.random() < 0.7
            if ok:
                for q in QUESTIONS[: len(kw["questions"])]:
                    extra[f"res:{q}"] = "ACCEPTED_AS_IS"
                if kw["labels"]:
                    extra["disp:m0"] = "NOT_A_DUPLICATE"
            req_kw["resolutions"] = tuple(
                OpenQuestionResolution(question=q[4:], resolution=Resolution(v))
                for q, v in extra.items()
                if q.startswith("res:")
            )
            req_kw["dispositions"] = tuple(
                MatchDisposition(match_id=q[5:], disposition=Disposition(v))
                for q, v in extra.items()
                if q.startswith("disp:")
            )
        elif action is A.REJECT:
            extra["reject_code"] = "OUT_OF_SCOPE"
            req_kw["reject_reason"] = RejectReason(code=RejectCode.OUT_OF_SCOPE)
        elif action is A.EDIT:
            n = f"paling lambat {rng.randint(1, 9)} hari"
            extra.update(
                {
                    "reason": "r",
                    "edit:deadline": n,
                    "before:deadline": direct.store.get("obl-1")[0].current.deadline or "",
                }
            )
            req_kw.update(
                reason="r",
                changes=(change("deadline", direct.store.get("obl-1")[0].current.deadline, n),),
            )
            if extra["before:deadline"] == n:
                continue
        stale = rng.random() < 0.15
        post = form(ui, app, action.value, **extra)
        if stale:
            post["base_version"] = "old"
        resp = call(app, "POST", f"/tasks/{ui.task.id}/action", who, post)
        req = ActionRequest(
            action=action,
            task_id=task.id,
            base_version="old" if stale else direct.store.version("obl-1"),
            actor=actor,
            at=CLOCK,
            **req_kw,
        )  # type: ignore[arg-type]
        out = apply(direct.store, task, req, CFG, direct.texts)
        if out.task is not None:
            task = out.task
        assert ui.store.get("obl-1") == direct.store.get("obl-1"), (
            who,
            action,
            extra,
            resp["status"],
            out.status,
            out.reasons,
        )
        assert app.tasks[ui.task.id] == task


def test_question_resolutions_carry_their_note_over_http_and_pages_need_no_script() -> None:
    w = World(questions=(QUESTIONS[0],))
    app = make_app(w)
    claim(app, w)
    page = call(app, "GET", f"/tasks/{w.task.id}")["body"]
    assert "<script" not in page.lower() and 'name="note:deadline:undelimited trigger"' in page
    post = form(
        w,
        app,
        "APPROVE",
        **{f"res:{QUESTIONS[0]}": "ACCEPTED_AS_IS", f"note:{QUESTIONS[0]}": "no deadline stated"},
    )
    assert call(app, "POST", f"/tasks/{w.task.id}/action", "bob", post)["status"].startswith("200")
    rec = w.store.get("obl-1")[1][0]
    assert rec.open_question_resolutions[0].note == "no deadline stated"
