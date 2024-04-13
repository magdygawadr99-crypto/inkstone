from __future__ import annotations

import pytest

from inkstone.markdown.entities import decode_entity
from inkstone.markdown.inlines import InlineParser
from inkstone.markdown.nodes import Emphasis, Text
from inkstone.markdown.utils import (
    escape_html,
    is_punctuation,
    is_unsafe_url,
    normalize_label,
    normalize_uri,
    parse_attrs,
    parse_line_numbers,
    unescape_string,
    unique_id,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("plain", "plain"),
        ("a < b > c", "a &lt; b &gt; c"),
        ('say "hi" & wave', "say &quot;hi&quot; &amp; wave"),
        ("&amp;", "&amp;amp;"),
        ("it's", "it's"),
        ("", ""),
    ],
)
def test_escape_html(text, expected):
    assert escape_html(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("no escapes", "no escapes"),
        ("\\*star\\*", "*star*"),
        ("back\\\\slash", "back\\slash"),
        ("\\a stays", "\\a stays"),
        ("&amp; &lt; &copy;", "& < ©"),
        ("&#65;&#x42;&#X43;", "ABC"),
        ("&unknown; &amp", "&unknown; &amp"),
        ("\\&amp;", "&amp;"),
        ("trailing\\", "trailing\\"),
    ],
)
def test_unescape_string(text, expected):
    assert unescape_string(text) == expected


@pytest.mark.parametrize(
    "ref, expected",
    [
        ("&amp;", "&"),
        ("&nbsp;", "\u00a0"),
        ("&AElig;", "Æ"),
        ("&ngE;", "≧̸"),
        ("&#35;", "#"),
        ("&#x1F600;", "\U0001f600"),
        ("&#X41;", "A"),
        ("&#0;", "\ufffd"),
        ("&#xD800;", "\ufffd"),
        ("&#1114112;", "\ufffd"),
        ("&nope;", None),
        ("&AMP;", "&"),
        ("&Amp;", None),
    ],
)
def test_decode_entity(ref, expected):
    assert decode_entity(ref) == expected


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("/plain/path.html", "/plain/path.html"),
        ("/with space", "/with%20space"),
        ("/already%20encoded", "/already%20encoded"),
        ("/100%", "/100%25"),
        ("/100%zz", "/100%25zz"),
        ("/ünï", "/%C3%BCn%C3%AF"),
        ("http://example.com/?a=1&b=2#frag", "http://example.com/?a=1&b=2#frag"),
        ('/quote"here', "/quote%22here"),
        ("/back\\slash", "/back%5Cslash"),
        ("/[brackets]", "/%5Bbrackets%5D"),
        ("/a`b", "/a%60b"),
        ("mailto:a+b@c.d", "mailto:a+b@c.d"),
        ("/(parens)*~!'", "/(parens)*~!'"),
        ("", ""),
    ],
)
def test_normalize_uri(uri, expected):
    assert normalize_uri(uri) == expected


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Foo", "foo"),
        ("  Foo   Bar  ", "foo bar"),
        ("Foo\n  bar", "foo bar"),
        ("ΑΓΩ", "αγω"),
        ("ẞ", "ss"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_label(label, expected):
    assert normalize_label(label) == expected


@pytest.mark.parametrize(
    "char", list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~") + ["«", "\u2014", "€", "£"]
)
def test_is_punctuation(char):
    assert is_punctuation(char)


@pytest.mark.parametrize("char", ["a", "Z", "0", " ", "\n", "é", "я", "中"])
def test_is_not_punctuation(char):
    assert not is_punctuation(char)


@pytest.mark.parametrize(
    "url, image, unsafe",
    [
        ("javascript:alert(1)", False, True),
        ("  JavaScript:alert(1)", False, True),
        ("vbscript:x", False, True),
        ("file:///etc/passwd", False, True),
        ("data:text/html,x", False, True),
        ("data:image/png;base64,AAAA", False, True),
        ("data:image/png;base64,AAAA", True, False),
        ("data:image/svg+xml,AAAA", True, True),
        ("javascript:alert(1)", True, True),
        ("http://example.com", False, False),
        ("/javascript:", False, False),
        ("", False, False),
    ],
)
def test_is_unsafe_url(url, image, unsafe):
    assert is_unsafe_url(url, image=image) is unsafe


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#id", {"id": "id"}),
        (".a .b", {"class": "a b"}),
        (".a.b#c", {"id": "c", "class": "a b"}),
        ("key=value", {"key": "value"}),
        ('key="two words"', {"key": "two words"}),
        ("key='single quoted'", {"key": "single quoted"}),
        ("flag", {"flag": True}),
        ("empty=", {"empty": ""}),
        (
            '#id .cls k=v flag data-x="1"',
            {"id": "id", "class": "cls", "k": "v", "flag": True, "data-x": "1"},
        ),
        ("class=x .y", {"class": "x y"}),
        ("id=explicit", {"id": "explicit"}),
        ("#first #second", {"id": "second"}),
        ("  padded  ", {"padded": True}),
        ("", {}),
    ],
)
def test_parse_attrs(text, expected):
    assert parse_attrs(text) == expected


