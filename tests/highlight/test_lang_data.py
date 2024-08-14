from __future__ import annotations

import pytest

from inkstone.highlight.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)

from .helpers import type_of, types_of, visible


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ('{"key": "value"}', '"key"', Name.Tag),
        ('{"key": "value"}', '"value"', String),
        ('{"key" : 1}', '"key"', Name.Tag),
        ('["a", "b"]', '"a"', String),
        ('{"n": 42}', "42", Number.Integer),
        ('{"n": -42}', "-42", Number.Integer),
        ('{"n": 1.5}', "1.5", Number.Float),
        ('{"n": 2e10}', "2e10", Number.Float),
        ('{"n": -1.5E-3}', "-1.5E-3", Number.Float),
        ('{"b": true}', "true", Keyword.Constant),
        ('{"b": null}', "null", Keyword.Constant),
        ('{"a": 1} // why', "// why", Comment.Single),
        ('/* c */ {"a": 1}', "/* c */", Comment.Multiline),
        ('{"a": [1, 2]}', "[", Punctuation),
    ],
)
def test_json_tokens(code, text, expected):
    assert type_of("json", code, text) is expected


def test_json_string_escapes():
    assert visible("json", '"a\\n\\"b\\u00e9"') == [
        (String, '"a'),
        (String.Escape, '\\n\\"'),
        (String, "b"),
        (String.Escape, "\\u00e9"),
        (String, '"'),
    ]


def test_json_bare_words_are_errors():
    tokens = visible("json", '{"a": undefined, "b": True}')
    assert (Error, "undefined") in tokens
    assert (Error, "True") in tokens


def test_json_lines():
    tokens = visible("json", '{"a": 1}\n{"a": 2}\n')
    assert tokens.count((Name.Tag, '"a"')) == 2


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("# note\nx = 1", "# note", Comment.Single),
        ("x = 1 # note", "# note", Comment.Single),
        ("title = 'x'", "title", Name.Attribute),
        ("title = 'x'", "=", Operator),
        ("title = 'x'", "'x'", String),
        ('"my key" = 1', '"my key"', Name.Attribute),
        ("a.b.c = 1", "c", Name.Attribute),
        ("a.b.c = 1", ".", Punctuation),
        ("[tool.pytest]", "tool.pytest", Name.Namespace),
        ("[[servers]]", "[[", Punctuation),
        ("[[servers]]", "servers", Name.Namespace),
        ("x = 42", "42", Number.Integer),
        ("x = +1_000", "+1_000", Number.Integer),
        ("x = 0xdead_BEEF", "0xdead_BEEF", Number.Hex),
        ("x = 0o755", "0o755", Number.Oct),
        ("x = 0b1101", "0b1101", Number.Bin),
        ("x = 3.14", "3.14", Number.Float),
        ("x = 5e+22", "5e+22", Number.Float),
        ("x = -inf", "-inf", Number.Float),
        ("x = nan", "nan", Number.Float),
        ("x = true", "true", Keyword.Constant),
        ("d = 1979-05-27", "1979-05-27", Literal.Date),
        ("d = 1979-05-27T07:32:00Z", "1979-05-27T07:32:00Z", Literal.Date),
        ("d = 1979-05-27 07:32:00.5Z", "1979-05-27 07:32:00.5Z", Literal.Date),
        ("d = 1979-05-27T07:32:00+01:00", "1979-05-27T07:32:00+01:00", Literal.Date),
        ("t = 07:32:00", "07:32:00", Literal.Date),
        ("x = [1, 2]", "[", Punctuation),
    ],
)
def test_toml_tokens(code, text, expected):
    assert type_of("toml", code, text) is expected


def test_toml_basic_strings_have_escapes_and_literal_strings_do_not():
    assert (String.Escape, "\\t") in visible("toml", 'x = "a\\tb"')
    assert visible("toml", "x = 'a\\tb'")[-1] == (String, "'a\\tb'")


