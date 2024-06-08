from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from inkstone.errors import InkstoneError
from inkstone.feeds import FeedError, XmlWriter
from inkstone.feeds.xmlwriter import escape_attr, escape_text, strip_illegal

DECLARATION = '<?xml version="1.0" encoding="utf-8"?>\n'


def document(build, **options) -> str:
    writer = XmlWriter(**options)
    build(writer)
    return writer.getvalue()


def roundtrip_text(text: str) -> str:
    xml = document(lambda w: w.element("root", text))
    return ET.fromstring(xml).text or ""


def test_feed_error_is_an_inkstone_error():
    assert issubclass(FeedError, InkstoneError)


def test_simple_document():
    w = XmlWriter()
    w.start("greeting", {"lang": "en"})
    w.text("hello")
    w.end("greeting")
    assert w.getvalue() == DECLARATION + '<greeting lang="en">hello</greeting>\n'


def test_declaration_can_be_left_out():
    assert document(lambda w: w.element("a"), declaration=False) == "<a/>\n"


def test_output_parses_as_utf8_bytes():
    xml = document(lambda w: w.element("a", "Crème brûlée 日本語 \U0001f600"))
    assert ET.fromstring(xml.encode("utf-8")).text == "Crème brûlée 日本語 \U0001f600"


def test_empty_elements_are_self_closing():
    def build(w):
        with w.start("root"):
            w.element("empty")
            w.element("blank", "")
            w.element("attrs", attrs={"a": "1"})
            w.start("manual")
            w.end()

    assert document(build, declaration=False) == (
        '<root><empty/><blank/><attrs a="1"/><manual/></root>\n'
    )


def test_element_stringifies_values():
    def build(w):
        with w.start("root"):
            w.element("n", 0)
            w.element("f", 1.5, {"count": 3, "ok": True, "no": False, "skip": None})

    root = ET.fromstring(document(build))
    assert root.find("n").text == "0"
    assert root.find("f").text == "1.5"
    assert root.find("f").attrib == {"count": "3", "ok": "true", "no": "false"}


@pytest.mark.parametrize(
    "text",
    [
        "a < b && c > d",
        "]]> is fine in text once > is escaped",
        "&amp; stays a literal entity reference",
        "<script>alert('x')</script>",
        "quotes \" and ' need nothing",
        "line one\nline two\ttabbed",
        "carriage\rreturn and CRLF\r\n",
        "Crème brûlée, 日本語, \U0001f600",
        "  leading and trailing space  ",
    ],
)
def test_text_survives_a_round_trip(text):
    assert roundtrip_text(text) == text


@pytest.mark.parametrize(
    "value",
    [
        'say "hi" & <wave>',
        "it's",
        "line one\nline two",
        "tab\tseparated",
        "carriage\rreturn",
        "https://example.com/?a=1&b=2",
        "]]>",
        "日本語 \U0001f600",
    ],
)
def test_attribute_values_survive_a_round_trip(value):
    xml = document(lambda w: w.element("root", attrs={"value": value}))
    assert ET.fromstring(xml).get("value") == value


def test_escaping_functions():
    assert escape_text('<a href="x">&</a>') == '&lt;a href="x"&gt;&amp;&lt;/a&gt;'
    assert (
        escape_attr('<a href="x">&</a>')
        == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
    )
    assert escape_text("a\rb") == "a&#13;b"
    assert escape_attr("a\nb\tc") == "a&#10;b&#9;c"


@pytest.mark.parametrize(
    "char",
    [
        "\x00",
        "\x01",
        "\x08",
        "\x0b",
        "\x0c",
        "\x1f",
        "\ufffe",
        "\uffff",
        "\ud800",
        "\udfff",
    ],
)
def test_characters_illegal_in_xml_are_stripped(char):
    assert strip_illegal(f"a{char}b") == "ab"

    def build(w):
        with w.start("root", {"attr": f"a{char}b"}):
            w.element("text", f"a{char}b")
            with w.start("cdata"):
                w.cdata(f"a{char}b")
            w.comment(f"a{char}b")

    xml = document(build)
    assert char not in xml
    root = ET.fromstring(xml.encode("utf-8", "strict"))
    assert root.get("attr") == root.find("text").text == root.find("cdata").text == "ab"


@pytest.mark.parametrize(
    "char", ["\t", "\n", " ", "\x7f", "\x85", "\u2028", "\ufffd", "\U0001f600"]
)
def test_legal_but_unusual_characters_are_kept(char):
    assert strip_illegal(f"a{char}b") == f"a{char}b"
    assert roundtrip_text(f"a{char}b") == f"a{char}b"