@pytest.mark.parametrize(
    "text",
    ['key="unterminated', "{nested}", "a = b", '"quoted"', "=x", "a<b=1", "1st=x"],
)
def test_parse_attrs_rejects_what_is_not_an_attribute_list(text):
    assert parse_attrs(text) is None


def test_parse_attrs_puts_id_and_class_first():
    assert list(parse_attrs("z=1 .c a=2 #i")) == ["id", "class", "z", "a"]


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("1", {1}),
        ("1 3", {1, 3}),
        ("1,3", {1, 3}),
        ("2-4", {2, 3, 4}),
        ("1 3-5, 9", {1, 3, 4, 5, 9}),
        ("x 2 y-z", {2}),
        ("5-3", set()),
        ("", set()),
        (None, set()),
        (True, set()),
    ],
)
def test_parse_line_numbers(spec, expected):
    assert parse_line_numbers(spec) == expected


def test_unique_id():
    seen: dict = {}
    assert [unique_id("a", seen) for _ in range(3)] == ["a", "a-1", "a-2"]
    assert unique_id("a-1", seen) == "a-1-1"
    assert unique_id("b", seen) == "b"
    assert unique_id("a", seen) == "a-3"


def test_inline_parser_on_its_own():
    nodes = InlineParser().parse("plain *emphasis* text")
    assert [type(node) for node in nodes] == [Text, Emphasis, Text]
    assert nodes[1].children[0].literal == "emphasis"
    assert nodes[1].children[0].parent is nodes[1]
    assert InlineParser().parse("") == []


def test_inline_parser_without_a_document_knows_no_references():
    nodes = InlineParser().parse("[ref] and [^note]")
    assert [type(node) for node in nodes] == [Text]
    assert nodes[0].literal == "[ref] and [^note]"


def test_smart_dash_runs():
    en, em = "\u2013", "\u2014"
    parser = InlineParser(smart=True)
    (node,) = parser.parse("a - b -- c --- d ---- e ----- f ------ g ------- h")
    assert node.literal == (
        f"a - b {en} c {em} d {en}{en} e {em}{en} f {em}{em} g {em}{en}{en} h"
    )


def test_parse_reference_reports_how_much_it_consumed():
    parser = InlineParser()
    refs: dict = {}
    text = '[a]: /url "title"\nrest'
    assert parser.parse_reference(text, refs) == len('[a]: /url "title"\n')
    assert refs["a"].dest == "/url" and refs["a"].title == "title"
    assert parser.parse_reference("[b]: /url trailing junk", refs) == 0
    assert parser.parse_reference("not a reference", refs) == 0
    assert parser.parse_reference("[ ]: /url", refs) == 0
    assert list(refs) == ["a"]
