import pytest
from ing_helpers import HEAD, READER, REG, body, fresh, pdf, tail
from pdfgen import make_pdf

from regulus.documents import DocStatus, process
from regulus.documents.models import Code
from regulus.ingestion.headings import GLITCH, reverify
from regulus.ingestion.ingest import ingest
from regulus.ingestion.models import HeadingNormalization, IssueCode
from regulus.ingestion.models import IngestionStatus as S


def codes(r):
    return [d.code for d in r.processed.diagnostics]


def test_the_measured_glitch_is_normalized_flagged_and_traceable():
    r = ingest(pdf(glitch={3: "Pasa13"}), REG, READER, fresh())
    assert "3" in r.article_index and Code.ARTICLE_GAP not in codes(r)
    (n,) = r.normalizations
    assert (n.article_number, n.original, n.normalized, n.previous_article, n.next_article) == (
        3,
        "Pasa13",
        "Pasal 3",
        2,
        4,
    )
    assert r.status is S.INGESTED_WITH_ISSUES
    assert any(i.code is IssueCode.HEADING_NORMALIZED and i.article_number == "3" for i in r.issues)


def test_without_normalization_the_result_is_exactly_phase_3():
    data = pdf(glitch={3: "Pasa13"})
    off = ingest(data, REG, READER, fresh(), normalize_headings=False)
    assert off.processed == process(data, REG, READER) and off.normalizations == ()
    assert "3" not in off.article_index and Code.ARTICLE_GAP in codes(off)
    assert off.status is S.INGESTED_WITH_ISSUES


def test_a_clean_document_is_ingested_without_issues():
    r = ingest(pdf(), REG, READER, fresh())
    assert (
        r.status is S.INGESTED
        and r.normalizations == ()
        and set(r.article_index) == {"1", "2", "3", "4", "5", "6"}
    )


def test_several_independent_gaps_are_each_normalized():
    r = ingest(pdf(glitch={2: "Pasa12", 5: "Pasa15"}), REG, READER, fresh())
    assert sorted(n.article_number for n in r.normalizations) == [
        2,
        5,
    ] and Code.ARTICLE_GAP not in codes(r)


@pytest.mark.parametrize("variant", ["Pasa13", "Pasal3", "PasaI3", "Pasa|3", "Pasa1 3"])
def test_the_closed_glitch_pattern_covers_its_variants(variant):
    assert GLITCH.match(variant)
    r = ingest(pdf(glitch={3: variant}), REG, READER, fresh())
    assert [n.article_number for n in r.normalizations] == [3] or "3" in r.article_index


def test_digits_that_do_not_equal_the_gap_are_not_normalized():
    r = ingest(pdf(glitch={3: "Pasa19"}), REG, READER, fresh())
    assert r.normalizations == () and "3" not in r.article_index and Code.ARTICLE_GAP in codes(r)


def test_a_glitched_line_without_a_gap_is_left_alone():
    extra = ["Pasa13"]
    r = ingest(pdf(extra=extra), REG, READER, fresh())
    assert r.normalizations == () and r.status is S.INGESTED


def test_two_candidate_lines_for_one_gap_are_not_normalized():
    lines = HEAD + body(6, {3: "Pasa13"})
    i = lines.index("Pasa13")
    lines.insert(i + 1, "Pasa13")
    data = make_pdf(["\n".join(lines[j : j + 14]) for j in range(0, len(lines), 14)])
    r = ingest(data, REG, READER, fresh())
    assert r.normalizations == () and "3" not in r.article_index and Code.ARTICLE_GAP in codes(r)


def test_a_glitched_line_out_of_position_is_not_normalized():
    lines = HEAD + body(6, {3: "Pass3"}) + ["Pasa13"] + tail(6)
    data = make_pdf(["\n".join(lines[j : j + 14]) for j in range(0, len(lines), 14)])
    r = ingest(data, REG, READER, fresh())
    assert r.normalizations == () and "3" not in r.article_index


def test_a_glitch_inside_running_text_is_not_a_heading():
    lines = HEAD + body(6, {3: "Pass3"})
    lines.insert(lines.index("Pass3") + 1, "sebagaimana dimaksud dalam Pasa13 dan seterusnya")
    data = make_pdf(["\n".join(lines[j : j + 14]) for j in range(0, len(lines), 14)])
    r = ingest(data, REG, READER, fresh())
    assert r.normalizations == () and "3" not in r.article_index


def test_a_tampered_normalization_fails_reverification():
    r = ingest(pdf(glitch={3: "Pasa13"}), REG, READER, fresh())
    present = {int(a.number): (a.page_start, a.page_end) for a in r.processed.articles}
    (n,) = r.normalizations
    assert reverify(n, present) == []
    bad = [
        n.model_copy(update={"original": "Pasal 3"}),
        n.model_copy(update={"original": "Pasa19"}),
        n.model_copy(update={"normalized": "Pasal 4"}),
        n.model_copy(update={"previous_article": 1}),
        n.model_copy(update={"page": 99}),
    ]
    assert all(reverify(b, present) for b in bad)
    assert isinstance(n, HeadingNormalization) and DocStatus.PROCESSED_OK


def test_every_normalization_in_a_result_reverifies():
    for g in ({3: "Pasa13"}, {2: "Pasa12", 5: "Pasa15"}, {1: "Pasa11"}):
        r = ingest(pdf(glitch=g), REG, READER, fresh())
        present = {int(a.number): (a.page_start, a.page_end) for a in r.processed.articles}
        assert all(reverify(n, present) == [] for n in r.normalizations)


def test_a_glitched_first_article_has_no_previous_heading_and_stays_a_reported_gap():
    r = ingest(pdf(glitch={1: "Pasa11"}), REG, READER, fresh())
    assert r.normalizations == () and "1" not in r.article_index
    assert r.status is S.INGESTED_WITH_ISSUES
