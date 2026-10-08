import hashlib

from ing_helpers import READER, REG, fresh, pdf

from regulus.documents import PdfPlumberReader
from regulus.ingestion.identity import INGESTION_VERSION, processing_key, reader_config_hash
from regulus.ingestion.ingest import ingest


def test_content_hash_is_the_sha256_of_the_exact_bytes_and_is_not_a_title():
    data = pdf()
    r = ingest(data, REG, READER, fresh())
    assert r.identity.content_hash == hashlib.sha256(data).hexdigest()
    assert r.identity.regulation_id == REG and r.identity.size_bytes == len(data)
    assert r.processed is not None and r.processed.document.content_hash == r.identity.content_hash


def test_equal_inputs_give_equal_keys_and_the_key_ignores_names():
    a = ingest(pdf(), "id-one", READER, fresh())
    b = ingest(pdf(), "id-two", READER, fresh())
    assert a.identity.processing_key == b.identity.processing_key
    assert a.identity.text_fingerprint == b.identity.text_fingerprint


def test_a_change_in_bytes_version_or_settings_changes_the_key():
    h = ingest(pdf(), REG, READER, fresh()).identity
    assert (
        ingest(pdf(tweak=" lagi"), REG, READER, fresh()).identity.processing_key != h.processing_key
    )
    assert (
        ingest(pdf(), REG, READER, fresh(), normalize_headings=False).identity.processing_key
        != h.processing_key
    )
    assert (
        ingest(pdf(), REG, PdfPlumberReader(min_chars=10), fresh()).identity.processing_key
        != h.processing_key
    )
    assert processing_key(h.content_hash, "2", h.reader_config_hash) != h.processing_key
    assert (
        processing_key(h.content_hash, INGESTION_VERSION, h.reader_config_hash) == h.processing_key
    )
    assert reader_config_hash(READER, True) != reader_config_hash(READER, False)


def test_the_identity_hierarchy_separates_bytes_from_text():
    a = ingest(pdf(title="one"), REG, READER, fresh()).identity
    b = ingest(pdf(title="two"), REG, READER, fresh()).identity
    assert a.content_hash != b.content_hash and a.text_fingerprint == b.text_fingerprint
    assert a.processing_key != b.processing_key
