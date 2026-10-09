from regulus.extraction.crossrefs import build_graph, mentions
from regulus.extraction.models import UnitKind as U

A = U.ARTICLE


def g(*units: tuple[str, str, str]):
    return build_graph([(uid, A, label, text) for uid, label, text in units])


def test_edge_with_exact_span() -> None:
    text = "Pasal 1\nlihat Pasal 2."
    graph = g(("u1", "1", text), ("u2", "2", "Pasal 2\nx"))
    (e,) = graph.edges
    assert (e.from_unit, e.to_unit) == ("u1", "u2") and text[e.start : e.end] == "Pasal 2"
    assert graph.unresolved == ()


def test_self_reference_ignored_including_heading() -> None:
    graph = g(("u1", "1", "Pasal 1\nsebagaimana dimaksud dalam Pasal 1"))
    assert graph.edges == () and graph.unresolved == ()


def test_missing_article_is_unresolved_not_an_edge() -> None:
    graph = g(("u1", "1", "Pasal 1\nlihat Pasal 99"))
    assert graph.edges == () and [(u.label, u.external) for u in graph.unresolved] == [
        ("99", False)
    ]


def test_ayat_is_article_level_and_span_covers_mention() -> None:
    text = "Pasal 1\nlihat Pasal 2 ayat (3) huruf a."
    (e,) = g(("u1", "1", text), ("u2", "2", "Pasal 2\nx")).edges
    assert text[e.start : e.end] == "Pasal 2 ayat (3)"


def test_other_instrument_is_never_an_edge() -> None:
    text = "Pasal 1\nsesuai Pasal 2 Undang-Undang Nomor 27 Tahun 2022 dan Pasal 2 huruf b Peraturan Pemerintah"
    graph = g(("u1", "1", text), ("u2", "2", "Pasal 2\nx"))
    assert graph.edges == () and [u.external for u in graph.unresolved] == [True, True]


def test_suffix_labels_and_word_boundaries() -> None:
    assert [m.label for m in mentions("Pasal 5a dan Pasal 6B; bipasal 7; Pasal 8xy")] == [
        "5A",
        "6B",
    ]
    graph = g(("u1", "1", "Pasal 1\nPasal 5a"), ("u5", "5A", "Pasal 5A\nx"))
    assert len(graph.edges) == 1


def test_amendment_units_have_no_edges_or_unresolved() -> None:
    graph = build_graph(
        [("a", U.AMENDMENT_UNIT, "I", "Pasal 2 diubah"), ("u2", A, "2", "Pasal 2\nx")]
    )
    assert graph.edges == () and graph.unresolved == ()


def test_duplicate_mentions_give_one_edge_each_in_stable_order() -> None:
    graph = g(
        ("u1", "1", "Pasal 1\nPasal 3 dan Pasal 2 dan Pasal 3"),
        ("u2", "2", "Pasal 2\n"),
        ("u3", "3", "Pasal 3\n"),
    )
    assert [e.start for e in graph.edges] == sorted(e.start for e in graph.edges)
    assert [e.to_unit for e in graph.edges] == ["u3", "u2", "u3"]
