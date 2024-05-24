from __future__ import annotations

import pytest

from inkstone.yamlite import YamlError
from inkstone.yamlite import scanner as s
from inkstone.yamlite.scanner import Scanner, tokenize


def kinds(text):
    return [tok.kind for tok in tokenize(text)][1:-1]


def scalars(text):
    return [(tok.value, tok.style) for tok in tokenize(text) if tok.kind == s.SCALAR]


def test_empty_input_is_just_the_stream_markers():
    assert [tok.kind for tok in tokenize("")] == [s.STREAM_START, s.STREAM_END]
    assert kinds("# nothing but a comment\n\n") == []


def test_block_mapping_tokens():
    assert kinds("a: 1\nb: 2\n") == [
        s.BLOCK_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.SCALAR,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.SCALAR,
        s.BLOCK_END,
    ]


def test_nested_blocks_close_in_order():
    assert kinds("a:\n  - x\n  - y\n") == [
        s.BLOCK_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.BLOCK_SEQUENCE_START,
        s.BLOCK_ENTRY,
        s.SCALAR,
        s.BLOCK_ENTRY,
        s.SCALAR,
        s.BLOCK_END,
        s.BLOCK_END,
    ]


def test_indentless_sequence_has_no_start_token():
    assert kinds("a:\n- x\n") == [
        s.BLOCK_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.BLOCK_ENTRY,
        s.SCALAR,
        s.BLOCK_END,
    ]


def test_flow_collection_tokens():
    assert kinds("[a, {b: c}]") == [
        s.FLOW_SEQUENCE_START,
        s.SCALAR,
        s.FLOW_ENTRY,
        s.FLOW_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.SCALAR,
        s.FLOW_MAPPING_END,
        s.FLOW_SEQUENCE_END,
    ]


def test_document_markers():
    assert kinds("---\na\n...\n---\nb\n") == [
        s.DOCUMENT_START,
        s.SCALAR,
        s.DOCUMENT_END,
        s.DOCUMENT_START,
        s.SCALAR,
    ]


def test_dashes_inside_a_line_are_not_a_document_marker():
    assert kinds("a: ---\n") == [
        s.BLOCK_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.SCALAR,
        s.BLOCK_END,
    ]
    assert scalars("---x\n") == [("---x", None)]


def test_anchor_alias_and_tag_tokens():
    tokens = tokenize("a: &ref !!str x\nb: *ref\n")
    found = [(tok.kind, tok.value) for tok in tokens if tok.value is not None]
    assert found == [
        (s.SCALAR, "a"),
        (s.ANCHOR, "ref"),
        (s.TAG, "!!str"),
        (s.SCALAR, "x"),
        (s.SCALAR, "b"),
        (s.ALIAS, "ref"),
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("plain text", [("plain text", None)]),
        ("'single'", [("single", "'")]),
        ('"double"', [("double", '"')]),
        ("|\n  literal\n", [("literal\n", "|")]),
        (">\n  folded\n  text\n", [("folded text\n", ">")]),
        ("a: b # trailing comment", [("a", None), ("b", None)]),
        ("a#b: c#d", [("a#b", None), ("c#d", None)]),
        (
            "url: http://example.com/x?y=1",
            [("url", None), ("http://example.com/x?y=1", None)],
        ),
        ("- -1\n- -x", [("-1", None), ("-x", None)]),
        ("a:\tb", [("a", None), ("b", None)]),
    ],
)
def test_scalar_values_and_styles(text, expected):
    assert scalars(text) == expected


def test_token_positions_are_zero_based():
    tokens = tokenize("a:\n  bee: 1\n")
    nested_key = [tok for tok in tokens if tok.kind == s.SCALAR][1]
    assert (nested_key.value, nested_key.line, nested_key.column) == ("bee", 1, 2)
    value = [tok for tok in tokens if tok.kind == s.SCALAR][2]
    assert (value.line, value.column) == (1, 7)


def test_key_token_carries_the_position_of_the_key():
    tokens = tokenize("first: 1\nsecond: 2\n")
    keys = [(tok.line, tok.column) for tok in tokens if tok.kind == s.KEY]
    assert keys == [(0, 0), (1, 0)]


def test_crlf_and_bom_are_normalised():
    assert scalars("\ufeffa: 1\r\nb: 2\r\n") == [
        ("a", None),
        ("1", None),
        ("b", None),
        ("2", None),
    ]
    assert tokenize("a: 1\r\nb: 2\r\n")[-2].line == 2


def test_peek_does_not_consume_and_end_token_repeats():
    scanner = Scanner("x")
    assert scanner.peek().kind == s.STREAM_START
    assert scanner.next().kind == s.STREAM_START
    assert scanner.check(s.SCALAR)
    assert scanner.next().value == "x"
    assert scanner.next().kind == s.STREAM_END
    assert scanner.next().kind == s.STREAM_END


def test_json_style_key_without_space_before_value():
    assert kinds('{"a":1}') == [
        s.FLOW_MAPPING_START,
        s.KEY,
        s.SCALAR,
        s.VALUE,
        s.SCALAR,
        s.FLOW_MAPPING_END,
    ]


def test_colon_inside_flow_plain_scalar_is_kept():
    assert scalars("[a:b, http://x.y/z]") == [("a:b", None), ("http://x.y/z", None)]


def test_long_text_before_colon_is_not_a_key():
    # simple keys are capped at 1024 characters
    text = "x" * 1100 + ": value"
    with pytest.raises(YamlError, match="mapping values are not allowed"):
        tokenize(text)


def test_control_characters_are_rejected_up_front():
    with pytest.raises(YamlError) as info:
        tokenize("a: 1\nb: \x01\n")
    assert (info.value.line, info.value.column) == (2, 4)


def test_token_repr_shows_one_based_position():
    token = tokenize("key: v")[2]
    assert repr(token) == "<key at 1:1>"
