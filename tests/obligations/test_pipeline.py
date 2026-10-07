from datetime import date

import pytest
from ob_helpers import REG, cands, changes_for, make_doc, one, run, val

from regulus.documents import DocStatus, locate
from regulus.domain import (
    EventType as T,
)
from regulus.domain import (
    Generated,
    Obligation,
    ObligationContent,
    Origin,
    Regulation,
    RegulatoryEvent,
)
from regulus.domain import (
    RegulationKind as K,
)
from regulus.lineage import LineageInput, analyze_impact
from regulus.lineage.models import (
    ChangedKind,
    ChangedProvision,
    Effect,
    TextRef,
    WithdrawnProvision,
)
from regulus.obligations import (
    ExtractionInput,
    RulesExtractor,
    extract,
)
from regulus.obligations import (
    FieldStatus as F,
)
from regulus.obligations import (
    ResultStatus as S,
)
from regulus.obligations.models import (
    DiagCode,
    ExtractionRequest,
    FieldStatus,
    ImpactKind,
    RawCandidate,
    RawField,
    RawFieldState,
)

ENUM = "Pasal 1\n(1) Pengendali wajib memiliki:\na. kebijakan privasi;\nb. kanal pelaporan.\n(2) Pengendali wajib menyimpan arsip."


def test_enumeration_is_not_split_and_items_are_structural_citations() -> None:
    out, doc = run(ENUM)
    lead, plain = out.results[0].candidates
    assert len(lead.items) == 2 and [i.quote[:2] for i in lead.items] == ["a.", "b."]
    assert val(lead.action) == "memiliki" and lead.object.status is F.NOT_STATED
    assert plain.items == () and val(plain.action) == "menyimpan"
    text = doc.articles[0].text
    assert all(text[i.start : i.end] == i.quote for i in lead.items)


def test_enumeration_item_with_marker_is_its_own_candidate_with_lead_in_actor() -> None:
    cs = cands("Pasal 1\nPengendali:\na. wajib menyimpan arsip;\nb. dilarang menghapus arsip.")
    assert [(c.modality.value, val(c.action)) for c in cs] == [
        ("OBLIGATION", "menyimpan"),
        ("PROHIBITION", "menghapus"),
    ]
    for c in cs:
        assert (
            val(c.actor) == "Pengendali"
            and c.lead_in is not None
            and c.lead_in.quote.startswith("Pengendali")
        )
        assert c.actor.value and c.actor.value.citation.within(c.lead_in)


def test_lead_in_with_action_and_an_item_carrying_a_marker_reports_it() -> None:
    out, _ = run("Pasal 1\nPengendali wajib menyimpan:\na. arsip;\nb. dilarang menghapus arsip.")
    r = out.results[0]
    assert [(c.modality.value, val(c.action)) for c in r.candidates] == [
        ("OBLIGATION", "menyimpan"),
        ("PROHIBITION", "menghapus"),
    ]
    assert len(r.candidates[0].items) == 2
    assert any(d.code is DiagCode.ENUMERATION_ITEM_MARKER for d in r.diagnostics)


def test_lead_in_marker_without_action_and_item_with_marker() -> None:
    out, _ = run("Pasal 1\nPengendali wajib:\na. menyimpan arsip;\nb. dilarang menghapus arsip.")
    r = out.results[0]
    lead, item = r.candidates
    assert (
        lead.action.status is F.UNDETERMINED
        and lead.action.reason == "enumerated_items"
        and len(lead.items) == 2
    )
    assert (item.modality.value, val(item.action)) == ("PROHIBITION", "menghapus")
    assert not [d for d in r.diagnostics if d.code is DiagCode.UNEXTRACTED_DEONTIC]
    assert any(d.code is DiagCode.ENUMERATION_ITEM_MARKER for d in r.diagnostics)


