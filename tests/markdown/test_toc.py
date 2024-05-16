from __future__ import annotations

import pytest

from inkstone.markdown import (
    Heading,
    Markdown,
    TocEntry,
    TocMarker,
    render_toc,
    slugify,
)

DOC = """\
# Getting started

## Install

### From source

## Configure

# Reference
"""


def outline(entries, depth=0):
    lines = []
    for entry in entries:
        lines.append("  " * depth + f"{entry.level} {entry.id}")
        lines.extend(outline(entry.children, depth + 1))
    return lines


def test_toc_is_nested_by_level():
    md = Markdown()
    md.convert(DOC)
    assert outline(md.toc) == [
        "1 getting-started",
        "  2 install",
        "    3 from-source",
        "  2 configure",
        "1 reference",
    ]
    first = md.toc[0]
    assert isinstance(first, TocEntry)
    assert (first.level, first.id) == (1, "getting-started")
    assert first.title == "Getting started"
    assert [child.title for child in first.children] == ["Install", "Configure"]


def test_toc_is_available_after_parse_too():
    md = Markdown()
    md.parse("# A\n## B\n")
    assert outline(md.toc) == ["1 a", "  2 b"]


def test_toc_belongs_to_the_last_document():
    md = Markdown()
    assert md.toc == []
    md.convert("# First\n")
    md.convert("# Second\n")
    assert [entry.title for entry in md.toc] == ["Second"]
    md.convert("no headings\n")
    assert md.toc == []
    assert md.render_toc() == ""


def test_skipped_levels_nest_under_the_nearest_shallower_heading():
    md = Markdown()
    md.convert("# A\n### deep\n## B\n#### deeper\n# C\n")
    assert outline(md.toc) == ["1 a", "  3 deep", "  2 b", "    4 deeper", "1 c"]


def test_document_starting_below_h1():
    md = Markdown()
    md.convert("### C\n## B\n# A\n## B2\n")
    assert outline(md.toc) == ["3 c", "2 b", "1 a", "  2 b2"]


def test_walk_flattens_an_entry():
    md = Markdown()
    md.convert(DOC)
    assert [entry.title for entry in md.toc[0].walk()] == [
        "Getting started",
        "Install",
        "From source",
        "Configure",
    ]


def test_render_toc():
    md = Markdown()
    md.convert(DOC)
    assert md.render_toc() == (
        "<ul>\n"
        '<li><a href="#getting-started">Getting started</a>\n'
        "<ul>\n"
        '<li><a href="#install">Install</a>\n'
        "<ul>\n"
        '<li><a href="#from-source">From source</a></li>\n'
        "</ul>\n"
        "</li>\n"
        '<li><a href="#configure">Configure</a></li>\n'
        "</ul>\n"
        "</li>\n"
        '<li><a href="#reference">Reference</a></li>\n'
        "</ul>\n"
    )
    assert render_toc(md.toc) == md.render_toc()


def test_titles_are_plain_text_and_escaped_when_rendered():
    md = Markdown()
    md.convert("# Using `<b>` & *friends* [here](/x)\n")
    (entry,) = md.toc
    assert entry.title == "Using <b> & friends here"
    assert entry.id == "using-b-friends-here"
    assert md.render_toc() == (
        '<ul>\n'
        '<li><a href="#using-b-friends-here">Using &lt;b&gt; &amp; friends here</a>'
        "</li>\n</ul>\n"
    )


def test_duplicate_headings_get_numbered_ids():
    md = Markdown()
    html = md.convert("# Intro\n## Intro\n## Intro\n## Intro-1\n")
    assert [entry.id for entry in md.toc[0].walk()] == [
        "intro",
        "intro-1",
        "intro-2",
        "intro-1-1",
    ]
    assert '<h2 id="intro-2">Intro</h2>' in html


def test_explicit_ids_are_never_taken_by_generated_ones():
    md = Markdown()
    md.convert("# Setup\n\n# Other {#setup}\n\n# Setup\n")
    assert [entry.id for entry in md.toc] == ["setup-1", "setup", "setup-2"]


