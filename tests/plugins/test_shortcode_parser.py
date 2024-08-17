from __future__ import annotations

import pytest

from inkstone.errors import ContentError
from inkstone.plugins.builtin._shortcode_parser import Shortcode, parse, scan


MULTI_LINE = {"src": "x.png", "alt": "two words"}


def shortcodes(text):
    return [node for node in parse(text) if isinstance(node, Shortcode)]


def only(text):
    found = shortcodes(text)
    assert len(found) == 1
    return found[0]


def flatten(nodes):
    """Names in document order, with nesting shown by brackets."""
    out = []
    for node in nodes:
        if isinstance(node, Shortcode):
            out.append(node.name)
            if node.inner is not None:
                out.append(flatten(node.inner))
    return out


@pytest.mark.parametrize(
    "source, args, kwargs",
    [
        ("{{< a >}}", [], {}),
        ("{{<a>}}", [], {}),
        ("{{<   a   >}}", [], {}),
        ("{{< a one two >}}", ["one", "two"], {}),
        ('{{< a "one two" three >}}', ["one two", "three"], {}),
        ("{{< a 'single quoted' >}}", ["single quoted"], {}),
        ("{{< a `raw \\n \"text\"` >}}", ['raw \\n "text"'], {}),
        ('{{< a key="value" >}}', [], {"key": "value"}),
        ("{{< a key=value >}}", [], {"key": "value"}),
        ("{{< a key = 'spaced' >}}", [], {"key": "spaced"}),
        ('{{< a pos key="v" other >}}', ["pos", "other"], {"key": "v"}),
        ('{{< a k1="a" k2="b" >}}', [], {"k1": "a", "k2": "b"}),
        ('{{< a key="" >}}', [], {"key": ""}),
        ('{{< a "" >}}', [""], {}),
        ('{{< a "say \\"hi\\"" >}}', ['say "hi"'], {}),
        ('{{< a "back\\\\slash" >}}', ["back\\slash"], {}),
        ('{{< a "line\\nbreak" >}}', ["line\nbreak"], {}),
        ('{{< a "C:\\dir\\file" >}}', ["C:\\dir\\file"], {}),
        ("{{< a https://e.org/?x=1&y=2 >}}", ["https://e.org/?x=1&y=2"], {}),
        ("{{< a 50% >}}", ["50%"], {}),
        ("{{< a a>b >}}", ["a>b"], {}),
        ("{{< a tight>}}", ["tight"], {}),
        ('{{< a data-id="7" aria.lbl="x" >}}', [], {"data-id": "7", "aria.lbl": "x"}),
        ('{{< a key="a=b" >}}', [], {"key": "a=b"}),
        ("{{< a x=1=2 >}}", [], {"x": "1=2"}),
        ('{{< a "{{< not a tag >}}" >}}', ["{{< not a tag >}}"], {}),
        ('{{< a\n  src="x.png"\n  alt="two words"\n>}}', [], MULTI_LINE),
    ],
)
def test_arguments(source, args, kwargs):
    node = only(source)
    assert node.name == "a"
    assert node.args == args
    assert node.kwargs == kwargs
    assert node.inner is None
    assert node.source == source


@pytest.mark.parametrize(
    "name", ["figure", "my-box", "my_box", "h2", "_private", "Note"]
)
def test_names(name):
    assert only(f"{{{{< {name} >}}}}").name == name


def test_text_around_shortcodes_is_kept_verbatim():
    text = "before {{< a >}} middle\n{{< b x >}}after"
    nodes = parse(text)
    assert [n for n in nodes if isinstance(n, str)] == ["before ", " middle\n", "after"]
    assert "".join(n if isinstance(n, str) else n.source for n in nodes) == text


def test_text_without_shortcodes_is_one_piece():
    text = "Plain *Markdown* with {braces} and {{ template }} syntax.\n"
    assert parse(text) == [text]
    assert parse("") == []


def test_paired_shortcode_wraps_its_content():
    node = only("{{< note title=x >}}\nBody *text*\n{{< /note >}}")
    assert node.inner == ["\nBody *text*\n"]
    assert node.kwargs == {"title": "x"}
    assert node.source.endswith("{{< /note >}}")


def test_empty_pair_has_empty_inner_not_none():
    assert only("{{< a >}}{{< /a >}}").inner == []


def test_self_closing_never_takes_content():
    first, second = shortcodes("{{< a />}} text {{< a >}}x{{< /a >}}")
    assert first.inner is None
    assert first.source == "{{< a />}}"
    assert second.inner == ["x"]


def test_self_closing_with_arguments():
    node = only('{{< br clear="all" />}}')
    assert node.kwargs == {"clear": "all"}
    assert node.inner is None


@pytest.mark.parametrize(
    "text, shape",
    [
        ("{{< a >}}{{< b >}}x{{< /b >}}{{< /a >}}", ["a", ["b", []]]),
        ("{{< a >}}{{< a >}}x{{< /a >}}{{< /a >}}", ["a", ["a", []]]),
        ("{{< a >}}{{< b >}}{{< c >}}x{{< /c >}}{{< /a >}}", ["a", ["b", "c", []]]),
        ("{{< a >}}{{< b >}}{{< /a >}}{{< b >}}y{{< /b >}}", ["a", ["b"], "b", []]),
        ("{{< a >}} {{< b />}} {{< /a >}}", ["a", ["b"]]),
        ("{{< a >}}{{< b >}}", ["a", "b"]),
        ("{{% a %}}{{< b >}}x{{< /b >}}{{% /a %}}", ["a", ["b", []]]),
    ],
)
def test_nesting(text, shape):
    assert flatten(parse(text)) == shape


