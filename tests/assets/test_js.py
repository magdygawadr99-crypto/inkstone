from __future__ import annotations

import shutil
import subprocess

import pytest

from inkstone.assets import AssetError, minify_js
from inkstone.assets.js import tokenize

NODE = shutil.which("node")


def code(source):
    """Tokens that are not whitespace, as (type, value) pairs."""
    return [
        (tok.type, tok.value)
        for tok in tokenize(source)
        if tok.type not in ("ws", "nl")
    ]


def regexes(source):
    return [value for kind, value in code(source) if kind == "regex"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0", "number"),
        ("42", "number"),
        ("0x1F", "number"),
        ("0b101", "number"),
        ("0o17", "number"),
        ("1_000_000", "number"),
        ("10n", "number"),
        ("1e-5", "number"),
        ("0.5e+3", "number"),
        (".5", "number"),
        ("1.", "number"),
        ("'a\\'b'", "string"),
        ('"a\\"b"', "string"),
        ("'a\\\nb'", "string"),
        ("''", "string"),
        ("`plain`", "template"),
        ("`a\nb`", "template"),
        ("`\\`${1}\\``", "template"),
        ("$", "name"),
        ("_private", "name"),
        ("caf\u00e9", "name"),
        ("#secret", "name"),
        ("a\\u0041", "name"),
        (">>>=", "punct"),
        ("?.", "punct"),
        ("...", "punct"),
        ("=>", "punct"),
        ("**=", "punct"),
        ("??=", "punct"),
        ("// line", "comment"),
        ("/* block\n */", "comment"),
        ("/re/gi", "regex"),
    ],
)
def test_single_token(text, expected):
    assert code(text) == [(expected, text)]


def test_number_followed_by_member_access():
    assert code("1..toString") == [
        ("number", "1."),
        ("punct", "."),
        ("name", "toString"),
    ]
    assert code("1.5.toFixed")[0] == ("number", "1.5")
    assert code("a?.5:1")[1:3] == [("punct", "?"), ("number", ".5")]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a / b / c", []),
        ("x = a /b/ c", []),
        ("1 / 2 / 3", []),
        ("'s' / 2 / c", []),
        ("`${a}` / 2 / c", []),
        ("(a + b) / 2 / c", []),
        ("a[0] / 2 / c", []),
        ("f() / 2 / c", []),
        ("a++ / 2 / c", []),
        ("x.return / 2 / c", []),
        ("x = {} / 2 / c", []),
        ("x = a ? {} / 2 / c : 0", []),
        ("x = { a: {} / 2 / c }", []),
        ("a /= 2 / c", []),
        ("x = y / 2 // c / d", []),
        ("this / 2 / c", []),
        ("a = /b/g", ["/b/g"]),
        ("/b/.test(s)", ["/b/"]),
        ("return /re/.test(s)", ["/re/"]),
        ("typeof /re/", ["/re/"]),
        ("if (x) /re/.test(s)", ["/re/"]),
        ("while (x) /re/.test(s)", ["/re/"]),
        ("for (const m of s) /re/.test(m)", ["/re/"]),
        ("{}\n/re/.test(s)", ["/re/"]),
        ("foo: {}\n/re/.test(s)", ["/re/"]),
        ("() => {}\n/re/.exec(s)", ["/re/"]),
        ("if (a) {} else {}\n/re/.exec(s)", ["/re/"]),
        ("a ? /b/ : /c/", ["/b/", "/c/"]),
        ("[/a/, /b/]", ["/a/", "/b/"]),
        ("f(/a/, b / c)", ["/a/"]),
        ("a = b / /c/.source.length", ["/c/"]),
        ("!/a/.test(s)", ["/a/"]),
        ("case /a/: break", ["/a/"]),
        ("/[/]/.test(s)", ["/[/]/"]),
        ("/[\\]/]/u.test(s)", ["/[\\]/]/u"]),
        ("/\\//.test(s)", ["/\\//"]),
        ("/=/.test(s)", ["/=/"]),
        ("x = /* c */ /re/", ["/re/"]),
    ],
)
def test_regex_versus_division(source, expected):
    assert regexes(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "`a${b}c`",
        "`a${`b${c}`}d`",
        "`${ {a: '}'}.a }`",
        "`${'}'}${\"`\"}`",
        "`${/}/.test(s)}`",
        "`${ a /* } */ }`",
        "`${ a // }\n }`",
        "`${ () => { return `${1}` } }`",
        "`$ {a} $$ \\${b}`",
    ],
)
def test_template_literal_is_one_token(source):
    assert code(source + " + tail") == [
        ("template", source),
        ("punct", "+"),
        ("name", "tail"),
    ]


