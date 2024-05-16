from __future__ import annotations

import pytest

from inkstone.markdown import (
    Admonition,
    DefinitionDescription,
    DefinitionList,
    DefinitionTerm,
    Heading,
    ListItem,
    Markdown,
)
from inkstone.markdown.extensions.attrs import split_attrs

tasks = Markdown(extensions=["tasklists"], heading_ids=False)
deflists = Markdown(extensions=["deflists"], heading_ids=False)
admonitions = Markdown(extensions=["admonitions"], heading_ids=False)
attrs = Markdown(extensions=["attrs"])
core = Markdown(extensions=[], heading_ids=False)

UNCHECKED = '<input type="checkbox" disabled="" />'
CHECKED = '<input type="checkbox" checked="" disabled="" />'


def test_task_list():
    assert tasks.convert("- [ ] foo\n- [x] bar\n") == (
        '<ul class="task-list">\n'
        f'<li class="task-list-item">{UNCHECKED} foo</li>\n'
        f'<li class="task-list-item">{CHECKED} bar</li>\n'
        "</ul>\n"
    )


def test_task_list_nested_and_mixed_with_plain_items():
    html = tasks.convert("- [x] foo\n  - [ ] bar\n  - [X] baz\n- plain\n")
    assert html == (
        '<ul class="task-list">\n'
        f'<li class="task-list-item">{CHECKED} foo\n'
        '<ul class="task-list">\n'
        f'<li class="task-list-item">{UNCHECKED} bar</li>\n'
        f'<li class="task-list-item">{CHECKED} baz</li>\n'
        "</ul>\n"
        "</li>\n"
        "<li>plain</li>\n"
        "</ul>\n"
    )


def test_task_items_in_loose_and_ordered_lists():
    html = tasks.convert("1. [ ] one\n\n2. [x] two\n")
    assert html == (
        '<ol class="task-list">\n'
        f'<li class="task-list-item">\n<p>{UNCHECKED} one</p>\n</li>\n'
        f'<li class="task-list-item">\n<p>{CHECKED} two</p>\n</li>\n'
        "</ol>\n"
    )


def test_task_item_text_keeps_its_inline_markup():
    html = tasks.convert("- [ ] *really* `do` this\n")
    assert f"{UNCHECKED} <em>really</em> <code>do</code> this" in html


@pytest.mark.parametrize(
    "source",
    [
        "- [ ]no space\n",
        "- [y] wrong letter\n",
        "- [] empty\n",
        "- [ ]\n",
        "-  text [ ] later\n",
        "[ ] not in a list\n",
        "- > [ ] in a quote\n",
    ],
)
def test_not_a_task_item(source):
    assert "checkbox" not in tasks.convert(source)


def test_checked_state_is_on_the_node():
    doc = tasks.parse("- [ ] a\n- [x] b\n- c\n")
    assert [item.checked for item in doc.find_all(ListItem)] == [False, True, None]


def test_tasklists_can_be_switched_off():
    assert core.convert("- [ ] foo\n") == "<ul>\n<li>[ ] foo</li>\n</ul>\n"


def test_checkbox_is_not_a_link_reference():
    html = tasks.convert("- [x] done\n\n[x]: /url\n")
    assert CHECKED in html and "/url" not in html


def test_definition_list():
    assert deflists.convert("Apple\n: A fruit\n") == (
        "<dl>\n<dt>Apple</dt>\n<dd>A fruit</dd>\n</dl>\n"
    )


def test_several_terms_and_several_definitions():
    html = deflists.convert("Term 1\nTerm 2\n: Definition A\n: Definition B\n")
    assert html == (
        "<dl>\n<dt>Term 1</dt>\n<dt>Term 2</dt>\n"
        "<dd>Definition A</dd>\n<dd>Definition B</dd>\n</dl>\n"
    )


def test_consecutive_terms_end_up_in_one_list():
    html = deflists.convert("Apple\n: Fruit\n\nCarrot\n: Vegetable\n\nPlain text.\n")
    assert html == (
        "<dl>\n<dt>Apple</dt>\n<dd>Fruit</dd>\n"
        "<dt>Carrot</dt>\n<dd>Vegetable</dd>\n</dl>\n<p>Plain text.</p>\n"
    )
    doc = deflists.parse("Apple\n: Fruit\n\nCarrot\n: Vegetable\n")
    (dl,) = doc.children
    assert isinstance(dl, DefinitionList)
    assert [type(child) for child in dl.children] == [
        DefinitionTerm,
        DefinitionDescription,
        DefinitionTerm,
        DefinitionDescription,
    ]
    assert (dl.line, dl.end_line) == (1, 5)


