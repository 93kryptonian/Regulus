from datetime import date

from regulus.change_detection import (
    Action,
    DeclaredRelation,
    RegulationIndex,
    SourceRecord,
    TargetRef,
    detect,
)
from regulus.domain import EventType, Regulation
from regulus.domain import RegulationKind as K


def test_synthetic_amend_between_real_identities() -> None:
    uu = Regulation.of(K.UU, "27", 2022, title="Pelindungan Data Pribadi")
    rec = SourceRecord(
        source_id="synthetic-fixture",
        kind=K.PP,
        number="33",
        year=2026,
        title="Peraturan Pelaksanaan UU Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi",
        promulgated_on=date(2026, 7, 16),
        relations=(
            DeclaredRelation(
                action=Action.MENGUBAH,
                target=TargetRef(raw="UU 27/2022", kind=K.UU, number="27", year=2022),
            ),
        ),
    )
    res = detect(rec, RegulationIndex([uu]), frozenset(), date(2026, 7, 17))
    by = {e.type: e for e in res.events}
    assert set(by) == {EventType.NEW, EventType.AMEND}
    assert (
        by[EventType.AMEND].regulation_id == "PP-33-2026" and by[EventType.AMEND].target_id == uu.id
    )