def test_tokens_cover_the_source_exactly():
    source = "#!/bin/node\r\nlet a = `x${1}` // c\r\n/* d */ a /= 2;\tb = /r/g\n"
    tokens = tokenize(source)
    assert "".join(tok.value for tok in tokens) == source
    assert tokens[0].type == "hashbang"
    assert [tok.value for tok in tokens if tok.type == "nl"] == ["\r\n", "\r\n", "\n"]


@pytest.mark.parametrize(
    "source, roles",
    [
        ("if (a) b", ["head"]),
        ("f(a)", [""]),
        ("x.if(a)", [""]),
        ("for await (a of b) c", ["head"]),
        ("while (a) b", ["while"]),
        ("if (a) { b }", ["head", "block"]),
        ("if (a) { b } else { c }", ["head", "block", "block"]),
        ("try { a } catch { b } finally { c }", ["block", "block", "block"]),
        ("switch (f(a)) { }", ["", "head", "block"]),
        ("do { a } while (b)", ["block", "while"]),
        ("f = (a) => { b }", ["", "arrow"]),
        ("f = function (a) { b }", ["", ""]),
        ("x = { a: [1] }", ["", ""]),
        ("class A { m() { } }", ["", "", ""]),
        ("{ a }", [""]),
        ("if (a]", [""]),
    ],
)
def test_roles_of_closing_brackets(source, roles):
    closers = [tok for tok in tokenize(source) if tok.value in (")", "]", "}")]
    assert [tok.role for tok in closers] == roles


@pytest.mark.parametrize(
    "source, line, what",
    [
        ("var a = 'oops\nvar b", 1, "string"),
        ('\n\nvar a = "oops', 3, "string"),
        ("a\n/* never closed", 2, "comment"),
        ("a = `never ${closed", 1, "template literal"),
        ("a = `never closed", 1, "template literal"),
        ("a = 1\nb = `x ${ y\n\n", 2, "template literal"),
        ("a = `${ 'oops\n }`", 1, "string"),
        ("\na = /never closed\n", 2, "regular expression"),
    ],
)
def test_unterminated_constructs_report_the_line(source, line, what):
    with pytest.raises(AssetError) as info:
        tokenize(source, "app.js")
    assert info.value.line == line
    assert info.value.path == "app.js"
    assert info.value.message == f"unterminated {what}"


def test_unexpected_character():
    with pytest.raises(AssetError, match="unexpected character"):
        tokenize("a = 1 \u00a7 2")