def test_blank_line_before_definition_makes_it_loose():
    html = deflists.convert("Term\n\n: Definition\n")
    assert html == "<dl>\n<dt>Term</dt>\n<dd>\n<p>Definition</p>\n</dd>\n</dl>\n"


def test_definition_with_several_blocks():
    html = deflists.convert(
        "Term\n:   First paragraph.\n\n    Second paragraph.\n\n        code\n"
    )
    assert html == (
        "<dl>\n<dt>Term</dt>\n<dd>\n<p>First paragraph.</p>\n<p>Second paragraph.</p>\n"
        "<pre><code>code\n</code></pre>\n</dd>\n</dl>\n"
    )


def test_tight_definition_with_nested_list():
    html = deflists.convert("Term\n: Intro\n  - one\n  - two\n")
    assert html == (
        "<dl>\n<dt>Term</dt>\n<dd>Intro\n<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n"
        "</dd>\n</dl>\n"
    )


def test_definition_continues_lazily():
    html = deflists.convert("Term\n: Definition that\nwraps around\n")
    assert html == (
        "<dl>\n<dt>Term</dt>\n<dd>Definition that\nwraps around</dd>\n</dl>\n"
    )


def test_terms_and_definitions_take_inline_markup():
    html = deflists.convert("*Term* `x`\n: **Bold** [link](/u)\n")
    assert "<dt><em>Term</em> <code>x</code></dt>" in html
    assert '<dd><strong>Bold</strong> <a href="/u">link</a></dd>' in html


def test_definition_list_inside_other_containers():
    html = deflists.convert("> Term\n> : Definition\n")
    assert html == (
        "<blockquote>\n<dl>\n<dt>Term</dt>\n<dd>Definition</dd>\n</dl>\n</blockquote>\n"
    )
    html = deflists.convert("- Term\n  : Definition\n")
    assert "<li>\n<dl>\n<dt>Term</dt>\n<dd>Definition</dd>\n</dl>\n</li>" in html


@pytest.mark.parametrize(
    "source, expected",
    [
        (": no term above\n", "<p>: no term above</p>\n"),
        ("Term\n:no space\n", "<p>Term\n:no space</p>\n"),
        ("# Heading\n: text\n", "<h1>Heading</h1>\n<p>: text</p>\n"),
        ("Term\n    : indented\n", "<p>Term\n: indented</p>\n"),
        (
            "> quoted\n: lazy line\n",
            "<blockquote>\n<p>quoted\n: lazy line</p>\n</blockquote>\n",
        ),
    ],
)
def test_not_a_definition(source, expected):
    assert deflists.convert(source) == expected


def test_reference_definition_above_the_term_is_not_a_term():
    html = deflists.convert("[ref]: /url\nTerm\n: See [ref]\n")
    assert html == '<dl>\n<dt>Term</dt>\n<dd>See <a href="/url">ref</a></dd>\n</dl>\n'
    html = deflists.convert("[ref]: /url\n: orphan\n")
    assert html == "<p>: orphan</p>\n"


def test_deflists_can_be_switched_off():
    assert core.convert("Term\n: Definition\n") == "<p>Term\n: Definition</p>\n"


def test_admonition():
    html = admonitions.convert('!!! note "Take note"\n    Some *text*.\n')
    assert html == (
        '<div class="admonition note">\n'
        '<p class="admonition-title">Take note</p>\n'
        "<p>Some <em>text</em>.</p>\n"
        "</div>\n"
    )


@pytest.mark.parametrize(
    "opener, title",
    [
        ("!!! note", "Note"),
        ("!!! warning", "Warning"),
        ("!!! see-also", "See also"),
        ("!!! TIP", "Tip"),
    ],
)
def test_admonition_title_defaults_to_the_kind(opener, title):
    html = admonitions.convert(opener + "\n    body\n")
    assert f'<p class="admonition-title">{title}</p>' in html


def test_admonition_with_empty_title_has_no_title_element():
    html = admonitions.convert('!!! note ""\n    body\n')
    assert html == '<div class="admonition note">\n<p>body</p>\n</div>\n'


def test_admonition_extra_classes_and_escaped_title():
    html = admonitions.convert('!!! danger inline end "<Don\'t> & co"\n    x\n')
    assert '<div class="admonition danger inline end">' in html
    assert "<p class=\"admonition-title\">&lt;Don't&gt; &amp; co</p>" in html


def test_admonition_body_can_hold_any_blocks():
    html = admonitions.convert(
        "!!! tip\n    First.\n\n        code\n\n    - a\n    - b\n\nOutside.\n"
    )
    assert html == (
        '<div class="admonition tip">\n<p class="admonition-title">Tip</p>\n'
        "<p>First.</p>\n<pre><code>code\n</code></pre>\n"
        "<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n</div>\n<p>Outside.</p>\n"
    )


