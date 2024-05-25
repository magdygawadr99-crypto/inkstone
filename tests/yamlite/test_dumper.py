from __future__ import annotations

import datetime as dt
import math
from collections import OrderedDict

import pytest

from inkstone import yamlite
from inkstone.yamlite import YamlError

TRICKY_STRINGS = [
    "",
    " ",
    "a",
    "two words",
    " leading",
    "trailing ",
    "yes",
    "No",
    "ON",
    "null",
    "Null",
    "~",
    "true",
    "False",
    "123",
    "-4",
    "1.5",
    "1e3",
    ".5",
    "+1",
    "0x1f",
    "0o17",
    ".inf",
    ".nan",
    "2024-05-03",
    "2024-05-03 14:00",
    "- item",
    "-",
    "-dash",
    "--",
    "---",
    "--- text",
    "...",
    "key: value",
    "ends with colon:",
    "a:b",
    ":a",
    "?q",
    "? q",
    "a #b",
    "a#b",
    "#hash",
    "@at",
    "`tick",
    "%pct",
    "100%",
    "!bang",
    "&amp",
    "*star",
    "|pipe",
    ">gt",
    "'single'",
    '"double"',
    "it's",
    'say "hi"',
    "mix ' and \"",
    "back\\slash",
    "C:\\Users\\sam",
    'quote " and \\ slash',
    "[x]",
    "{x}",
    "x, y",
    "x]",
    "<<",
    "=",
    "tab\there",
    "\ttab first",
    "line\nbreak",
    "trailing newline\n",
    "two trailing\n\n",
    "three trailing\n\n\n",
    "\nleading newline",
    "\n\nblank lines first\n",
    " indented first line\nsecond",
    "first\n  indented second\n",
    "trailing spaces  \nnext",
    "blank with spaces\n   \nend",
    "  \n  ",
    "\n",
    "\n\n",
    "\r\n",
    "cr\rmiddle\n",
    "nul\x00",
    "bell\x07",
    "esc\x1b[0m",
    "del\x7f",
    "é",
    "日本語",
    "😀",
    "nbsp\xa0inside",
    "\xa0",
    "\u2028",
    "\x85next line",
    "\ufeffbom",
    "# heading\n\nSome *markdown* body.\n\n- list\n- items\n",
    "code:\n\tindented with a tab\n",
    "word " * 60,
]


def roundtrip(value, **options):
    return yamlite.loads(yamlite.dumps(value, **options))


@pytest.mark.parametrize("text", TRICKY_STRINGS)
def test_strings_survive_in_every_position(text):
    assert roundtrip(text) == text
    assert roundtrip({"key": text}) == {"key": text}
    assert roundtrip([text]) == [text]
    assert roundtrip({text: 1}) == {text: 1}
    nested = {"items": [{"name": text, "after": 1}, [text, [text]]]}
    assert roundtrip(nested) == nested
    assert roundtrip(nested, indent=4) == nested


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -12,
        2**70,
        1.5,
        -0.001,
        1e300,
        1e-7,
        math.inf,
        -math.inf,
        dt.date(2024, 5, 3),
        dt.datetime(2024, 5, 3, 14, 0),
        dt.datetime(2024, 5, 3, 14, 0, 5, 123456),
        dt.datetime(2024, 5, 3, 14, 0, tzinfo=dt.timezone.utc),
        dt.datetime(2024, 5, 3, 14, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3.5))),
        [],
        {},
        [[]],
        [{}],
        {"a": []},
        {"a": {}},
        [[1, 2], [3, [4, [5]]]],
        {"a": {"b": {"c": {"d": [1, {"e": None}]}}}},
        [{"a": 1, "b": [1, 2]}, {"c": {"d": "e"}}],
        {1: "int", 2.5: "float", None: "none", "s": "str"},
        {True: "t", False: "f"},
        {dt.date(2024, 1, 1): "new year"},
    ],
)
def test_values_roundtrip(value):
    back = roundtrip(value)
    assert back == value
    assert type(back) is type(value)
    assert roundtrip({"wrapped": [value]}) == {"wrapped": [value]}


def test_nan_roundtrips():
    assert math.isnan(roundtrip(math.nan))
    assert yamlite.dumps(math.nan) == ".nan\n"