def test_toml_multiline_strings():
    code = 'a = """\nfirst \\\n   second "quoted"\n"""\nb = 1\n'
    tokens = visible("toml", code)
    assert tokens[2][0] is String
    assert (String.Escape, "\\\n   ") in tokens
    assert tokens[-2:] == [(Operator, "="), (Number.Integer, "1")]
    assert tokens[-3] == (Name.Attribute, "b")
    literal = visible("toml", "a = '''\nraw \\n\n'''\nb = 2\n")
    assert literal[2] == (String, "'''\nraw \\n\n'''")


def test_toml_multiline_array_is_not_a_table_header():
    code = "ports = [\n  [1, 2],\n  [3],\n]\n[next]\n"
    assert types_of("toml", code, "1") == [Number.Integer]
    tokens = visible("toml", code)
    assert [text for ttype, text in tokens if ttype is Name.Namespace] == ["next"]


def test_toml_inline_table():
    tokens = visible("toml", 'p = { x = 1.5, "y z" = [true], name = "n" }')
    assert (Name.Attribute, "x") in tokens
    assert (Number.Float, "1.5") in tokens
    assert (Name.Attribute, '"y z"') in tokens
    assert (Keyword.Constant, "true") in tokens
    assert (String, '"n"') in tokens


def test_toml_unterminated_string_does_not_swallow_the_next_line():
    assert type_of("toml", 'a = "oops\nb = 1\n', "b") is Name.Attribute


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("key: value", "key", Name.Tag),
        ("key: value", ":", Punctuation),
        ("key: value", "value", String),
        ("key: some longer value", "some longer value", String),
        ("two words: x", "two words", Name.Tag),
        ('"quoted": x', '"quoted"', Name.Tag),
        ("# note", "# note", Comment.Single),
        ("a: b # note", "# note", Comment.Single),
        ("a: b#c", "b#c", String),
        ("url: http://x.y:80/z", "http://x.y:80/z", String),
        ("n: 42", "42", Number.Integer),
        ("n: -42", "-42", Number.Integer),
        ("n: 3.10", "3.10", Number.Float),
        ("n: 1e5", "1e5", Number.Float),
        ("n: .inf", ".inf", Number.Float),
        ("n: 0x1F", "0x1F", Number.Hex),
        ("n: 0o17", "0o17", Number.Oct),
        ("v: 1.2.3", "1.2.3", String),
        ("v: 42 apples", "42 apples", String),
        ("b: true", "true", Keyword.Constant),
        ("b: No", "No", Keyword.Constant),
        ("b: ~", "~", Keyword.Constant),
        ("b: null", "null", Keyword.Constant),
        ("b: nullable", "nullable", String),
        ("d: 2024-03-01", "2024-03-01", Literal.Date),
        ("d: 2024-03-01T10:30:00Z", "2024-03-01T10:30:00Z", Literal.Date),
        ("- item", "-", Punctuation),
        ("- item", "item", String),
        ("- -5", "-5", Number.Integer),
        ("a: &anchor x", "&anchor", Name.Label),
        ("a: *anchor", "*anchor", Name.Variable),
        ("a: !!str 1", "!!str", Keyword.Type),
        ("a: !Custom x", "!Custom", Keyword.Type),
        ("--- \na: 1", "---", Name.Namespace),
        ("%YAML 1.2\n---", "%YAML 1.2", Comment.Preproc),
        ("<<: *base", "<<", Name.Tag),
    ],
)
def test_yaml_tokens(code, text, expected):
    assert type_of("yaml", code, text) is expected


def test_yaml_quoted_strings():
    double = visible("yaml", r'a: "x\ty\"z"')
    assert (String.Escape, r"\t") in double and (String.Escape, r"\"") in double
    single = visible("yaml", "a: 'it''s'")
    assert single[2:] == [(String, "'it"), (String.Escape, "''"), (String, "s'")]


def test_yaml_flow_collections():
    tokens = visible("yaml", "a: [1, two, {k: v, n: 3.5}, 'q'] # c")
    assert (Number.Integer, "1") in tokens
    assert (String, "two") in tokens
    assert (Name.Tag, "k") in tokens and (String, "v") in tokens
    assert (Number.Float, "3.5") in tokens
    assert tokens[-1] == (Comment.Single, "# c")


