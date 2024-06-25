from __future__ import annotations

import datetime as dt
import sys

import pytest

from inkstone import frontmatter
from inkstone.errors import ContentError

needs_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="tomllib is new in Python 3.11"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\ntitle: x\n---\nbody\n", ("title: x\n", "body\n", "yaml")),
        ("+++\ntitle = 'x'\n+++\nbody\n", ("title = 'x'\n", "body\n", "toml")),
        (';;;\n"title": "x"\n;;;\nbody\n', ('"title": "x"\n', "body\n", "json")),
        ('{\n  "title": "x"\n}\nbody\n', ('{\n  "title": "x"\n}', "body\n", "json")),
        ('{"title": "x"}\nbody\n', ('{"title": "x"}', "body\n", "json")),
        ("---\n---\nbody\n", ("", "body\n", "yaml")),
        ("---\ntitle: x\n---\n", ("title: x\n", "", "yaml")),
        ("---\ntitle: x\n---", ("title: x\n", "", "yaml")),
        ("---\ntitle: x\n...\nbody\n", ("title: x\n", "body\n", "yaml")),
        ("---  \ntitle: x\n--- \t\nbody\n", ("title: x\n", "body\n", "yaml")),
        ("---\na: 1\n\n---\n\nbody\n", ("a: 1\n\n", "\nbody\n", "yaml")),
        ("{}\nbody\n", ("{}", "body\n", "json")),
    ],
)
def test_split(text, expected):
    assert frontmatter.split(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "just a body\n",
        "\n---\ntitle: late\n---\n",
        "----\nfour dashes\n----\n",
        "--- title: x ---\n",
        "{{ page.title }}\n",
        "{% extends 'base.html' %}\n",
        "{ not json\n",
        "text\n---\nrule further down\n---\n",
        " ---\nindented fence\n---\n",
    ],
)
def test_split_without_front_matter(text):
    assert frontmatter.split(text) == (None, text, None)


def test_split_keeps_line_endings_and_drops_bom():
    raw, body, fmt = frontmatter.split("\ufeff---\r\ntitle: x\r\n---\r\nbody\r\n")
    assert (raw, body, fmt) == ("title: x\r\n", "body\r\n", "yaml")
    assert frontmatter.split("\ufeffno front matter") == (None, "no front matter", None)


def test_split_does_not_look_for_fences_inside_the_body():
    text = "---\ntitle: x\n---\nbody\n---\nmore\n"
    assert frontmatter.split(text) == ("title: x\n", "body\n---\nmore\n", "yaml")


def test_split_json_block_with_nested_braces_and_strings():
    text = '{\n  "a": {"b": "}"},\n  "c": "\\"{"\n}\n# Title\n'
    raw, body, fmt = frontmatter.split(text)
    assert raw == '{\n  "a": {"b": "}"},\n  "c": "\\"{"\n}'
    assert body == "# Title\n"
    assert fmt == "json"


def test_split_json_block_keeps_text_after_the_closing_brace():
    raw, body, _ = frontmatter.split('{"a": 1} tail\nmore')
    assert (raw, body) == ('{"a": 1}', " tail\nmore")


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("---\ntitle: x\nbody without closing fence\n", "never closed"),
        ("---\n", "never closed"),
        ("---", "never closed"),
        ("+++\ntitle = 'x'\n", r"another '\+\+\+' line"),
        (';;;\n"a": 1\n', "never closed"),
        ('{\n  "title": "x"\n', "missing '}'"),
    ],
)
def test_missing_closing_fence(text, fragment):
    with pytest.raises(ContentError, match=fragment) as info:
        frontmatter.split(text)
    assert info.value.line == 1
    with pytest.raises(ContentError, match=fragment) as info:
        frontmatter.parse(text, path="content/post.md")
    assert str(info.value).startswith("content/post.md:1: ")


def test_parse_yaml():
    text = (
        "---\n"
        "title: Hello\n"
        "date: 2024-05-03\n"
        "tags: [a, b]\n"
        "draft: true\n"
        "---\n"
        "# Body\n"
    )
    meta, body = frontmatter.parse(text)
    assert meta == {
        "title": "Hello",
        "date": dt.date(2024, 5, 3),
        "tags": ["a", "b"],
        "draft": True,
    }
    assert body == "# Body\n"


@needs_tomllib
def test_parse_toml():
    text = '+++\ntitle = "Hello"\ndate = 2024-05-03\n[extra]\nweight = 3\n+++\nBody\n'
    meta, body = frontmatter.parse(text)
    assert meta == {
        "title": "Hello",
        "date": dt.date(2024, 5, 3),
        "extra": {"weight": 3},
    }
    assert body == "Body\n"


def test_parse_json_in_both_spellings():
    expected = ({"title": "Hello", "tags": ["a"], "n": 1.5}, "Body\n")
    braces = '{\n  "title": "Hello",\n  "tags": ["a"],\n  "n": 1.5\n}\nBody\n'
    fenced = ';;;\n"title": "Hello",\n"tags": ["a"],\n"n": 1.5\n;;;\nBody\n'
    fenced_with_braces = ';;;\n{"title": "Hello", "tags": ["a"], "n": 1.5}\n;;;\nBody\n'
    assert frontmatter.parse(braces) == expected
    assert frontmatter.parse(fenced) == expected
    assert frontmatter.parse(fenced_with_braces) == expected


@pytest.mark.parametrize(
    "text",
    [
        "no front matter at all\n",
        "---\n---\nbody\n",
        "---\n\n   \n---\nbody\n",
        "---\n# only a comment\n---\nbody\n",
        "+++\n+++\nbody\n",
        ";;;\n;;;\nbody\n",
        "{}\nbody\n",
    ],
)
def test_parse_empty_metadata(text):
    meta, body = frontmatter.parse(text)
    assert meta == {}
    assert body.endswith("body\n") or body == text


def test_parse_handles_bom_and_crlf():
    text = "\ufeff---\r\ntitle: Hello\r\nlist:\r\n  - a\r\n---\r\nBody\r\n"
    assert frontmatter.parse(text) == ({"title": "Hello", "list": ["a"]}, "Body\r\n")


@pytest.mark.parametrize(
    ("text", "line", "fragment"),
    [
        ("---\ntitle: x\nbad: a: b\n---\n", 3, "invalid YAML front matter"),
        ("---\n\n\n\nkey: 'open\n---\n", 5, "unclosed quoted string"),
        ("---\na: 1\na: 2\n---\n", 3, "duplicate key"),
        ("---\n- a\n- b\n---\n", 2, "not a list"),
        ("---\njust a string\n---\n", 2, "not a str"),
        ('{\n  "a": 1,\n  "b": \n}\n', 4, "invalid JSON front matter"),
        (';;;\n"a": 1,\n"b": oops\n;;;\n', 3, "invalid JSON front matter"),
    ],
)
def test_parse_errors_report_file_line_numbers(text, line, fragment):
    with pytest.raises(ContentError, match=fragment) as info:
        frontmatter.parse(text, path="post.md")
    error = info.value
    assert error.line == line
    assert error.path == "post.md"
    assert str(error).startswith(f"post.md:{line}: ")


@needs_tomllib
@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("+++\ntitle = 'x'\nbroken = \n+++\n", 3),
        ("+++\na = 1\na = 2\n+++\n", 3),
        ("+++\n\n\nkey = [1, 2\n+++\nbody", 5),
    ],
)
def test_parse_toml_errors(text, line):
    with pytest.raises(ContentError, match="invalid TOML front matter") as info:
        frontmatter.parse(text, path="post.md")
    assert info.value.line == line


def test_parse_error_without_path_mentions_the_line():
    with pytest.raises(ContentError) as info:
        frontmatter.parse("---\nok: 1\nbad: [1, 2\n---\n")
    assert info.value.path is None
    assert str(info.value).endswith("(line 3)")
    assert "(column 6)" in str(info.value)


@pytest.mark.parametrize("fmt", ["yaml", "json"])
@pytest.mark.parametrize(
    ("meta", "body"),
    [
        ({"title": "Hello: world", "tags": ["a", "b"], "n": 3}, "Body text\n"),
        ({"nested": {"a": [1, 2, {"b": None}]}, "flag": False}, "\n\nSpaced body\n"),
        ({"multi": "line one\nline two\n"}, "---\nBody starting with a rule\n"),
        ({}, "Just a body\n"),
        ({"title": "No body"}, ""),
        ({"unicode": "héllo ✓"}, "ünïcödé\r\nwith crlf\r\n"),
    ],
)
def test_dumps_roundtrips(fmt, meta, body):
    text = frontmatter.dumps(meta, body, fmt)
    assert frontmatter.parse(text) == (meta, body)
    assert frontmatter.split(text)[2] == fmt


@needs_tomllib
@pytest.mark.parametrize(
    ("meta", "body"),
    [
        ({"title": "Hello", "tags": ["a", "b"], "n": 3, "x": 1.5}, "Body\n"),
        (
            {"date": dt.date(2024, 5, 3), "extra": {"deep": {"k": "v"}}},
            "+ not a fence\n",
        ),
        ({}, "Body\n"),
    ],
)
def test_dumps_toml_roundtrips(meta, body):
    text = frontmatter.dumps(meta, body, "toml")
    assert text.startswith("+++\n")
    assert frontmatter.parse(text) == (meta, body)


def test_dumps_layout():
    assert frontmatter.dumps({"title": "x"}, "Body\n") == "---\ntitle: x\n---\nBody\n"
    assert frontmatter.dumps({}, "Body\n") == "---\n---\nBody\n"
    assert frontmatter.dumps({"a": 1}, "Body\n", "json") == '{\n  "a": 1\n}\nBody\n'


def test_dumps_yaml_keeps_dates_json_stringifies_them():
    meta = {"date": dt.date(2024, 5, 3)}
    assert frontmatter.parse(frontmatter.dumps(meta, ""))[0] == meta
    as_json = frontmatter.parse(frontmatter.dumps(meta, "", "json"))[0]
    assert as_json == {"date": "2024-05-03"}


def test_dumps_rejects_unknown_formats_and_values():
    with pytest.raises(ValueError, match="unknown front matter format"):
        frontmatter.dumps({}, "", "xml")
    with pytest.raises(TypeError):
        frontmatter.dumps({"x": object()}, "", "json")
