import pytest

from regulus.generation.verify import tokens
from regulus.obligations import FieldStatus as F
from regulus.obligations import Modality as M
from regulus.similarity.models import (
    FIELDS,
    FieldEntry,
    RelationConfig,
    Representation,
)
from regulus.similarity.models import (
    Label as L,
)
from regulus.similarity.models import (
    Relation as R,
)
from regulus.similarity.relation import classify

P, NS, U = F.PRESENT, F.NOT_STATED, F.UNDETERMINED


def rep(
    text: str = "t", modality: M | None = M.OBLIGATION, **fields: str | None | F
) -> Representation:
    out: dict[str, FieldEntry] = {}
    for n in FIELDS:
        v = fields.get(n)
        if v is U:
            out[n] = FieldEntry(state=U)
        elif v is None:
            out[n] = FieldEntry(state=NS)
        else:
            assert isinstance(v, str)
            out[n] = FieldEntry(state=P, tokens=tuple(tokens(v)), value=v)
    return Representation(
        obligation_id="o",
        text=text,
        text_tokens=tuple(tokens(text)),
        fields=out,
        modality=modality,
        hash="h",
    )


CORE = {"actor": "Pengendali", "action": "menyimpan", "object": "arsip"}


def label(a: Representation, b: Representation) -> L:
    return classify(a, b).label


def test_identical_core_and_parameters_is_a_possible_duplicate() -> None:
    v = classify(
        rep(**CORE, deadline="paling lambat 3 hari"), rep(**CORE, deadline="paling lambat 3 hari")
    )
    assert v.label is L.POSSIBLE_DUPLICATE and v.cap_reasons == ()
    assert {c.field: c.relation for c in v.comparisons}["deadline"] is R.EQUAL
    assert {c.field: c.relation for c in v.comparisons}["frequency"] is R.BOTH_NOT_STATED
    assert v.supporting_fields == ("actor", "action", "object", "deadline")


def test_overlapping_core_above_tau_dup_is_still_a_possible_duplicate() -> None:
    a = rep(
        actor="Pengendali Data Pribadi",
        action="menyimpan",
        object="arsip pemrosesan data pribadi lengkap",
    )
    b = rep(
        actor="Pengendali Data Pribadi", action="menyimpan", object="arsip pemrosesan data pribadi"
    )
    v = classify(a, b)
    assert v.label is L.POSSIBLE_DUPLICATE
    assert next(c for c in v.comparisons if c.field == "object").relation is R.OVERLAP


def test_overlap_below_tau_dup_is_not_a_duplicate() -> None:
    a = rep(**{**CORE, "object": "arsip pemrosesan data pribadi lengkap"})
    b = rep(**{**CORE, "object": "arsip pemrosesan"})
    assert label(a, b) is L.RELATED


def test_parameter_differences_make_a_variant() -> None:
    assert (
        label(
            rep(**CORE, deadline="paling lambat 3 hari"),
            rep(**CORE, deadline="paling lambat 7 hari"),
        )
        is L.VARIANT
    )
    assert label(rep(**CORE, deadline="paling lambat 3 hari"), rep(**CORE)) is L.VARIANT
    assert label(rep(**CORE, frequency="setiap bulan"), rep(**CORE)) is L.VARIANT
    assert (
        label(
            rep(**CORE, condition="apabila diminta"), rep(**CORE, condition="apabila diminta lain")
        )
        is L.VARIANT
    )
    assert label(rep(**CORE, exception="kecuali a"), rep(**CORE)) is L.VARIANT


def test_opposite_modality_on_the_same_core_is_contradictory() -> None:
    assert label(rep(**CORE), rep(modality=M.PROHIBITION, **CORE)) is L.CONTRADICTORY_MODALITY
    assert (
        label(rep(**CORE, deadline="x"), rep(modality=M.PROHIBITION, **CORE))
        is L.CONTRADICTORY_MODALITY
    )


def test_one_shared_field_is_related_and_names_it() -> None:
    v = classify(rep(**CORE), rep(actor="Pengendali", action="menghapus", object="data"))
    assert v.label is L.RELATED and v.supporting_fields == ("actor",)
    v2 = classify(rep(**CORE), rep(actor="Lembaga", action="menyimpan", object="data"))
    assert v2.label is L.RELATED and v2.supporting_fields == ("action",)