def test_yaml_literal_block_scalar():
    code = "script: |\n  echo: not a key\n  # not a comment\n\n  last\nnext: 1\n"
    tokens = visible("yaml", code)
    assert tokens[:3] == [(Name.Tag, "script"), (Punctuation, ":"), (Punctuation, "|")]
    assert tokens[3] == (String, "  echo: not a key\n  # not a comment\n\n  last\n")
    assert tokens[4:] == [(Name.Tag, "next"), (Punctuation, ":"), (Number.Integer, "1")]


@pytest.mark.parametrize("indicator", ["|", ">", "|-", ">+", "|2", ">-  # why"])
def test_yaml_block_scalar_indicators(indicator):
    code = f"a: {indicator}\n    text: here\nb: 1\n"
    tokens = visible("yaml", code)
    assert (String, "    text: here\n") in tokens
    assert (Name.Tag, "b") in tokens


def test_yaml_block_scalar_in_a_sequence_and_nested_mapping():
    code = "steps:\n  - run: |\n      make all\n      make test\n  - name: next\n"
    tokens = visible("yaml", code)
    assert (String, "      make all\n      make test\n") in tokens
    assert (Name.Tag, "name") in tokens and (String, "next") in tokens


def test_yaml_empty_block_scalar_does_not_eat_siblings():
    tokens = visible("yaml", "a: |\nb: 1\n")
    assert (Name.Tag, "b") in tokens
    assert not [t for t in tokens if t[0] is String]


def test_yaml_pipe_inside_a_value_is_not_a_block_scalar():
    tokens = visible("yaml", "cmd: cat x | grep y\nnext: 1\n")
    assert (String, "cat x | grep y") in tokens
    assert (Name.Tag, "next") in tokens


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("; note", "; note", Comment.Single),
        ("# note", "# note", Comment.Single),
        ("[section]", "section", Name.Namespace),
        ("[two words]", "two words", Name.Namespace),
        ("key = value", "key", Name.Attribute),
        ("key = value", "=", Operator),
        ("key = value", "value", String),
        ("key: value", ":", Operator),
        ("key=value", "value", String),
        ("log file = x", "log file", Name.Attribute),
        ("color = #fff", "#fff", String),
        ("port = 8080", "8080", Number.Integer),
        ("ratio = 0.75", "0.75", Number.Float),
        ("debug = yes", "yes", Keyword.Constant),
        ("debug = False", "False", Keyword.Constant),
        ("mode = yes please", "yes", String),
        ("version = 1.2.3", "1.2.3", String),
        ("x = a ; note", "; note", Comment.Single),
        ("path = a;b", "a;b", String),
        ("url = %(base)s/x", "%(base)s", String.Interpol),
        ("url = ${paths:root}/x", "${paths:root}", String.Interpol),
        ("skip-networking", "skip-networking", Name.Attribute),
    ],
)
def test_ini_tokens(code, text, expected):
    assert type_of("ini", code, text) is expected


def test_ini_continuation_lines_belong_to_the_value():
    code = "deps =\n    requests>=2.0\n    click\nnext = 1\n"
    tokens = visible("ini", code)
    assert (String, "requests>=2.0") in tokens
    assert (String, "click") in tokens
    keys = [text for ttype, text in tokens if ttype is Name.Attribute]
    assert keys == ["deps", "next"]