def test_enumerated_action_is_one_candidate_with_the_items_not_split() -> None:
    out, _ = run("Pasal 1\nPengendali wajib:\na. menyampaikan laporan;\nb. menyimpan dokumen.")
    r = out.results[0]
    (c,) = r.candidates
    assert r.status is S.EXTRACTED and not [
        d for d in r.diagnostics if d.code is DiagCode.UNEXTRACTED_DEONTIC
    ]
    assert (c.action.status, c.action.reason, c.object.status) == (
        F.UNDETERMINED,
        "enumerated_items",
        F.NOT_STATED,
    )
    assert [i.quote[:2] for i in c.items] == ["a.", "b."] and val(c.actor) == "Pengendali"
    assert [(d.code, d.severity) for d in r.diagnostics] == [(DiagCode.UNDETERMINED_FIELD, "info")]


def test_marker_followed_by_colon_without_items_gets_no_exception() -> None:
    out, _ = run("Pasal 1\nPengendali wajib:")
    r = out.results[0]
    assert r.status is S.UNRESOLVED and r.candidates == ()
    assert [d.code for d in r.diagnostics] == [DiagCode.UNEXTRACTED_DEONTIC]


def test_enumerated_object_keeps_a_present_action_and_is_not_split() -> None:
    c = one("Pasal 1\nPengendali wajib memuat:\na. nama;\nb. alamat.")
    assert val(c.action) == "memuat" and len(c.items) == 2 and c.object.status is F.NOT_STATED


class Scripted:
    id, version = "scripted", "1"

    def __init__(self, mutate=None, raises: Exception | None = None) -> None:  # type: ignore[no-untyped-def]
        self.mutate, self.raises, self.base = mutate, raises, RulesExtractor()

    def extract(self, request: ExtractionRequest) -> tuple[RawCandidate, ...]:
        if self.raises:
            raise self.raises
        return tuple(self.mutate(c) if self.mutate else c for c in self.base.extract(request))


BODY = "Pasal 1\nPengendali wajib menyampaikan laporan. Lembaga berwenang melakukan pengawasan."


def run_with(extractor):  # type: ignore[no-untyped-def]
    out, _ = run(BODY, extractor)
    return out.results[0]


def fake(value: str, start: int, end: int) -> RawFieldState:
    return RawFieldState(
        status=FieldStatus.PRESENT, value=RawField(value=value, start=start, end=end)
    )


def test_fabricated_action_drops_the_candidate_and_the_marker_is_reported() -> None:
    r = run_with(
        Scripted(
            lambda c: c.model_copy(
                update={"action": fake("memusnahkan", c.action.value.start, c.action.value.end)}
            )
        )
    )  # type: ignore[union-attr]
    assert r.candidates == () and r.dropped_ungrounded >= 1 and r.status is S.UNRESOLVED
    assert [d.code for d in r.diagnostics] == [DiagCode.UNEXTRACTED_DEONTIC]


def test_fabricated_non_critical_field_becomes_undetermined_and_is_counted() -> None:
    r = run_with(
        Scripted(
            lambda c: c.model_copy(
                update={"frequency": fake("setiap bulan", c.object.value.start, c.object.value.end)}
            )
        )
    )  # type: ignore[union-attr]
    (cand,) = r.candidates
    assert (
        cand.frequency.status is F.UNDETERMINED
        and cand.frequency.reason == "ungrounded value dropped"
    )
    assert r.dropped_ungrounded == 1 and val(cand.action) == "menyampaikan"


def test_field_outside_the_clause_is_dropped() -> None:
    text = BODY

    def outside(c: RawCandidate) -> RawCandidate:
        s = text.index("pengawasan")
        return c.model_copy(update={"object": fake("pengawasan", s, s + len("pengawasan"))})

    r = run_with(Scripted(outside))
    assert r.candidates[0].object.status is F.UNDETERMINED and r.dropped_ungrounded == 1


def test_marker_not_in_lexicon_or_wrong_modality_drops_the_candidate() -> None:
    def bad_marker(c: RawCandidate) -> RawCandidate:
        return c.model_copy(
            update={
                "marker": RawField(
                    value="menyampaikan", start=c.action.value.start, end=c.action.value.end
                )
            }
        )  # type: ignore[union-attr]

    assert run_with(Scripted(bad_marker)).candidates == ()
    wrong = run_with(Scripted(lambda c: c.model_copy(update={"modality": "PROHIBITION"})))
    assert wrong.candidates == () and wrong.status is S.UNRESOLVED


