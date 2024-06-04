from __future__ import annotations

import pytest

from inkstone.markdown import Markdown, PlainTextRenderer, plain_text

md = Markdown()


def text_of(source: str, **options) -> str:
    return PlainTextRenderer(**options).render(md.parse(source))


@pytest.mark.parametrize(
    "source, expected",
    [
        ("Just words.", "Just words."),
        ("*emphasis* and **strong** and ~~struck~~", "emphasis and strong and struck"),
        ("`code` stays as `it is`", "code stays as it is"),
        ("a [link](http://example.com 'title') here", "a link here"),
        ("<http://example.com>", "http://example.com"),
        ("an ![alt *text*](pic.png) image", "an alt text image"),
        ("soft\nbreak", "soft break"),
        ("hard  \nbreak", "hard\nbreak"),
        ("entities &amp; &copy; \\*escapes\\*", "entities & © *escapes*"),
        ("inline <b>html</b> tags", "inline html tags"),
        ("a < b > c & d", "a < b > c & d"),
        ("# Heading *text*", "Heading text"),
        ("Setext\n======", "Setext"),
        ("    indented code\n", "indented code"),
        ("---", ""),
        ("", ""),
    ],
)
def test_inline_and_leaf_rendering(source, expected):
    assert text_of(source) == expected


def test_blocks_are_separated_by_blank_lines():
    assert text_of("# Title\n\nOne.\n\nTwo\nlines.\n") == "Title\n\nOne.\n\nTwo lines."


def test_tight_list_items_go_on_their_own_lines():
    assert text_of("- one\n- two\n  - nested\n- three\n") == "one\ntwo\nnested\nthree"
    assert text_of("1. first\n2. second\n") == "first\nsecond"


def test_loose_list_items_are_separated_like_paragraphs():
    assert text_of("- one\n\n- two\n") == "one\n\ntwo"


def test_block_quote_and_nested_content():
    assert text_of("> quoted *text*\n>\n> second\n\nafter") == (
        "quoted text\n\nsecond\n\nafter"
    )


def test_code_blocks_keep_their_layout():
    source = "before\n\n```python\ndef f():\n    return 1\n```\n\nafter\n"
    assert text_of(source) == "before\n\ndef f():\n    return 1\n\nafter"


def test_code_blocks_can_be_left_out():
    source = "before\n\n```\ncode\n```\n\n    more code\n\nafter\n"
    assert text_of(source, code_blocks=False) == "before\n\nafter"


def test_image_alt_text_can_be_left_out():
    assert text_of("see ![the alt](x.png) here", images=False) == "see here"


def test_raw_html_blocks_are_dropped_by_default():
    source = "<div class='x'>\nraw &amp; <b>bold</b>\n</div>\n\npara\n"
    assert text_of(source) == "para"
    assert text_of(source, raw_html=True) == "raw & bold\n\npara"


def test_comments_scripts_and_styles_never_show_up():
    source = (
        "<!-- a comment -->\n\n"
        "<script>\nvar x = '<b>';\n</script>\n\n"
        "<style>p { color: red }</style>\n\n"
        "text\n"
    )
    assert text_of(source) == "text"
    assert text_of(source, raw_html=True) == "text"


def test_tables():
    source = "| Name | Qty |\n|---|---|\n| *Apple* | 3 |\n| Pear | |\n"
    assert text_of(source) == "Name | Qty\nApple | 3\nPear"


def test_definition_lists():
    assert text_of("Term\n: The *definition*\n\nOther\n: Second\n") == (
        "Term\nThe definition\nOther\nSecond"
    )


def test_admonitions_include_their_title():
    assert text_of('!!! note "Heads up"\n    Body text.\n') == "Heads up\n\nBody text."
    assert text_of('!!! note ""\n    Body text.\n') == "Body text."
    assert text_of("!!! warning\n") == "Warning"


def test_task_list_markers_and_toc_marker_leave_no_text():
    assert text_of("- [x] done\n- [ ] todo\n") == "done\ntodo"
    assert text_of("[TOC]\n\n# Only heading\n") == "Only heading"


def test_footnotes():
    source = "Claim[^1] made.\n\n[^1]: Source *here*.\n"
    assert text_of(source) == "Claim made."
    assert text_of(source, footnotes=True) == "Claim made.\n\nSource here."


def test_abbreviations_and_marks_contribute_their_text():
    full = Markdown(extensions=["abbr", "mark", "sub", "sup"])
    doc = full.parse("==HTML== is H~2~O^3^\n\n*[HTML]: Hyper Text")
    assert plain_text(doc) == "HTML is H2O3"


def test_custom_separator_gives_one_line():
    source = (
        "# Title\n\nPara one\nwraps.\n\n- a\n- b\n\n"
        "```\nx\ny\n```\n\nhard  \nbreak\n"
    )
    assert text_of(source, separator=" ") == "Title Para one wraps. a b x y hard break"


def test_runs_of_spaces_collapse_in_prose_but_not_in_code():
    assert text_of("a     b") == "a b"
    assert text_of("    a     b\n") == "a     b"


def test_rendering_a_subtree():
    doc = md.parse("# The *title*\n\nBody with `code`.\n")
    heading, paragraph = doc.children
    renderer = PlainTextRenderer()
    assert renderer.render(heading) == "The title"
    assert renderer.render(paragraph) == "Body with code."
    assert renderer.render(paragraph.children[0]) == "Body with "


def test_plain_text_helper_passes_options():
    doc = md.parse("a\n\n```\ncode\n```\n")
    assert plain_text(doc) == "a\n\ncode"
    assert plain_text(doc, code_blocks=False) == "a"


def test_no_markup_survives_a_busy_document():
    source = (
        "# Big *Title* {#id}\n\n"
        "Some **bold** text with a [link](/x), `code`, ~~del~~ and <em>html</em>.\n\n"
        "> - [ ] quoted task\n\n"
        "| a | b |\n|:-:|--:|\n| 1 | 2 |\n\n"
        "!!! tip\n    Use www.example.com\n\n"
        "---\n\nEnd[^n].\n\n[^n]: note\n"
    )
    text = text_of(source)
    for char in "*`~<>[]#{}":
        assert char not in text
    assert text.splitlines()[0] == "Big Title"
    assert "www.example.com" in text
