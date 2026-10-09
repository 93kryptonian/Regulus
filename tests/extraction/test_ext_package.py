import hashlib
from typing import Any

import pytest
from ext_helpers import REG, article_text, diag, make_result, prov
from pydantic import ValidationError

import regulus.extraction.package as pkg
from regulus.documents.models import Code, Level
from regulus.extraction import (
    ExtractionPackage,
    ExtractionUnit,
    PackageStatus,
    SignalKind,
    UnitKind,
    build_package,
    load_signals,
)
from regulus.extraction.models import HintStatus, Phase6Hint
from regulus.ingestion.models import HeadingNormalization, IngestionStatus, Issue, IssueCode
from regulus.lineage.models import ChangedKind, ChangedProvision, TextRef
from regulus.obligations import ExtractionInput, RulesExtractor, extract


def test_every_article_becomes_exactly_one_unit_in_order() -> None:
    r = make_result()
    p = build_package(r)
    assert p.status is PackageStatus.PACKAGED
    assert [u.label for u in p.units] == list(r.article_index)
    assert [u.article_id for u in p.units] == [a.article_id for a in r.article_index.values()]
    assert [u.ordinal for u in p.units] == [0, 1, 2]


def test_unit_without_any_signal_is_still_present() -> None:
    r = make_result(
        [("1", article_text("1", "Uraian tanpa kata kunci.")), ("2", article_text("2"))]
    )
    u = build_package(r).units[0]
    assert [s.kind for s in u.signals] == [SignalKind.NO_SIGNAL]
    assert u.phase6.status is HintStatus.NO_OBLIGATION


def test_complete_hand_over_regardless_of_hints_and_graph() -> None:
    r = make_result([(str(i), article_text(str(i), "Uraian netral.")) for i in range(1, 8)])
    p = build_package(r)
    assert len(p.units) == 7 and all(u.phase6.status is HintStatus.NO_OBLIGATION for u in p.units)


def test_provenance_reconstructs_phase3_text() -> None:
    r = make_result()
    assert r.processed is not None
    by_id = {a.id: a for a in r.processed.articles}
    for u in build_package(r).units:
        assert u.article_id is not None
        a = by_id[u.article_id]
        assert (u.page_start, u.page_end, u.text_hash) == (a.page_start, a.page_end, a.text_hash)
        assert hashlib.sha256(a.text.encode()).hexdigest() == u.text_hash


def test_repeated_labels_get_distinct_unit_ids() -> None:
    r = make_result(
        [("5", article_text("5")), ("5", article_text("5")), ("5", article_text("5"))],
        ids=[f"{REG}:5", f"{REG}:5#2", f"{REG}:5#3"],
    )
    p = build_package(r)
    assert len({u.unit_id for u in p.units}) == 3


def test_validator_rejects_collisions_and_manufactured_coverage() -> None:
    p = build_package(make_result())
    u = p.units[0]
    with pytest.raises(ValidationError, match="duplicate unit_id"):
        ExtractionPackage.model_validate(
            {**p.model_dump(), "units": [u.model_dump(), u.model_dump()]}
        )
    clone = u.model_dump() | {"unit_id": "other", "ordinal": 1}
    with pytest.raises(ValidationError, match="duplicate article_id"):
        ExtractionPackage.model_validate({**p.model_dump(), "units": [u.model_dump(), clone]})
    with pytest.raises(ValidationError, match="PACKAGED needs units"):
        ExtractionPackage.model_validate({**p.model_dump(), "units": [], "graph": {}})
    with pytest.raises(ValidationError, match="FAILED package carries no units"):
        ExtractionPackage.model_validate({**p.model_dump(), "status": "FAILED"})


def test_unit_schema_ties_article_id_to_kind() -> None:
    p = build_package(make_result(amendments=[("I", "Pasal 2 diubah menjadi wajib.")]))
    a = p.units[-1].model_dump()
    assert a["kind"] == "AMENDMENT_UNIT" and a["article_id"] is None
    with pytest.raises(ValidationError):
        ExtractionUnit.model_validate({**a, "article_id": "x"})
    with pytest.raises(ValidationError):
        ExtractionUnit.model_validate({**p.units[0].model_dump(), "article_id": None})
    bad: dict[str, Any] = {
        **a,
        "signals": [
            *a["signals"],
            {"kind": "NO_SIGNAL", "term": "", "start": 0, "end": 0, "signals_version": "1"},
        ],
    }
    with pytest.raises(ValidationError):
        ExtractionUnit.model_validate(bad)


