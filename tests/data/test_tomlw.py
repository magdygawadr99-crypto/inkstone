from __future__ import annotations

import datetime as dt
import math
import sys

import pytest

from inkstone import tomlw
from inkstone.errors import InkstoneError
from inkstone.tomlw import TomlError

needs_tomllib = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="tomllib is new in Python 3.11"
)

if sys.version_info >= (3, 11):
    import tomllib

PLUS_TWO = dt.timezone(dt.timedelta(hours=2))


def roundtrip(data):
    return tomllib.loads(tomlw.dumps(data))


@needs_tomllib
@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "",
        "with \"quotes\" and 'apostrophes'",
        "back\\slash",
        "C:\\Users\\sam\\site",
        r"^\d+\.\d+$",
        "it's got a \\ and a quote",
        "tab\tinside",
        "control \x01 \x1f \x7f chars",
        "unicode: héllo ✓ 日本語 😀",
        "line one\nline two\n",
        "no trailing newline\nat the end",
        "\nstarts with a newline",
        "windows\r\nline endings\r\n",
        'triple """ quotes\ninside',
        'ends with a quote"\n"',
        "trailing backslash \\\nnext line",
        "   leading and trailing spaces   ",
        0,
        -7,
        2**62,
        1.5,
        -0.0001,
        1e100,
        1e-10,
        math.inf,
        -math.inf,
        True,
        False,
        dt.date(2024, 5, 3),
        dt.time(14, 30),
        dt.time(14, 30, 5, 250000),
        dt.datetime(2024, 5, 3, 14, 30),
        dt.datetime(2024, 5, 3, 14, 30, 5, 123456),
        dt.datetime(2024, 5, 3, 14, 30, tzinfo=dt.timezone.utc),
        dt.datetime(2024, 5, 3, 14, 30, tzinfo=dt.timezone(dt.timedelta(hours=-7))),
        [],
        [1, 2, 3],
        ["a", "b"],
        [[1, 2], ["x"]],
        [1, "mixed", 2.5, True],
        ["multi\nline", "in an array"],
        {},
        ["long string number %d" % index for index in range(12)],
    ],
)
def test_values_roundtrip(value):
    back = roundtrip({"key": value})["key"]
    assert back == value
    assert type(back) is type(value)


@needs_tomllib
def test_nan_roundtrips():
    assert tomlw.dumps({"x": math.nan}) == "x = nan\n"
    assert math.isnan(roundtrip({"x": math.nan})["x"])


@needs_tomllib
@pytest.mark.parametrize(
    "data",
    [
        {},
        {"a": 1, "b": {"c": 2}},
        {"a": {"b": {"c": {"d": 1}}}},
        {"a": {"x": 1, "b": {"y": 2, "c": {"z": 3}}}},
        {"table": {}, "after": 1},
        {"a": {"empty": {}}},
        {"servers": [{"name": "a", "port": 1}, {"name": "b", "port": 2}]},
        {"a": {"items": [{"n": 1}, {"n": 2, "sub": {"k": "v"}}]}},
        {"outer": [{"inner": [{"x": 1}, {"x": 2}]}, {"inner": [{"x": 3}]}]},
        {"points": [{}, {"x": 1}]},
        {"mixed": [1, {"a": 1}, [2, {"b": [3]}]]},
        {"inline": [[{"a": 1}], [{"b": {"c": 2}}]]},
        {"key with spaces": 1, "dotted.key": 2, "": 3, "ключ": 4, 'quo"te': 5},
        {"weird table": {"sub.table": {"k": 1}}, "list of": [{"odd key!": True}]},
        {"1": "numeric key", "a-b_c": "bare"},
        {"z": 1, "nested": {"q": 1}, "a": 2, "more": [{"k": 1}], "m": 3},
    ],
)
def test_documents_roundtrip(data):
    assert roundtrip(data) == data


@needs_tomllib
def test_realistic_front_matter_roundtrips():
    meta = {
        "title": "Hello, TOML",
        "date": dt.datetime(2024, 5, 3, 9, 30, tzinfo=PLUS_TWO),
        "draft": False,
        "tags": ["a", "b"],
        "weight": 10,
        "summary": "First line.\nSecond line.\n",
        "author": {"name": "Sam", "links": {"web": "https://example.com"}},
        "resources": [
            {"src": "cover.jpg", "params": {"alt": "The cover"}},
            {"src": "notes.pdf"},
        ],
    }
    assert roundtrip(meta) == meta


def test_plain_values_come_before_tables():
    data = {"table": {"x": 1}, "top": "level", "list": [{"a": 1}], "last": 2}
    assert tomlw.dumps(data) == (
        'top = "level"\n'
        "last = 2\n"
        "\n"
        "[table]\n"
        "x = 1\n"
        "\n"
        "[[list]]\n"
        "a = 1\n"
    )


def test_table_holding_only_tables_gets_no_header_of_its_own():
    assert tomlw.dumps({"a": {"b": {"c": 1}}}) == "[a.b]\nc = 1\n"
    assert tomlw.dumps({"a": {"x": 1, "b": {"c": 1}}}) == "[a]\nx = 1\n\n[a.b]\nc = 1\n"