def test_unclosed_shortcode_gives_its_content_back_to_the_parent():
    nodes = parse("{{< a >}}one {{< b >}} two{{< /a >}}")
    outer = nodes[0]
    assert [n if isinstance(n, str) else n.name for n in outer.inner] == [
        "one ",
        "b",
        " two",
    ]
    assert outer.inner[1].inner is None
    assert outer.inner[1].source == "{{< b >}}"


def test_closing_tag_tolerates_spaces():
    assert only("{{< a >}}x{{</a>}}").inner == ["x"]
    assert only("{{< a >}}x{{<  /  a  >}}").inner == ["x"]


def test_markdown_form():
    node = only("{{% note %}}\n*inner*\n{{% /note %}}")
    assert node.markdown is True
    assert node.inner == ["\n*inner*\n"]
    assert only("{{< note >}}x{{< /note >}}").markdown is False
    assert only("{{% toc %}}").inner is None
    assert only('{{% a b="c" /%}}').kwargs == {"b": "c"}


@pytest.mark.parametrize(
    "text",
    [
        "```\n{{< a >}}\n```\n",
        "```html\n{{< a >}}\n```\n",
        "````\n```\n{{< a >}}\n```\n````\n",
        "~~~\n{{< a >}}\n~~~\n",
        "  ```\n  {{< a >}}\n  ```\n",
        "> ```\n> {{< a >}}\n> ```\n",
        "- item\n\n  ```\n  {{< a >}}\n  ```\n",
        "```\n{{< a >}}\nnever closed",
        "inline `{{< a >}}` code",
        "double ``{{< a >}} ` still code`` here",
        "a span that `wraps\n{{< a >}} over` lines",
        "<!-- {{< a >}} -->",
        "<!--\n{{< a >}}\n-->",
        "\\{{< a >}}",
        "\\{{% a %}}",
    ],
)
def test_not_parsed_inside_code_comments_or_when_escaped(text):
    assert parse(text) == [text]


@pytest.mark.parametrize(
    "text, names",
    [
        ("```\ncode\n```\n{{< a >}}", ["a"]),
        ("`code` {{< a >}} `more`", ["a"]),
        ("a lone ` backtick {{< a >}}", ["a"]),
        ("`unclosed span\n\n{{< a >}}", ["a"]),
        ("``` not a fence ``` {{< a >}}", ["a"]),
        ("<!-- c --> {{< a >}}", ["a"]),
        ("<!-- never closed {{< a >}}", ["a"]),
        ("~~~\n{{< x >}}\n~~~\n\n{{< a >}}\n\n```\n{{< y >}}\n```", ["a"]),
        ("```\n{{< x >}}\n``\n```\n{{< a >}}", ["a"]),
    ],
)
def test_parsing_resumes_after_code(text, names):
    assert [node.name for node in shortcodes(text)] == names


def test_escaped_form_prints_the_tag():
    assert parse("{{</* figure src=x */>}}") == ["{{< figure src=x >}}"]
    assert parse("{{%/* note */%}}") == ["{{% note %}}"]
    assert parse("a {{< /* b */ >}} c") == ["a ", "{{< b >}}", " c"]


def test_line_numbers():
    text = "one\n\n{{< a >}}\ntext {{< b >}}\n\n{{< c >}}\nx\n{{< /c >}}\n"
    lines = [(node.name, node.line) for node in shortcodes(text)]
    assert lines == [("a", 3), ("b", 4), ("c", 6)]


def test_line_numbers_count_lines_inside_code():
    text = "```\n1\n2\n```\n{{< a >}}"
    assert only(text).line == 5


@pytest.mark.parametrize(
    "text, line, message",
    [
        ("{{< >}}", 1, "expected a shortcode name"),
        ("{{< 9lives >}}", 1, "expected a shortcode name"),
        ("x\n{{< a", 2, "never closed"),
        ("{{< a b c", 1, "never closed"),
        ("\n\n{{< a {{< b >}}", 3, "'a' is never closed"),
        ('{{< a "open >}}', 1, "unterminated quote"),
        ("{{< a key= >}}", 1, "'key=' has no value"),
        ("{{< a %}}", 1, "ends with '%}}'"),
        ("{{% a >}}", 1, "ends with '>}}'"),
        ("text\n{{< /a >}}", 2, "without an opening"),
        ("{{< a >}}x{{< /b >}}", 1, "closing tag for 'b'"),
        ("{{< a >}}\nx\n{{% /a %}}", 3, "closed with {{% %}}"),
        ("{{< /a b >}}", 1, "takes no arguments"),
        ("{{</* a >}}", 1, "is never closed"),
        ("ok\n\n{{< a >}}{{< /a >}}{{< /a >}}", 3, "without an opening"),
    ],
)
def test_errors_carry_the_line(text, line, message):
    with pytest.raises(ContentError) as caught:
        parse(text)
    assert caught.value.line == line
    assert message in caught.value.message


def test_scan_returns_tags_with_positions():
    text = "ab {{< x 1 >}} cd {{< /x >}}"
    tokens = scan(text)
    tags = [token for token in tokens if not isinstance(token, str)]
    assert [(tag.kind, tag.name) for tag in tags] == [("open", "x"), ("close", "x")]
    assert text[tags[0].start : tags[0].end] == "{{< x 1 >}}"
    assert text[tags[1].start : tags[1].end] == "{{< /x >}}"
    assert scan("{{< y />}}")[0].kind == "self"


def test_long_documents_parse_in_reasonable_time():
    text = ("Some `code` and text.\n\n{{< a k=v >}}\n\n```\n{{< no >}}\n```\n\n") * 2000
    assert len(shortcodes(text)) == 2000