def test_amendment_style_document_has_amendment_units_only() -> None:
    r = make_result([], amendments=[("I", "Pasal 2 diubah."), ("II", "Pasal 3 dihapus.")])
    p = build_package(r)
    assert [u.kind for u in p.units] == [UnitKind.AMENDMENT_UNIT] * 2
    assert all(u.article_id is None for u in p.units) and p.graph.edges == ()


@pytest.mark.parametrize("status", [IngestionStatus.FAILED, IngestionStatus.REFUSED])
def test_failed_or_refused_ingestion_gives_a_failed_package(status: IngestionStatus) -> None:
    p = build_package(make_result(status=status))
    assert p.status is PackageStatus.FAILED and p.units == ()


def test_gap_regions_and_issues_stay_visible() -> None:
    issues = (Issue(code=IssueCode.ARTICLE_GAP, article_number="4", detail="3"),)
    diags = (diag(Code.PAGE_FAILED, 2, "boom"), diag(Code.ANNEX_NOT_PROCESSED, None, "lampiran"))
    r = make_result(
        [("1", article_text("1")), ("2", article_text("2")), ("4", article_text("4"))],
        status=IngestionStatus.INGESTED_WITH_ISSUES,
        issues=issues,
        diagnostics=diags,
    )
    p = build_package(r)
    assert p.status is PackageStatus.PACKAGED_WITH_ISSUES
    assert [u.label for u in p.units] == ["1", "2", "4"] and p.missing_articles == ("3",)
    assert [(x.kind.value, x.page) for x in p.unprocessed_regions] == [
        ("ANNEX_NOT_PROCESSED", None),
        ("PAGE_FAILED", 2),
    ]
    assert p.inherited_issues == issues


def test_multiple_and_truncated_gap_names() -> None:
    issues = (Issue(code=IssueCode.ARTICLE_GAP, article_number="30", detail="3,4,10,..."),)
    p = build_package(make_result(issues=issues, status=IngestionStatus.INGESTED_WITH_ISSUES))
    assert p.missing_articles == ("3", "4", "10", "...")


def test_index_document_mismatch_is_reported_not_hidden() -> None:
    r = make_result()
    assert r.processed is not None
    broken = r.model_copy(
        update={"processed": r.processed.model_copy(update={"articles": r.processed.articles[:2]})}
    )
    p = build_package(broken)
    assert p.status is PackageStatus.PACKAGED_WITH_ISSUES
    assert any(
        i.code is IssueCode.OTHER_ERROR and i.article_number == "3" for i in p.inherited_issues
    )
    assert len(p.units) == 2


def test_heading_normalization_flag() -> None:
    n = HeadingNormalization(
        article_number=2,
        page=1,
        line_index=0,
        original="Pasall 2",
        normalized="Pasal 2",
        previous_article=1,
        next_article=3,
    )
    p = build_package(make_result(normalizations=(n,)))
    assert [u.heading_normalized for u in p.units] == [False, True, False]


class _Boom(RulesExtractor):
    def extract(self, request):  # type: ignore[no-untyped-def]
        if request.owner_id.endswith(":2"):
            raise RuntimeError("x")
        return super().extract(request)


def test_phase6_exception_is_contained_to_one_unit() -> None:
    result = make_result()
    p = build_package(result, _Boom())
    got = [u.phase6.status for u in p.units]
    assert got[1] is HintStatus.FAILED and got[0] is got[2] is HintStatus.EXTRACTED
    assert len(p.units) == 3


def test_phase6_exception_outside_extract_is_phase6_failed(monkeypatch) -> None:
    def boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise RuntimeError("x")

    monkeypatch.setattr(pkg, "extract", boom)
    p = build_package(make_result())
    assert all(u.phase6 == Phase6Hint(status=HintStatus.PHASE6_FAILED) for u in p.units)
    assert p.status is PackageStatus.PACKAGED_WITH_ISSUES and len(p.units) == 3


