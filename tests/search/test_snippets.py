from __future__ import annotations

import re

import pytest

from inkstone.search import Analyzer, highlight, snippet

from .corpus import DOCS

FILLER = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod. "


def plain(html: str) -> str:
    return re.sub(r"</?mark>", "", html)


def marked(html: str) -> list[str]:
    return re.findall(r"<mark>(.*?)</mark>", html)


def test_highlight_wraps_matching_words():
    html = highlight("Static site generators", {"static", "generat"})
    assert html == "<mark>Static</mark> site <mark>generators</mark>"


def test_highlight_escapes_the_text_around_and_inside_matches():
    html = highlight(
        'Tom & "Jerry" <b>generators</b> AT&T', {"generat", "at&t", "jerri"}
    )
    assert html == (
        "Tom &amp; &quot;<mark>Jerry</mark>&quot; "
        "&lt;b&gt;<mark>generators</mark>&lt;/b&gt; AT&amp;T"
    )


@pytest.mark.parametrize("terms", [[], set(), ["nothing", "here"]])
def test_highlight_without_matches_only_escapes(terms):
    assert highlight("a < b & c", terms) == "a &lt; b &amp; c"


def test_highlight_empty_text():
    assert highlight("", {"anything"}) == ""


def test_highlight_matches_through_stemming_and_folding():
    html = highlight("Running to the CAFÉ, she ran.", {"run", "cafe"})
    assert marked(html) == ["Running", "CAFÉ"]


def test_highlight_takes_terms_not_raw_words():
    # "generators" is not an index term when stemming is on
    assert marked(highlight("generators", {"generators"})) == []
    plain_words = Analyzer(stemming=False)
    assert marked(highlight("generators", {"generators"}, analyzer=plain_words)) == [
        "generators"
    ]


def test_highlight_marks_a_compound_once():
    terms = Analyzer().terms("snake_case")
    assert highlight("use snake_case here", terms) == "use <mark>snake_case</mark> here"


def test_highlight_can_mark_part_of_a_compound():
    assert (
        highlight("use snake_case here", {"snake"})
        == "use <mark>snake</mark>_case here"
    )
    assert highlight("HTMLParser", {"parser"}) == "HTML<mark>Parser</mark>"


def test_highlight_leaves_the_possessive_out_of_the_mark():
    assert highlight("the dog's bone", {"dog"}) == "the <mark>dog</mark>&#x27;s bone"


def test_highlight_with_another_tag():
    assert highlight("static site", {"site"}, tag="em") == "static <em>site</em>"


def test_snippet_of_short_text_is_the_whole_text():
    assert snippet("A static site.", {"static"}) == "A <mark>static</mark> site."


def test_snippet_shows_the_surroundings_of_a_match():
    text = FILLER * 10 + "The needle is here. " + FILLER * 10
    html = snippet(text, {"needl"}, max_length=120)
    assert marked(html) == ["needle"]
    assert html.startswith("…") and html.endswith("…")
    assert len(plain(html)) <= 122
    assert "The <mark>needle</mark> is here." in html


def test_snippet_does_not_cut_words_in_half():
    text = FILLER * 10 + "The needle is here. " + FILLER * 10
    known = set(text.split())
    for max_length in (60, 77, 101, 150):
        body = plain(snippet(text, {"needl"}, max_length=max_length)).strip("…")
        assert set(body.split()) <= known


def test_snippet_prefers_the_window_with_the_most_different_terms():
    text = (
        "Alpha comes first and alone. "
        + FILLER * 6
        + "Much later alpha meets beta at last. "
        + FILLER * 6
        + "Beta again, alone."
    )
    html = snippet(text, {"alpha", "beta"}, max_length=100)
    assert marked(html) == ["alpha", "beta"]


def test_snippet_prefers_more_matches_when_the_terms_are_the_same():
    text = (
        "One alpha here. " + FILLER * 6 + "Then alpha, alpha and alpha. " + FILLER * 6
    )
    assert marked(snippet(text, {"alpha"}, max_length=80)) == ["alpha"] * 3


def test_snippet_takes_the_earliest_of_equally_good_windows():
    text = "First alpha. " + FILLER * 6 + "Second alpha. " + FILLER * 6
    html = snippet(text, {"alpha"}, max_length=60)
    assert html.startswith("First <mark>alpha</mark>.")


def test_snippet_without_a_match_starts_at_the_beginning():
    html = snippet(FILLER * 10, {"needl"}, max_length=50)
    assert html == "Lorem ipsum dolor sit amet consectetur adipiscing…"


def test_snippet_at_the_start_has_no_leading_ellipsis():
    html = snippet("Needle first. " + FILLER * 10, {"needl"}, max_length=60)
    assert html.startswith("<mark>Needle</mark> first.")
    assert html.endswith("…")


def test_snippet_at_the_end_uses_the_room_on_the_left():
    html = snippet(FILLER * 10 + "Last comes the needle.", {"needl"}, max_length=60)
    assert html.startswith("…")
    assert html.endswith("Last comes the <mark>needle</mark>.")
    assert len(plain(html)) > 40


def test_snippet_collapses_whitespace():
    text = "A static\n\n   site\tgenerator.\n" + "\n".join([FILLER] * 5)
    html = snippet(text, {"static"}, max_length=40)
    assert html.startswith("A <mark>static</mark> site generator.")
    assert "\n" not in html and "  " not in html


def test_snippet_escapes_html():
    text = "Use <b>bold</b> & <i>needle</i> sparingly. " + FILLER * 5
    html = snippet(text, {"needl"}, max_length=60)
    assert "&lt;i&gt;<mark>needle</mark>&lt;/i&gt;" in html
    assert "<b>" not in html and "&amp;" in html


def test_snippet_options():
    text = FILLER * 4 + "needle " + FILLER * 4
    html = snippet(text, {"needl"}, max_length=40, tag="b", ellipsis="[...]")
    assert "<b>needle</b>" in html
    assert html.startswith("[...]") and html.endswith("[...]")


def test_snippet_keeps_a_match_that_is_longer_than_the_window():
    text = FILLER + "internationalization_and_localization_helpers " + FILLER
    terms = Analyzer().terms("internationalization_and_localization_helpers")
    html = snippet(text, terms, max_length=20)
    assert marked(html) == ["internationalization_and_localization_helpers"]


def test_snippet_for_a_search_hit(index):
    [hit] = index.search("footnotes underrated")
    body = dict((doc_id, fields) for doc_id, fields, _ in DOCS)[hit.doc_id]["body"]
    html = snippet(body, hit.terms, analyzer=index.analyzer, max_length=70)
    assert marked(html) == ["footnotes", "underrated"]
    assert html.startswith("…") and html.endswith("…")
