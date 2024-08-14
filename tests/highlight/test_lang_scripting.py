from __future__ import annotations

import pytest

from inkstone.highlight.token import (
    Comment,
    Keyword,
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
        ("def foo(): pass", "def", Keyword.Declaration),
        ("def foo(): pass", "foo", Name.Function),
        ("def foo(): pass", "pass", Keyword),
        ("def __init__(self): ...", "__init__", Name.Function.Magic),
        ("def __init__(self): ...", "self", Name.Builtin.Pseudo),
        ("def __init__(self): ...", "...", Keyword.Constant),
        ("class Foo(Base): pass", "class", Keyword.Declaration),
        ("class Foo(Base): pass", "Foo", Name.Class),
        ("class Foo(Base): pass", "Base", Name),
        ("async def go(): await x", "async", Keyword),
        ("async def go(): await x", "go", Name.Function),
        ("x = None", "None", Keyword.Constant),
        ("x = True and not y", "and", Operator.Word),
        ("x = True and not y", "not", Operator.Word),
        ("for i in range(3): pass", "in", Operator.Word),
        ("for i in range(3): pass", "range", Name.Builtin),
        ("obj.range(3)", "range", Name),
        ("raise ValueError(x)", "ValueError", Name.Exception),
        ("MAX_SIZE = 10", "MAX_SIZE", Name.Constant),
        ("@app.route('/')\ndef f(): pass", "@app.route", Name.Decorator),
        ("a @ b", "@", Operator),
        ("x: int = 1  # note", "# note", Comment.Single),
        ("#!/usr/bin/python\nx = 1", "#!/usr/bin/python", Comment.Hashbang),
        ("x = y if z else w", "else", Keyword),
        ("x = lambda a: a", "lambda", Keyword),
        ("if (n := len(a)) > 1: pass", ":=", Operator),
        ("def f() -> int: ...", "->", Operator),
        ("__name__", "__name__", Name.Variable.Magic),
    ],
)
def test_python_tokens(code, text, expected):
    assert type_of("python", code, text) is expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("42", Number.Integer),
        ("1_000_000", Number.Integer),
        ("0xDEAD_beef", Number.Hex),
        ("0o777", Number.Oct),
        ("0b1010", Number.Bin),
        ("3.14", Number.Float),
        (".5", Number.Float),
        ("1e-10", Number.Float),
        ("1_0.5e3", Number.Float),
        ("2j", Number.Float),
    ],
)
def test_python_numbers(code, expected):
    assert visible("python", f"x = {code}")[-1] == (expected, code)


def test_python_imports():
    assert visible("python", "import os.path as p, sys") == [
        (Keyword.Namespace, "import"),
        (Name.Namespace, "os.path"),
        (Keyword.Namespace, "as"),
        (Name, "p"),
        (Punctuation, ","),
        (Name.Namespace, "sys"),
    ]
    assert visible("python", "from ..pkg.mod import thing")[:4] == [
        (Keyword.Namespace, "from"),
        (Name.Namespace, "..pkg.mod"),
        (Keyword.Namespace, "import"),
        (Name, "thing"),
    ]


def test_python_from_outside_an_import_is_a_plain_keyword():
    assert type_of("python", "yield from gen()", "from") is Keyword
    assert type_of("python", "yield from gen()", "gen") is Name
    assert type_of("python", "raise A() from err", "err") is Name


def test_python_soft_keywords_only_where_a_statement_starts():
    code = "match command:\n    case [x]:\n        pass\nmatch = 1\ncase = match\n"
    assert types_of("python", code, "match") == [Keyword, Name, Name]
    assert types_of("python", code, "case") == [Keyword, Name]
    assert type_of("python", "type Alias = int", "type") is Keyword.Declaration
    assert type_of("python", "x = type(y)", "type") is Name.Builtin


def test_python_docstrings_versus_ordinary_strings():
    code = 'def f():\n    """Doc."""\n    x = """not doc"""\n'
    assert type_of("python", code, '"""Doc."""') is String.Doc
    assert type_of("python", code, '"""not doc"""') is String


