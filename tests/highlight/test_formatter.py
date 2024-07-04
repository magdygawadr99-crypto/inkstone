from __future__ import annotations

import re

import pytest

from inkstone.highlight import HighlightError, HtmlFormatter, get_lexer
from inkstone.highlight.formatter import escape_html, parse_line_numbers
from inkstone.highlight.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    String,
    Text,
    Token,
    Whitespace,
)

STREAM = [
    (Keyword, "return"),
    (Whitespace, " "),
    (Name, "x"),
    (Whitespace, " "),
    (Operator, "+"),
    (Whitespace, " "),
    (Number.Integer, "1"),
    (Whitespace, "\n"),
]
THREE_LINES = [
    (Name, "a"),
    (Text, "\n"),
    (Name, "b"),
    (Text, "\n"),
    (Name, "c"),
    (Text, "\n"),
]


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        text = text.replace(entity, char)
    return text.replace("&amp;", "&")


def test_default_markup():
    assert HtmlFormatter().format(STREAM) == (
        '<div class="highlight"><pre><code>'
        '<span class="k">return</span> <span class="n">x</span> '
        '<span class="o">+</span> <span class="mi">1</span>\n'
        "</code></pre></div>"
    )


def test_empty_stream():
    assert HtmlFormatter().format([]) == (
        '<div class="highlight"><pre><code></code></pre></div>'
    )
    assert HtmlFormatter(nowrap=True).format([]) == ""
    assert HtmlFormatter(linenos=True).format([]).count("<pre>") == 2


def test_missing_final_newline_is_added():
    html = HtmlFormatter(nowrap=True).format([(Name, "x")])
    assert html == '<span class="n">x</span>\n'


def test_text_and_whitespace_get_no_span():
    stream = [(Text, "plain"), (Whitespace, "  "), (Token, "raw")]
    html = HtmlFormatter(nowrap=True).format(stream)
    assert html == "plain  raw\n"


def test_adjacent_tokens_of_one_type_share_a_span():
    stream = [(String, '"'), (String, "abc"), (String, '"'), (Name, "x"), (Name, "y")]
    html = HtmlFormatter(nowrap=True).format(stream)
    assert html == '<span class="s">&quot;abc&quot;</span><span class="n">xy</span>\n'


def test_types_that_share_a_class_are_merged_too():
    # an unregistered subtype falls back to its parent's class
    stream = [(Name.Function, "a"), (Name.Function.Whatever, "b")]
    assert HtmlFormatter(nowrap=True).format(stream) == '<span class="nf">ab</span>\n'


def test_different_types_are_not_merged():
    html = HtmlFormatter(nowrap=True).format([(Keyword, "a"), (Keyword.Type, "b")])
    assert html == '<span class="k">a</span><span class="kt">b</span>\n'


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a < b", "a &lt; b"),
        ("a > b", "a &gt; b"),
        ("a & b", "a &amp; b"),
        ('say "hi"', "say &quot;hi&quot;"),
        ("it's", "it&#39;s"),
        ("&lt;", "&amp;lt;"),
        ("</code></pre><script>", "&lt;/code&gt;&lt;/pre&gt;&lt;script&gt;"),
        ("plain", "plain"),
    ],
)
def test_escaping(text, expected):
    assert escape_html(text) == expected
    assert HtmlFormatter(nowrap=True).format([(Text, text)]) == expected + "\n"
    assert HtmlFormatter(nowrap=True).format([(Name, text)]) == (
        f'<span class="n">{expected}</span>\n'
    )


def test_multiline_tokens_are_split_so_spans_never_cross_lines():
    stream = [(Comment.Multiline, "/* a\n   b\n*/"), (Text, "\n")]
    assert HtmlFormatter(nowrap=True).format(stream) == (
        '<span class="cm">/* a</span>\n'
        '<span class="cm">   b</span>\n'
        '<span class="cm">*/</span>\n'
    )


