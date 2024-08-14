from __future__ import annotations

import pytest

from inkstone.highlight.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)

from .helpers import type_of, types_of, visible


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("<p>hi</p>", "p", Name.Tag),
        ("<p>hi</p>", "hi", Text),
        ('<a href="x.html">y</a>', "href", Name.Attribute),
        ('<a href="x.html">y</a>', '"x.html"', String),
        ("<a href=x.html>y</a>", "x.html", String),
        ("<a href='x'>y</a>", "'x'", String),
        ("<input disabled>", "disabled", Name.Attribute),
        ("<br/>", "/>", Punctuation),
        ("<!DOCTYPE html>", "<!DOCTYPE html>", Comment.Preproc),
        ("<!-- a\nb -->x", "<!-- a\nb -->", Comment.Multiline),
        ("a &amp; b", "&amp;", Name.Entity),
        ("a &#169; b", "&#169;", Name.Entity),
        ("a &#x1F600; b", "&#x1F600;", Name.Entity),
        ("<DIV CLASS=a>", "DIV", Name.Tag),
        ("<my-widget x-data='1'>", "my-widget", Name.Tag),
        ("<p @click='go' :id='x'>", "@click", Name.Attribute),
    ],
)
def test_html_tokens(code, text, expected):
    assert type_of("html", code, text) is expected


def test_html_stray_angle_brackets_and_ampersands_are_text():
    tokens = visible("html", "<p>a < b && c > d</p>")
    assert not [t for t in tokens if t[0] is Error]
    assert types_of("html", "<p>a < b && c > d</p>", "p") == [Name.Tag, Name.Tag]
    assert (Name.Tag, "b") not in tokens


def test_html_script_content_is_javascript():
    code = '<script type="module">\nconst x = `<b>${y}</b>`;\n</script><p>'
    assert type_of("html", code, "const") is Keyword.Declaration
    assert type_of("html", code, "${") is String.Interpol
    assert types_of("html", code, "script") == [Name.Tag, Name.Tag]
    assert type_of("html", code, "p") is Name.Tag


def test_html_closing_tag_inside_a_script_string_still_ends_it():
    # same as browsers: the first </script> wins, string or not
    code = '<script>x = "</script>";'
    assert types_of("html", code, "script") == [Name.Tag, Name.Tag]


def test_html_style_content_is_css():
    code = "<style>\n.card > a:hover { color: #fff; margin: 0 2px }\n</style>"
    assert type_of("html", code, ".card") is Name.Class
    assert type_of("html", code, "color") is Name.Property
    assert type_of("html", code, "#fff") is Number.Hex
    assert type_of("html", code, "px") is Keyword.Type
    assert types_of("html", code, "style") == [Name.Tag, Name.Tag]


def test_html_unclosed_script_takes_the_rest_of_the_document():
    code = "<script>\nlet a = 1;\n<p>not html</p>"
    assert type_of("html", code, "let") is Keyword.Declaration
    assert (Name.Tag, "p") not in visible("html", code)


def test_html_inline_style_and_event_attributes_are_delegated():
    code = "<p style=\"color: red; margin: 0\" onclick='go(1)'>x</p>"
    assert types_of("html", code, "color") == [Name.Property]
    assert type_of("html", code, "red") is Name.Constant
    assert type_of("html", code, "style") is Name.Attribute
    assert type_of("html", code, "go") is Name
    assert type_of("html", code, "1") is Number.Integer


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ('<?xml version="1.0"?><a/>', "<?xml", Comment.Preproc),
        ('<?xml version="1.0"?><a/>', "version", Name.Attribute),
        ('<?xml version="1.0"?><a/>', '"1.0"', String),
        ('<?xml version="1.0"?><a/>', "?>", Comment.Preproc),
        ("<atom:link href='x'/>", "atom", Name.Namespace),
        ("<atom:link href='x'/>", "link", Name.Tag),
        ("<a xmlns:xsi='u'/>", "xmlns:xsi", Name.Attribute),
        ("<a><![CDATA[<b> & ]]></a>", "<![CDATA[", Comment.Preproc),
        ("<a><![CDATA[<b> & ]]></a>", "<b> & ", String),
        ("<a>&lt;&#x263A;</a>", "&lt;&#x263A;", Name.Entity),
        ("<a><!-- c --></a>", "<!-- c -->", Comment.Multiline),
        ("<Résumé/>", "Résumé", Name.Tag),
    ],
)
def test_xml_tokens(code, text, expected):
    assert type_of("xml", code, text) is expected


def test_xml_doctype_with_internal_subset_is_one_token():
    code = '<!DOCTYPE note [\n  <!ENTITY w "x">\n]>\n<note/>'
    assert visible("xml", code)[0] == (
        Comment.Preproc,
        '<!DOCTYPE note [\n  <!ENTITY w "x">\n]>',
    )