def test_python_string_escapes_and_placeholders():
    tokens = visible("python", r'"a\n%s{0!r}\x41" % x')
    assert (String.Escape, r"\n") in tokens
    assert (String.Interpol, "%s{0!r}") in tokens
    assert (String.Escape, r"\x41") in tokens
    assert type_of("python", '"100% sure"', '"100% sure"') is String


def test_python_raw_strings_have_no_escapes():
    tokens = visible("python", r'r"\d+\n" + rb"\x00"')
    assert not [t for t in tokens if t[0] is String.Escape]
    assert tokens[0] == (String.Affix, "r")
    assert (String.Affix, "rb") in tokens


def test_python_fstring_interpolation():
    tokens = visible("python", 'f"{user.name!r:>10} is {{not}} {age + 1}"')
    assert tokens[0] == (String.Affix, "f")
    assert (Name, "user") in tokens
    assert (String.Interpol, "!r:") in tokens
    assert (String, ">10") in tokens
    assert (String.Escape, "{{") in tokens
    assert (Name, "age") in tokens and (Number.Integer, "1") in tokens
    assert tokens[-1] == (String, '"')


def test_python_fstring_nested_quotes_and_brackets():
    tokens = visible("python", "f'{d[\"k\"]} {x if y else {1: 2}[1]}' + z")
    assert (String, '"k"') in tokens
    assert (Keyword, "else") in tokens
    assert tokens[-2:] == [(Operator, "+"), (Name, "z")]


def test_python_unterminated_string_stops_at_the_line_end():
    assert type_of("python", 'x = "oops\ny = 1\n', "y") is Name
    assert type_of("python", 'x = "oops\ny = 1\n', "1") is Number.Integer


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("function add(a, b) { return a + b }", "function", Keyword.Declaration),
        ("function add(a, b) { return a + b }", "add", Name.Function),
        ("function add(a, b) { return a + b }", "return", Keyword),
        ("class Shape extends Base {}", "Shape", Name.Class),
        ("class Shape extends Base {}", "extends", Keyword),
        ("const add = (a, b) => a + b;", "const", Keyword.Declaration),
        ("const add = (a, b) => a + b;", "add", Name.Function),
        ("const add = (a, b) => a + b;", "=>", Operator),
        ("const inc = x => x + 1", "inc", Name.Function),
        ("handler = async function () {}", "handler", Name.Function),
        ("let total = 1", "total", Name),
        ("x = null ?? undefined", "null", Keyword.Constant),
        ("x = null ?? undefined", "undefined", Keyword.Constant),
        ("x = null ?? undefined", "??", Operator),
        ("this.x = 1", "this", Name.Builtin.Pseudo),
        ("console.log(1)", "console", Name.Builtin),
        ("console.log(1)", "log", Name),
        ("throw new TypeError('x')", "TypeError", Name.Exception),
        ("throw new TypeError('x')", "new", Keyword),
        ("p.catch(f).finally(g)", "catch", Name),
        ("p.catch(f).finally(g)", "finally", Name),
        ("f(...this.args)", "this", Name.Builtin.Pseudo),
        ("import x from 'y'", "from", Keyword),
        ("Array.from(x)", "from", Name),
        ("const from = 1", "from", Name),
        ("for (const k of list) {}", "of", Keyword),
        ("@observable x = 1", "@observable", Name.Decorator),
        ("// note\nx", "// note", Comment.Single),
        ("/* a\n b */ x", "/* a\n b */", Comment.Multiline),
        ("/** doc */ x", "/** doc */", Comment.Doc),
        ("#!/usr/bin/env node\nx", "#!/usr/bin/env node", Comment.Hashbang),
        ("x = 10n", "10n", Number.Integer),
        ("x = 0xFFn", "0xFFn", Number.Hex),
        ("x = 1_000.5e3", "1_000.5e3", Number.Float),
        ("x = 0b101", "0b101", Number.Bin),
        ("x = 0o17", "0o17", Number.Oct),
        ("a?.b", "?.", Operator),
        ("this.#count++", "#count", Name),
    ],
)
def test_javascript_tokens(code, text, expected):
    assert type_of("javascript", code, text) is expected


