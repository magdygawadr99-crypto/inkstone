from __future__ import annotations

import pytest

from inkstone.content.summary import (
    close_open_tags,
    first_paragraph,
    has_more_marker,
    make_summary,
    plain_summary,
    split_at_marker,
    strip_marker,
    truncate_html,
)


def test_split_at_the_marker():
    html = "<p>Intro.</p>\n<!-- more -->\n<p>The rest.</p>\n"
    summary, content = split_at_marker(html)
    assert summary == "<p>Intro.</p>\n"
    assert content == "<p>Intro.</p>\n<p>The rest.</p>\n"


@pytest.mark.parametrize(
    "marker", ["<!-- more -->", "<!--more-->", "<!--  MORE  -->", "<!-- More -->"]
)
def test_marker_spellings(marker):
    assert has_more_marker(f"<p>a</p>{marker}<p>b</p>")
    summary, content = split_at_marker(f"<p>a</p>\n{marker}\n<p>b</p>")
    assert summary == "<p>a</p>\n"
    assert "more" not in content.lower()


def test_no_marker():
    assert split_at_marker("<p>Just text.</p>") is None
    assert not has_more_marker("<p>more, more, more</p>")
    assert not has_more_marker("<pre>&lt;!-- more --&gt;</pre>")
    assert strip_marker("<p>Just text.</p>") == "<p>Just text.</p>"


def test_marker_inside_a_paragraph_closes_it():
    summary, content = split_at_marker("<p>Before <!-- more --> after.</p>")
    assert summary == "<p>Before</p>\n"
    assert content == "<p>Before  after.</p>"


def test_marker_inside_nested_markup_is_balanced():
    html = (
        "<blockquote>\n<ul>\n<li>one</li>\n<li><em>two\n"
        "<!-- more -->\nstill two</em></li>\n</ul>\n</blockquote>\n"
    )
    summary, _content = split_at_marker(html)
    assert summary.rstrip().endswith("<li><em>two</em></li></ul></blockquote>")
    assert summary.count("<ul>") == summary.count("</ul>") == 1


def test_marker_right_after_an_opening_tag_leaves_no_empty_element():
    summary, _content = split_at_marker("<p>Lead.</p>\n<p><!-- more -->Rest.</p>")
    assert summary == "<p>Lead.</p>\n"


def test_only_the_first_marker_splits_but_all_are_removed():
    html = "<p>a</p><!-- more --><p>b</p><!-- more --><p>c</p>"
    summary, content = split_at_marker(html)
    assert summary == "<p>a</p>\n"
    assert content == "<p>a</p><p>b</p><p>c</p>"


@pytest.mark.parametrize(
    ("fragment", "expected"),
    [
        ("<p>open", "<p>open</p>"),
        ("<div><p>a</p><p>b", "<div><p>a</p><p>b</p></div>"),
        ("<p>line<br>break <img src='x'>", "<p>line<br>break <img src='x'></p>"),
        ("<p>done</p>", "<p>done</p>"),
        ("<ul><li>a<li>b", "<ul><li>a<li>b</li></li></ul>"),
        ("<p>self <br/> closing <b>bold", "<p>self <br/> closing <b>bold</b></p>"),
        ("<P>Upper <EM>case", "<P>Upper <EM>case</em></p>"),
        ("text <!-- <b> in a comment --> more", "text <!-- <b> in a comment --> more"),
        ('<a href="x>y">link', '<a href="x>y">link</a>'),
        ("", ""),
    ],
)
def test_close_open_tags(fragment, expected):
    assert close_open_tags(fragment) == expected


def test_close_open_tags_ignores_markup_inside_script_and_style():
    fragment = "<div><script>if (a < b) { x = '<p>'; }</script><p>text"
    assert close_open_tags(fragment).endswith("<p>text</p></div>")


def test_first_paragraph_skips_ones_without_text():
    html = (
        '<p><img src="a.png" alt=""></p>\n<p>  </p>\n'
        "<p>Real <em>text</em>.</p>\n<p>x</p>"
    )
    assert first_paragraph(html) == "<p>Real <em>text</em>.</p>"
    assert first_paragraph("<ul><li>no paragraphs</li></ul>") == ""
    assert first_paragraph("") == ""


def test_summary_prefers_the_marker():
    html = "<p>Intro.</p>\n<!-- more -->\n<p>Rest.</p>\n"
    summary, content = make_summary(html, explicit="<p>From front matter.</p>")
    assert summary.html == "<p>Intro.</p>\n"
    assert summary.truncated is True
    assert content == "<p>Intro.</p>\n<p>Rest.</p>\n"


