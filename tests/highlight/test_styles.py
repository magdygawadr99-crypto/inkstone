from __future__ import annotations

import re

import pytest

from inkstone.highlight import (
    HighlightError,
    HtmlFormatter,
    get_style,
    highlight,
    list_styles,
    styles,
)
from inkstone.highlight.styles import (
    DEFAULT_STYLE,
    Style,
    TokenStyle,
    contrast_ratio,
    register_style,
)
from inkstone.highlight.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    String,
    Token,
    css_class,
    styled_types,
)

STYLES = list_styles()


def make_style(rules, name="test"):
    return Style(
        name,
        background="#ffffff",
        foreground="#000000",
        highlight="#ffffcc",
        line_numbers="#999999",
        rules=rules,
    )


def test_builtin_styles():
    assert STYLES == ["dusk", "midnight", "mono", "paper", "parchment"]
    assert DEFAULT_STYLE in STYLES


def test_get_style_is_case_insensitive_and_passes_instances_through():
    assert get_style("Dusk") is get_style("dusk")
    assert get_style(" paper ") is get_style("paper")
    style = make_style({})
    assert get_style(style) is style


@pytest.mark.parametrize("name", ["nope", "", None, 3])
def test_unknown_style(name):
    with pytest.raises(HighlightError, match="no style called"):
        get_style(name)


def test_unknown_style_message_lists_what_exists():
    with pytest.raises(HighlightError, match="dusk, midnight, mono, paper, parchment"):
        get_style("monokai")


@pytest.mark.parametrize("name", STYLES)
def test_light_and_dark(name):
    style = get_style(name)
    assert style.dark == (name in {"dusk", "midnight"})
    # the page colours have to agree with that
    assert contrast_ratio(style.foreground, style.background) >= 7


@pytest.mark.parametrize("name", STYLES)
def test_every_token_colour_is_readable_on_its_background(name):
    style = get_style(name)
    for ttype in styled_types():
        token_style = style.style_for(ttype)
        foreground = token_style.color or style.foreground
        background = token_style.background or style.background
        assert contrast_ratio(foreground, background) >= 4.5, (name, ttype)
        # and still legible on a highlighted line
        if not token_style.background:
            assert contrast_ratio(foreground, style.highlight) >= 3.5, (name, ttype)


@pytest.mark.parametrize("name", STYLES)
def test_chrome_colours_are_visible(name):
    style = get_style(name)
    assert contrast_ratio(style.line_numbers, style.background) >= 3
    assert 1.05 <= contrast_ratio(style.highlight, style.background) <= 2


@pytest.mark.parametrize("name", STYLES)
def test_styles_distinguish_the_basics(name):
    style = get_style(name)
    plain = style.style_for(Token)
    assert plain == TokenStyle()
    for ttype in (Keyword, String, Comment, Name.Function, Generic.Deleted, Error):
        assert style.style_for(ttype) != plain, ttype
    assert style.style_for(Comment).italic
    assert style.style_for(Generic.Strong).bold
    assert style.style_for(Generic.Emph).italic


def test_rule_parsing():
    style = make_style(
        {
            Keyword: "bold #AB1234",
            String: "italic underline bg:#eee #123",
            Comment: "",
        }
    )
    assert style.style_for(Keyword) == TokenStyle(color="#ab1234", bold=True)
    assert style.style_for(String) == TokenStyle(
        color="#112233", background="#eeeeee", italic=True, underline=True
    )
    assert style.style_for(Comment) == TokenStyle()
    assert not style.style_for(Comment)
    assert style.style_for(Keyword)


def test_children_inherit_what_their_rule_leaves_out():
    style = make_style(
        {
            Keyword: "bold italic #111111",
            Keyword.Type: "nobold #222222",
            Keyword.Constant: "noitalic",
            Keyword.Pseudo: "noinherit underline",
        }
    )
    assert style.style_for(Keyword.Type) == TokenStyle(color="#222222", italic=True)
    assert style.style_for(Keyword.Constant) == TokenStyle(color="#111111", bold=True)
    assert style.style_for(Keyword.Pseudo) == TokenStyle(underline=True)
    # no rule of its own: same as the parent
    assert style.style_for(Keyword.Declaration) == style.style_for(Keyword)
    assert style.style_for(Keyword.Type.Deeper) == style.style_for(Keyword.Type)


def test_types_without_any_rule_are_unstyled():
    style = make_style({Keyword: "bold"})
    assert style.style_for(Name.Function) == TokenStyle()
    assert style.style_for(Token) == TokenStyle()


@pytest.mark.parametrize(
    "spec", ["red", "#12", "#12345", "#gggggg", "bg:blue", "bolder", "bg:"]
)
def test_bad_rules_fail_when_the_style_is_defined(spec):
    with pytest.raises(HighlightError, match="not a hex colour"):
        make_style({Keyword: spec})


