from datetime import UTC, datetime

import pytest
from gen_helpers import REG, candidates, make_doc, run

from regulus.domain import (
    ObligationStatus as OS,
)
from regulus.domain import (
    Origin,
    OwnerKind,
    TransitionError,
    apply_decision,
    submit,
)
from regulus.generation import (
    ExtractiveGenerator,
    GenerationConfig,
    GenerationInput,
    GenerationRequest,
    Status,
    Violation,
    generate,
)
from regulus.generation.models import Disposition, Step
from regulus.generation.verify import verify_evidence
from regulus.obligations import FieldStatus as F

BODY = "Pasal 1\nPengendali wajib menyampaikan laporan setiap 3 bulan kepada Lembaga."


def one(body: str = BODY, **kw):  # type: ignore[no-untyped-def]
    out, doc, cands = run(body, **kw)
    (r,) = out.results
    return r, cands[0], doc


def test_generated_obligation_basics() -> None:
    r, c, _ = one()
    assert r.status is Status.GENERATED and r.obligation is not None and r.record is not None
    o = r.obligation
    assert o.id.startswith("obl-") and o.status is OS.GENERATED and o.origin is Origin.RULE
    assert o.generated.meta is None and o.current == o.generated.content
    assert o.article_id == f"{REG}:1" and o.source_owner_id == f"{REG}:1"
    assert o.current.text == "Pengendali wajib menyampaikan laporan setiap 3 bulan kepada Lembaga"
    assert (o.current.actor, o.current.action, o.current.object, o.current.frequency) == (
        "Pengendali",
        "menyampaikan",
        "laporan",
        "setiap 3 bulan",
    )
    assert (
        o.current.deadline is None and o.current.condition is None and o.current.exception is None
    )
    assert (
        r.record.generator == "extractive@1"
        and r.record.candidate_id == c.id
        and r.record.source_complete
    )
    assert r.record.extractor == c.extractor and r.record.model is None


def test_evidence_is_built_from_the_candidates_own_citations() -> None:
    r, c, doc = one()
    text = doc.articles[0].text
    assert all(
        e.obligation_id == r.obligation.id and e.owner_kind is OwnerKind.ARTICLE for e in r.evidence
    )  # type: ignore[union-attr]
    assert all(text[e.span[0] : e.span[1]] == e.quote for e in r.evidence)
    assert (c.clause.start, c.clause.end) in {e.span for e in r.evidence}
    assert len({e.span for e in r.evidence}) == len(r.evidence)


def test_every_candidate_field_has_exactly_one_disposition() -> None:
    r, c, _ = one()
    refs = [(e.field.role, e.field.index) for e in r.trace.candidate]  # type: ignore[union-attr]
    assert len(refs) == len(set(refs)) and {
        "clause",
        "marker",
        "actor",
        "action",
        "object",
        "deadline",
        "frequency",
    } <= {x[0] for x in refs}
    by = {e.field.role: e for e in r.trace.candidate}  # type: ignore[union-attr]
    assert (
        by["deadline"].disposition is Disposition.ABSENT_NOT_STATED
        and by["actor"].disposition is Disposition.PRESERVED
    )
    assert {c_.field for c_ in r.trace.content} >= {  # type: ignore[union-attr]
        ct.field
        for ct in r.trace.content
        if ct.field in ("actor", "action", "object", "frequency", "text")
    }  # type: ignore[union-attr]
    text = next(ct for ct in r.trace.content if ct.field == "text")  # type: ignore[union-attr]
    assert {s.role for s in text.sources} >= {
        "clause",
        "marker",
        "actor",
        "action",
        "object",
        "frequency",
    }


def test_whitespace_is_normalized_and_recorded() -> None:
    r, _, _ = one("Pasal 1\nPengendali Data\nPribadi wajib menyampaikan\nlaporan.")
    assert r.obligation.current.actor == "Pengendali Data Pribadi"  # type: ignore[union-attr]
    step = next(e for e in r.trace.candidate if e.field.role == "actor")  # type: ignore[union-attr]
    assert step.disposition is Disposition.NORMALIZED and step.steps == (Step.WHITESPACE_COLLAPSE,)
    assert "\n" not in r.obligation.current.text  # type: ignore[union-attr]