def test_cdata_is_written_verbatim():
    def build(w):
        with w.start("root"):
            w.cdata("<p>Fish &amp; chips</p>")

    xml = document(build, declaration=False)
    assert xml == "<root><![CDATA[<p>Fish &amp; chips</p>]]></root>\n"
    assert ET.fromstring(xml).text == "<p>Fish &amp; chips</p>"


@pytest.mark.parametrize(
    "text",
    [
        "a ]]> b",
        "]]>",
        "]]>]]>",
        "ends with ]]",
        "]]]]>>",
        "if (a[b[0]]>1) { x &&= y; }",
        "<![CDATA[nested]]>",
        "",
    ],
)
def test_cdata_end_marker_inside_cdata(text):
    def build(w):
        with w.start("root"):
            w.cdata(text)

    assert (ET.fromstring(document(build)).text or "") == text


@pytest.mark.parametrize(
    "text", ["plain", "double -- dash", "---", "ends with -", "a--b--c", "-->", ""]
)
def test_comments_stay_well_formed(text):
    def build(w):
        w.comment(text)
        with w.start("root"):
            w.comment(text)
            w.element("child")

    xml = document(build)
    root = ET.fromstring(xml)
    assert [child.tag for child in root] == ["child"]
    assert xml.count("<!--") == 2


def test_comment_text_is_written_as_is_when_harmless():
    xml = document(
        lambda w: (w.comment(" generated <by> inkstone & co "), w.element("a"))
    )
    assert "<!-- generated <by> inkstone & co -->" in xml


def test_namespaces_are_declared_on_the_element():
    def build(w):
        namespaces = {"": "urn:default", "x": "urn:x"}
        with w.start("root", {"id": "1"}, namespaces=namespaces):
            w.element("x:child", "text", {"x:flag": "yes"})

    xml = document(build, declaration=False)
    assert xml == (
        '<root xmlns="urn:default" xmlns:x="urn:x" id="1">'
        '<x:child x:flag="yes">text</x:child></root>\n'
    )
    root = ET.fromstring(xml)
    assert root.tag == "{urn:default}root"
    child = root.find("{urn:x}child")
    assert child.get("{urn:x}flag") == "yes"


def test_prefix_declared_on_an_ancestor_is_in_scope():
    def build(w):
        with w.start("a", namespaces={"x": "urn:x"}), w.start("b"), w.start("c"):
            w.element("x:deep")

    assert ET.fromstring(document(build)).find(".//{urn:x}deep") is not None


def test_prefix_declared_through_a_plain_attribute_counts():
    xml = document(lambda w: w.element("x:a", attrs={"xmlns:x": "urn:x"}))
    assert ET.fromstring(xml).tag == "{urn:x}a"


def test_xml_prefix_needs_no_declaration():
    xml = document(lambda w: w.element("a", attrs={"xml:lang": "en"}))
    assert ET.fromstring(xml).get("{http://www.w3.org/XML/1998/namespace}lang") == "en"


def test_undeclared_element_prefix_is_an_error():
    w = XmlWriter()
    with pytest.raises(FeedError, match="prefix 'atom'"):
        w.start("atom:link")


def test_undeclared_attribute_prefix_is_an_error():
    w = XmlWriter()
    with pytest.raises(FeedError, match="prefix 'x'"):
        w.start("a", {"x:b": "1"})


def test_prefix_declared_on_a_sibling_is_out_of_scope():
    w = XmlWriter()
    w.start("root")
    w.element("x:a", namespaces={"x": "urn:x"})
    with pytest.raises(FeedError, match="not declared"):
        w.element("x:b")


def test_declaring_a_namespace_twice_is_an_error():
    w = XmlWriter()
    with pytest.raises(FeedError, match="twice"):
        w.start("a", {"xmlns:x": "urn:one"}, namespaces={"x": "urn:two"})


@pytest.mark.parametrize(
    "name", ["", "1abc", "a b", "<x>", "a:b:c", "-a", ":a", "a:", "a>b"]
)
def test_invalid_names_are_refused(name):
    with pytest.raises(FeedError, match="not a valid XML"):
        XmlWriter().start(name)
    with pytest.raises(FeedError, match="not a valid XML"):
        XmlWriter().start("ok", {name: "value"})


@pytest.mark.parametrize("name", ["a", "_a", "a-b", "a.b", "a1", "ns:tag", "été"])
def test_valid_names_are_accepted(name):
    namespaces = {"ns": "urn:ns"} if ":" in name else None
    xml = document(lambda w: w.element(name, namespaces=namespaces))
    ET.fromstring(xml.encode("utf-8"))


def test_end_without_start_is_an_error():
    with pytest.raises(FeedError, match="without an open element"):
        XmlWriter().end()


