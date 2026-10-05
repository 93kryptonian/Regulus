from datetime import UTC, date, datetime

from regulus.domain import (
    Article,
    EventType,
    Generated,
    GenerationMetadata,
    Obligation,
    ObligationContent,
    ObligationEvidence,
    Origin,
    Regulation,
    RegulationKind,
    RegulatoryEvent,
    ReviewDecision,
    apply_decision,
)
from regulus.domain import (
    ObligationStatus as S,
)

TEXT = (
    "Dalam Peraturan Pemerintah ini yang dimaksud dengan: 1. Data Pribadi adalah data tentang "
    "orang perseorangan yang teridentifikasi atau dapat diidentifikasi secara tersendiri atau "
    "dikombinasi dengan Informasi lainnya."
)


def test_pp33_2026_end_to_end_without_external_services() -> None:
    reg = Regulation.of(
        RegulationKind.PP,
        "33",
        2026,
        title="Peraturan Pelaksanaan UU Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi",
        issuer="Presiden Republik Indonesia",
        enacted_on=date(2026, 7, 16),
        promulgated_on=date(2026, 7, 16),
    )
    uu = Regulation.of(RegulationKind.UU, "27", 2022, title="Pelindungan Data Pribadi")
    ev = RegulatoryEvent(
        id="e1",
        type=EventType.NEW,
        regulation_id=reg.id,
        occurred_on=date(2026, 1, 1),
        detected_on=date(2026, 1, 2),
        basis="LN 2026/88, TLN 7190",
    )
    assert ev.regulation_id == reg.id and uu.id != reg.id

    art = Article.of(reg.id, "1", TEXT, 2, 2, parent="BAB I")
    c = ObligationContent(text="Personal Data means data about an identifiable individual.")
    meta = GenerationMetadata(model="stub", prompt_version="v0", generated_at=datetime.now(UTC))
    ob = Obligation(
        id="o1",
        article_id=art.id,
        origin=Origin.AI,
        status=S.PENDING_REVIEW,
        generated=Generated(content=c, meta=meta),
        current=c,
    )
    quote = "Data Pribadi adalah data tentang orang perseorangan"
    s = TEXT.index(quote)
    evd = ObligationEvidence(
        obligation_id=ob.id, article_id=art.id, span=(s, s + len(quote)), quote=quote
    )
    assert evd.matches(art)

    d = ReviewDecision(
        id="d1",
        obligation_id=ob.id,
        reviewer="reviewer-1",
        at=datetime.now(UTC),
        from_status=S.PENDING_REVIEW,
        to_status=S.APPROVED,
    )
    assert apply_decision(ob, d, [evd]).status is S.APPROVED