def test_blank_lines_are_kept():
    stream = [(Name, "a"), (Text, "\n\n\n"), (Name, "b")]
    html = HtmlFormatter(nowrap=True).format(stream)
    assert html == '<span class="n">a</span>\n\n\n<span class="n">b</span>\n'


def test_carriage_returns_are_dropped():
    assert HtmlFormatter(nowrap=True).format([(Name, "a"), (Text, "\r\n")]) == (
        '<span class="n">a</span>\n'
    )


def test_css_class_option_is_used_and_escaped():
    assert (
        HtmlFormatter(css_class="codehilite")
        .format([])
        .startswith('<div class="codehilite">')
    )
    assert '<div class="a&quot;b">' in HtmlFormatter(css_class='a"b').format([])


def test_class_prefix_applies_to_every_class_but_the_wrapper():
    formatter = HtmlFormatter(class_prefix="hl-", linenos="inline", hl_lines=[1])
    html = formatter.format(STREAM)
    assert '<div class="highlight">' in html
    assert '<span class="hl-k">return</span>' in html
    assert '<span class="hl-hll">' in html
    assert '<span class="hl-lineno">1 </span>' in html


def test_filename_caption():
    html = HtmlFormatter(filename="src/<main>.py").format(STREAM)
    assert html.startswith(
        '<div class="highlight"><div class="filename">src/&lt;main&gt;.py</div><pre>'
    )
    assert "filename" not in HtmlFormatter(filename="").format(STREAM)


def test_nowrap_returns_only_the_lines():
    html = HtmlFormatter(nowrap=True, filename="x.py", linenos="table").format(STREAM)
    assert html.startswith('<span class="k">return</span>')
    assert html.endswith("</span>\n")
    for wrapper in ("<div", "<pre", "<code", "<table", "x.py"):
        assert wrapper not in html


def test_table_line_numbers():
    html = HtmlFormatter(linenos="table").format(THREE_LINES)
    assert html == (
        '<div class="highlight"><table class="linenotable"><tr>'
        '<td class="linenos"><pre>1\n2\n3</pre></td>'
        '<td class="code"><pre><code>'
        '<span class="n">a</span>\n<span class="n">b</span>\n<span class="n">c</span>\n'
        "</code></pre></td></tr></table></div>"
    )


def test_true_means_table_line_numbers():
    assert HtmlFormatter(linenos=True).format(STREAM) == (
        HtmlFormatter(linenos="table").format(STREAM)
    )


def test_inline_line_numbers():
    html = HtmlFormatter(linenos="inline", nowrap=True).format(THREE_LINES)
    assert html.splitlines() == [
        '<span class="lineno">1 </span><span class="n">a</span>',
        '<span class="lineno">2 </span><span class="n">b</span>',
        '<span class="lineno">3 </span><span class="n">c</span>',
    ]


def test_line_numbers_are_right_aligned_to_the_widest():
    stream = [(Text, "x\n" * 11)]
    table = HtmlFormatter(linenos="table", line_start=95).format(stream)
    assert "<pre> 95\n 96\n 97\n 98\n 99\n100\n" in table
    inline = HtmlFormatter(linenos="inline", line_start=95, nowrap=True).format(stream)
    assert inline.startswith('<span class="lineno"> 95 </span>x\n')
    assert '<span class="lineno">105 </span>x\n' in inline


def test_line_start_offsets_the_numbers():
    html = HtmlFormatter(linenos="table", line_start=10).format(THREE_LINES)
    assert "<pre>10\n11\n12</pre>" in html


@pytest.mark.parametrize("bad", ["yes", "tables", 1, 2, ["table"]])
def test_unknown_linenos_mode_is_rejected(bad):
    with pytest.raises(HighlightError, match="linenos"):
        HtmlFormatter(linenos=bad)


def test_highlighted_lines_are_wrapped_with_their_newline():
    html = HtmlFormatter(hl_lines=[2], nowrap=True).format(THREE_LINES)
    assert html == (
        '<span class="n">a</span>\n'
        '<span class="hll"><span class="n">b</span>\n</span>'
        '<span class="n">c</span>\n'
    )