def test_xml_does_not_treat_script_specially():
    assert type_of("xml", "<script>let x</script>", "let x") is Text


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("a { color: red }", "a", Name.Tag),
        ("a { color: red }", "color", Name.Property),
        ("a { color: red }", "red", Name.Constant),
        (".btn-primary { }", ".btn-primary", Name.Class),
        ("#main { }", "#main", Name.Constant),
        ("a:hover::before { }", ":hover::before", Name.Decorator),
        ("li:nth-child(2n+1) { }", "2n+1", Number),
        ('a[href^="http"] { }', "href", Name.Attribute),
        ('a[href^="http"] { }', "^=", Operator),
        ('a[href^="http"] { }', '"http"', String),
        ("a > b + c ~ d { }", ">", Operator),
        ("* { margin: 0 }", "*", Name.Tag),
        ("a { width: 1.5em }", "1.5", Number.Float),
        ("a { width: 1.5em }", "em", Keyword.Type),
        ("a { width: 50% }", "%", Keyword.Type),
        ("a { margin: -2px }", "-2", Number.Integer),
        ("a { color: #FFAA00 }", "#FFAA00", Number.Hex),
        ("a { color: rgb(0, 0, 0) }", "rgb", Name.Function),
        ("a { display: flex }", "flex", Keyword.Constant),
        ("a { top: 0 !important }", "!important", Keyword),
        ("a { --gap: 2px; x: var(--gap) }", "--gap", Name.Variable),
        ("a { font: 12px 'My Font' }", "'My Font'", String),
        ("a { background: url(a/b.png) }", "a/b.png", String.Other),
        ("/* c */ a { }", "/* c */", Comment.Multiline),
        ("@media screen { a { } }", "@media", Keyword),
        ("@media (min-width: 10px) { }", "min-width", Name.Property),
        ("@media a and b { }", "and", Operator.Word),
        ("@page :first { margin: 1in }", ":first", Name.Decorator),
        ('@import "x.css";', '"x.css"', String),
        ("A { COLOR: RED }", "RED", Name.Constant),
    ],
)
def test_css_tokens(code, text, expected):
    assert type_of("css", code, text) is expected


def test_css_nested_rule_versus_declaration():
    code = (
        ".card {\n  color: blue;\n  a:hover { color: red }\n  &.on { top: 0 }\n}\n"
        "b { }"
    )
    assert types_of("css", code, "color") == [Name.Property, Name.Property]
    assert type_of("css", code, "a") is Name.Tag
    assert type_of("css", code, ":hover") is Name.Decorator
    assert type_of("css", code, "&") is Name.Tag
    assert type_of("css", code, "b") is Name.Tag


def test_css_rules_inside_media_queries():
    code = "@media print { .a { color: red } }\n.b { }"
    assert type_of("css", code, ".a") is Name.Class
    assert type_of("css", code, "color") is Name.Property
    assert type_of("css", code, ".b") is Name.Class


def test_css_braces_in_strings_do_not_end_a_declaration():
    code = 'a { content: "}{;"; color: red }'
    assert type_of("css", code, '"}{;"') is String
    assert types_of("css", code, "content") == [Name.Property]
    assert type_of("css", code, "red") is Name.Constant


def test_css_keyframes():
    code = "@keyframes spin { from { opacity: 0 } 50% { opacity: .5 } }"
    assert type_of("css", code, "spin") is Name
    assert type_of("css", code, "from") is Name.Tag
    assert type_of("css", code, "50%") is Number
    assert type_of("css", code, ".5") is Number.Float


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("# Title\n", "# Title", Generic.Heading),
        ("## Section\n", "## Section", Generic.Subheading),
        ("#hashtag\n", "#hashtag", Text),
        ("Title\n=====\n", "Title", Generic.Heading),
        ("Title\n-----\n", "Title", Generic.Subheading),
        ("some *emphasis* here", "*emphasis*", Generic.Emph),
        ("some _emphasis_ here", "_emphasis_", Generic.Emph),
        ("some **strong** here", "**strong**", Generic.Strong),
        ("some __strong__ here", "__strong__", Generic.Strong),
        ("some ***both*** here", "***both***", Generic.Strong),
        ("some ~~gone~~ here", "~~gone~~", Generic.Deleted),
        ("call `foo()` now", "`foo()`", String.Backtick),
        ("a ``b ` c`` d", "``b ` c``", String.Backtick),
        ("> quoted", "> ", Keyword),
        ("- item", "-", Keyword),
        ("12. item", "12.", Keyword),
        ("- [x] done", "[x]", Keyword),
        ("see [docs](http://x.y/z)", "docs", Name.Tag),
        ("see [docs](http://x.y/z)", "http://x.y/z", Name.Attribute),
        ('see [docs](x.html "The Docs")', '"The Docs"', String),
        ("![alt text](img.png)", "alt text", Name.Tag),
        ("see [docs][ref]", "ref", Name.Label),
        ("[ref]: http://x.y\n", "[ref]", Name.Label),
        ("[ref]: http://x.y\n", "http://x.y", Name.Attribute),
        ("note[^1]", "[^1]", Name.Label),
        ("<https://x.y>", "https://x.y", Name.Attribute),
        ("go to https://x.y/z.", "https://x.y/z", Name.Attribute),
        ("AT&amp;T", "&amp;", Name.Entity),
        ("\\*not em\\*", "\\*", String.Escape),
        ("a <!-- c --> b", "<!-- c -->", Comment.Multiline),
        ("line<br/>break", "br", Name.Tag),
        ("* * *\n", "* * *", Punctuation),
        ("---\n", "---", Punctuation),
        ("|---|:-:|\n", "|---|:-:|", Punctuation),
    ],
)
def test_markdown_tokens(code, text, expected):
    assert type_of("markdown", code, text) is expected