def test_mismatched_end_tag_is_an_error():
    w = XmlWriter()
    w.start("a")
    w.start("b")
    with pytest.raises(FeedError, match="</a> does not match <b>"):
        w.end("a")


def test_second_root_is_an_error():
    w = XmlWriter()
    w.element("a")
    with pytest.raises(FeedError, match="second root"):
        w.start("b")


def test_text_outside_the_root_is_an_error():
    with pytest.raises(FeedError, match="outside"):
        XmlWriter().text("stray")
    w = XmlWriter()
    w.element("a")
    with pytest.raises(FeedError, match="outside"):
        w.cdata("stray")


def test_unclosed_element_is_an_error():
    w = XmlWriter()
    w.start("a")
    w.start("b")
    w.end()
    with pytest.raises(FeedError, match="<a> was never closed"):
        w.getvalue()


def test_document_without_a_root_is_an_error():
    w = XmlWriter()
    w.comment("nothing here")
    with pytest.raises(FeedError, match="no root"):
        w.getvalue()


def test_with_block_closes_the_element():
    w = XmlWriter(declaration=False)
    with w.start("a") as inner:
        assert inner is w
        assert w.depth == 1
        with w.start("b"):
            assert w.depth == 2
    assert w.depth == 0
    assert w.getvalue() == "<a><b/></a>\n"


def test_with_block_does_not_hide_an_exception():
    w = XmlWriter()
    with pytest.raises(RuntimeError, match="boom"):
        with w.start("a"):
            w.start("b")
            raise RuntimeError("boom")
    assert w.depth == 2


def test_none_text_is_ignored():
    def build(w):
        with w.start("a"):
            w.text(None)
            w.text("")

    assert document(build, declaration=False) == "<a/>\n"


def test_pretty_printing_indents_element_content():
    def build(w):
        with w.start("feed"):
            w.element("title", "Hello")
            with w.start("entry"):
                w.element("id", "1")
                w.element("link", attrs={"href": "/"})
            w.comment("done")

    assert document(build, pretty=True) == (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<feed>\n"
        "  <title>Hello</title>\n"
        "  <entry>\n"
        "    <id>1</id>\n"
        '    <link href="/"/>\n'
        "  </entry>\n"
        "  <!--done-->\n"
        "</feed>\n"
    )


def test_pretty_printing_with_another_indent():
    def build(w):
        with w.start("a"), w.start("b"):
            w.element("c")

    xml = document(build, pretty=True, indent="\t", declaration=False)
    assert xml == "<a>\n\t<b>\n\t\t<c/>\n\t</b>\n</a>\n"


def test_pretty_printing_never_touches_text():
    def build(w):
        with w.start("p"):
            w.text("  some ")
            w.element("b", "bold")
            w.text(" text\n")
            w.cdata("raw")

    pretty = document(build, pretty=True, declaration=False)
    assert pretty == "<p>  some <b>bold</b> text\n<![CDATA[raw]]></p>\n"
    assert pretty == document(build, declaration=False)


def test_pretty_and_compact_output_are_the_same_document():
    def build(w):
        with w.start("root", {"a": "1"}):
            for n in range(3):
                with w.start("item", {"n": n}):
                    w.element("name", f"item {n}")
                    w.element("empty")

    def shape(element):
        children = [shape(child) for child in element]
        return (element.tag, element.attrib, (element.text or "").strip(), children)

    pretty = ET.fromstring(document(build, pretty=True))
    compact = ET.fromstring(document(build))
    assert shape(pretty) == shape(compact)


def test_processing_instruction_before_the_root():
    def build(w):
        w.pi("xml-stylesheet", 'type="text/xsl" href="/feed.xsl"')
        w.element("a")

    xml = document(build, pretty=True)
    assert xml.splitlines()[1] == '<?xml-stylesheet type="text/xsl" href="/feed.xsl"?>'
    ET.fromstring(xml)


@pytest.mark.parametrize(
    ("href", "kind"),
    [("/feed.xsl", "text/xsl"), ("/style.CSS", "text/css"), ("/a?b=1&c=2", "text/xsl")],
)
def test_stylesheet_instruction(href, kind):
    w = XmlWriter(pretty=True)
    w.stylesheet(href)
    w.element("a")
    line = w.getvalue().splitlines()[1]
    assert line.startswith(f'<?xml-stylesheet type="{kind}" href="')
    assert "&amp;" in line or "&" not in href
    ET.fromstring(w.getvalue())


@pytest.mark.parametrize(
    ("target", "data"),
    [("xml", ""), ("XML", "x"), ("a:b", ""), ("1x", ""), ("ok", "oops ?> more")],
)
def test_bad_processing_instructions_are_refused(target, data):
    with pytest.raises(FeedError):
        XmlWriter().pi(target, data)