MINIFY_CASES = [
    # plain whitespace
    ("var a = 1;", "var a=1;"),
    ("a = b + c", "a=b+c"),
    ("function f ( a , b ) { return a ; }", "function f(a,b){return a}"),
    ("  \n  ", ""),
    # tokens that must not fuse
    ("a + +b", "a+ +b"),
    ("a - -b", "a- -b"),
    ("a++ + b", "a++ +b"),
    ("a + ++b", "a+ ++b"),
    ("a - --b", "a- --b"),
    ("a + -b", "a+-b"),
    ("a / /re/.source", "a/ /re/.source"),
    ("a < !--b", "a< !--b"),
    ("a-- > b", "a-- >b"),
    ("typeof a", None),
    ("a in b", None),
    ("a instanceof B", None),
    ("1 in a", None),
    ("'a' in b", "'a'in b"),
    ("/a/ in b", None),
    ("1 .toString()", None),
    ("1..toString()", None),
    ("1.5 .toFixed()", "1.5.toFixed()"),
    ("a ? .5 : 1", "a?.5:1"),
    ("x = a ?. b", "x=a?.b"),
    ("return /re/", "return/re/"),
    ("return 'x'", "return'x'"),
    ("return .5", None),
    ("static #a", None),
    # comments
    ("a // c\nb", "a\nb"),
    ("a /* c */ + b", "a+b"),
    ("a = 1 // c", "a=1"),
    ("/*! keep */\nvar a", None),
    ("var a /*! keep */", "var a/*! keep */"),
    ("/** @license MIT */ var a", "/** @license MIT */var a"),
    ("a = 1 /* x\n y */ b = 2", "a=1\nb=2"),
    ("return /*! x */\n1", "return/*! x */\n1"),
    # literals are left exactly as written
    ("a = '  x  ' + \"  y  \"", "a='  x  '+\"  y  \""),
    ("a = `  ${ b  +  c }  `", "a=`  ${ b  +  c }  `"),
    ("a = /  x  /g", "a=/  x  /g"),
    ("a = 'it\\'s' // 'not a comment", "a='it\\'s'"),
    ("a = '// not a comment'", "a='// not a comment'"),
    # line breaks that carry meaning
    ("a = 1\nb = 2", "a=1\nb=2"),
    ("a = 1;\nb = 2", "a=1;b=2"),
    ("return\na", None),
    ("return (\n  a\n)", "return(a)"),
    ("return\n(a)", None),
    ("throw\nnew Error()", None),
    ("continue\nlabel", None),
    ("a\n++b", None),
    ("a++\nb", None),
    ("a()\nb()", None),
    ("a = 'x'\n'y'", "a='x'\n'y'"),
    ("let x = 1\n!y", "let x=1\n!y"),
    ("x = function () {\n}\ny = 1", "x=function(){}\ny=1"),
    (
        "class A {\n  x = 1\n  y = 2\n  static #z = 3;\n}",
        "class A{x=1\ny=2\nstatic #z=3}",
    ),
    ("x.return\nfoo()", None),
    ("if (a) b = 1\nelse c = 2", "if(a)b=1\nelse c=2"),
    ("if (a) x = {}\nelse y()", "if(a)x={}\nelse y()"),
    ("if (a) x = function () {}\nelse y()", "if(a)x=function(){}\nelse y()"),
    ("f = () => {\n}\n[1, 2].forEach(g)", "f=()=>{}\n[1,2].forEach(g)"),
    ("f = () => {}\n(g)()", "f=()=>{}\n(g)()"),
    ("f = () => {}\n`t`", "f=()=>{}\n`t`"),
    ("a++\n(b)", None),
    ("a--\n[b]", None),
    ("a = b\n[c]", "a=b\n[c]"),
    ("a = b\n* c", "a=b\n*c"),
    (
        "class A {\n  x\n  [y]() {}\n  z\n  *g() {}\n  'q'\n  [r] = 1\n}",
        "class A{x\n[y](){}\nz\n*g(){}\n'q'\n[r]=1}",
    ),
    ("do a()\nwhile (b)\nc()", "do a()\nwhile(b)\nc()"),
    ("do {\n  a()\n}\nwhile (b)\nc()", "do{a()}while(b)\nc()"),
    ("while (a)\n  b()", "while(a)\nb()"),
    ("typeof\na", None),
    # line breaks that do not
    ("a\n(b)", "a(b)"),
    ("f = function () {}\n(g)()", "f=function(){}(g)()"),
    ("a = f()\n[c]", "a=f()[c]"),
    ("a = f()\n* c", "a=f()*c"),
    ("x = {}\n[c]", "x={}[c]"),
    ("f(() => {}\n)", "f(()=>{})"),
    ("x = a ? () => {}\n: b", "x=a?()=>{}:b"),
    ("for (;;) {\n}\nfoo()", "for(;;){}foo()"),
    ("if (a) {\n}\n(b)()", "if(a){}(b)()"),
    ("if (a) {\n}\n/re/.test(b)", "if(a){}/re/.test(b)"),
    ("typeof\n(a)", "typeof(a)"),
    ("a = b +\nc", "a=b+c"),
    ("a = b\n+ c", "a=b+c"),
    ("a\n.b()\n.c()", "a.b().c()"),
    ("a = b\n`c`", "a=b`c`"),
    ("x\n/re/.test(y)", "x/re/.test(y)"),
    ("if (a)\n  b()", "if(a)b()"),
    ("if (a)\n  ++b", "if(a)++b"),
    ("if (a)\n{\n  b()\n}\nelse\n{\n  c()\n}", "if(a){b()}else{c()}"),
    ("try\n{ a() }\ncatch (e)\n{ }\nfinally\n{ }", "try{a()}catch(e){}finally{}"),
    ("var a = {\n  b: 1,\n  c: 2\n}", "var a={b:1,c:2}"),
    ("return\n}", "return}"),
    ("a\nin b", "a in b"),
    # semicolons before a closing brace
    ("{ a = 1; }", "{a=1}"),
    ("{ a(); }", "{a()}"),
    ("{ ; }", "{}"),
    ("{ a;; }", "{a}"),
    ("{ while (a);; }", "{while(a);}"),
    ("x = function () { function g() {}; };", "x=function(){function g(){}};"),
    ("x = { a: 1 };", "x={a:1};"),
    ("{ x.else; }", "{x.else}"),
    ("{ while (a); }", "{while(a);}"),
    ("{ if (a) b; else; }", "{if(a)b;else;}"),
    ("{ a: ; }", "{a:;}"),
    ("{ do; while (a); }", "{do;while(a);}"),
    ("for (;;) {}", "for(;;){}"),
    ("{ a; /*! x */ }", "{a;/*! x */}"),
    # odds and ends
    ("#!/usr/bin/env node\nvar a = 1", "#!/usr/bin/env node\nvar a=1"),
    ("a = b ?? c", "a=b??c"),
    ("a = (b, c) => ({ d })", "a=(b,c)=>({d})"),
    ("async function* f() { yield* g() }", "async function*f(){yield*g()}"),
    ("label: for (;;) { break label }", "label:for(;;){break label}"),
    ("a = b ? c : d", "a=b?c:d"),
    ("new Foo", None),
    ("x = [1, , 2]", "x=[1,,2]"),
]


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify(before, after):
    assert minify_js(before) == (before if after is None else after)


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify_is_idempotent(before, after):
    once = minify_js(before)
    assert minify_js(once) == once