def test_highlighted_lines_count_from_the_top_of_the_block():
    html = HtmlFormatter(hl_lines=[1], line_start=50, linenos="inline", nowrap=True)
    first = html.format(THREE_LINES).splitlines()[0]
    assert first.startswith('<span class="hll"><span class="lineno">50 </span>')


def test_highlighted_lines_outside_the_block_are_ignored():
    html = HtmlFormatter(hl_lines=[0, 7, 99], nowrap=True).format(THREE_LINES)
    assert "hll" not in html


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("", set()),
        (None, set()),
        ((), set()),
        ([3, 1, 3], {1, 3}),
        ({2}, {2}),
        (range(2, 5), {2, 3, 4}),
        ("4", {4}),
        ("1,3", {1, 3}),
        ("1 3", {1, 3}),
        ("2-4", {2, 3, 4}),
        ("1, 3-5  8", {1, 3, 4, 5, 8}),
        ("5 - 6", {5, 6}),
        ("7-7", {7}),
        ("9-8", set()),
        (["2", 3], {2, 3}),
    ],
)
def test_parse_line_numbers(spec, expected):
    assert parse_line_numbers(spec) == expected


@pytest.mark.parametrize("spec", ["a", "1-", "-3", "1-2-3", "1.5", [1, "x"], [None]])
def test_parse_line_numbers_rejects_junk(spec):
    with pytest.raises(HighlightError):
        parse_line_numbers(spec)


def test_hl_lines_accepts_a_range_string():
    html = HtmlFormatter(hl_lines="1-2", nowrap=True).format(THREE_LINES)
    assert html.count('class="hll"') == 2


def test_line_anchors():
    formatter = HtmlFormatter(line_anchors="L", line_start=7, nowrap=True)
    html = formatter.format(THREE_LINES)
    assert html.splitlines()[0] == '<span id="L-7"><span class="n">a</span></span>'
    assert 'id="L-9"' in html


def test_inline_styles_replace_classes():
    html = HtmlFormatter(inline_styles=True, style="paper").format(STREAM)
    assert "class=" not in html.replace('class="highlight"', "")
    assert '<pre style="background-color: #fbfaf7; color: #2a2a2e">' in html
    assert '<span style="color: #7a3e9d; font-weight: bold">return</span>' in html
    # plain names have no rule in this style, so no span at all
    assert " x " in html


def test_inline_styles_for_line_numbers_and_highlights():
    formatter = HtmlFormatter(
        inline_styles=True, linenos="inline", hl_lines=[1], style="dusk"
    )
    html = formatter.format(STREAM)
    assert '<span style="display: block; background-color: #34364d">' in html
    assert '<span style="color: #7a7fa3; user-select: none">1 </span>' in html


def test_unknown_style_is_rejected():
    with pytest.raises(HighlightError, match="no style called 'nope'"):
        HtmlFormatter(style="nope")


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"linenos": "table"},
        {"linenos": "inline"},
        {"hl_lines": [1, 3]},
        {"nowrap": True},
        {"inline_styles": True},
        {"line_anchors": "line", "linenos": "table", "filename": "a.py"},
    ],
)
def test_text_content_survives_formatting(options):
    code = 'def f(x):\n    """Doc <b>."""\n\n    return x & 1 if x > "a" else \'b\'\n'
    html = HtmlFormatter(**options).format(get_lexer("python").tokenize(code))
    if options.get("linenos") == "table":
        html = html.split('<td class="code">')[1]
    text = strip_tags(html)
    if options.get("linenos") == "inline":
        text = "".join(line[2:] for line in text.splitlines(keepends=True))
    assert text == code


def test_format_accepts_a_generator_once():
    formatter = HtmlFormatter(nowrap=True)
    assert formatter.format(pair for pair in STREAM) == formatter.format(STREAM)


def test_formatter_can_be_reused():
    formatter = HtmlFormatter(linenos="inline")
    assert formatter.format(STREAM) == formatter.format(STREAM)