def test_summary_from_front_matter_when_there_is_no_marker():
    summary, content = make_summary(
        "<p>One.</p>\n<p>Two.</p>\n", explicit="<p>Custom.</p>\n"
    )
    assert summary.html == "<p>Custom.</p>\n"
    assert summary.truncated is True
    assert content == "<p>One.</p>\n<p>Two.</p>\n"


def test_summary_falls_back_to_the_first_paragraph():
    summary, content = make_summary("<h2>Title</h2>\n<p>One.</p>\n<p>Two.</p>\n")
    assert summary.html == "<p>One.</p>\n"
    assert summary.truncated is True
    assert content == "<h2>Title</h2>\n<p>One.</p>\n<p>Two.</p>\n"


def test_summary_of_a_single_paragraph_is_not_truncated():
    summary, _content = make_summary("<p>All there is.</p>\n")
    assert summary.html == "<p>All there is.</p>\n"
    assert summary.truncated is False


def test_marker_at_the_very_end_is_not_truncated():
    summary, content = make_summary("<p>All there is.</p>\n<!-- more -->\n")
    assert summary.truncated is False
    assert "more" not in content


def test_marker_before_any_text_falls_through_to_the_other_rules():
    summary, content = make_summary("<!-- more -->\n<p>First.</p>\n<p>Second.</p>\n")
    assert summary.html == "<p>First.</p>\n"
    assert "<!--" not in content


def test_summary_without_paragraphs_truncates_by_words():
    items = "".join(f"<li>word{n} and more</li>" for n in range(60))
    summary, _content = make_summary(f"<ul>{items}</ul>", fallback_words=10)
    assert summary.truncated is True
    assert summary.html.endswith("</li></ul>")
    assert "word3" in summary.html and "word30" not in summary.html
    assert summary.html.count("<li>") == summary.html.count("</li>")


def test_summary_of_nothing():
    summary, content = make_summary("")
    assert summary.html == "" and summary.truncated is False
    assert content == ""


def test_footnote_markers_are_left_out_of_summaries():
    html = (
        '<p>Claim<sup class="footnote-ref">'
        '<a href="#fn-1" id="fnref-1">1</a></sup>.</p>\n'
        "<!-- more -->\n<p>Rest.</p>\n"
        '<section class="footnotes"><ol><li id="fn-1">Note.</li></ol></section>\n'
    )
    summary, content = make_summary(html)
    assert summary.html == "<p>Claim.</p>\n"
    # the page itself keeps them
    assert 'href="#fn-1"' in content


def test_truncate_html_keeps_tags_balanced():
    html = "<p>The <strong>quick brown fox</strong> jumps over the lazy dog.</p>"
    assert truncate_html(html, 15) == "<p>The <strong>quick brown…</strong></p>"
    assert truncate_html(html, 1000) == html
    assert truncate_html(html, 0) == "<p>…</p>"


def test_truncate_html_backs_off_to_a_word_boundary():
    html = "<p>The <strong>quick brown fox</strong> jumps over the lazy dog.</p>"
    # 14 characters end inside "brown"
    assert truncate_html(html, 14) == "<p>The <strong>quick…</strong></p>"
    # but not when that would give up most of the room
    assert truncate_html("<p>Supercalifragilistic word</p>", 10) == "<p>Supercalif…</p>"


def test_truncate_html_leaves_trailing_markup_alone():
    html = '<p>Short.</p><hr><p><img src="x.png" alt=""></p>'
    assert truncate_html(html, 6) == html


def test_truncate_html_does_not_count_tags_or_split_entities():
    link = '<a href="https://example.com/a/very/long/address">'
    html = f"<p>{link}Fish &amp; chips</a> daily</p>"
    short = truncate_html(html, 8, suffix="...")
    assert short.startswith(f"<p>{link}Fish &amp;")
    assert short.endswith("...</a></p>")
    assert "&am..." not in short


def test_truncate_html_by_words():
    html = "<p>one two three</p><p>four five six</p>"
    assert truncate_html(html, 4, words=True) == "<p>one two three</p><p>four…</p>"


def test_plain_summary_strips_markup():
    text = plain_summary("<p>Some <em>marked up</em> text &amp; more.</p>", 20)
    assert "<" not in text
    assert text.startswith("Some marked up")
    assert len(text) <= 20
