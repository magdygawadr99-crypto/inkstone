from __future__ import annotations

import html
import re

import pytest

import inkstone.highlight as hl
from inkstone.highlight import (
    HighlightError,
    HtmlFormatter,
    Token,
    get_lexer,
    get_style,
    guess_language,
    highlight,
    list_languages,
    list_styles,
)

from .samples import SAMPLES

CODE = "def greet(name):\n    return f'hi {name}'\n"


def text_of(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def test_public_names_are_exported():
    promised = {
        "highlight",
        "get_lexer",
        "list_languages",
        "guess_language",
        "HtmlFormatter",
        "get_style",
        "list_styles",
        "Token",
        "HighlightError",
    }
    assert promised <= set(hl.__all__)
    for name in hl.__all__:
        assert hasattr(hl, name), name


def test_highlight_wraps_the_code_in_div_pre_code():
    markup = highlight(CODE, "python")
    assert markup.startswith('<div class="highlight"><pre><code>')
    assert markup.endswith("</code></pre></div>")
    assert '<span class="kd">def</span> <span class="nf">greet</span>' in markup
    assert text_of(markup) == CODE


def test_highlight_accepts_aliases_in_any_case():
    assert highlight(CODE, "py") == highlight(CODE, "python")
    assert highlight(CODE, "PY") == highlight(CODE, "python")


@pytest.mark.parametrize("lang", [None, "", "klingon", "text"])
def test_unknown_or_missing_language_gives_escaped_plain_text(lang):
    markup = highlight("if a < b && c:\n    <tag>\n", lang)
    assert markup == (
        '<div class="highlight"><pre><code>'
        "if a &lt; b &amp;&amp; c:\n    &lt;tag&gt;\n"
        "</code></pre></div>"
    )


def test_positional_arguments_follow_the_documented_order():
    by_position = highlight(CODE, "python", "inline", [2], "code", "greet.py", 10)
    by_keyword = highlight(
        CODE,
        "python",
        linenos="inline",
        hl_lines=[2],
        css_class="code",
        filename="greet.py",
        line_start=10,
    )
    assert by_position == by_keyword
    assert by_keyword.startswith(
        '<div class="code"><div class="filename">greet.py</div>'
    )
    assert '<span class="lineno">10 </span>' in by_keyword
    assert '<span class="hll"><span class="lineno">11 </span>' in by_keyword


def test_filename_picks_the_language_when_none_is_given():
    assert '<span class="kd">def</span>' in highlight(CODE, filename="greet.py")
    assert "<span" not in highlight(CODE, filename="greet.unknown")


def test_explicit_language_wins_over_the_filename():
    markup = highlight('{"a": 1}', "json", filename="data.py")
    assert '<span class="nt">&quot;a&quot;</span>' in markup
    assert '<div class="filename">data.py</div>' in markup


def test_linenos_true_gives_a_table():
    markup = highlight(CODE, "python", linenos=True)
    assert '<table class="linenotable">' in markup
    assert '<td class="linenos"><pre>1\n2</pre></td>' in markup


def test_extra_options_reach_the_formatter():
    assert highlight("x = 1", "python", nowrap=True) == (
        '<span class="n">x</span> <span class="o">=</span> <span class="mi">1</span>\n'
    )
    styled = highlight("x = 1", "python", inline_styles=True, style="midnight")
    assert 'style="background-color: #0b0d12; color: #eceff4"' in styled
    with pytest.raises(TypeError):
        highlight("x", "python", no_such_option=True)


def test_bad_option_values_raise_highlight_error():
    with pytest.raises(HighlightError):
        highlight("x", "python", style="nope")
    with pytest.raises(HighlightError):
        highlight("x", "python", hl_lines="one")
    with pytest.raises(HighlightError):
        highlight("x", "python", linenos="sideways")


def test_windows_and_old_mac_line_endings_are_normalised():
    expected = highlight("a = 1\nb = 2\n", "python")
    assert highlight("a = 1\r\nb = 2\r\n", "python") == expected
    assert highlight("a = 1\rb = 2\r", "python") == expected
    assert "\r" not in highlight("a\r\nb", None)


def test_empty_code():
    assert highlight("", "python") == (
        '<div class="highlight"><pre><code></code></pre></div>'
    )


def test_trailing_blank_lines_are_preserved():
    assert text_of(highlight("x\n\n\n", "python")) == "x\n\n\n"
    assert highlight("x\n\n\n", None, linenos=True).count("\n3</pre>") == 1


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_highlighted_samples_keep_their_text(lang):
    for code in SAMPLES[lang]:
        expected = code.replace("\r\n", "\n")
        if expected and not expected.endswith("\n"):
            expected += "\n"
        assert text_of(highlight(code, lang)) == expected


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_highlighted_samples_are_balanced_markup(lang):
    for code in SAMPLES[lang]:
        markup = highlight(code, lang, linenos="inline", hl_lines="1-3")
        assert markup.count("<span") == markup.count("</span>")
        # nothing from the source may survive as a tag
        tags = set(re.findall(r"</?(\w+)", markup))
        assert tags <= {"div", "pre", "code", "span"}


def test_highlight_error_carries_location():
    error = HighlightError("no lexer for language 'x'", path="post.md", line=12)
    assert str(error) == "post.md:12: no lexer for language 'x'"
    assert error.path == "post.md" and error.line == 12


def test_lexer_tokenize_is_lazy_and_yields_pairs():
    stream = get_lexer("python").tokenize("x = 1")
    assert iter(stream) is stream
    ttype, text = next(stream)
    assert ttype is Token.Name and text == "x"


def test_languages_listing_and_guessing_agree_with_get_lexer():
    for name, aliases, _ in list_languages():
        assert get_lexer(name).name == name
        assert all(get_lexer(alias).name == name for alias in aliases)
    assert guess_language(CODE) == "python"
    assert guess_language("whatever", filename="notes.md") == "markdown"


def test_stylesheet_for_a_named_style():
    assert "dusk" in list_styles()
    assert get_style("dusk").dark
    css = HtmlFormatter(style="dusk").get_css(selector=".highlight")
    assert css.startswith(".highlight { background-color: #1e1f2b")
    assert ".highlight .k {" in css