def test_structural_items_must_match_phase3_provisions() -> None:
    r = run_with(Scripted(lambda c: c.model_copy(update={"items": ((0, 5),)})))
    assert r.candidates[0].items == () and r.dropped_ungrounded == 1


class EnumForger:
    id, version = "forger", "1"

    def __init__(self, text_between: bool) -> None:
        self.between = text_between

    def extract(self, request: ExtractionRequest) -> tuple[RawCandidate, ...]:
        (c,) = RulesExtractor().extract(request)
        if self.between:
            return (
                c.model_copy(
                    update={
                        "action": RawFieldState(
                            status=FieldStatus.UNDETERMINED, reason="enumerated_items"
                        )
                    }
                ),
            )
        return (
            c.model_copy(
                update={
                    "action": RawFieldState(
                        status=FieldStatus.UNDETERMINED, reason="enumerated_items"
                    ),
                    "items": (),
                }
            ),
        )


def test_enumerated_action_exception_cannot_be_forged_by_an_extractor() -> None:
    body = "Pasal 1\nPengendali wajib menyimpan arsip."
    out, _ = run(body, EnumForger(True))
    assert out.results[0].candidates == () and out.results[0].status is S.UNRESOLVED
    no_items, _ = run(
        "Pasal 1\nPengendali wajib:\na. menyimpan arsip;\nb. menghapus arsip.", EnumForger(False)
    )
    assert no_items.results[0].candidates == () and no_items.results[0].status is S.UNRESOLVED
    other_reason = Scripted(
        lambda c: c.model_copy(
            update={"action": RawFieldState(status=FieldStatus.UNDETERMINED, reason="why not")}
        )
    )
    out3, _ = run(
        "Pasal 1\nPengendali wajib:\na. menyimpan arsip;\nb. menghapus arsip.", other_reason
    )
    assert out3.results[0].candidates == ()


def test_extractor_failure_is_failed_never_no_obligation() -> None:
    for exc in (RuntimeError("x"), TimeoutError("slow")):
        r = run_with(Scripted(raises=exc))
        assert r.status is S.FAILED and r.candidates == ()


def test_clause_outside_the_region_is_dropped() -> None:
    r = run_with(Scripted(lambda c: c.model_copy(update={"clause": (0, 3)})))
    assert r.candidates == () and r.status is S.UNRESOLVED


def test_every_candidate_citation_equals_its_text_and_resolves_to_pages() -> None:
    out, doc = run(ENUM + "\nPasal 2\nSetiap Orang dilarang menggunakan data pribadi.")
    by_id = {a.id: a for a in doc.articles}
    pages = {p.number: p for p in doc.pages}
    for r in out.results:
        for c in r.candidates:
            text = by_id[c.clause.owner_id].text
            cites = [
                c.clause,
                c.marker.citation,
                *(v.citation for v in c.conditions + c.exceptions),
                *c.items,
            ]
            for name in ("actor", "action", "object", "deadline", "frequency"):
                v = getattr(c, name).value
                cites += [v.citation] if v else []
            for ct in cites:
                assert text[ct.start : ct.end] == ct.quote
                spans = locate(doc.provenance[ct.owner_id], ct.start, ct.end)
                assert "".join(pages[s.page].text[s.start : s.end] for s in spans).replace(
                    "\n", ""
                ) == ct.quote.replace("\n", "")


def test_deterministic_ids_and_extractor_version_changes_them() -> None:
    a, _ = run(ENUM)
    b, _ = run(ENUM)
    assert a.model_dump_json() == b.model_dump_json()
    sc, _ = run(ENUM, Scripted())
    assert {c.id for r in a.results for c in r.candidates}.isdisjoint(
        {c.id for r in sc.results for c in r.candidates}
    )
    ids = [c.id for r in a.results for c in r.candidates]
    assert len(ids) == len(set(ids))