def test_several_conditions_are_joined_with_the_originals_in_the_trace() -> None:
    r, _, _ = one(
        "Pasal 1\nDalam hal terjadi kegagalan, Pengendali wajib menghapus data apabila diminta Subjek."
    )
    assert r.obligation.current.condition == "Dalam hal terjadi kegagalan; apabila diminta Subjek"  # type: ignore[union-attr]
    ct = next(c for c in r.trace.content if c.field == "condition")  # type: ignore[union-attr]
    assert Step.JOIN in ct.steps and [(s.role, s.index) for s in ct.sources] == [
        ("condition", 0),
        ("condition", 1),
    ]


def test_duplicate_condition_is_dropped_with_the_closed_reason() -> None:
    out, doc, cands = run("Pasal 1\nDalam hal X, Pengendali wajib menghapus data apabila diminta.")
    c = cands[0]
    dup = c.model_copy(update={"conditions": (c.conditions[0], c.conditions[0])})
    res = generate(GenerationInput(candidates=(dup,), documents={REG: doc}), ExtractiveGenerator())
    (r,) = res.results
    assert r.status is Status.GENERATED
    dropped = [e for e in r.trace.candidate if e.disposition is Disposition.DROPPED]  # type: ignore[union-attr]
    assert [(e.field.role, e.field.index, e.reason) for e in dropped] == [
        ("condition", 1, "DUPLICATE")
    ]
    assert r.obligation.current.condition == "Dalam hal X"  # type: ignore[union-attr]


def test_not_stated_and_undetermined_are_kept_apart() -> None:
    r, _, _ = one("Pasal 1\nDalam melakukan pemrosesan, Pengendali wajib menunjukkan bukti.")
    assert r.obligation.current.actor is None  # type: ignore[union-attr]
    by = {e.field.role: e for e in r.trace.candidate}  # type: ignore[union-attr]
    assert (
        by["actor"].disposition is Disposition.ABSENT_UNDETERMINED
        and by["deadline"].disposition is Disposition.ABSENT_NOT_STATED
    )
    assert r.open_questions == ("actor:comma inside the actor phrase",)
    plain, _, _ = one()
    assert plain.open_questions == ()


def test_enumerated_action_is_generated_with_items_and_an_open_question() -> None:
    r, c, _ = one("Pasal 1\nPengendali wajib:\na. menyampaikan laporan;\nb. menyimpan dokumen.")
    assert c.action.status is F.UNDETERMINED
    assert r.status is Status.GENERATED and r.obligation.current.action is None  # type: ignore[union-attr]
    assert (
        "menyampaikan laporan" in r.obligation.current.text
        and "menyimpan dokumen" in r.obligation.current.text
    )  # type: ignore[union-attr]
    assert r.open_questions == ("action:enumerated_items",)
    assert [e.field.role for e in r.trace.candidate].count("item") == 2  # type: ignore[union-attr]


def test_enumeration_item_with_lead_in_actor() -> None:
    out, doc, cands = run(
        "Pasal 1\nPengendali:\na. wajib menyimpan arsip;\nb. dilarang menghapus arsip."
    )
    assert [r.status for r in out.results] == [Status.GENERATED, Status.GENERATED]
    t = out.results[0].obligation.current.text  # type: ignore[union-attr]
    assert t.startswith("Pengendali") and "wajib menyimpan arsip" in t


