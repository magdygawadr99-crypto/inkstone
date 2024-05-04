from __future__ import annotations

import pytest

from inkstone.tmpl import TemplateSyntaxError
from inkstone.tmpl.lexer import (
    BLOCK_BEGIN,
    BLOCK_END,
    DATA,
    EOF,
    FLOAT,
    INTEGER,
    NAME,
    OP,
    OPERATORS,
    STRING,
    VARIABLE_BEGIN,
    VARIABLE_END,
    Token,
    TokenStream,
    tokenize,
)


def kinds(source, **options):
    return [token.type for token in tokenize(source, **options)]


def data(source, **options):
    return [t.value for t in tokenize(source, **options) if t.type == DATA]


def expression_tokens(source):
    tokens = tokenize("{{ " + source + " }}")
    return [(t.type, t.value) for t in tokens[1:-2]]


def test_plain_text_is_a_single_data_token():
    assert tokenize("hello world") == [
        Token(DATA, "hello world", 1),
        Token(EOF, None, 1),
    ]


def test_empty_source_is_just_eof():
    assert kinds("") == [EOF]


def test_variable_tag():
    assert kinds("a {{ b }} c") == [
        DATA,
        VARIABLE_BEGIN,
        NAME,
        VARIABLE_END,
        DATA,
        EOF,
    ]


def test_block_tag():
    tokens = tokenize("{% if user %}")
    assert [(t.type, t.value) for t in tokens[:-1]] == [
        (BLOCK_BEGIN, "{%"),
        (NAME, "if"),
        (NAME, "user"),
        (BLOCK_END, "%}"),
    ]


def test_tags_without_inner_spaces():
    assert kinds("{{b}}{%if x%}") == [
        VARIABLE_BEGIN,
        NAME,
        VARIABLE_END,
        BLOCK_BEGIN,
        NAME,
        NAME,
        BLOCK_END,
        EOF,
    ]


def test_comment_leaves_no_tokens_and_data_is_merged():
    assert data("a{# hidden {{ x }} #}b") == ["ab"]


def test_single_braces_are_just_text():
    assert data("body { color: red } {x}") == ["body { color: red } {x}"]


def test_every_operator_is_one_token():
    source = "** // == != <= >= + - * / % ~ < > = . , : | ( ) [ ] { }"
    tokens = expression_tokens(source)
    assert [value for _, value in tokens] == source.split()
    assert {kind for kind, _ in tokens} == {OP}
    assert sorted(source.split()) == sorted(OPERATORS)


def test_two_character_operators_are_not_split():
    assert expression_tokens("a ** b // c <= d != e") == [
        (NAME, "a"),
        (OP, "**"),
        (NAME, "b"),
        (OP, "//"),
        (NAME, "c"),
        (OP, "<="),
        (NAME, "d"),
        (OP, "!="),
        (NAME, "e"),
    ]


@pytest.mark.parametrize(
    "source, kind, value",
    [
        ("42", INTEGER, 42),
        ("007", INTEGER, 7),
        ("1_000_000", INTEGER, 1000000),
        ("0x1F", INTEGER, 31),
        ("0o17", INTEGER, 15),
        ("0b101", INTEGER, 5),
        ("3.14", FLOAT, 3.14),
        ("1e3", FLOAT, 1000.0),
        ("2.5e-1", FLOAT, 0.25),
        ("1_0.5", FLOAT, 10.5),
    ],
)
def test_number_literals(source, kind, value):
    assert expression_tokens(source) == [(kind, value)]


def test_number_after_a_dot_is_an_index_not_a_float():
    assert expression_tokens("rows.0.1") == [
        (NAME, "rows"),
        (OP, "."),
        (INTEGER, 0),
        (OP, "."),
        (INTEGER, 1),
    ]


@pytest.mark.parametrize(
    "source, value",
    [
        ("'abc'", "abc"),
        ('"abc"', "abc"),
        ("''", ""),
        (r"'it\'s'", "it's"),
        ('\'say "hi"\'', 'say "hi"'),
        (r'"a\nb\tc"', "a\nb\tc"),
        (r'"back\\slash"', "back\\slash"),
        (r'"\x41\u00e9"', "Aé"),
        (r'"\U0001F600"', "\U0001f600"),
        (r'"\q stays"', "\\q stays"),
        ('"café"', "café"),
    ],
)
def test_string_literals(source, value):
    assert expression_tokens(source) == [(STRING, value)]