def test_bad_page_colours_are_rejected():
    with pytest.raises(HighlightError):
        Style(
            "x",
            background="white",
            foreground="#000",
            highlight="#ff0",
            line_numbers="#999",
            rules={},
        )


def test_token_style_css():
    assert TokenStyle().css() == ""
    assert TokenStyle(color="#123456").css() == "color: #123456"
    everything = TokenStyle(
        color="#123456", background="#eeeeee", bold=True, italic=True, underline=True
    )
    assert everything.css() == (
        "color: #123456; background-color: #eeeeee; font-weight: bold; "
        "font-style: italic; text-decoration: underline"
    )


@pytest.mark.parametrize(
    "first, second, expected",
    [
        ("#000000", "#ffffff", 21.0),
        ("#ffffff", "#000000", 21.0),
        ("#fff", "#000", 21.0),
        ("#777777", "#777777", 1.0),
        ("#767676", "#ffffff", 4.54),
    ],
)
def test_contrast_ratio(first, second, expected):
    assert contrast_ratio(first, second) == pytest.approx(expected, abs=0.01)


def test_register_style_makes_it_available_by_name(monkeypatch):
    monkeypatch.setattr(styles, "_styles", dict(styles._styles))
    style = register_style(make_style({Keyword: "bold"}, name="Scratch"))
    assert get_style("scratch") is style
    assert "scratch" in list_styles()
    assert ".k { font-weight: bold }" in HtmlFormatter(style="scratch").get_css()


@pytest.mark.parametrize("name", STYLES)
def test_css_has_a_rule_for_every_styled_class(name):
    style = get_style(name)
    css = HtmlFormatter(style=name).get_css()
    for ttype in styled_types():
        declarations = style.style_for(ttype).css()
        rule = f".highlight .{css_class(ttype)} {{ {declarations} }}"
        assert (rule in css) == bool(declarations), ttype


@pytest.mark.parametrize("name", STYLES)
def test_css_is_well_formed(name):
    css = HtmlFormatter(style=name).get_css()
    assert css.endswith("\n")
    for line in css.splitlines():
        assert re.fullmatch(r"[^{}]+ \{ [^{}]+ \}(?: /\* [\w.]+ \*/)?", line), line
        assert line.startswith(".highlight")
    assert css.count("{") == css.count("}") == len(css.splitlines())


def test_css_block_rules():
    css = HtmlFormatter(style="dusk").get_css(selector=".highlight")
    lines = css.splitlines()
    assert lines[0] == ".highlight { background-color: #1e1f2b; color: #d7d9e4 }"
    assert ".highlight .hll { display: block; background-color: #34364d }" in lines
    assert (
        ".highlight .lineno, .highlight .linenos pre "
        "{ color: #7a7fa3; user-select: none }"
    ) in lines
    assert ".highlight .k { color: #c79bf2 } /* Keyword */" in lines
    assert ".highlight .c { color: #8a90b3; font-style: italic } /* Comment */" in lines


def test_css_child_rules_repeat_inherited_properties():
    # a .kd span carries no .k class, so its rule has to stand alone
    css = HtmlFormatter(style="paper").get_css()
    assert (
        ".highlight .kd { color: #7a3e9d; font-weight: bold } /* Keyword.Declaration */"
        in css
    )


def test_css_selector_variants():
    css = HtmlFormatter(style="paper").get_css(selector="article pre.code")
    assert "article pre.code .k { " in css
    multi = HtmlFormatter(style="paper").get_css(selector=".a, .b")
    assert ".a .k, .b .k { " in multi
    assert multi.startswith(".a, .b { background-color")
    bare = HtmlFormatter(style="paper").get_css(selector="")
    assert bare.startswith("pre { ")
    assert "\n.k { " in bare


def test_css_media_query_wrapper():
    css = HtmlFormatter(style="dusk").get_css(media="(prefers-color-scheme: dark)")
    lines = css.splitlines()
    assert lines[0] == "@media (prefers-color-scheme: dark) {"
    assert lines[-1] == "}"
    assert all(line.startswith("  .highlight") for line in lines[1:-1])


def test_css_class_prefix():
    css = HtmlFormatter(style="paper", class_prefix="hl-").get_css()
    assert ".highlight .hl-k { " in css
    assert ".highlight .hl-hll { " in css
    assert ".highlight .k { " not in css


def test_css_classes_match_the_markup():
    code = "def f(x):\n    return 'a' + 1  # c\n"
    used = set(
        re.findall(r'class="(\w+)"', highlight(code, "python", linenos="inline"))
    )
    css = HtmlFormatter().get_css()
    for name in used - {"highlight", "n"}:
        assert f".highlight .{name}" in css, name