def test_amendment_unit_candidate_cites_the_unit_and_belongs_to_the_target_article() -> None:
    from datetime import date

    from regulus.documents import process
    from regulus.documents.models import PageSource, RawPage
    from regulus.domain import EventType as T
    from regulus.domain import Regulation, RegulatoryEvent
    from regulus.domain import RegulationKind as K
    from regulus.lineage import LineageInput, analyze_impact
    from regulus.obligations import ExtractionInput, RulesExtractor, extract

    actor = Regulation.of(K.PP, "5", 2026, title="Perubahan", promulgated_on=date(2026, 7, 16))
    target = Regulation.of(K.PP, "10", 2020, title="Target", promulgated_on=date(2020, 1, 1))
    body = (
        "PERATURAN PEMERINTAH\nNOMOR 5 TAHUN 2026\nTENTANG PERUBAHAN ATAS PERATURAN PEMERINTAH\nMenimbang : bahwa.\n"
        "MEMUTUSKAN:\nMenetapkan: PERATURAN PEMERINTAH.\nPasal I\n"
        "Beberapa ketentuan dalam Peraturan Pemerintah Nomor 10 Tahun 2020 diubah sebagai berikut:\n"
        "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut:\nPasal 5\n(1) Setiap Orang wajib melapor paling lambat 7 hari.\n"
        "Pasal II\nPeraturan Pemerintah ini mulai berlaku pada tanggal diundangkan.\nDitetapkan di Jakarta"
    )
    doc = process(
        b"u", actor.id, lambda d: [RawPage(number=1, source=PageSource.NATIVE, text=body)]
    )
    ev = RegulatoryEvent(
        id="e1",
        type=T.AMEND,
        regulation_id=actor.id,
        target_id=target.id,
        occurred_on=date(2026, 7, 16),
        detected_on=date(2026, 7, 17),
        basis="b",
    )
    lin = analyze_impact(
        ev, LineageInput(events=(ev,), regulations=(actor, target), documents={actor.id: doc})
    )
    ex = extract(ExtractionInput(changes=lin.changed, documents={actor.id: doc}), RulesExtractor())
    (cand,) = ex.results[0].candidates
    res = generate(
        GenerationInput(candidates=(cand,), documents={actor.id: doc}), ExtractiveGenerator()
    )
    (r,) = res.results
    o = r.obligation
    assert r.status is Status.GENERATED and o is not None
    assert o.article_id == f"{target.id}:5" and o.source_owner_id.endswith(":unit-I")
    assert {e.owner_kind for e in r.evidence} == {OwnerKind.AMENDMENT_UNIT} and all(
        e.owner_id == o.source_owner_id for e in r.evidence
    )
    assert (o.current.actor, o.current.action, o.current.deadline) == (
        "Setiap Orang",
        "melapor",
        "paling lambat 7 hari",
    )
    pending = submit(o)
    assert apply_decision(pending, _approve(o.id), list(r.evidence)).status is OS.APPROVED
    wrong = [
        e.model_copy(update={"owner_id": f"{target.id}:5", "owner_kind": OwnerKind.ARTICLE})
        for e in r.evidence
    ]
    with pytest.raises(TransitionError):
        apply_decision(pending, _approve(o.id), wrong)


def _approve(oid: str):  # type: ignore[no-untyped-def]
    from regulus.domain import ReviewDecision

    return ReviewDecision(
        id="d",
        obligation_id=oid,
        reviewer="r",
        at=datetime(2026, 8, 1, tzinfo=UTC),
        from_status=OS.PENDING_REVIEW,
        to_status=OS.APPROVED,
    )


class Scripted:
    id, version, origin, model, prompt_version = "scripted", "1", Origin.RULE, None, None

    def __init__(self, mutate=None, raises=None, returns=None) -> None:  # type: ignore[no-untyped-def]
        self.mutate, self.raises, self.returns = mutate, raises, returns

    def generate(self, request: GenerationRequest):  # type: ignore[no-untyped-def]
        if self.raises:
            raise self.raises
        if self.returns is not None:
            return self.returns
        raw = ExtractiveGenerator().generate(request)
        return self.mutate(raw) if self.mutate else raw


def test_generator_failure_and_malformed_output_yield_no_obligation() -> None:
    for g in (
        Scripted(raises=RuntimeError("x")),
        Scripted(raises=TimeoutError("slow")),
        Scripted(returns={"text": "x"}),
        Scripted(returns=None.__class__),
    ):
        out, _, _ = run(BODY, g)
        (r,) = out.results
        assert r.status is Status.GENERATOR_FAILED and r.obligation is None and r.evidence == ()


def test_rejected_output_is_kept_for_audit_but_never_promoted() -> None:
    out, _, _ = run(
        BODY,
        Scripted(
            lambda raw: raw.model_copy(update={"text": raw.text + " kecuali ditentukan lain"})
        ),
    )
    (r,) = out.results
    assert r.status is Status.REJECTED_BY_VERIFICATION and Violation.NEW_WORD in r.violations
    assert r.obligation is None and r.raw is not None and r.record is None


def test_partial_output_never_becomes_an_obligation() -> None:
    out, _, _ = run(
        BODY, Scripted(lambda raw: raw.model_copy(update={"text": "Pengendali wajib menyampaikan"}))
    )
    (r,) = out.results
    assert r.status is Status.REJECTED_BY_VERIFICATION and Violation.FIELD_LOST in r.violations


