from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.markdown import Markdown
from inkstone.plugins.builtin.toc import Toc, build_tree

from .helpers import make_page

SOURCE = """\
# Title

Intro paragraph.

## First

### Detail

#### Too deep

## Second & last
"""


def run(config, text=SOURCE, settings=None, **page_attrs):
    page = make_page("Doc", **page_attrs)
    html = Toc(config, settings or {}).page_html(page, Markdown().convert(text))
    return page, html


def flat(entries):
    return [(entry.level, entry.id, entry.title) for e in entries for entry in e.walk()]


def test_defaults_keep_levels_two_and_three(config):
    page, html = run(config)
    assert flat(page.toc) == [
        (2, "first", "First"),
        (3, "detail", "Detail"),
        (2, "second-last", "Second & last"),
    ]
    assert page.toc_html == (
        "<ul>\n"
        '<li><a href="#first">First</a>\n'
        '<ul>\n<li><a href="#detail">Detail</a></li>\n</ul>\n'
        "</li>\n"
        '<li><a href="#second-last">Second &amp; last</a></li>\n'
        "</ul>\n"
    )
    # the content itself is not touched by default
    assert html == Markdown().convert(SOURCE)


@pytest.mark.parametrize(
    "settings, ids",
    [
        ({"min_level": 1}, ["title", "first", "detail", "second-last"]),
        ({"max_level": 2}, ["first", "second-last"]),
        ({"max_level": 4}, ["first", "detail", "too-deep", "second-last"]),
        ({"min_level": 3, "max_level": 4}, ["detail", "too-deep"]),
        ({"min_level": 5, "max_level": 6}, []),
    ],
)
def test_level_settings(config, settings, ids):
    page, _html = run(config, settings=settings)
    assert [entry_id for _level, entry_id, _title in flat(page.toc)] == ids
    assert bool(page.toc_html) is bool(ids)


@pytest.mark.parametrize(
    "settings",
    [
        {"min_level": 0},
        {"max_level": 7},
        {"min_level": 4, "max_level": 2},
        {"min_level": "2"},
        {"insert": "bottom"},
        {"anchors": "yes"},
        {"min_items": 0},
    ],
)
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"plugin\.toc"):
        Toc(config, settings)


def test_headings_keep_their_inline_markup_out_of_the_title(config):
    page, _html = run(config, "## Using `code` and *emphasis* <b>here</b>")
    assert page.toc[0].title == "Using code and emphasis here"


def test_headings_without_an_id_are_left_out(config):
    html = '<h2>No id</h2>\n<h2 id="yes">With id</h2>\n'
    page = make_page("Doc")
    Toc(config, {}).page_html(page, html)
    assert flat(page.toc) == [(2, "yes", "With id")]


def test_headings_inside_code_do_not_count(config):
    html = (
        '<pre><code>&lt;h2 id="x"&gt;</code><h2 id="fake">Fake</h2></pre>\n'
        '<h2 id="a">A</h2>'
    )
    page = make_page("Doc")
    Toc(config, {}).page_html(page, html)
    assert [entry.id for entry in page.toc] == ["a"]


def test_front_matter_can_switch_it_off(config):
    page, html = run(config, meta={"toc": False})
    assert page.toc == []
    assert page.toc_html == ""


def test_front_matter_can_change_the_range(config):
    page, _html = run(config, meta={"toc": {"max_level": 4}})
    assert [entry.id for e in page.toc for entry in e.walk()] == [
        "first",
        "detail",
        "too-deep",
        "second-last",
    ]
    with pytest.raises(PluginError, match="toc"):
        run(config, meta={"toc": {"min_level": 9}})


def test_min_items(config):
    page, _html = run(config, "## Only one", settings={"min_items": 2})
    assert page.toc == [] and page.toc_html == ""
    page, _html = run(config, "## One\n\n## Two", settings={"min_items": 2})
    assert len(page.toc) == 2


def test_toc_marker_gets_the_trimmed_list(config):
    page, html = run(config, "[TOC]\n\n" + SOURCE)
    nav = html[html.index("<nav") : html.index("</nav>")]
    assert 'href="#first"' in nav and 'href="#detail"' in nav
    assert 'href="#title"' not in nav and 'href="#too-deep"' not in nav
    assert html.count('<nav class="toc">') == 1


def test_toc_marker_stays_when_the_sidebar_list_is_off(config):
    page, html = run(config, "[TOC]\n\n" + SOURCE, meta={"toc": False})
    assert page.toc_html == ""
    assert '<nav class="toc">' in html


def test_toc_marker_disappears_when_nothing_is_in_range(config):
    _page, html = run(config, "[TOC]\n\n# Only a title\n\ntext")
    assert "<nav" not in html
    assert '<h1 id="only-a-title">' in html


@pytest.mark.parametrize(
    "where, before",
    [("top", "<h1"), ("before-first-heading", '<h2 id="first"')],
)
def test_automatic_insertion(config, where, before):
    page, html = run(config, settings={"insert": where})
    assert html.count('<nav class="toc">') == 1
    assert html.index('<nav class="toc">') < html.index(before)
    if where == "before-first-heading":
        assert html.index("Intro paragraph") < html.index("<nav")
    assert page.toc_html in html


def test_insertion_respects_an_explicit_marker_and_the_off_switch(config):
    _page, html = run(config, SOURCE + "\n[TOC]\n", settings={"insert": "top"})
    assert html.count('<nav class="toc">') == 1
    assert html.index("<nav") > html.index("<h1")
    _page, html = run(config, settings={"insert": "top"}, meta={"toc": False})
    assert "<nav" not in html
    _page, html = run(config, "no headings", settings={"insert": "top"})
    assert "<nav" not in html


def test_anchor_links(config):
    page, html = run(config, settings={"anchors": True})
    assert (
        '<h2 id="first">First <a class="heading-anchor" href="#first" '
        'aria-label="Link to this section">¶</a></h2>'
    ) in html
    assert 'href="#too-deep"' in html
    # the page title is below min_level
    assert '<h1 id="title">Title</h1>' in html
    # the anchor text is not part of the table of contents
    assert page.toc[0].title == "First"


def test_anchor_settings(config):
    settings = {
        "anchors": True,
        "anchor_text": "#",
        "anchor_class": "permalink",
        "anchor_position": "before",
    }
    _page, html = run(config, "## A & B", settings=settings)
    assert html == (
        '<h2 id="a-b"><a class="permalink" href="#a-b" '
        'aria-label="Link to this section">#</a> A &amp; B</h2>\n'
    )


def test_anchors_are_not_added_twice(config):
    plugin = Toc(config, {"anchors": True})
    page = make_page("Doc")
    once = plugin.page_html(page, Markdown().convert(SOURCE))
    assert plugin.page_html(page, once) == once


def test_anchors_and_insertion_together(config):
    settings = {"anchors": True, "insert": "before-first-heading", "max_level": 2}
    _page, html = run(config, settings=settings)
    assert html.index("</nav>") < html.index('<h2 id="first">')
    assert html.count("heading-anchor") == 4


def test_build_tree_copes_with_skipped_levels():
    tree = build_tree([(2, "a", "A"), (4, "b", "B"), (3, "c", "C"), (2, "d", "D")])
    assert [entry.id for entry in tree] == ["a", "d"]
    assert [child.id for child in tree[0].children] == ["b", "c"]
    assert build_tree([]) == []