def test_admonition_ends_at_first_unindented_block():
    html = admonitions.convert("!!! note\n    inside\n\noutside\n")
    assert html.endswith("<p>inside</p>\n</div>\n<p>outside</p>\n")
    html = admonitions.convert("!!! note\nnot indented\n")
    assert html.endswith("</div>\n<p>not indented</p>\n")


def test_nested_admonitions():
    html = admonitions.convert("!!! note\n    outer\n\n    !!! tip\n        inner\n")
    assert html.count('<div class="admonition') == 2
    assert html.index("outer") < html.index("admonition tip") < html.index("inner")


def test_collapsible_admonitions():
    html = admonitions.convert('??? faq "Why?"\n    Because.\n')
    assert html == (
        '<details class="admonition faq">\n<summary>Why?</summary>\n'
        "<p>Because.</p>\n</details>\n"
    )
    html = admonitions.convert("???+ faq\n    Open.\n")
    assert html.startswith(
        '<details class="admonition faq" open>\n<summary>Faq</summary>'
    )


def test_admonition_node():
    doc = admonitions.parse('text\n\n??? Bug extra "It broke"\n    details\n')
    box = doc.children[1]
    assert isinstance(box, Admonition)
    assert (box.kind, box.classes, box.title) == ("bug", ["extra"], "It broke")
    assert box.collapsible and not box.open
    assert (box.line, box.end_line) == (3, 4)


@pytest.mark.parametrize(
    "source",
    [
        "!!!note\n    x\n",
        "!!!\n    x\n",
        '!!! "only a title"\n    x\n',
        "!! note\n    x\n",
        "    !!! note\n",
        "?? note\n",
    ],
)
def test_not_an_admonition(source):
    assert "admonition" not in admonitions.convert(source)


def test_admonitions_can_be_switched_off():
    assert core.convert("!!! note\n    body\n") == "<p>!!! note\nbody</p>\n"


def test_heading_attributes():
    html = attrs.convert("## Title {#custom-id .cls .other data-level=2}\n")
    assert html == '<h2 id="custom-id" class="cls other" data-level="2">Title</h2>\n'


def test_heading_attributes_on_setext_and_closed_atx():
    assert attrs.convert("Title {#top}\n=====\n") == '<h1 id="top">Title</h1>\n'
    assert attrs.convert("## Title {#mid} ##\n") == '<h2 id="mid">Title</h2>\n'


def test_heading_class_only_still_gets_a_generated_id():
    assert attrs.convert("# Some Title {.fancy}\n") == (
        '<h1 id="some-title" class="fancy">Some Title</h1>\n'
    )


def test_heading_attribute_values_can_be_quoted():
    html = attrs.convert("# T {title=\"two words\" lang='en' hidden .x}\n")
    assert html == '<h1 id="t" class="x" title="two words" lang="en" hidden>T</h1>\n'


@pytest.mark.parametrize(
    "source, expected",
    [
        ("# Using {braces}\n", '<h1 id="using-braces">Using {braces}</h1>\n'),
        ("# Empty {}\n", '<h1 id="empty">Empty {}</h1>\n'),
        (
            "# {#lead} not at the end\n",
            '<h1 id="lead-not-at-the-end">{#lead} not at the end</h1>\n',
        ),
        ("# Escaped \\{#x}\n", '<h1 id="escaped-x">Escaped {#x}</h1>\n'),
        ("# Broken {#a\n", '<h1 id="broken-a">Broken {#a</h1>\n'),
    ],
)
def test_braces_that_are_not_attributes(source, expected):
    assert attrs.convert(source) == expected


def test_attributes_are_kept_on_the_node():
    doc = attrs.parse("# T {#a .b key=v}")
    (heading,) = doc.find_all(Heading)
    assert heading.attrs == {"id": "a", "class": "b", "key": "v"}
    assert heading.id == "a"


def test_attrs_can_be_switched_off():
    md = Markdown(extensions=[])
    assert md.convert("# T {#a}\n") == '<h1 id="t-a">T {#a}</h1>\n'


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Title {#x}", ("Title", {"id": "x"})),
        ("Title   {.a .b}  ", ("Title", {"class": "a b"})),
        ("Title {k=v}", ("Title", {"k": "v"})),
        ("Title {flag}", ("Title {flag}", {})),
        ("Title", ("Title", {})),
        ("{#only}", ("", {"id": "only"})),
    ],
)
def test_split_attrs(text, expected):
    assert split_attrs(text) == expected