def test_hints_equal_a_direct_phase6_run_and_negation_is_preserved() -> None:
    texts = [
        ("1", article_text("1")),
        ("2", article_text("2", "Pelaku usaha tidak wajib melapor.")),
        ("3", article_text("3", "Pelaku usaha dilarang menyimpan data.")),
    ]
    r = make_result(texts)
    assert r.processed is not None
    p = build_package(r)
    for u, a in zip(p.units, r.processed.articles, strict=True):
        ch = ChangedProvision(
            regulation_id=REG,
            article_number=a.number,
            kind=ChangedKind.NEW_REGULATION_ARTICLE,
            text_ref=TextRef(owner_id=a.id, start=0, end=len(a.text)),
        )
        res = extract(
            ExtractionInput(changes=(ch,), documents={REG: r.processed}), RulesExtractor()
        ).results[0]
        assert u.phase6 == pkg.hint_from(res)
    assert any(d.code == "NEGATED_MARKER" for d in p.units[1].phase6.diagnostics)
    assert p.units[1].phase6.status is HintStatus.NO_OBLIGATION


def test_cross_reference_graph_in_package() -> None:
    r = make_result(
        [("1", article_text("1", "Lihat Pasal 2 dan Pasal 9.")), ("2", article_text("2"))]
    )
    p = build_package(r)
    assert len(p.graph.edges) == 1 and [u.label for u in p.graph.unresolved] == ["9"]


def test_enumeration_uses_phase3_provisions() -> None:
    t = article_text("1", "Pelaku wajib: a. melapor; b. menyimpan.")
    owner = f"{REG}:1"
    provs = (
        prov(owner, Level.HURUF, ("a",), "melapor", (20, 27)),
        prov(owner, Level.HURUF, ("b",), "menyimpan", (30, 39)),
    )
    u = build_package(make_result([("1", t)], provisions=provs)).units[0]
    assert any(s.kind is SignalKind.ENUMERATION for s in u.signals) and len(u.provision_ids) == 2


def test_identical_input_gives_byte_identical_packages() -> None:
    r = make_result(
        [
            (
                str(i),
                article_text(
                    str(i), f"Pelaku wajib melapor sesuai Pasal {i % 3 + 1} dan dapat mengajukan."
                ),
            )
            for i in range(1, 12)
        ]
    )
    a, b = build_package(r), build_package(r)
    assert a.model_dump_json() == b.model_dump_json()


def test_package_key_changes_with_every_output_affecting_version(monkeypatch) -> None:
    base = build_package(make_result()).package_key
    assert build_package(make_result()).package_key == base
    assert build_package(make_result(key="pk-2")).package_key != base
    sig = load_signals().model_copy(update={"version": "2"})
    assert build_package(make_result(), signals=sig).package_key != base

    ex = RulesExtractor()
    ex.version = "other"
    assert build_package(make_result(), ex).package_key != base
    lex2 = RulesExtractor().lex.model_copy(update={"version": "9"})
    assert build_package(make_result(), RulesExtractor(lex2)).package_key != base
    monkeypatch.setattr(pkg, "PHASE19_VERSION", "2")
    assert build_package(make_result()).package_key != base


def test_package_versions_are_read_from_the_running_code() -> None:
    v = build_package(make_result()).versions
    ex = RulesExtractor()
    assert (v.signals, v.phase6_extractor, v.phase6_lexicon, v.phase19) == (
        "1",
        ex.version,
        ex.lex.version,
        pkg.PHASE19_VERSION,
    )


def test_provision_ids_are_deterministic_collision_free_and_reconstructable() -> None:
    owner = f"{REG}:1"
    t = article_text("1", "Pelaku wajib: a. melapor; a. menyimpan; b. menghapus.")
    provs = (
        prov(owner, Level.HURUF, ("1", "a"), "x", (20, 25)),
        prov(owner, Level.HURUF, ("1", "a"), "y", (26, 30)),
        prov(owner, Level.HURUF, ("1", "b"), "z", (31, 40)),
    )
    r = make_result([("1", t)], provisions=provs)
    ids = build_package(r).units[0].provision_ids
    assert ids == build_package(r).units[0].provision_ids
    assert len(set(ids)) == 3 == len(ids)
    for pid, p in zip(ids, provs, strict=True):
        head, rest = pid.split("#", 1)
        i, path = rest.split(":", 1)
        assert head == owner and provs[int(i)] is p and path == ".".join(p.path)
