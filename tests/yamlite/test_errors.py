from __future__ import annotations

import pytest

from inkstone import yamlite
from inkstone.errors import InkstoneError
from inkstone.yamlite import YamlError


@pytest.mark.parametrize(
    ("text", "line", "column", "fragment"),
    [
        ("a: b: c\n", 1, 5, "mapping values are not allowed here"),
        ("title: Hello: world\n", 1, 13, "needs quotes"),
        ('a: "unclosed\n', 1, 4, "unclosed quoted string"),
        ("ok: 1\nbad: 'never closed\nmore: 2\n", 2, 6, "unclosed quoted string"),
        ("a:\n  b: 1\n c: 2\n", 3, 2, "inconsistent indentation"),
        ("  - a\n- b\n", 2, 1, "inconsistent indentation"),
        ("- a: 1\n   b: 2\n", 2, 5, "mapping values are not allowed here"),
        ("a: 1\n\tb: 2\n", 2, 1, "tabs cannot be used for indentation"),
        ("a:\n  b: 1\n  \tc: 2\n", 3, 3, "tabs cannot be used for indentation"),
        ("a: 1\nb: 2\na: 3\n", 3, 1, r'duplicate key "a" \(first used on line 1\)'),
        ("x:\n  k: 1\n  k: 2\n", 3, 3, 'duplicate key "k"'),
        ("{a: 1, a: 2}\n", 1, 8, 'duplicate key "a"'),
        ("1: a\n1: b\n", 2, 1, "duplicate key 1 "),
        ("a: *missing\n", 1, 4, 'undefined alias "missing"'),
        ("a: &x\n  b: *x\n", 2, 6, 'undefined alias "x"'),
        ("- a\nb: 1\n", 2, 1, "expected a sequence entry"),
        ("a: 1\n- b\n", 2, 1, "expected a mapping key"),
        ("a: 1\njust text\nb: 2\n", 2, 1, "missing ':' after mapping key"),
        ("a: 1\nb\n", 2, 1, "missing ':' after mapping key"),
        ("key: - a\n", 1, 6, "sequence entries are not allowed here"),
        ("[a, b\n", 1, 1, r"flow sequence is never closed \(missing '\]'\)"),
        ("x: {a: 1\n", 1, 4, r"flow mapping is never closed \(missing '\}'\)"),
        ("a: [1, 2\nb: 3\n", 2, 2, r"expected ',' or '\]'"),
        ("a: ]\n", 1, 4, r"unexpected '\]' outside of a flow collection"),
        ("a: 1\n}\n", 2, 1, r"unexpected '\}' outside of a flow collection"),
        ("a: , b\n", 1, 4, "unexpected ',' outside of a flow collection"),
        ("[a,, b]\n", 1, 4, "empty entry"),
        ("[- a]\n", 1, 2, "not allowed inside flow collections"),
        ("{: 1}\n", 1, 2, "missing mapping key"),
        (": 1\n", 1, 1, "missing mapping key"),
        ("[a,\n---\nb]\n", 2, 1, "inside an unclosed flow collection"),
        ("? a\n: b\n", 1, 1, "complex keys"),
        ("[a]: b\n", 1, 1, "only scalars can be used as mapping keys"),
        ("{a: 1}: b\n", 1, 1, "only scalars can be used as mapping keys"),
        ("%YAML 1.2\n---\na: 1\n", 1, 1, "directives"),
        ("a: !local 1\n", 1, 4, 'unsupported tag "!local"'),
        ("a: !!set {x}\n", 1, 4, 'unsupported tag "!!set"'),
        ("a: !<unclosed\n", 1, 4, "unclosed '!<'"),
        ('a: "\\q"\n', 1, 5, r"unknown escape sequence '\\q'"),
        ('a: "\\x4"\n', 1, 5, "expected 2 hexadecimal digits"),
        ('a: "\\uZZZZ"\n', 1, 5, "expected 4 hexadecimal digits"),
        ('a: "\\UFFFFFFFF"\n', 1, 5, "not a valid code point"),
        ("a: |x\n  text\n", 1, 5, "unexpected text after block scalar indicator"),
        ("a: |0\n  text\n", 1, 5, "between 1 and 9"),
        ("a: @home\n", 1, 4, "cannot start with '@'"),
        ("a: `cmd`\n", 1, 4, "cannot start with '`'"),
        ("a: %50\n", 1, 4, "cannot start with '%'"),
        ("a: &\n", 1, 4, "expected a name right after '&'"),
        ("a: *bold* text\n", 1, 9, "in alias name"),
        ("a: &x &y 1\n", 1, 7, "two anchors"),
        ("a: !!str !!int 1\n", 1, 10, "two tags"),
        ("a: &x *x\n", 1, 7, "alias cannot take an anchor"),
        ("[a, |\n  b]\n", 1, 5, "block scalars are not allowed inside flow"),
        ('a: "one\n---\nb: 2\n', 1, 4, "unclosed quoted string"),
        ("a: 1\n...\nb: 2\n--- x\n---\n- [\n", 6, 3, "never closed"),
        ('"a":1\n', 1, 4, "expected the end of the document"),
        ("[a]\n[b]\n", 2, 1, "expected the end of the document"),
    ],
)
def test_error_positions(text, line, column, fragment):
    with pytest.raises(YamlError, match=fragment) as info:
        yamlite.load_all(text)
    assert (info.value.line, info.value.column) == (line, column)


def test_error_message_includes_position():
    with pytest.raises(YamlError) as info:
        yamlite.loads("a: 1\nb: [1,\n")
    error = info.value
    assert str(error).endswith("(line 2, column 4)")
    assert error.problem == "flow sequence is never closed (missing ']')"
    assert "line" not in error.problem


def test_yaml_error_is_an_inkstone_error_with_optional_path():
    error = YamlError("bad thing", line=3, column=7, path="data/site.yaml")
    assert isinstance(error, InkstoneError)
    assert error.path == "data/site.yaml"
    assert str(error) == "data/site.yaml:3: bad thing (line 3, column 7)"
    assert str(YamlError("no position")) == "no position"
    assert str(YamlError("line only", line=2)) == "line only (line 2)"


def test_error_in_second_document_reports_absolute_line():
    with pytest.raises(YamlError) as info:
        yamlite.load_all("a: 1\n---\nb: 2\nb: 3\n")
    assert info.value.line == 4


def test_loads_ignores_errors_after_the_first_document():
    assert yamlite.loads("a: 1\n---\nb: [\n") == {"a": 1}


def test_crlf_does_not_shift_line_numbers():
    with pytest.raises(YamlError) as info:
        yamlite.loads("a: 1\r\nb: 2\r\nc: x: y\r\n")
    assert (info.value.line, info.value.column) == (3, 5)


def test_long_scalars_are_shortened_in_messages():
    with pytest.raises(YamlError) as info:
        yamlite.loads("[a]\n" + "y" * 60 + "\n")
    assert info.value.problem.endswith('found the scalar "' + "y" * 21 + '..."')


def test_deep_nesting_fails_cleanly():
    with pytest.raises(YamlError, match="nested too deeply"):
        yamlite.loads("[" * 5000)


def test_self_referencing_anchor_is_an_error():
    with pytest.raises(YamlError, match="undefined alias"):
        yamlite.loads("a: &a [*a]\n")
