from ing_helpers import READER, REG, fresh, pdf

from regulus.ingestion.ingest import ingest
from regulus.ingestion.models import IngestionStatus as S
from regulus.ingestion.models import RegistryOutcome as O


class Counting:
    def __init__(self):
        self.calls = 0

    def __call__(self, data):
        self.calls += 1
        return READER(data)

    ocr = None
    min_chars = 50
    dpi = 200


def test_new_then_unchanged_without_reprocessing():
    reg, rd = fresh(), Counting()
    first = ingest(pdf(), REG, rd, reg)
    n = rd.calls
    again = ingest(pdf(), REG, rd, reg)
    assert first.registry is O.NEW and again.registry is O.UNCHANGED and rd.calls == n
    assert again.model_copy(update={"registry": O.NEW}) == first


def test_new_bytes_under_the_same_id_is_a_new_version_and_the_old_one_is_kept():
    reg = fresh()
    a = ingest(pdf(), REG, READER, reg)
    b = ingest(pdf(tweak=" baru"), REG, READER, reg)
    assert b.registry is O.NEW_VERSION and len(reg.versions(REG)) == 2
    assert reg.find(REG, a.identity.processing_key) == a
    assert reg.find(REG, b.identity.processing_key) == b


def test_the_same_bytes_under_another_id_is_refused_as_duplicate_content():
    reg = fresh()
    ingest(pdf(), REG, READER, reg)
    dup = ingest(pdf(), "other-id", READER, reg)
    assert dup.registry is O.DUPLICATE_CONTENT and dup.status is S.REFUSED and dup.processed is None
    assert reg.owner_of(dup.identity.content_hash) == REG and reg.versions("other-id") == ()


def test_a_rerendered_file_with_equal_text_is_flagged():
    reg = fresh()
    ingest(pdf(title="one"), REG, READER, reg)
    again = ingest(pdf(title="two"), REG, READER, reg)
    assert again.registry is O.RERENDERED and len(reg.versions(REG)) == 2


def test_same_bytes_with_different_settings_are_reprocessed_not_unchanged():
    reg = fresh()
    ingest(pdf(), REG, READER, reg)
    other = ingest(pdf(), REG, READER, reg, normalize_headings=False)
    assert other.registry is O.REPROCESSED and len(reg.versions(REG)) == 1


def test_unreadable_input_fails_and_leaves_the_registry_untouched():
    reg = fresh()
    r = ingest(b"this is not a pdf", REG, READER, reg)
    assert r.status is S.FAILED and r.registry is O.NOT_REGISTERED and r.article_index == {}
    assert reg.versions(REG) == () and reg.owner_of(r.identity.content_hash) is None


def test_a_failed_input_is_never_reported_as_ingested():
    for junk in (b"", b"%PDF-1.4 broken", b"\x00" * 100):
        assert ingest(junk, REG, READER, fresh()).status is S.FAILED