def test_order_independent_and_inputs_untouched() -> None:
    doc = make_doc(ENUM + "\nPasal 2\nSetiap Orang dilarang menggunakan data pribadi.")
    changes = changes_for(doc)
    one_way = extract(ExtractionInput(changes=changes, documents={REG: doc}), RulesExtractor())
    other = extract(ExtractionInput(changes=changes[::-1], documents={REG: doc}), RulesExtractor())
    assert one_way.model_dump_json() == other.model_dump_json()
    inp = ExtractionInput(changes=changes, documents={REG: doc})
    snap = inp.model_dump_json()
    extract(inp, RulesExtractor())
    assert inp.model_dump_json() == snap


def test_missing_document_and_incomplete_document() -> None:
    doc = make_doc("Pasal 1\nPengendali wajib menyimpan arsip.")
    miss = extract(ExtractionInput(changes=changes_for(doc), documents={}), RulesExtractor())
    assert miss.results[0].status is S.NOT_EXTRACTABLE and not miss.results[0].complete
    partial, _ = run("Pasal 1\nPengendali wajib menyimpan arsip.", fail=True)
    r = partial.results[0]
    assert r.status is S.EXTRACTED and not r.complete
    assert DiagCode.INCOMPLETE_SOURCE in [d.code for d in r.diagnostics]


def obligation(oid: str, article_id: str) -> Obligation:
    c = ObligationContent(text="x")
    return Obligation(
        id=oid, article_id=article_id, origin=Origin.RULE, generated=Generated(content=c), current=c
    )


def test_term_replaced_yields_no_candidates_but_an_impact() -> None:
    doc = make_doc("Pasal 1\nPengendali wajib menyimpan arsip.")
    ch = changes_for(doc, ChangedKind.TERM_REPLACED)
    out = extract(
        ExtractionInput(
            changes=ch, documents={REG: doc}, obligations=(obligation("o1", f"{REG}:1"),)
        ),
        RulesExtractor(),
    )
    assert out.results[0].status is S.NO_OBLIGATION and out.results[0].candidates == ()
    (imp,) = out.impacts
    assert (imp.kind, imp.affected_obligation_ids, imp.review_required) == (
        ImpactKind.TERM_REPLACED,
        ("o1",),
        True,
    )


def test_modified_change_gives_candidates_and_an_impact_listing_existing_obligations() -> None:
    doc = make_doc("Pasal 1\nPengendali wajib menyimpan arsip.")
    out = extract(
        ExtractionInput(
            changes=changes_for(doc, ChangedKind.MODIFIED),
            documents={REG: doc},
            obligations=(obligation("o1", f"{REG}:1"), obligation("o2", f"{REG}:2")),
        ),
        RulesExtractor(),
    )
    assert out.results[0].status is S.EXTRACTED
    (imp,) = out.impacts
    assert imp.kind is ImpactKind.MODIFIED and imp.affected_obligation_ids == ("o1",)


def test_added_and_new_articles_need_no_impact() -> None:
    doc = make_doc("Pasal 1\nPengendali wajib menyimpan arsip.")
    for kind in (ChangedKind.ADDED, ChangedKind.NEW_REGULATION_ARTICLE):
        out = extract(
            ExtractionInput(changes=changes_for(doc, kind), documents={REG: doc}), RulesExtractor()
        )
        assert out.impacts == ()


@pytest.mark.parametrize(
    ("known", "complete", "review"),
    [(True, True, True), (False, True, False), (False, False, True)],
)
def test_withdrawn_provision_review_rule(known: bool, complete: bool, review: bool) -> None:
    w = WithdrawnProvision(
        regulation_id=REG, article_number="7", effect=Effect.DELETED, impact_id="imp-1"
    )
    obs = (obligation("o1", f"{REG}:7"),) if known else ()
    out = extract(
        ExtractionInput(withdrawn=(w,), obligations=obs, obligations_complete=complete),
        RulesExtractor(),
    )
    (imp,) = out.impacts
    assert (
        imp.kind is ImpactKind.WITHDRAWN
        and imp.review_required is review
        and imp.store_complete is complete
    )
    assert imp.affected_obligation_ids == (("o1",) if known else ())