def test_heading_without_any_word_characters_still_gets_an_id():
    md = Markdown()
    assert md.convert("# ***\n# !!!\n") == (
        '<h1 id="section">***</h1>\n<h1 id="section-1">!!!</h1>\n'
    )


def test_heading_ids_can_be_turned_off():
    md = Markdown(heading_ids=False)
    assert md.convert("# One\n## Two {#kept}\n") == (
        '<h1>One</h1>\n<h2 id="kept">Two</h2>\n'
    )
    assert [(entry.id, entry.title) for entry in md.toc[0].walk()] == [
        ("", "One"),
        ("kept", "Two"),
    ]
    assert md.render_toc() == (
        '<ul>\n<li>One\n<ul>\n<li><a href="#kept">Two</a></li>\n</ul>\n</li>\n</ul>\n'
    )


def test_headings_inside_containers_are_included():
    md = Markdown()
    md.convert("# Top\n\n> ## Quoted\n\n- ### In a list\n\n!!! note\n    ## Boxed\n")
    assert [entry.title for entry in md.toc[0].walk()] == [
        "Top",
        "Quoted",
        "In a list",
        "Boxed",
    ]


def test_toc_marker_is_replaced():
    md = Markdown()
    html = md.convert("[TOC]\n\n# One\n\n## Two\n")
    assert html == (
        '<nav class="toc">\n'
        "<ul>\n"
        '<li><a href="#one">One</a>\n'
        "<ul>\n"
        '<li><a href="#two">Two</a></li>\n'
        "</ul>\n"
        "</li>\n"
        "</ul>\n"
        "</nav>\n"
        '<h1 id="one">One</h1>\n'
        '<h2 id="two">Two</h2>\n'
    )


def test_toc_marker_can_sit_anywhere_and_sees_the_whole_document():
    md = Markdown()
    html = md.convert("# Before\n\n[toc]\n\n# After\n")
    nav = html[html.index("<nav") : html.index("</nav>")]
    assert "#before" in nav and "#after" in nav


def test_toc_marker_node_and_empty_toc():
    md = Markdown()
    doc = md.parse("intro\n\n[TOC]\n")
    assert isinstance(doc.children[1], TocMarker)
    assert doc.children[1].line == 3
    assert md.render(doc) == "<p>intro</p>\n"


@pytest.mark.parametrize(
    "source",
    ["[TOC] trailing words\n", "see [TOC]\n", "`[TOC]`\n", "    [TOC]\n", "\\[TOC]\n"],
)
def test_marker_must_be_a_paragraph_of_its_own(source):
    md = Markdown()
    assert "<nav" not in md.convert(source + "\n# H\n")


def test_toc_extension_can_be_switched_off():
    md = Markdown(extensions=[])
    assert md.convert("[TOC]\n\n# H\n") == '<p>[TOC]</p>\n<h1 id="h">H</h1>\n'
    # the table of contents itself does not depend on the marker extension
    assert [entry.id for entry in md.toc] == ["h"]


def test_heading_nodes_carry_their_id():
    doc = Markdown().parse("# One\n\nText\n\n## Two words\n")
    assert [h.id for h in doc.find_all(Heading)] == ["one", "two-words"]


@pytest.mark.parametrize(
    "text, slug",
    [
        ("Hello, World!", "hello-world"),
        ("  spaces   everywhere  ", "spaces-everywhere"),
        ("snake_case stays", "snake_case-stays"),
        ("dash - dash -- dash", "dash-dash-dash"),
        ("Ünïcödé Çharacters", "ünïcödé-çharacters"),
        ("日本語 の 見出し", "日本語-の-見出し"),
        ("C++ & C#", "c-c"),
        ("1. Numbered", "1-numbered"),
        ("", "section"),
        ("?!", "section"),
        ("ﬁne ligature", "fine-ligature"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug
