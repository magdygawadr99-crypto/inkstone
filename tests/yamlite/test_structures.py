from __future__ import annotations

import datetime as dt

import pytest

from inkstone import yamlite
from inkstone.yamlite import YamlError


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a: 1\nb: two\n", {"a": 1, "b": "two"}),
        ("a:\n  b:\n    c: deep\n", {"a": {"b": {"c": "deep"}}}),
        ("a:\n  b: 1\nc: 2\n", {"a": {"b": 1}, "c": 2}),
        ("a:\nb:\n", {"a": None, "b": None}),
        ("a:   spaced   \n", {"a": "spaced"}),
        ("key with spaces: v\n", {"key with spaces": "v"}),
        ('"quoted key": v\n', {"quoted key": "v"}),
        ("'a: b': v\n", {"a: b": "v"}),
        (
            "7: int\n2.5: float\ntrue: bool\n~: nothing\n",
            {7: "int", 2.5: "float", True: "bool", None: "nothing"},
        ),
        ("2024-05-03: launch\n", {dt.date(2024, 5, 3): "launch"}),
        ("a: 1 # comment\n# full line\nb: 2\n", {"a": 1, "b": 2}),
        ("\n\na: 1\n\n\nb: 2\n\n", {"a": 1, "b": 2}),
        ("a: 1\r\nb:\r\n  c: 2\r\n", {"a": 1, "b": {"c": 2}}),
        ("    a: 1\n    b: 2\n", {"a": 1, "b": 2}),
        ("a: b:c\n", {"a": "b:c"}),
        ("a:b: c\n", {"a:b": "c"}),
        ("time: 12:30:45\n", {"time": "12:30:45"}),
        ("win: C:\\dir\\file\n", {"win": "C:\\dir\\file"}),
        ("emoji: 🎉 party\n", {"emoji": "🎉 party"}),
    ],
)
def test_block_mappings(text, expected):
    assert yamlite.loads(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("- a\n- b\n", ["a", "b"]),
        ("- 1\n- 2.5\n- true\n- ~\n", [1, 2.5, True, None]),
        ("-\n- a\n-\n", [None, "a", None]),
        ("- - a\n  - b\n- - c\n", [["a", "b"], ["c"]]),
        ("-\n  - a\n  - b\n", [["a", "b"]]),
        (
            "- name: x\n  size: 1\n- name: y\n",
            [{"name": "x", "size": 1}, {"name": "y"}],
        ),
        ("-\n  name: x\n  size: 1\n", [{"name": "x", "size": 1}]),
        ("- a: 1\n  b:\n    - x\n    - y\n", [{"a": 1, "b": ["x", "y"]}]),
        ("- - - deep\n", [[["deep"]]]),
        ("- key:\n    nested: 1\n", [{"key": {"nested": 1}}]),
        ("  - a\n  - b\n", ["a", "b"]),
        ("- a # one\n# between\n- b\n", ["a", "b"]),
        ("- -1\n- - 1\n", [-1, [1]]),
    ],
)
def test_block_sequences(text, expected):
    assert yamlite.loads(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a:\n  - 1\n  - 2\nb: 3\n", {"a": [1, 2], "b": 3}),
        ("a:\n- 1\n- 2\nb: 3\n", {"a": [1, 2], "b": 3}),
        ("a:\n- x: 1\n  y: 2\n- x: 3\n", {"a": [{"x": 1, "y": 2}, {"x": 3}]}),
        ("a:\n  b:\n  - 1\n  c: 2\n", {"a": {"b": [1], "c": 2}}),
        ("a:\n-\n- b\n", {"a": [None, "b"]}),
    ],
)
def test_sequences_as_mapping_values(text, expected):
    assert yamlite.loads(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[]", []),
        ("{}", {}),
        ("[a, b, c]", ["a", "b", "c"]),
        ("[1, 2.0, true, null, ~]", [1, 2.0, True, None, None]),
        ("[a, b, ]", ["a", "b"]),
        ("[[1, 2], [3]]", [[1, 2], [3]]),
        ("[a b, c d]", ["a b", "c d"]),
        ("['a, b', \"c: d\"]", ["a, b", "c: d"]),
        ("{a: 1, b: two}", {"a": 1, "b": "two"}),
        ("{a: 1, }", {"a": 1}),
        ("{a: [1, 2], b: {c: d}}", {"a": [1, 2], "b": {"c": "d"}}),
        ("{a, b: 1}", {"a": None, "b": 1}),
        ("{a: , b: 1}", {"a": None, "b": 1}),
        ("[a: 1, b]", [{"a": 1}, "b"]),
        ('{"a":1,"b":[true,null]}', {"a": 1, "b": [True, None]}),
        ("{url: http://x.y/z, t: 12:30}", {"url": "http://x.y/z", "t": "12:30"}),
        ("[\n  a,\n  b,   # note\n  c\n]\n", ["a", "b", "c"]),
        ("{\n  a: 1,\n  b: 2\n}\n", {"a": 1, "b": 2}),
        ("[a\n  b, c]", ["a b", "c"]),
        ("k: [1, 2]\nm: {x: y}\n", {"k": [1, 2], "m": {"x": "y"}}),
        ("tags: [a, b,\n  c]\nnext: 1\n", {"tags": ["a", "b", "c"], "next": 1}),
        ("- [a, b]\n- {c: d}\n", [["a", "b"], {"c": "d"}]),
        ("k: []\nm: {}\n", {"k": [], "m": {}}),
    ],
)
def test_flow_collections(text, expected):
    assert yamlite.loads(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v: |\n  one\n  two\n", "one\ntwo\n"),
        ("v: |-\n  one\n  two\n", "one\ntwo"),
        ("v: |+\n  one\n\n\n", "one\n\n\n"),
        ("v: |\n  one\n\n\n", "one\n"),
        ("v: |\n  one\n\n  two\n", "one\n\ntwo\n"),
        ("v: |\n\n  after blank\n", "\nafter blank\n"),
        ("v: |\n  keep\n    indent\n  here\n", "keep\n  indent\nhere\n"),
        ("v: |\n  # not a comment\n  a: b\n", "# not a comment\na: b\n"),
        ("v: |   # header comment\n  text\n", "text\n"),
        ("v: |2\n   lead\n  rest\n", " lead\nrest\n"),
        ("v: |1-\n  two spaces in, one kept\n", " two spaces in, one kept"),
        ("v: |-2\n    x\n", "  x"),
        ("v: |\n  trailing  \n", "trailing  \n"),
        ("v: |\n  no final newline", "no final newline\n"),
        ("v: |\n", ""),
        ("v: |+\n\n\n", "\n\n"),
        ("v: |\n  tab\there\n", "tab\there\n"),
        ("v: >\n  one\n  two\n", "one two\n"),
        ("v: >-\n  one\n  two\n", "one two"),
        ("v: >\n  one\n\n  two\n", "one\ntwo\n"),
        ("v: >\n  one\n\n\n  two\n", "one\n\ntwo\n"),
        ("v: >\n  a\n    code\n  b\n", "a\n  code\nb\n"),
        ("v: >+\n  one\n\n", "one\n\n"),
        ("v: >\n  one\n  two\n\n\n", "one two\n"),
    ],
)
def test_block_scalars(text, expected):
    assert yamlite.loads(text) == {"v": expected}


def test_block_scalar_stops_at_dedent():
    doc = "a: |\n  text\nb: 1\n"
    assert yamlite.loads(doc) == {"a": "text\n", "b": 1}


def test_block_scalars_in_sequences_and_at_top_level():
    assert yamlite.loads("- |\n  one\n- >-\n  two\n  three\n") == ["one\n", "two three"]
    assert yamlite.loads("|\n  top\n  level\n") == "top\nlevel\n"
    assert yamlite.loads("--- |\nflush left\n") == "flush left\n"
    assert yamlite.loads("- key: |\n    nested\n  other: 1\n") == [
        {"key": "nested\n", "other": 1}
    ]


def test_top_level_block_scalar_stops_at_document_marker():
    assert yamlite.load_all("--- |\none\n---\ntwo\n") == ["one\n", "two"]


def test_anchors_and_aliases():
    doc = "a: &x 1\nb: *x\nc: &y [1, 2]\nd: *y\ne: &z {k: v}\nf: *z\n"
    data = yamlite.loads(doc)
    assert data == {
        "a": 1,
        "b": 1,
        "c": [1, 2],
        "d": [1, 2],
        "e": {"k": "v"},
        "f": {"k": "v"},
    }
    assert data["c"] is data["d"]


def test_anchor_on_block_collection():
    doc = (
        "base: &base\n"
        "  x: 1\n"
        "  y: 2\n"
        "copy: *base\n"
        "list: &items\n"
        "  - a\n"
        "again: *items\n"
    )
    data = yamlite.loads(doc)
    assert data["copy"] == {"x": 1, "y": 2}
    assert data["again"] == ["a"]