def test_no_field_evidence_is_similar_text_only() -> None:
    v = classify(
        rep(text="sama sekali", **CORE), rep(actor="Lembaga", action="menghapus", object="data")
    )
    assert v.label is L.SIMILAR_TEXT_ONLY and v.supporting_fields == ()


def test_swapped_actor_and_recipient_is_never_a_duplicate() -> None:
    a = rep(
        text="Pengendali wajib melaporkan insiden kepada Lembaga",
        actor="Pengendali",
        action="melaporkan",
        object="insiden",
    )
    b = rep(
        text="Lembaga wajib melaporkan insiden kepada Pengendali",
        actor="Lembaga",
        action="melaporkan",
        object="insiden",
    )
    assert label(a, b) is L.RELATED


@pytest.mark.parametrize("name", ["actor", "action", "object"])
def test_undetermined_core_field_caps_the_label_at_related(name: str) -> None:
    a = rep(**CORE)
    b = rep(**{**CORE, name: U})
    v = classify(a, b)
    assert v.label is L.RELATED and f"CAPPED_BY_UNDETERMINED({name})" in v.cap_reasons
    both_dup = rep(**{**CORE, name: U})
    assert classify(both_dup, both_dup).label is L.RELATED


def test_undetermined_core_cannot_become_variant_or_contradictory() -> None:
    a = rep(**{**CORE, "actor": U}, deadline="x")
    b = rep(modality=M.PROHIBITION, **{**CORE, "actor": U})
    assert classify(a, b).label is L.RELATED
    assert classify(a, rep(**{**CORE, "actor": U})).label is L.RELATED


def test_missing_core_field_is_capped_not_undetermined() -> None:
    v = classify(rep(**{**CORE, "object": None}), rep(**{**CORE, "object": None}))
    assert v.label is L.RELATED and "CAPPED_BY_MISSING(object)" in v.cap_reasons


def test_unknown_modality_caps_at_related() -> None:
    v = classify(rep(modality=None, **CORE), rep(**CORE))
    assert v.label is L.RELATED and "CAPPED_BY_UNDETERMINED(modality)" in v.cap_reasons


def test_undetermined_parameter_prevents_duplicate_but_not_a_proven_difference() -> None:
    v = classify(rep(**CORE, deadline=U), rep(**CORE))
    assert v.label is L.RELATED and "CAPPED_BY_UNDETERMINED(deadline)" in v.cap_reasons
    assert label(rep(**CORE, deadline=U, frequency="setiap bulan"), rep(**CORE)) is L.VARIANT
    assert (
        label(rep(**CORE, deadline=U), rep(modality=M.PROHIBITION, **CORE))
        is L.CONTRADICTORY_MODALITY
    )


def test_label_is_symmetric_for_every_pair_class() -> None:
    reps = [
        rep(**CORE),
        rep(**CORE, deadline="x"),
        rep(modality=M.PROHIBITION, **CORE),
        rep(**{**CORE, "actor": U}),
        rep(actor="Lembaga", action="menyimpan", object="data"),
        rep(**{**CORE, "object": None}),
    ]
    for a in reps:
        for b in reps:
            assert label(a, b) is label(b, a)


def test_classification_never_reads_text_or_scores() -> None:
    a = rep(text="kata kata sangat berbeda", **CORE)
    b = rep(text="tidak ada hubungan lexical", **CORE)
    assert label(a, b) is L.POSSIBLE_DUPLICATE
    assert classify(a, b) == classify(a, b)


def test_composite_orders_within_a_label_and_is_bounded() -> None:
    full = classify(rep(**CORE), rep(**CORE))
    part = classify(
        rep(**CORE), rep(actor="Pengendali", action="menyimpan", object="arsip lain sekali dua")
    )
    assert 0.0 <= part.composite <= full.composite <= 1.0


def test_thresholds_are_configurable_and_versioned() -> None:
    a = rep(**{**CORE, "object": "arsip pemrosesan data pribadi lengkap"})
    b = rep(**{**CORE, "object": "arsip pemrosesan data pribadi"})
    assert classify(a, b, RelationConfig(tau_dup=0.7)).label is L.POSSIBLE_DUPLICATE
    assert classify(a, b, RelationConfig(tau_dup=0.99)).label is L.RELATED
