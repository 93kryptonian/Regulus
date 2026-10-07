from datetime import UTC, datetime
from itertools import product

import pytest
from pydantic import ValidationError

from regulus.domain import (
    TRANSITIONS,
    Article,
    FieldChange,
    Obligation,
    ObligationEvidence,
    OwnerKind,
    ReviewDecision,
    TransitionError,
    apply_decision,
    submit,
)
from regulus.domain import (
    ObligationStatus as S,
)

AT = datetime(2026, 2, 1, tzinfo=UTC)


def decision(frm: S, to: S, **kw: object) -> ReviewDecision:
    return ReviewDecision(
        id="d", obligation_id="o1", reviewer="r", at=AT, from_status=frm, to_status=to, **kw
    )  # type: ignore[arg-type]


def edit(o: Obligation, **kw: object) -> ReviewDecision:
    ch = (FieldChange(field="deadline", before="3 months", after="14 days"),)
    return decision(S.PENDING_REVIEW, S.EDITED, reason="per art. 5", changes=ch, **kw)


def test_transition_table_is_closed() -> None:
    for a, b in product(S, S):
        ok = b in TRANSITIONS[a]
        if ok:
            continue
        with pytest.raises(ValidationError):
            decision(a, b, reason="r", changes=())


def test_terminal_states_have_no_exits() -> None:
    assert not TRANSITIONS[S.REJECTED] and not TRANSITIONS[S.PUBLISHED]


def test_reason_and_changes_rules() -> None:
    with pytest.raises(ValidationError):
        decision(S.PENDING_REVIEW, S.REJECTED)
    with pytest.raises(ValidationError):
        decision(S.PENDING_REVIEW, S.EDITED, reason="x")
    with pytest.raises(ValidationError):
        decision(
            S.PENDING_REVIEW,
            S.APPROVED,
            changes=(FieldChange(field="text", before="a", after="b"),),
        )


def test_field_change_validation() -> None:
    with pytest.raises(ValidationError):
        FieldChange(field="nope", before="a", after="b")
    with pytest.raises(ValidationError):
        FieldChange(field="text", before="a", after="a")


def test_approve_requires_evidence(obligation: Obligation, evidence: ObligationEvidence) -> None:
    d = decision(S.PENDING_REVIEW, S.APPROVED)
    with pytest.raises(TransitionError):
        apply_decision(obligation, d, [])
    other = evidence.model_copy(update={"obligation_id": "zzz"})
    with pytest.raises(TransitionError):
        apply_decision(obligation, d, [other])
    assert apply_decision(obligation, d, [evidence]).status is S.APPROVED


def test_edit_updates_current_keeps_generated(obligation: Obligation) -> None:
    new = apply_decision(obligation, edit(obligation), [])
    assert new.status is S.EDITED
    assert new.current.deadline == "14 days"
    assert new.generated == obligation.generated
    assert obligation.current.deadline == "3 months"


def test_edit_back_to_review_then_approve(
    obligation: Obligation, evidence: ObligationEvidence
) -> None:
    o = apply_decision(obligation, edit(obligation), [])
    o = apply_decision(o, decision(S.EDITED, S.PENDING_REVIEW), [])
    o = apply_decision(o, decision(S.PENDING_REVIEW, S.APPROVED), [evidence])
    o = apply_decision(o, decision(S.APPROVED, S.PUBLISHED), [])
    assert o.status is S.PUBLISHED and o.current.deadline == "14 days"


def test_stale_decision_and_stale_edit(obligation: Obligation) -> None:
    with pytest.raises(TransitionError):
        apply_decision(obligation, decision(S.APPROVED, S.PUBLISHED), [])
    stale = decision(
        S.PENDING_REVIEW,
        S.EDITED,
        reason="x",
        changes=(FieldChange(field="deadline", before="1 year", after="2"),),
    )
    with pytest.raises(TransitionError):
        apply_decision(obligation, stale, [])


def test_wrong_obligation_and_double_approval(
    obligation: Obligation, evidence: ObligationEvidence
) -> None:
    other = decision(S.PENDING_REVIEW, S.APPROVED).model_copy(update={"obligation_id": "x"})
    with pytest.raises(TransitionError):
        apply_decision(obligation, other, [evidence])
    d = decision(S.PENDING_REVIEW, S.APPROVED)
    once = apply_decision(obligation, d, [evidence])
    with pytest.raises(TransitionError):
        apply_decision(once, d, [evidence])


