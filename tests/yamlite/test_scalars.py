from __future__ import annotations

import datetime as dt
import math

import pytest

from inkstone import yamlite
from inkstone.yamlite import YamlError
from inkstone.yamlite.resolver import resolve

UTC = dt.timezone.utc


def tz(hours):
    return dt.timezone(dt.timedelta(hours=hours))


def value_of(text):
    return yamlite.loads(f"v: {text}\n")["v"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("null", None),
        ("Null", None),
        ("NULL", None),
        ("~", None),
        ("", None),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", 0),
        ("42", 42),
        ("-17", -17),
        ("+3", 3),
        ("007", 7),
        ("0x1F", 31),
        ("0xff", 255),
        ("0o17", 15),
        ("123456789012345678901234567890", 123456789012345678901234567890),
        ("1.5", 1.5),
        ("-0.25", -0.25),
        (".5", 0.5),
        ("1.", 1.0),
        ("1e3", 1000.0),
        ("6.02E+23", 6.02e23),
        ("-1.5e-3", -0.0015),
        (".inf", math.inf),
        ("+.Inf", math.inf),
        ("-.INF", -math.inf),
    ],
)
def test_plain_scalars_follow_the_core_schema(text, expected):
    value = value_of(text)
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize("text", [".nan", ".NaN", ".NAN"])
def test_nan(text):
    assert math.isnan(value_of(text))


@pytest.mark.parametrize(
    "text",
    [
        "yes",
        "No",
        "on",
        "off",
        "y",
        "nil",
        "None",
        "tRuE",
        "nULL",
        "0x",
        "0xZZ",
        "0o8",
        "0b101",
        "1_000",
        "1.2.3",
        "1e",
        "e3",
        "12:30",
        "1:30:00",
        "+",
        "--",
        ".",
        "..",
        "-.inf.",
        ".infinity",
        "2024-13-45",
        "2024-02-30",
        "2024-5-3",
        "2024-05-03x",
        "v1.0",
        "hello world",
        "über",
    ],
)
def test_lookalikes_stay_strings(text):
    assert value_of(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-05-03", dt.date(2024, 5, 3)),
        ("2024-05-03 14:00", dt.datetime(2024, 5, 3, 14, 0)),
        ("2024-05-03T14:00:05", dt.datetime(2024, 5, 3, 14, 0, 5)),
        ("2024-05-03t14:00:05", dt.datetime(2024, 5, 3, 14, 0, 5)),
        ("2024-05-03 14:00:05.25", dt.datetime(2024, 5, 3, 14, 0, 5, 250000)),
        (
            "2024-05-03 14:00:05.123456789",
            dt.datetime(2024, 5, 3, 14, 0, 5, 123456),
        ),
        ("2024-05-03T14:00:05Z", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=UTC)),
        ("2024-05-03 14:00:05 +02:00", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=tz(2))),
        (
            "2024-05-03T14:00:05-0530",
            dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=tz(-5.5)),
        ),
        ("2024-05-03 14:00:05 -5", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=tz(-5))),
    ],
)
def test_dates_and_timestamps(text, expected):
    value = value_of(text)
    assert value == expected
    assert type(value) is type(expected)
    if isinstance(expected, dt.datetime):
        assert value.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize(
    "text",
    ["'123'", '"true"', '"~"', "'2024-05-03'", '"1.5"', "'null'", '""', "''"],
)
def test_quoted_scalars_are_always_strings(text):
    assert value_of(text) == text[1:-1]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (r'"a\tb"', "a\tb"),
        (r'"line\nbreak"', "line\nbreak"),
        (r'"quote \" inside"', 'quote " inside'),
        (r'"back\\slash"', "back\\slash"),
        (r'"slash\/ok"', "slash/ok"),
        (r'"nul\0"', "nul\0"),
        (r'"\a\b\v\f\r\e"', "\x07\x08\x0b\x0c\r\x1b"),
        (r'"\x41\u00e9\U0001F600"', "Aé😀"),
        (r'"\ud83d\ude00"', "😀"),
        (r'"nbsp\_next\N"', "nbsp\xa0next\x85"),
        (r'"\L\P"', "\u2028\u2029"),
        (r'"esc\ space"', "esc space"),
        ('"keeps # hash"', "keeps # hash"),
        ('"keeps: colon"', "keeps: colon"),
        ("\"it's\"", "it's"),
    ],
)
def test_double_quoted_escapes(text, expected):
    assert value_of(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("'it''s'", "it's"),
        ("''''", "'"),
        (r"'no \n escapes'", r"no \n escapes"),
        ("'say \"hi\"'", 'say "hi"'),
        ("'  padded  '", "  padded  "),
        ("'# not a comment'", "# not a comment"),
    ],
)
def test_single_quoted(text, expected):
    assert value_of(text) == expected


def test_quoted_scalars_fold_line_breaks():
    doc = 'v: "first\n  second\n\n  third"\n'
    assert yamlite.loads(doc) == {"v": "first second\nthird"}
    doc = "v: 'one  \n   two'\n"
    assert yamlite.loads(doc) == {"v": "one two"}


def test_escaped_line_break_joins_without_a_space():
    doc = 'v: "long\\\n   word"\n'
    assert yamlite.loads(doc) == {"v": "longword"}


def test_plain_scalars_fold_over_lines():
    doc = "v: one\n  two\n\n  three\nnext: 1\n"
    assert yamlite.loads(doc) == {"v": "one two\nthree", "next": 1}


def test_folded_plain_scalar_is_not_resolved_piecewise():
    assert yamlite.loads("v: 1\n  2\n") == {"v": "1 2"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("!!str 123", "123"),
        ("!!str true", "true"),
        ("!!str", ""),
        ("!!str 2024-05-03", "2024-05-03"),
        ("! 12", "12"),
        ("!!int '42'", 42),
        ('!!int "0x10"', 16),
        ("!!float 3", 3.0),
        ("!!float '1e2'", 100.0),
        ("!!bool 'true'", True),
        ("!!null ''", None),
        ("!!timestamp '2024-05-03'", dt.date(2024, 5, 3)),
        ("!<tag:yaml.org,2002:str> 7", "7"),
    ],
)
def test_explicit_tags(text, expected):
    value = value_of(text)
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("!!int abc", 'cannot read "abc" as !!int'),
        ("!!float nope", "as !!float"),
        ("!!bool yes", "as !!bool"),
        ("!!python/object:os.system x", "unsupported tag"),
        ("!custom x", "unsupported tag"),
        ("!!seq x", "cannot be applied to a scalar"),
        ("!!map [1]", "cannot be applied to a sequence"),
    ],
)
def test_bad_tags(text, fragment):
    with pytest.raises(YamlError, match=fragment):
        value_of(text)


def test_collection_tags_are_accepted_when_they_fit():
    assert yamlite.loads("v: !!seq [1, 2]\nm: !!map {a: 1}\n") == {
        "v": [1, 2],
        "m": {"a": 1},
    }


def test_top_level_scalars():
    assert yamlite.loads("just text") == "just text"
    assert yamlite.loads("42") == 42
    assert yamlite.loads('"quoted"\n') == "quoted"
    assert yamlite.loads("--- 2024-05-03\n") == dt.date(2024, 5, 3)


def test_resolve_is_usable_on_its_own():
    assert resolve("12") == 12
    assert resolve("twelve") == "twelve"
    assert resolve("") is None