def test_strings_may_contain_tag_delimiters():
    assert expression_tokens('"}}" ~ "%}" ~ "{#"') == [
        (STRING, "}}"),
        (OP, "~"),
        (STRING, "%}"),
        (OP, "~"),
        (STRING, "{#"),
    ]


def test_closing_braces_of_nested_dicts_do_not_end_the_tag():
    tokens = tokenize('{{ {"a": {"b": 1}} }}')
    assert [t.value for t in tokens[-4:-1]] == ["}", "}", "}}"]
    assert tokens[-2].type == VARIABLE_END


def test_unicode_names():
    assert expression_tokens("größe") == [(NAME, "größe")]


def test_line_numbers():
    tokens = tokenize("a\n{{ b }}\n{% if c %}\n{{ d\n| e }}")
    lines = {t.value: t.lineno for t in tokens if t.type == NAME}
    assert lines == {"b": 2, "if": 3, "c": 3, "d": 4, "e": 5}


def test_line_numbers_after_multiline_comment_and_string():
    tokens = tokenize("{# one\ntwo\nthree #}{{ 'a\nb' }}\n{{ x }}")
    assert [t.lineno for t in tokens if t.type == VARIABLE_BEGIN] == [3, 5]


def test_data_token_knows_its_first_line():
    tokens = tokenize("{{ a }}\n\nsecond\nthird{{ b }}")
    assert tokens[3] == Token(DATA, "\n\nsecond\nthird", 1)
    assert tokens[4].lineno == 4


def test_line_numbers_survive_whitespace_control():
    tokens = tokenize("{% if a -%}\n\n\n{{ b }}\n{%- endif %}")
    lines = {t.value: t.lineno for t in tokens if t.type == NAME}
    assert lines == {"if": 1, "a": 1, "b": 4, "endif": 5}


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a  {%- if x %}  b", ["a", "  b"]),
        ("a  {% if x -%}  b", ["a  ", "b"]),
        ("a \n {%- if x -%} \n b", ["a", "b"]),
        ("a  {{- x }}  b", ["a", "  b"]),
        ("a  {{ x -}}  b", ["a  ", "b"]),
        ("a  {#- note -#}  b", ["ab"]),
        ("a  {#- note #}  b", ["a  b"]),
    ],
)
def test_minus_sign_strips_whitespace(source, expected):
    assert data(source) == expected


def test_minus_before_the_end_is_not_a_subtraction():
    assert expression_tokens("a") == [(NAME, "a")]
    tokens = tokenize("{{ a -}}")
    assert [t.type for t in tokens] == [VARIABLE_BEGIN, NAME, VARIABLE_END, EOF]


def test_minus_inside_expression_is_still_an_operator():
    assert expression_tokens("a -b") == [(NAME, "a"), (OP, "-"), (NAME, "b")]


def test_trim_blocks_removes_the_newline_after_a_block_tag():
    source = "{% if x %}\nfoo\n{% endif %}\nbar"
    assert data(source) == ["\nfoo\n", "\nbar"]
    assert data(source, trim_blocks=True) == ["foo\n", "bar"]


def test_trim_blocks_only_takes_one_newline():
    assert data("{% if x %}\n\nfoo", trim_blocks=True) == ["\nfoo"]


def test_trim_blocks_leaves_variable_tags_alone():
    assert data("{{ x }}\nfoo", trim_blocks=True) == ["\nfoo"]


def test_trim_blocks_applies_to_comments():
    assert data("{# note #}\nfoo", trim_blocks=True) == ["foo"]


def test_plus_sign_overrides_trim_blocks():
    assert data("{% if x +%}\nfoo", trim_blocks=True) == ["\nfoo"]


def test_lstrip_blocks_removes_indentation_before_a_block_tag():
    source = "  {% if x %}\n    foo\n  {% endif %}"
    assert data(source) == ["  ", "\n    foo\n  "]
    assert data(source, lstrip_blocks=True) == ["\n    foo\n"]


def test_lstrip_blocks_needs_the_tag_to_start_the_line():
    assert data("a  {% if x %}", lstrip_blocks=True) == ["a  "]
    assert data("{{ a }}  {% if x %}", lstrip_blocks=True) == ["  "]


def test_lstrip_blocks_leaves_variable_tags_alone():
    assert data("  {{ x }}", lstrip_blocks=True) == ["  "]


def test_lstrip_blocks_applies_to_comments():
    assert data("x\n  {# note #}y", lstrip_blocks=True) == ["x\ny"]