def test_edit_cannot_blank_required_text(obligation: Obligation) -> None:
    d = decision(
        S.PENDING_REVIEW,
        S.EDITED,
        reason="x",
        changes=(FieldChange(field="text", before=obligation.current.text, after=None),),
    )
    with pytest.raises(ValidationError):
        apply_decision(obligation, d, [])


def test_apply_is_pure(obligation: Obligation, evidence: ObligationEvidence) -> None:
    snap = obligation.model_dump()
    apply_decision(obligation, decision(S.PENDING_REVIEW, S.APPROVED), [evidence])
    assert obligation.model_dump() == snap


def test_evidence_span_rules(article: Article, evidence: ObligationEvidence) -> None:
    assert evidence.matches(article.id, article.text)
    bad = evidence.model_copy(update={"quote": "x" * len(evidence.quote)})
    assert not bad.matches(article.id, article.text)
    for span in [(5, 5), (-1, 3), (0, 99)]:
        with pytest.raises(ValidationError):
            ObligationEvidence(
                obligation_id="o",
                owner_id="a",
                owner_kind=OwnerKind.ARTICLE,
                span=span,
                quote="abc",
            )
    long = evidence.model_copy(update={"span": (len(article.text) - 3, len(article.text) + 5)})
    assert not long.matches(article.id, article.text)


def test_submit_is_a_workflow_step_not_a_decision(obligation: Obligation) -> None:
    gen = obligation.model_copy(update={"status": S.GENERATED})
    assert submit(gen).status is S.PENDING_REVIEW
    assert gen.status is S.GENERATED
    with pytest.raises(TransitionError):
        submit(obligation)
    with pytest.raises(ValidationError):
        decision(S.GENERATED, S.PENDING_REVIEW)


def test_evidence_wrong_article_and_unverified_not_counted(
    article: Article, obligation: Obligation, evidence: ObligationEvidence
) -> None:
    other = article.model_copy(update={"id": "other"})
    assert not evidence.matches(other.id, other.text)
    forged = evidence.model_copy(update={"quote": "x" * len(evidence.quote)})
    verified = [e for e in (forged,) if e.matches(article.id, article.text)]
    with pytest.raises(TransitionError):
        apply_decision(obligation, decision(S.PENDING_REVIEW, S.APPROVED), verified)


def test_amendment_sourced_obligation_cites_the_unit_not_the_article(
    obligation: Obligation,
) -> None:
    unit_text = "Pasal 5\n(1) Setiap Orang wajib melapor."
    ob = obligation.model_copy(
        update={"article_id": "PP-10-2020:5", "source_owner_id": "PP-5-2026:unit-I"}
    )
    quote = "wajib melapor"
    s = unit_text.index(quote)
    ev = ObligationEvidence(
        obligation_id=ob.id,
        owner_id="PP-5-2026:unit-I",
        owner_kind=OwnerKind.AMENDMENT_UNIT,
        span=(s, s + len(quote)),
        quote=quote,
    )
    assert ev.matches("PP-5-2026:unit-I", unit_text) and not ev.matches("PP-10-2020:5", unit_text)
    assert not ev.matches("PP-5-2026:unit-I", "other text entirely")
    assert apply_decision(ob, decision(S.PENDING_REVIEW, S.APPROVED), [ev]).status is S.APPROVED
    wrong_owner = ev.model_copy(
        update={"owner_id": "PP-10-2020:5", "owner_kind": OwnerKind.ARTICLE}
    )
    with pytest.raises(TransitionError):
        apply_decision(ob, decision(S.PENDING_REVIEW, S.APPROVED), [wrong_owner])


def test_source_owner_id_is_required_and_article_id_keeps_its_meaning(
    obligation: Obligation,
) -> None:
    data = obligation.model_dump()
    del data["source_owner_id"]
    with pytest.raises(ValidationError):
        Obligation.model_validate(data)
    assert obligation.source_owner_id == obligation.article_id