@pytest.mark.parametrize(
    "code",
    ["snake_case_name", "2 * 3 * 4", "a * b", "x_ y_", "5 ~ 6 ~ 7", "a ** b"],
)
def test_markdown_lookalikes_are_not_emphasis(code):
    kinds = {ttype for ttype, _ in visible("markdown", code)}
    assert not kinds & {Generic.Emph, Generic.Strong, Generic.Deleted}


def test_markdown_fenced_code_is_lexed_in_its_language():
    code = "```python\ndef f():\n    pass\n```\nafter *this*\n"
    tokens = visible("markdown", code)
    assert tokens[:2] == [(String.Backtick, "```"), (Name.Label, "python")]
    assert (Keyword.Declaration, "def") in tokens
    assert (Name.Function, "f") in tokens
    assert tokens.count((String.Backtick, "```")) == 2
    assert tokens[-1] == (Generic.Emph, "*this*")


def test_markdown_fence_with_unknown_language_is_a_plain_string():
    tokens = visible("markdown", "~~~ nosuchlang\n# not a heading\n~~~\n")
    assert tokens == [
        (String.Backtick, "~~~"),
        (Name.Label, "nosuchlang"),
        (String, "# not a heading\n"),
        (String.Backtick, "~~~"),
    ]


def test_markdown_fence_attributes_and_alias():
    tokens = visible("markdown", '```js {hl_lines="1"}\nlet x;\n```\n')
    assert (Name.Attribute, '{hl_lines="1"}') in tokens
    assert (Keyword.Declaration, "let") in tokens


def test_markdown_longer_fence_contains_shorter_ones():
    code = "````md\n```\ninner\n```\n````\n# after\n"
    tokens = visible("markdown", code)
    assert tokens[0] == (String.Backtick, "````")
    assert tokens[-2:] == [(String.Backtick, "````"), (Generic.Heading, "# after")]


def test_markdown_unclosed_fence_runs_to_the_end():
    tokens = visible("markdown", "```\n# code\n*code*")
    assert tokens == [(String.Backtick, "```"), (String, "# code\n*code*")]


def test_markdown_yaml_front_matter():
    code = "---\ntitle: Hello\ndraft: true\n---\n\n# Body\n"
    tokens = visible("markdown", code)
    assert tokens[0] == (Name.Namespace, "---\n")
    assert (Name.Tag, "title") in tokens
    assert (Keyword.Constant, "true") in tokens
    assert tokens[-1] == (Generic.Heading, "# Body")


def test_markdown_toml_front_matter():
    tokens = visible("markdown", '+++\ntitle = "Hello"\n+++\ntext\n')
    assert (Name.Attribute, "title") in tokens
    assert (String, '"Hello"') in tokens
    assert tokens[-1] == (Text, "text")


def test_markdown_rule_in_the_middle_is_not_front_matter():
    tokens = visible("markdown", "intro\n\n---\n\nkey: value\n")
    assert (Punctuation, "---") in tokens
    assert not [t for t in tokens if t[0] is Name.Tag]


def test_markdown_indented_fence_inside_a_list_item():
    code = "1. item\n\n   ```sh\n   echo hi\n   ```\n\nafter\n"
    tokens = visible("markdown", code)
    assert tokens.count((String.Backtick, "```")) == 2
    assert (Name.Label, "sh") in tokens
    assert (Name.Builtin, "echo") in tokens
    assert tokens[-1] == (Text, "after")