def test_plus_sign_overrides_lstrip_blocks():
    assert data("  {%+ if x %}", lstrip_blocks=True) == ["  "]


def test_trim_and_lstrip_together_make_tags_vanish():
    source = "<ul>\n  {% for x in xs %}\n  <li>{{ x }}</li>\n  {% endfor %}\n</ul>"
    assert data(source, trim_blocks=True, lstrip_blocks=True) == [
        "<ul>\n",
        "  <li>",
        "</li>\n",
        "</ul>",
    ]


def test_raw_block_is_plain_data():
    assert tokenize("{% raw %}{{ x }} {% if %}{# c #}{% endraw %}") == [
        Token(DATA, "{{ x }} {% if %}{# c #}", 1),
        Token(EOF, None, 1),
    ]


def test_raw_block_whitespace_control():
    assert data("a {%- raw -%} {{ x }} {%- endraw -%} b") == ["a{{ x }}b"]
    assert data("a {% raw %} {{ x }} {% endraw %} b") == ["a  {{ x }}  b"]


def test_raw_block_with_trim_blocks():
    source = "{% raw %}\n{{ x }}\n{% endraw %}\nend"
    assert data(source, trim_blocks=True) == ["{{ x }}\nend"]


def test_line_numbers_after_raw_block():
    tokens = tokenize("{% raw %}\n\n{% endraw %}\n{{ x }}")
    assert tokens[1].type == VARIABLE_BEGIN
    assert tokens[1].lineno == 4


def test_newlines_are_normalised():
    assert data("a\r\nb\rc\n\nd") == ["a\nb\nc\n\nd"]


def test_single_trailing_newline_is_dropped_by_default():
    assert data("line\n") == ["line"]
    assert data("line\n\n") == ["line\n"]
    assert data("line\n", keep_trailing_newline=True) == ["line\n"]


@pytest.mark.parametrize(
    "source, message, line",
    [
        ("{{ a", "unclosed '{{'", 1),
        ("a\n{% if x", "unclosed '{%'", 2),
        ("a\n\n{{ b\n\n", "unclosed '{{'", 3),
        ("{# never ends", "unclosed comment", 1),
        ("x\n{% raw %} foo", "unclosed raw block", 2),
        ("{{ 'abc }}", "unterminated string", 1),
        ("{{ a $ b }}", "unexpected character '$'", 1),
        ("{{ a && b }}", "use 'and'", 1),
        ("{{ !a }}", "use 'not'", 1),
        ("{{ (a] }}", "unexpected ']', expected ')'", 1),
        ("{{ a) }}", "unexpected ')'", 1),
        ("\n\n{{ foo(1 }}", "expected ')'", 3),
    ],
)
def test_lexer_errors(source, message, line):
    with pytest.raises(TemplateSyntaxError) as excinfo:
        tokenize(source, "page.html")
    assert message in excinfo.value.message
    assert excinfo.value.line == line
    assert excinfo.value.path == "page.html"


def test_stray_closing_delimiters_are_text():
    assert data("a }} b %} c #}") == ["a }} b %} c #}"]


def test_token_stream_look_and_next():
    stream = TokenStream(tokenize("{{ a.b }}"))
    assert stream.current.type == VARIABLE_BEGIN
    assert stream.look().value == "a"
    assert stream.look(2).value == "."
    stream.skip(2)
    assert stream.current.value == "."
    assert stream.look(100).type == EOF


def test_token_stream_stays_on_eof():
    stream = TokenStream(tokenize(""))
    assert stream.next().type == EOF
    assert stream.next().type == EOF


def test_token_stream_skip_helpers():
    stream = TokenStream(tokenize("{{ not a + b }}"))
    stream.next()
    assert not stream.skip_name("and")
    assert stream.skip_name("not")
    assert stream.at_name("a", "b")
    stream.next()
    assert not stream.skip_op("-")
    assert stream.at_op("+", "-")
    assert stream.skip_op("+")


def test_token_stream_expect_describes_what_it_found():
    stream = TokenStream(tokenize("{{ 'text' }}"), "page.html")
    stream.next()
    with pytest.raises(TemplateSyntaxError) as excinfo:
        stream.expect(NAME)
    assert excinfo.value.message == "expected a name, got string 'text'"
    with pytest.raises(TemplateSyntaxError, match="expected ':', got string"):
        stream.expect_op(":")
    assert stream.expect(STRING).value == "text"
    assert stream.expect(VARIABLE_END)