def test_timezone_offset_is_preserved():
    moment = dt.datetime(2024, 5, 3, 14, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert roundtrip(moment).utcoffset() == dt.timedelta(hours=2)


def test_mapping_layout():
    data = {"title": "Hello", "count": 3, "nested": {"a": 1, "b": [1, 2]}, "empty": []}
    assert yamlite.dumps(data) == (
        "title: Hello\n"
        "count: 3\n"
        "nested:\n"
        "  a: 1\n"
        "  b:\n"
        "    - 1\n"
        "    - 2\n"
        "empty: []\n"
    )


def test_sequence_of_mappings_uses_compact_form():
    data = [{"name": "a", "tags": ["x"]}, {"name": "b"}]
    assert yamlite.dumps(data) == "- name: a\n  tags:\n    - x\n- name: b\n"


def test_nested_sequences_share_a_line():
    assert yamlite.dumps([[1, 2], [3]]) == "- - 1\n  - 2\n- - 3\n"


def test_indent_option():
    data = {"a": {"b": [1, {"c": 2, "d": 3}]}}
    assert yamlite.dumps(data, indent=4) == (
        "a:\n"
        "    b:\n"
        "        - 1\n"
        "        - c: 2\n"
        "          d: 3\n"
    )
    with pytest.raises(ValueError):
        yamlite.dumps(data, indent=0)


def test_scalar_spellings():
    data = {"n": None, "t": True, "f": False, "i": 7, "x": 0.5}
    assert yamlite.dumps(data) == "n: null\nt: true\nf: false\ni: 7\nx: 0.5\n"
    assert yamlite.dumps({"d": dt.date(2024, 5, 3)}) == "d: 2024-05-03\n"
    assert yamlite.dumps(math.inf) == ".inf\n"
    assert yamlite.dumps(-math.inf) == "-.inf\n"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("plain", "plain\n"),
        ("123", '"123"\n'),
        ("true", '"true"\n'),
        ("yes", '"yes"\n'),
        ("", '""\n'),
        ("a: b", '"a: b"\n'),
        ("it's fine", "it's fine\n"),
        ("# no", '"# no"\n'),
        ("C:\\dir: x", "'C:\\dir: x'\n"),
        ('"quoted" start', "'\"quoted\" start'\n"),
        ("tab\there", '"tab\\there"\n'),
        ("bell\x07", '"bell\\x07"\n'),
        ("\u2028", '"\\L"\n'),
        ("\ufeff", '"\\ufeff"\n'),
    ],
)
def test_string_quoting_style(value, expected):
    assert yamlite.dumps(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\nb\n", "text: |\n  a\n  b\n"),
        ("a\nb", "text: |-\n  a\n  b\n"),
        ("a\n\n\n", "text: |+\n  a\n\n\n"),
        ("a\n\nb\n", "text: |\n  a\n\n  b\n"),
        (" a\nb\n", "text: |2\n   a\n  b\n"),
        ("\n", 'text: "\\n"\n'),
        ("a\r\nb", 'text: "a\\r\\nb"\n'),
    ],
)
def test_multiline_strings_become_block_scalars(value, expected):
    assert yamlite.dumps({"text": value}) == expected


def test_block_scalar_inside_sequence_item():
    data = [{"body": "one\ntwo\n", "n": 1}, "x\ny"]
    assert yamlite.dumps(data) == (
        "- body: |\n"
        "    one\n"
        "    two\n"
        "  n: 1\n"
        "- |-\n"
        "  x\n"
        "  y\n"
    )


def test_block_scalar_with_wide_indent_falls_back_to_quotes():
    text = " starts with a space\nsecond"
    dumped = yamlite.dumps({"k": text}, indent=12)
    assert dumped == 'k: " starts with a space\\nsecond"\n'
    assert yamlite.loads(dumped) == {"k": text}


def test_sort_keys():
    data = {"b": 1, "a": {"z": 1, "y": 2}, "c": [{"q": 1, "p": 2}]}
    assert yamlite.dumps(data, sort_keys=True) == (
        "a:\n  y: 2\n  z: 1\nb: 1\nc:\n  - p: 2\n    q: 1\n"
    )
    assert yamlite.dumps(data).startswith("b: 1\n")


def test_sort_keys_with_mixed_key_types():
    data = {"b": 1, 2: "int", "a": 2, 1: "int", None: 0}
    dumped = yamlite.dumps(data, sort_keys=True)
    assert dumped == "null: 0\n1: int\n2: int\na: 2\nb: 1\n"
    assert yamlite.loads(dumped) == data


def test_keys_are_quoted_when_needed():
    data = {"plain": 1, "has space": 2, "a: b": 3, "": 4, "123": 5, "null": 6}
    assert yamlite.dumps(data) == (
        'plain: 1\nhas space: 2\n"a: b": 3\n"": 4\n"123": 5\n"null": 6\n'
    )


def test_tuples_sets_and_other_mappings():
    assert yamlite.dumps((1, 2)) == "- 1\n- 2\n"
    assert yamlite.dumps({"s": {3, 1, 2}}) == "s:\n  - 1\n  - 2\n  - 3\n"
    assert yamlite.dumps(OrderedDict(b=1, a=2)) == "b: 1\na: 2\n"
    assert yamlite.dumps({"t": ()}) == "t: []\n"


def test_unsupported_values_raise():
    with pytest.raises(YamlError, match="cannot represent object"):
        yamlite.dumps({"x": object()})
    with pytest.raises(YamlError, match="cannot represent bytes"):
        yamlite.dumps([b"raw"])
    with pytest.raises(YamlError, match="keys must be scalars"):
        yamlite.dumps({(1, 2): "tuple key"})


def test_cycles_are_detected():
    loop: list = [1]
    loop.append(loop)
    with pytest.raises(YamlError, match="contains itself"):
        yamlite.dumps(loop)
    shared = {"x": 1}
    assert roundtrip({"a": shared, "b": shared}) == {"a": {"x": 1}, "b": {"x": 1}}


def test_output_ends_with_a_single_newline():
    for value in ({"a": 1}, [1], "x", "multi\nline\n", {"a": {"b": "c\nd\n"}}):
        dumped = yamlite.dumps(value)
        assert dumped.endswith("\n") and not dumped.endswith("\n\n")


def test_dump_then_load_all_as_stream():
    documents = [{"a": 1}, ["x", "y"], "text"]
    stream = "---\n".join(yamlite.dumps(doc) for doc in documents)
    assert yamlite.load_all(stream) == documents