def test_minify_normalises_line_endings_and_bom():
    assert minify_js("\ufeffa = 1\r\nb = `x\r\ny`\r\n") == "a=1\nb=`x\ny`"


def test_minify_passes_the_path_to_errors():
    with pytest.raises(AssetError) as info:
        minify_js("a = 1\nb = 'oops\n", path="js/app.js")
    assert str(info.value) == "js/app.js:2: unterminated string"


PROGRAM = r"""
'use strict';
var out = [];
function log() { out.push(Array.prototype.join.call(arguments, ' ')); }
var a = 10, b = 2, g = 5;
log(a / b / g, a /b/ g);
var re = /[/\]]+/g, s = 'a/b]c';
log(s.replace(re, '-'), /=/.test('='), a /= 2);
if (a) /x/.test('x') && log('regex after if');
log(`x${ `y${ {a: '}'}.a }` + "`" }z`,
  `a${1 + 1}b${[1, 2].map(n => `<${n}>`).join('')}`);
function f() {
  return (
    1
  )
}
function h() {
  return
  2
}
log(f(), h());
var i = 1, j = 2
i
++
j
log(i, j, i + +j, i - -j, i++ + j, i-- - j, i + ++j);
var obj = {
  default: 1,
  return: 2,
  in: 3
};
log(obj.default
  , obj.return
  , obj.in);
log(1 .toString(), 1..toString(), 0x1F, 1e3, .5, 1_000, 10n);
var q = a
/ b
/ g;
log(q);
outer: for (var x = 0; x < 3; x++) {
  for (;;) { if (x) continue outer; break outer; }
}
do x++; while (x < 5)
log(x, typeof /re/, 'in' in {in: 1}, 1 in [0, 1]);
class A {
  static #count = 0;
  x = 1
  y = 2
  static inc() { return ++A.#count; }
  get z() { return this.x + this.y }
}
log(new A().z, A.inc());
log('it\'s' + "a \"q\"" + 'multi\
line', a ? .5 : 1, obj?.default, null ?? 'dflt');
if (!a) {
  log('then')
}
else
{
  log('else')
}
log(1 < !--a, a-- > 0, a);
while (0);
if (0); else;
switch (a) { case 1: ; default: log('switch') }
try { throw new Error('boom') } catch (e) { log(e.message) } finally { log('finally') }
var fn = function () { return 1; };
(function () { log('iife', fn()) })();
console.log(out.join('|'));
"""


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_minified_program_behaves_the_same(tmp_path):
    small = minify_js(PROGRAM)
    assert len(small) < len(PROGRAM)
    results = []
    for name, source in (("original.js", PROGRAM), ("minified.js", small)):
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        done = subprocess.run([NODE, str(path)], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        results.append(done.stdout)
    assert results[0] == results[1]
    assert "regex after if" in results[0]