def test_not_generable_when_source_or_citation_is_missing() -> None:
    doc = make_doc(BODY)
    cand = candidates(doc)[0]
    miss = generate(GenerationInput(candidates=(cand,), documents={}), ExtractiveGenerator())
    assert (
        miss.results[0].status is Status.NOT_GENERABLE
        and miss.results[0].reason == "SOURCE_MISSING"
    )
    other = make_doc("Pasal 1\nTeks yang sama sekali berbeda dari sebelumnya untuk dokumen lain.")
    bad = generate(
        GenerationInput(candidates=(cand,), documents={REG: other}), ExtractiveGenerator()
    )
    assert (
        bad.results[0].status is Status.NOT_GENERABLE
        and bad.results[0].reason == "CITATION_MISMATCH"
    )


class FakeAI(ExtractiveGenerator):
    id, version, origin = "fake-ai", "1", Origin.AI

    def __init__(self, model: str | None = "m", prompt: str | None = "p1") -> None:
        self.model, self.prompt_version = model, prompt


def test_ai_origin_requires_and_records_generation_metadata() -> None:
    when = datetime(2026, 9, 9, tzinfo=UTC)
    doc = make_doc(BODY)
    inp = GenerationInput(candidates=candidates(doc), documents={REG: doc})
    (r,) = generate(inp, FakeAI(), generated_at=when).results
    assert r.status is Status.GENERATED and r.obligation.origin is Origin.AI  # type: ignore[union-attr]
    meta = r.obligation.generated.meta  # type: ignore[union-attr]
    assert (meta.model, meta.prompt_version, meta.generated_at) == ("m", "p1", when)
    assert (r.record.model, r.record.prompt_version, r.record.generated_at) == ("m", "p1", when)  # type: ignore[union-attr]
    (bad,) = generate(inp, FakeAI(model=None)).results
    assert bad.status is Status.REJECTED_BY_VERIFICATION and bad.violations == (
        Violation.LIFECYCLE_INVALID,
    )


def test_generation_never_produces_anything_but_generated_status() -> None:
    out, _, _ = run(BODY + "\nPasal 2\nSetiap Orang dilarang menggunakan data.")
    assert {r.obligation.status for r in out.results if r.obligation} == {OS.GENERATED}


def test_incomplete_extraction_is_flagged_not_hidden() -> None:
    doc = make_doc(BODY)
    c = candidates(doc)[0]
    (r,) = generate(
        GenerationInput(candidates=(c,), documents={REG: doc}, extraction_complete={c.id: False}),
        ExtractiveGenerator(),
    ).results
    assert r.status is Status.GENERATED and r.record.source_complete is False  # type: ignore[union-attr]


def test_deterministic_ids_and_version_sensitivity_and_purity() -> None:
    doc = make_doc(BODY)
    inp = GenerationInput(candidates=candidates(doc), documents={REG: doc})
    snap = inp.model_dump_json()
    a, b = generate(inp, ExtractiveGenerator()), generate(inp, ExtractiveGenerator())
    assert a.model_dump_json() == b.model_dump_json() and inp.model_dump_json() == snap
    other = generate(inp, ExtractiveGenerator(), GenerationConfig(config_version="2"))
    assert a.results[0].obligation.id != other.results[0].obligation.id  # type: ignore[union-attr]
    (v2,) = generate(inp, Scripted()).results
    assert v2.obligation.id != a.results[0].obligation.id  # type: ignore[union-attr]


def test_forged_evidence_is_rejected_by_the_evidence_verifier() -> None:
    r, c, doc = one()
    text = doc.articles[0].text
    good = list(r.evidence)
    oid = r.obligation.id  # type: ignore[union-attr]
    assert verify_evidence(good, c, text, oid) == []
    forged = good[0].model_copy(update={"span": (0, 4), "quote": text[:4]})
    assert verify_evidence([forged, *good[1:]], c, text, oid) == [Violation.CITATION_MISMATCH]
    assert verify_evidence([], c, text, oid) == [Violation.CITATION_MISMATCH]
    other_obl = good[0].model_copy(update={"obligation_id": "obl-x"})
    assert verify_evidence([other_obl, *good[1:]], c, text, oid) == [Violation.CITATION_MISMATCH]
    no_clause = [e for e in good if e.span != (c.clause.start, c.clause.end)]
    assert verify_evidence(no_clause, c, text, oid) == [Violation.CITATION_MISMATCH]


def test_output_is_a_valid_phase1_obligation() -> None:
    r, _, _ = one()
    from regulus.domain import Obligation, ObligationEvidence

    assert Obligation.model_validate_json(r.obligation.model_dump_json()) == r.obligation  # type: ignore[union-attr]
    assert all(ObligationEvidence.model_validate_json(e.model_dump_json()) == e for e in r.evidence)