def test_alias_in_flow_and_as_sequence_item():
    assert yamlite.loads("- &a x\n- *a\n- [*a, *a]\n") == ["x", "x", ["x", "x"]]


def test_alias_as_mapping_key():
    assert yamlite.loads("name: &n title\n*n : value\n") == {
        "name": "title",
        "title": "value",
    }


def test_anchors_do_not_leak_between_documents():
    with pytest.raises(YamlError, match='undefined alias "a"'):
        yamlite.load_all("x: &a 1\n---\ny: *a\n")


def test_merge_key():
    doc = "base: &b\n  x: 1\n  y: 2\nitem:\n  <<: *b\n  y: 3\n  z: 4\n"
    assert yamlite.loads(doc)["item"] == {"x": 1, "y": 3, "z": 4}


def test_merge_does_not_modify_the_source():
    doc = "base: &b {x: 1}\nitem:\n  <<: *b\n  x: 2\n"
    assert yamlite.loads(doc) == {"base": {"x": 1}, "item": {"x": 2}}


def test_merge_list_prefers_earlier_sources():
    doc = (
        "one: &one {a: 1, b: 1}\n"
        "two: &two {b: 2, c: 2}\n"
        "all:\n"
        "  <<: [*one, *two]\n"
        "  d: 4\n"
    )
    assert yamlite.loads(doc)["all"] == {"a": 1, "b": 1, "c": 2, "d": 4}


def test_merge_key_position_does_not_matter():
    doc = "base: &b {x: 1, y: 1}\nitem:\n  y: 9\n  <<: *b\n"
    assert yamlite.loads(doc)["item"] == {"x": 1, "y": 9}


def test_merge_inline_mapping_and_flow_context():
    assert yamlite.loads("a: {<<: {x: 1}, y: 2}\n") == {"a": {"x": 1, "y": 2}}


def test_quoted_merge_key_is_an_ordinary_key():
    assert yamlite.loads('"<<": 1\n') == {"<<": 1}


def test_merge_needs_mappings():
    with pytest.raises(YamlError, match="merge key"):
        yamlite.loads("a:\n  <<: 5\n")
    with pytest.raises(YamlError, match="merge key"):
        yamlite.loads("a:\n  <<: [1, 2]\n")


def test_load_all_splits_documents():
    stream = "a: 1\n---\nb: 2\n---\n- c\n"
    assert yamlite.load_all(stream) == [{"a": 1}, {"b": 2}, ["c"]]
    assert yamlite.load_all("---\na: 1\n...\n---\nb: 2\n...\n") == [{"a": 1}, {"b": 2}]
    assert yamlite.load_all("--- one\n--- two\n") == ["one", "two"]


def test_empty_documents():
    assert yamlite.load_all("") == []
    assert yamlite.load_all("# only a comment\n") == []
    assert yamlite.load_all("---\n") == [None]
    assert yamlite.load_all("---\n---\na\n") == [None, "a"]
    assert yamlite.load_all("a\n---\n") == ["a", None]


def test_loads_returns_first_document_only():
    assert yamlite.loads("a: 1\n---\nb: 2\n") == {"a": 1}
    assert yamlite.loads("") is None
    assert yamlite.loads("   \n\n") is None


def test_loads_accepts_bytes():
    assert yamlite.loads("name: Zoë\n".encode("utf-8")) == {"name": "Zoë"}
    with pytest.raises(YamlError, match="UTF-8"):
        yamlite.loads(b"name: \xff\n")


def test_key_order_is_preserved():
    doc = "zebra: 1\napple: 2\nmango: 3\n"
    assert list(yamlite.loads(doc)) == ["zebra", "apple", "mango"]


def test_realistic_front_matter():
    doc = """\
title: "Notes on YAML: the good parts"
date: 2024-05-03 09:30:00 +02:00
draft: false
tags: [yaml, parsing]
author:
  name: Sam
  links:
    - https://example.com/~sam
    - mailto:sam@example.com
summary: >
  A long summary that is folded
  into a single line.
aliases:
  - /old/url/
"""
    data = yamlite.loads(doc)
    assert data["title"] == "Notes on YAML: the good parts"
    assert data["date"].utcoffset() == dt.timedelta(hours=2)
    assert data["draft"] is False
    assert data["tags"] == ["yaml", "parsing"]
    assert data["author"]["links"][1] == "mailto:sam@example.com"
    assert data["summary"] == "A long summary that is folded into a single line.\n"
    assert data["aliases"] == ["/old/url/"]