def test_amending_unit_wording_is_extracted_and_cites_the_unit() -> None:
    actor = Regulation.of(K.PP, "5", 2026, title="Perubahan", promulgated_on=date(2026, 7, 16))
    target = Regulation.of(K.PP, "10", 2020, title="Target", promulgated_on=date(2020, 1, 1))
    body = (
        "PERATURAN PEMERINTAH\nNOMOR 5 TAHUN 2026\nTENTANG PERUBAHAN ATAS PERATURAN PEMERINTAH\nMenimbang : bahwa.\n"
        "MEMUTUSKAN:\nMenetapkan: PERATURAN PEMERINTAH.\nPasal I\n"
        "Beberapa ketentuan dalam Peraturan Pemerintah Nomor 10 Tahun 2020 diubah sebagai berikut:\n"
        "1. Ketentuan Pasal 5 diubah sehingga berbunyi sebagai berikut:\nPasal 5\n(1) Setiap Orang wajib melapor paling lambat 7 hari.\n"
        "Pasal II\nPeraturan Pemerintah ini mulai berlaku pada tanggal diundangkan.\nDitetapkan di Jakarta"
    )
    from regulus.documents import process
    from regulus.documents.models import PageSource, RawPage

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
    assert [c.kind for c in lin.changed] == [ChangedKind.MODIFIED]
    out = extract(ExtractionInput(changes=lin.changed, documents={actor.id: doc}), RulesExtractor())
    (cand,) = out.results[0].candidates
    assert cand.clause.owner_id.endswith(":unit-I") and cand.change_ref.regulation_id == target.id
    assert (val(cand.actor), val(cand.action), val(cand.deadline)) == (
        "Setiap Orang",
        "melapor",
        "paling lambat 7 hari",
    )


def test_real_domain_objects_are_accepted_as_they_are() -> None:
    ch = ChangedProvision(
        regulation_id=REG,
        article_number="1",
        kind=ChangedKind.ADDED,
        text_ref=TextRef(owner_id=f"{REG}:1", start=0, end=5),
    )
    assert (
        extract(ExtractionInput(changes=(ch,)), RulesExtractor()).results[0].status
        is S.NOT_EXTRACTABLE
    )
    assert DocStatus.PROCESSED_OK
    one("Pasal 1\nPengendali wajib menyimpan arsip.")


def test_model_invariant_rejects_an_enumerated_action_without_items() -> None:
    from regulus.obligations import ObligationCandidate
    from regulus.obligations.models import ChangeRef, Citation, FieldState, FieldValue

    c = Citation(owner_id="o", start=0, end=14, quote="Pengendali ada")
    marker = FieldValue(value="ada", citation=Citation(owner_id="o", start=11, end=14, quote="ada"))
    ns = FieldState(status=F.NOT_STATED)
    enum = FieldState(status=F.UNDETERMINED, reason="enumerated_items")
    base = dict(
        id="c",
        change_ref=ChangeRef(regulation_id="r", article_number="1", owner_id="o"),
        clause=c,
        modality="OBLIGATION",
        marker=marker,
        actor=ns,
        object=ns,
        deadline=ns,
        frequency=ns,
        extractor="x",
    )
    with pytest.raises(ValueError):
        ObligationCandidate(action=enum, **base)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ObligationCandidate(
            action=FieldState(status=F.UNDETERMINED, reason="other"),
            items=(Citation(owner_id="o", start=0, end=3, quote="Pen"),),
            **base,
        )  # type: ignore[arg-type]
    ok = ObligationCandidate(
        action=enum, items=(Citation(owner_id="o", start=0, end=3, quote="Pen"),), **base
    )  # type: ignore[arg-type]
    assert ok.action.reason == "enumerated_items"
