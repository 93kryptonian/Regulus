from datetime import date
from pathlib import Path

import pytest

from regulus.documents import DocStatus, PdfPlumberReader, process
from regulus.domain import EventType as T
from regulus.domain import Regulation, RegulatoryEvent
from regulus.domain import RegulationKind as K
from regulus.lineage import LineageInput, analyze_impact

PDF = Path(__file__).parents[2] / "pdf"
PP20, UU21 = PDF / "pp20_1980.pdf", PDF / "uu21_1982.pdf"
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not (PP20.exists() and UU21.exists()), reason="real instruments absent"),
]


def event(actor: Regulation, target: Regulation) -> RegulatoryEvent:
    return RegulatoryEvent(
        id=f"e-{target.id}",
        type=T.AMEND,
        regulation_id=actor.id,
        target_id=target.id,
        occurred_on=actor.promulgated_on or date.min,
        detected_on=date(2026, 1, 1),
        basis="BPK",
    )


def test_pp20_1980_real_formulas_stay_unresolved_without_false_resolution() -> None:
    actor = Regulation.of(
        K.PP, "20", 1980, title="Perubahan dan Tambahan", promulgated_on=date(1980, 6, 23)
    )
    target = Regulation.of(K.PP, "21", 1967, title="Radio Amatirisme")
    doc = process(PP20.read_bytes(), actor.id, PdfPlumberReader())
    assert doc.status is DocStatus.PROCESSED_OK and [u.label for u in doc.amendment_units] == [
        "I",
        "II",
    ]
    e = event(actor, target)
    res = analyze_impact(
        e, LineageInput(events=(e,), regulations=(actor, target), documents={actor.id: doc})
    )
    assert res.impacts == () and res.changed == () and res.withdrawn == () and res.complete
    reasons = sorted(u.reason for u in res.unresolved_operations)
    assert reasons == ["LOCATOR_UNPARSEABLE"] + ["UNSUPPORTED_OPERATION"] * 5
    assert all(u.spans for u in res.unresolved_operations)


def test_uu21_1982_unit_naming_two_laws_is_ambiguous_for_both_events() -> None:
    actor = Regulation.of(K.UU, "21", 1982, title="Perubahan", promulgated_on=date(1982, 9, 20))
    targets = [
        Regulation.of(K.UU, "11", 1966, title="Pers"),
        Regulation.of(K.UU, "4", 1967, title="UU 4/1967"),
    ]
    doc = process(UU21.read_bytes(), actor.id, PdfPlumberReader())
    assert [u.label for u in doc.amendment_units] == ["I", "II"]
    for t in targets:
        e = event(actor, t)
        res = analyze_impact(
            e, LineageInput(events=(e,), regulations=(actor, t), documents={actor.id: doc})
        )
        assert res.impacts == () and [u.reason for u in res.unresolved_operations] == [
            "AMBIGUOUS_UNIT_TARGET"
        ]