@pytest.mark.parametrize(
    "code, regex",
    [
        ("x = /ab+c/gi;", "/ab+c/gi"),
        ("x = /[/\\]]+/;", "/[/\\]]+/"),
        ("if (/^\\d+$/.test(s)) {}", "/^\\d+$/"),
        ("return /x/;", "/x/"),
        ("f(a, /b/)", "/b/"),
        ("/start/.test(x)", "/start/"),
    ],
)
def test_javascript_regex_literals(code, regex):
    assert type_of("javascript", code, regex) is String.Regex


@pytest.mark.parametrize(
    "code", ["x = a / b / c;", "x = (a) / 2 / (b);", "i++ / 2 / j"]
)
def test_javascript_division_is_not_a_regex(code):
    tokens = visible("javascript", code)
    assert not [t for t in tokens if t[0] is String.Regex]
    assert tokens.count((Operator, "/")) == 2


def test_javascript_template_literal_interpolation():
    tokens = visible("javascript", "`a ${x.map(i => ({ v: i }))} b` + c")
    assert tokens[0] == (String.Backtick, "`a ")
    assert tokens[1] == (String.Interpol, "${")
    assert (Name, "map") in tokens
    assert (String.Interpol, "}") in tokens
    assert (String.Backtick, " b`") in tokens
    assert tokens[-1] == (Name, "c")


def test_javascript_nested_templates():
    tokens = visible("javascript", "`${a ? `in ${b}` : ''}` + c")
    assert tokens.count((String.Interpol, "${")) == 2
    assert (String.Backtick, "`in ") in tokens
    assert tokens[-1] == (Name, "c")


def test_javascript_string_escapes():
    tokens = visible("javascript", r"'a\n\u{1F600}\x41' + " + '"b\\"c"')
    assert (String.Escape, r"\n\u{1F600}\x41") in tokens
    assert (String.Escape, '\\"') in tokens


def test_javascript_method_definitions():
    code = "class A {\n  static async load(id) {\n  }\n  get size() {\n  }\n}\n"
    assert type_of("javascript", code, "load") is Name.Function
    assert type_of("javascript", code, "static") is Keyword
    assert type_of("javascript", code, "async") is Keyword
    assert type_of("javascript", code, "size") is Name.Function
    assert type_of("javascript", code, "get") is Keyword


def test_javascript_control_flow_is_not_a_method():
    code = "  if (x) {\n  }\n  while (y) {\n  }\n  map.get(k)\n"
    assert type_of("javascript", code, "if") is Keyword
    assert type_of("javascript", code, "while") is Keyword
    assert type_of("javascript", code, "get") is Name


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("interface Props { id: string }", "interface", Keyword.Declaration),
        ("interface Props { id: string }", "Props", Name.Class),
        ("interface Props { id: string }", "string", Keyword.Type),
        ("type Pair = [string, number]", "type", Keyword.Declaration),
        ("type Pair = [string, number]", "Pair", Name.Class),
        ("type Pair = [string, number]", "number", Keyword.Type),
        ("const type = x.type", "type", Name),
        ("enum Color { Red }", "Color", Name.Class),
        ("namespace App.Models {}", "App.Models", Name.Namespace),
        ("class A { private readonly x = 1 }", "private", Keyword),
        ("class A { private readonly x = 1 }", "readonly", Keyword),
        ("let x = y as unknown", "as", Keyword),
        ("let x = y as unknown", "unknown", Keyword.Type),
        ("function f(object: Foo) {}", "object", Name),
        ("const string = 'x'", "string", Name),
        ("let f: () => void", "void", Keyword.Type),
        ("void 0", "void", Keyword),
        ("import type { A } from './a'", "type", Keyword),
        ("export type { A } from './a'", "type", Keyword),
        ("export type Fn = () => void", "type", Keyword.Declaration),
        ("export type Fn = () => void", "Fn", Name.Class),
        ("abstract class A {}", "abstract", Keyword),
        ("function f<T>(x: T): T { return x }", "f", Name.Function),
        ("const x = 1", "const", Keyword.Declaration),
        ("x = /re/g", "/re/g", String.Regex),
    ],
)
def test_typescript_tokens(code, text, expected):
    assert type_of("typescript", code, text) is expected


