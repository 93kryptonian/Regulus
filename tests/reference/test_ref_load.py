import random

import pytest
from ref_helpers import write_reference_dir

from regulus.reference.load import ReferenceError, build_corpus, load_corpus, obligation_id
from regulus.reference.models import DiscrepancyKind as K
from regulus.reference.normalize import norm, parse_article
from regulus.reference.synthetic import synthetic_corpus, synthetic_rows


def kinds(c, rid):
    return {d.kind for d in c.discrepancies if d.regulation_id == rid}


def test_normalization_is_versioned_and_keeps_originals():
    assert norm("  Melakukan  PENDAFTARAN  ") == "melakukan pendaftaran"
    assert parse_article("Pasal 12") == 12 and parse_article(" pasal   7 ") == 7
    assert parse_article("Pasal 12 ayat (1)") is None and parse_article("Lampiran I") is None
    assert synthetic_corpus().normalization_version == "1"


def test_three_entities_and_one_obligation_with_two_article_links():
    c = synthetic_corpus()
    ob = next(o for o in c.obligations if o.normalized_text == "melakukan pendaftaran usaha")
    arts = sorted(link.article for link in c.links if link.obligation_id == ob.obligation_id)
    assert arts == [1, 2] and len(c.obligations_of("syn-a")) == 5


def test_identical_repeated_links_are_a_second_obligation_not_noise():
    c = synthetic_corpus()
    rep = [o for o in c.obligations if o.normalized_text == "melaporkan kegiatan usaha"]
    assert sorted(o.ordinal for o in rep) == [1, 2] and len({o.obligation_id for o in rep}) == 2
    assert K.COUNT_MATCHED in kinds(c, "syn-a")


def test_identity_is_not_text_alone():
    c = synthetic_corpus()
    rep = [o for o in c.obligations if o.normalized_text == "melaporkan kegiatan usaha"]
    assert rep[0].obligation_id != obligation_id("syn-a", rep[0].normalized_text, 99)
    assert rep[0].obligation_id == obligation_id("syn-a", rep[0].normalized_text, rep[0].ordinal)
    assert obligation_id("syn-a", "x", 1) != obligation_id("syn-b", "x", 1)


def test_label_copies_collapse_once_and_are_reported():
    c = synthetic_corpus()
    reg = next(r for r in c.regulations if r.regulation_id == "syn-b")
    assert len(reg.labels) == 2 and K.LABEL_COPIES_IDENTICAL in kinds(c, "syn-b")
    assert len(c.obligations_of("syn-b")) == 2


def test_uneven_repeats_count_the_minimum_and_are_flagged():
    c = synthetic_corpus()
    assert K.IRREGULAR_MULTIPLICITY in kinds(c, "syn-b")
    assert K.COUNT_BELOW_DECLARED in kinds(c, "syn-b")
    d = next(x for x in c.discrepancies if x.kind is K.COUNT_BELOW_DECLARED)
    assert d.detail == {"derived": 2, "declared": 3}


def test_multi_text_article_is_kept_and_flagged():
    c = synthetic_corpus()
    assert K.MULTI_TEXT_ARTICLE in kinds(c, "syn-a")
    link = next(x for x in c.links if x.regulation_id == "syn-a" and x.article == 5)
    assert len(link.article_texts) == 2


def test_parse_error_unknown_sector_and_undeclared_count():
    c = synthetic_corpus()
    assert {K.PARSE_ERROR, K.UNKNOWN_SECTOR, K.COUNT_UNDECLARED} <= kinds(c, "syn-c")
    assert not any(link.article == 0 for link in c.links)
    assert len(c.obligations_of("syn-c")) == 2


def test_a_sector_difference_is_a_different_link_not_a_duplicate():
    d, counts, sectors = synthetic_rows()
    d = [r for r in d if r["Regulation_id"] == "syn-a"]
    d.append({**d[0], "Sector": "Sektor C"})
    c = build_corpus(d, counts, sectors)
    ob = next(o for o in c.obligations if o.normalized_text == "melakukan pendaftaran usaha")
    assert set(ob.sectors) == {"Sektor A", "Sektor C"}


def test_label_copies_that_differ_are_refused_naming_the_field():
    d, counts, sectors = synthetic_rows()
    d.append(
        {
            **d[-1],
            "Regulation_id": "syn-b",
            "Regulation": "Synthetic Regulation B",
            "Obligation": "Tambahan beda",
        }
    )
    with pytest.raises(ReferenceError) as e:
        build_corpus(d, counts, sectors)
    assert e.value.fields == ["Regulation"] and "Tambahan" not in str(e.value)


def test_conflicting_declared_counts_are_reported():
    d, counts, sectors = synthetic_rows()
    counts[2] = {**counts[2], "obligation_count": "9"}
    c = build_corpus(d, counts, sectors)
    assert K.DECLARED_COUNT_CONFLICT in kinds(c, "syn-b")


def test_input_order_does_not_change_the_corpus():
    d, counts, sectors = synthetic_rows()
    base = build_corpus(d, counts, sectors)
    for seed in range(5):
        shuffled = d[:]
        random.Random(seed).shuffle(shuffled)
        assert build_corpus(shuffled, counts, sectors).obligations == base.obligations
        assert build_corpus(shuffled, counts, sectors).links == base.links


def test_building_twice_is_identical():
    assert synthetic_corpus() == synthetic_corpus()


def test_load_from_files_matches_building_from_rows(tmp_path):
    d, counts, sectors = synthetic_rows()
    write_reference_dir(tmp_path, d, counts, sectors)
    loaded = load_corpus(tmp_path)
    assert loaded.obligations == build_corpus(d, counts, sectors).obligations
    assert set(loaded.source_digests) == {
        "reference data.xlsx",
        "obligations count.xlsx",
        "sector reference.xlsx",
    }


def test_a_missing_column_is_refused_naming_the_file_and_field(tmp_path):
    d, counts, sectors = synthetic_rows()
    write_reference_dir(tmp_path, d, counts, sectors)
    from ref_helpers import write_xlsx

    write_xlsx(tmp_path / "sector reference.xlsx", ["Other"], [["x"]])
    with pytest.raises(ReferenceError) as e:
        load_corpus(tmp_path)
    assert e.value.fields == ["Sector"] and "sector reference" in e.value.rule


def test_absent_files_are_refused_not_partially_loaded(tmp_path):
    with pytest.raises(ReferenceError):
        load_corpus(tmp_path)