def test_ini_indented_keys_under_a_section_are_keys():
    code = "[core]\n\teditor = vim\n\tpager = less\n"
    tokens = visible("ini", code)
    assert [text for ttype, text in tokens if ttype is Name.Attribute] == [
        "editor",
        "pager",
    ]


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("SELECT a FROM t", "SELECT", Keyword),
        ("select a from t", "from", Keyword),
        ("SELECT a FROM t", "a", Name),
        ("-- note\nSELECT 1", "-- note", Comment.Single),
        ("SELECT /* c */ 1", "/* c */", Comment.Multiline),
        ("SELECT /* a /* b */ c */ 1", "/* a /* b */ c */", Comment.Multiline),
        ("SELECT 'it''s'", "''", String.Escape),
        ("SELECT 'C:\\' , 1", "1", Number.Integer),
        ('SELECT "my col" FROM t', '"my col"', Name),
        ("SELECT `col` FROM t", "`col`", Name),
        ("SELECT 1.5e3", "1.5e3", Number.Float),
        ("SELECT 0xFF", "0xFF", Number.Hex),
        ("SELECT COUNT(*) FROM t", "COUNT", Name.Function),
        ("SELECT count FROM t", "count", Name),
        ("SELECT coalesce(a, 0)", "coalesce", Name.Function),
        ("CREATE TABLE t (id INTEGER)", "INTEGER", Keyword.Type),
        ("CREATE TABLE t (n varchar(10))", "varchar", Keyword.Type),
        ("WHERE a IS NULL", "NULL", Keyword.Constant),
        ("WHERE a = TRUE", "TRUE", Keyword.Constant),
        ("WHERE a = ?", "?", Name.Variable),
        ("WHERE a = $1", "$1", Name.Variable),
        ("WHERE a = :name", ":name", Name.Variable),
        ("WHERE a = @name", "@name", Name.Variable),
        ("WHERE a = %(name)s", "%(name)s", Name.Variable),
        ("SELECT a::text", "::", Operator),
        ("SELECT a::text", "text", Keyword.Type),
        ("WHERE a <> b", "<>", Operator),
        ("SELECT a->>'k'", "->>", Operator),
        ("SELECT a @> b", "@>", Operator),
        ("SELECT $$ it's $$", "$$ it's $$", String),
        ("SELECT $fn$ a $$ b $fn$", "$fn$ a $$ b $fn$", String),
    ],
)
def test_sql_tokens(code, text, expected):
    assert type_of("sql", code, text) is expected


def test_sql_strings_span_lines():
    tokens = visible("sql", "SELECT 'one\ntwo' AS x")
    assert (String, "'one\ntwo'") in tokens
    assert tokens[-2:] == [(Keyword, "AS"), (Name, "x")]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("diff --git a/x b/x", Generic.Heading),
        ("index 3f1a2b4..9c8d7e6 100644", Generic.Heading),
        ("Index: trunk/x.py", Generic.Heading),
        ("new file mode 100644", Generic.Heading),
        ("rename from old.py", Generic.Heading),
        ("Only in a: x.txt", Generic.Heading),
        ("Binary files a/x.png and b/x.png differ", Generic.Heading),
        ("+added", Generic.Inserted),
        ("-removed", Generic.Deleted),
        ("+", Generic.Inserted),
        ("-", Generic.Deleted),
        ("> added", Generic.Inserted),
        ("< removed", Generic.Deleted),
        ("! changed", Generic.Strong),
        (" context", Text),
        ("\\ No newline at end of file", Comment),
        ("3c3", Generic.Subheading),
        ("5a6,7", Generic.Subheading),
        ("***************", Generic.Subheading),
        ("*** 1,4 ****", Generic.Subheading),
        ("--- 1,4 ----", Generic.Subheading),
        ("---", Punctuation),
        ("--- some deleted text", Generic.Deleted),
    ],
)
def test_diff_lines(line, expected):
    assert visible("diff", f"x\n{line}\ny\n")[1] == (expected, line)


def test_diff_file_header_pair():
    tokens = visible("diff", "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n")
    assert tokens[0] == (Generic.Heading, "--- a/x.py")
    assert tokens[1] == (Generic.Heading, "+++ b/x.py")
    assert tokens[2] == (Generic.Subheading, "@@ -1 +1 @@")
    assert tokens[3:] == [(Generic.Deleted, "-a"), (Generic.Inserted, "+b")]


def test_diff_hunk_header_keeps_its_context_separate():
    tokens = visible("diff", "@@ -10,7 +10,8 @@ def build(site):\n")
    assert tokens == [
        (Generic.Subheading, "@@ -10,7 +10,8 @@"),
        (Text, " def build(site):"),
    ]


def test_diff_context_format_header():
    tokens = visible("diff", "*** a.txt\t2024\n--- b.txt\t2024\n***************\n")
    assert [ttype for ttype, _ in tokens] == [
        Generic.Heading,
        Generic.Heading,
        Generic.Subheading,
    ]