def test_empty_document_and_empty_tables():
    assert tomlw.dumps({}) == ""
    assert tomlw.dumps({"t": {}}) == "t = {}\n"
    assert tomlw.dumps({"a": {"b": None}}) == "[a]\n"


def test_scalar_spellings():
    data = {"t": True, "f": False, "i": -3, "x": 0.5, "big": 1e20, "inf": -math.inf}
    assert tomlw.dumps(data) == (
        "t = true\nf = false\ni = -3\nx = 0.5\nbig = 1e+20\ninf = -inf\n"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("plain", '"plain"'),
        ('say "hi"', '"say \\"hi\\""'),
        ("C:\\dir", "'C:\\dir'"),
        ("it's C:\\dir", '"it\'s C:\\\\dir"'),
        ("tab\t", '"tab\\t"'),
        ("\x00", '"\\u0000"'),
        ("a\nb\n", '"""\na\nb\n"""'),
        ('q"\n', '"""\nq"\n"""'),
        ('x""y\n', '"""\nx\\"\\"y\n"""'),
        ("cr\r\n", '"""\ncr\\r\n"""'),
    ],
)
def test_string_styles(value, expected):
    assert tomlw.dumps({"s": value}) == f"s = {expected}\n"


def test_multiline_strings_inside_arrays_are_escaped_instead():
    assert tomlw.dumps({"a": ["x\ny"]}) == 'a = ["x\\ny"]\n'


def test_keys_are_quoted_only_when_needed():
    data = {"bare_key-1": 1, "needs quoting": 2, "dotted.name": 3, "": 4}
    assert tomlw.dumps(data) == (
        'bare_key-1 = 1\n"needs quoting" = 2\n"dotted.name" = 3\n"" = 4\n'
    )
    assert tomlw.dumps({"a b": {"c.d": {"k": 1}}}) == '["a b"."c.d"]\nk = 1\n'


def test_inline_tables_in_mixed_arrays():
    data = {"mixed": [1, {"a": 1, "b": "x"}, {}]}
    assert tomlw.dumps(data) == 'mixed = [1, { a = 1, b = "x" }, {}]\n'


def test_long_arrays_are_wrapped():
    data = {"items": ["a fairly long string value"] * 4}
    assert tomlw.dumps(data) == (
        "items = [\n"
        '    "a fairly long string value",\n'
        '    "a fairly long string value",\n'
        '    "a fairly long string value",\n'
        '    "a fairly long string value",\n'
        "]\n"
    )
    assert tomlw.dumps({"short": [1, 2, 3]}) == "short = [1, 2, 3]\n"


@needs_tomllib
def test_none_values_are_dropped_from_tables():
    data = {"a": 1, "gone": None, "t": {"keep": 1, "gone": None}, "i": [{"x": None}]}
    assert roundtrip(data) == {"a": 1, "t": {"keep": 1}, "i": [{}]}
    assert roundtrip({"mixed": [1, {"a": None, "b": 2}]}) == {"mixed": [1, {"b": 2}]}


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ({"a": [1, None]}, "no null"),
        ({"a": object()}, "cannot represent object"),
        ({"a": {1, 2}}, "cannot represent set"),
        ({1: "x"}, "keys must be strings"),
        ({"t": {2: "x"}}, "keys must be strings"),
        ({"t": {"u": {None: 1}}}, "keys must be strings"),
        ({"a": dt.time(1, 2, tzinfo=dt.timezone.utc)}, "UTC offset"),
        ([1, 2], "must be a table"),
    ],
)
def test_unsupported_data(data, fragment):
    with pytest.raises(TomlError, match=fragment):
        tomlw.dumps(data)


def test_tuples_are_arrays():
    assert tomlw.dumps({"t": (1, 2), "tables": ({"a": 1},)}) == (
        "t = [1, 2]\n\n[[tables]]\na = 1\n"
    )


@needs_tomllib
def test_loads_wraps_tomllib():
    assert tomlw.loads('a = 1\n[t]\nb = "x"\n') == {"a": 1, "t": {"b": "x"}}
    assert tomlw.loads("") == {}


@needs_tomllib
@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("a = \n", 1),
        ("a = 1\nb = [1, 2\n", 3),
        ("a = 1\n\n\nc d = 2\n", 4),
        ("a = 1\na = 2\n", 2),
        ("[t]\n[t]\n", 2),
    ],
)
def test_loads_reports_the_line(text, line):
    with pytest.raises(TomlError) as info:
        tomlw.loads(text)
    error = info.value
    assert isinstance(error, InkstoneError)
    assert error.line == line
    assert "at line" not in error.message and "column" not in error.message


def test_loads_without_tomllib(monkeypatch):
    monkeypatch.setattr(tomlw, "tomllib", None)
    with pytest.raises(TomlError, match="Python 3.11"):
        tomlw.loads("a = 1\n")