def test_typescript_methods_with_generics_and_return_types():
    code = "class S {\n  protected async load<K>(key: K): Promise<K> {\n  }\n}\n"
    assert type_of("typescript", code, "load") is Name.Function
    assert type_of("typescript", code, "protected") is Keyword


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("#!/bin/sh\necho hi", "#!/bin/sh", Comment.Hashbang),
        ("echo hi # note", "# note", Comment.Single),
        ("echo a#b", "a#b", Text),
        ("echo hi", "echo", Name.Builtin),
        ("git checkout test", "test", Text),
        ("ls | read x", "read", Name.Builtin),
        ("if true; then exit 1; fi", "if", Keyword),
        ("if true; then exit 1; fi", "then", Keyword),
        ("if true; then exit 1; fi", "exit", Name.Builtin),
        ("if true; then exit 1; fi", "fi", Keyword),
        ("for f in *.txt; do :; done", "in", Keyword),
        ("ls --for=x in/out", "in/out", Text),
        ("NAME=value", "NAME", Name.Variable),
        ("NAME=value", "=", Operator),
        ("arr+=(x)", "+=", Operator),
        ("echo $HOME", "$HOME", Name.Variable),
        ("echo $1 $? $@", "$?", Name.Variable),
        ("greet() { :; }", "greet", Name.Function),
        ("function greet { :; }", "greet", Name.Function),
        ("function greet { :; }", "function", Keyword),
        ("a && b || c", "&&", Operator),
        ("cmd > out 2>&1", ">&1", Operator),
        ("echo 'single $x'", "'single $x'", String.Single),
        ("x=$'a\\tb'", "$'a\\tb'", String.Single),
        ("[[ -f x ]]", "[[", Keyword),
        ("sleep 10", "10", Number),
        ("echo a\\ b", "\\ ", String.Escape),
    ],
)
def test_bash_tokens(code, text, expected):
    assert type_of("bash", code, text) is expected


def test_bash_double_quotes_interpolate():
    tokens = visible("bash", 'echo "hi $USER, ${HOME:-/root} $(date +%s) \\"q\\""')
    assert (String.Double, '"hi ') in tokens
    assert (Name.Variable, "$USER") in tokens
    assert (String.Interpol, "${") in tokens
    assert (Name.Variable, "HOME") in tokens
    assert (Operator, ":-") in tokens
    assert (Keyword, "$(") in tokens
    assert (String.Escape, '\\"') in tokens
    assert tokens[-1] == (String.Double, '"')


def test_bash_nested_command_substitution():
    tokens = visible("bash", 'x="$(cd "$(dirname "$0")" && pwd)" y')
    assert tokens.count((Keyword, "$(")) == 2
    assert tokens.count((Keyword, ")")) == 2
    assert tokens[-1] == (Text, "y")


def test_bash_arithmetic():
    tokens = visible("bash", "n=$(( (count + 1) * 0x10 )) z")
    assert (Keyword, "$((") in tokens and (Keyword, "))") in tokens
    assert (Name.Variable, "count") in tokens
    assert (Number, "0x10") in tokens
    assert tokens[-1] == (Text, "z")


def test_bash_heredoc():
    code = "cat <<EOF | wc -l\nhello $name\nEOF\necho done\n"
    tokens = visible("bash", code)
    assert tokens[1:3] == [(Operator, "<<"), (String.Delimiter, "EOF")]
    assert (String.Heredoc, "hello $name\n") in tokens
    assert tokens.count((String.Delimiter, "EOF")) == 2
    assert (Name.Builtin, "echo") in tokens


def test_bash_quoted_and_indented_heredoc_delimiters():
    quoted = visible("bash", "cat <<'END'\nraw\nEND\n")
    assert (String.Delimiter, "'END'") in quoted
    assert (String.Heredoc, "raw\n") in quoted
    indented = visible("bash", "cat <<-END\n\tbody\n\tEND\n")
    assert (String.Heredoc, "\tbody\n") in indented


def test_bash_here_string_is_not_a_heredoc():
    tokens = visible("bash", 'grep x <<< "$text"\necho ok\n')
    assert (Operator, "<<<") in tokens
    assert not [t for t in tokens if t[0] is String.Heredoc]
