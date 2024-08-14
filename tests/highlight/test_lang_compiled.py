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
)

from .helpers import type_of, types_of, visible


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("int main(void) { return 0; }", "int", Keyword.Type),
        ("int main(void) { return 0; }", "main", Name.Function),
        ("int main(void) { return 0; }", "return", Keyword),
        ("int main(void) { return 0; }", "0", Number.Integer),
        ("x = foo(1);", "foo", Name.Function),
        ("if (x) y();", "if", Keyword),
        ("n = sizeof(int);", "sizeof", Keyword),
        ("struct point p;", "point", Name.Class),
        ("enum color c;", "color", Name.Class),
        ("size_t n = MAX_LEN;", "size_t", Keyword.Type),
        ("size_t n = MAX_LEN;", "MAX_LEN", Name.Constant),
        ("p = NULL;", "NULL", Name.Builtin),
        ("b = true;", "true", Keyword.Constant),
        ("#include <stdio.h>", "#include", Comment.Preproc),
        ("#include <stdio.h>", "<stdio.h>", Comment.PreprocFile),
        ('#  include "a.h"', '"a.h"', Comment.PreprocFile),
        ("#define N 10", "#define N 10", Comment.Preproc),
        ("// note\nx;", "// note", Comment.Single),
        ("/* a\nb */ x;", "/* a\nb */", Comment.Multiline),
        ("/** doc */ x;", "/** doc */", Comment.Doc),
        ("/// doc\nx;", "/// doc", Comment.Doc),
        ("c = 'a';", "'a'", String.Char),
        ("c = '\\n';", "'\\n'", String.Char),
        ("c = L'x';", "L", String.Affix),
        ("x = 0xFFul;", "0xFFul", Number.Hex),
        ("x = 0755;", "0755", Number.Oct),
        ("x = 0b1010;", "0b1010", Number.Bin),
        ("x = 10UL;", "10UL", Number.Integer),
        ("x = 1.5e-3f;", "1.5e-3f", Number.Float),
        ("x = .5;", ".5", Number.Float),
        ("x = 1e9;", "1e9", Number.Float),
        ("x = 0x1.8p3;", "0x1.8p3", Number.Float),
        ("p->next = q;", "->", Operator),
        ("a <<= 2;", "<<=", Operator),
        ("x = a ? b : c;", "?", Operator),
    ],
)
def test_c_tokens(code, text, expected):
    assert type_of("c", code, text) is expected


def test_c_string_escapes_and_format_specifiers():
    tokens = visible("c", r'printf("a\t%-5.2f %s %%\n", x);')
    assert (String.Escape, r"\t") in tokens
    assert (String.Interpol, "%-5.2f") in tokens
    assert (String.Interpol, "%s") in tokens
    assert (String.Escape, r"\n") in tokens


def test_c_macro_continuation_lines():
    code = "#define SWAP(a, b) \\\n    do { } while (0) /* c */\nint x;\n"
    tokens = visible("c", code)
    assert tokens[0][0] is Comment.Preproc
    assert (Keyword, "do") not in tokens
    assert (Comment.Multiline, "/* c */") in tokens
    assert tokens[-3:] == [(Keyword.Type, "int"), (Name, "x"), (Punctuation, ";")]


def test_c_goto_labels():
    code = "    goto done;\ndone:\n    return;\n  default:\n    break;\n"
    assert types_of("c", code, "done") == [Name, Name.Label]
    assert type_of("c", code, "default") is Keyword


def test_c_ternary_on_a_new_line_is_not_a_label():
    assert Name.Label not in [t for t, _ in visible("c", "x = a\n  ? b\n  : c;\n")]


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("class Foo : public Bar {};", "class", Keyword),
        ("class Foo : public Bar {};", "Foo", Name.Class),
        ("class Foo : public Bar {};", "public", Keyword),
        ("namespace a::b {}", "a::b", Name.Namespace),
        ("enum class Color { Red };", "Color", Name.Class),
        ("std::vector<int> v;", "std", Name.Namespace),
        ("std::vector<int> v;", "::", Punctuation),
        ("std::vector<int> v;", "vector", Name),
        ("auto p = nullptr;", "nullptr", Keyword.Constant),
        ("auto p = nullptr;", "auto", Keyword),
        ("template <typename T> T f();", "template", Keyword),
        ("template <typename T> T f();", "typename", Keyword),
        ("x = static_cast<int>(y);", "static_cast", Keyword),
        ("auto p = make<Foo>(1);", "make", Name.Function),
        ("[[nodiscard]] int f();", "[[nodiscard]]", Name.Decorator),
        ("int n = 1'000'000;", "1'000'000", Number.Integer),
        ("public:\n  int x;", "public", Keyword),
        ("a <=> b", "<=>", Operator),
        ("throw std::runtime_error(m);", "throw", Keyword),
        ("void f() noexcept override;", "override", Keyword),
        ("int main() {}", "main", Name.Function),
    ],
)
def test_cpp_tokens(code, text, expected):
    assert type_of("cpp", code, text) is expected


def test_cpp_raw_string():
    code = 'auto s = R"sql(SELECT "x" \\n FROM t)sql"; int y;'
    tokens = visible("cpp", code)
    assert (String.Affix, "R") in tokens
    assert (String, '"sql(SELECT "x" \\n FROM t)sql"') in tokens
    assert (Keyword.Type, "int") in tokens


def test_c_does_not_know_cpp_keywords():
    assert type_of("c", "int class = 1;", "class") is Name
    assert type_of("c", "int new = 1;", "new") is Name


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("package main", "package", Keyword.Namespace),
        ("package main", "main", Name.Namespace),
        ('import "fmt"', "import", Keyword.Namespace),
        ('import "fmt"', '"fmt"', String),
        ("func main() {}", "func", Keyword.Declaration),
        ("func main() {}", "main", Name.Function),
        ("func (s *Server) Run() error {}", "Run", Name.Function),
        ("func (s *Server) Run() error {}", "Server", Name),
        ("func (s *Server) Run() error {}", "error", Keyword.Type),
        ("f := func(x int) error { return nil }", "error", Keyword.Type),
        ("type Server struct {}", "Server", Name.Class),
        ("type Server struct {}", "struct", Keyword.Declaration),
        ("var x int = 1", "var", Keyword.Declaration),
        ("var x int = 1", "int", Keyword.Type),
        ("x := make([]int, 3)", ":=", Operator),
        ("x := make([]int, 3)", "make", Name.Builtin),
        ("make := 3", "make", Name),
        ("fmt.Println(x)", "Println", Name.Function),
        ("ch <- v", "<-", Operator),
        ("go run()", "go", Keyword),
        ("defer f.Close()", "defer", Keyword),
        ("x = nil", "nil", Keyword.Constant),
        ("x = iota", "iota", Keyword.Constant),
        ("// note", "// note", Comment.Single),
        ("//go:embed x.txt", "//go:embed x.txt", Comment.Preproc),
        ("/* a\nb */", "/* a\nb */", Comment.Multiline),
        ("s := `raw\n\\n`", "`raw\n\\n`", String.Backtick),
        ("r := 'a'", "'a'", String.Char),
        ("r := '\\u00e9'", "'\\u00e9'", String.Char),
        ("x := 0x1F", "0x1F", Number.Hex),
        ("x := 0o17", "0o17", Number.Oct),
        ("x := 0755", "0755", Number.Oct),
        ("x := 0b11", "0b11", Number.Bin),
        ("x := 1_000", "1_000", Number.Integer),
        ("x := 0", "0", Number.Integer),
        ("x := 1.5e3", "1.5e3", Number.Float),
        ("x := 2i", "2i", Number.Float),
        ("x := 0.5", "0.5", Number.Float),
    ],
)
def test_go_tokens(code, text, expected):
    assert type_of("go", code, text) is expected


def test_go_string_escapes_and_verbs():
    tokens = visible("go", r'fmt.Printf("%d items\t%+v %q\n", n, v, s)')
    assert (String.Interpol, "%d") in tokens
    assert (String.Escape, r"\t") in tokens
    assert (String.Interpol, "%+v") in tokens
    assert (String.Interpol, "%q") in tokens


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("fn main() {}", "fn", Keyword.Declaration),
        ("fn main() {}", "main", Name.Function),
        ("pub struct Point { x: f64 }", "pub", Keyword),
        ("pub struct Point { x: f64 }", "Point", Name.Class),
        ("pub struct Point { x: f64 }", "f64", Keyword.Type),
        ("enum Shape { Circle }", "Shape", Name.Class),
        ("trait Draw {}", "Draw", Name.Class),
        ("impl Draw for Point {}", "impl", Keyword.Declaration),
        ("impl Draw for Point {}", "for", Keyword),
        ("mod util;", "util", Name.Namespace),
        ("use std::fmt::Display;", "use", Keyword.Namespace),
        ("use std::fmt::Display;", "std", Name.Namespace),
        ("use std::fmt::Display;", "Display", Name.Class),
        ("let mut x = 5;", "let", Keyword.Declaration),
        ("let mut x = 5;", "mut", Keyword),
        ("let v: Vec<u8> = Vec::new();", "Vec", Name.Builtin),
        ("let v: Vec<u8> = Vec::new();", "new", Name.Function),
        ("let x = Some(1);", "Some", Name.Builtin),
        ("self.x", "self", Name.Builtin.Pseudo),
        ("fn f() -> Self {}", "Self", Name.Builtin.Pseudo),
        ("let b = true;", "true", Keyword.Constant),
        ("const MAX: u32 = 10;", "MAX", Name.Constant),
        ('println!("hi");', "println!", Name.Function.Magic),
        ("let v = vec![1];", "vec!", Name.Function.Magic),
        ("if a != b {}", "!=", Operator),
        ("fn f<'a>(x: &'a str) {}", "'a", Name.Label),
        ("let c = 'a';", "'a'", String.Char),
        ("let c = '\\n';", "'\\n'", String.Char),
        ("let c = b'x';", "b'x'", String.Char),
        ("'outer: loop {}", "'outer", Name.Label),
        ("#[derive(Debug)]", "#[derive(Debug)]", Comment.Preproc),
        ("#![no_std]", "#![no_std]", Comment.Preproc),
        ("/// doc", "/// doc", Comment.Doc),
        ("//! crate doc", "//! crate doc", Comment.Doc),
        ("// note", "// note", Comment.Single),
        ("/* a /* b */ c */ x", "/* a /* b */ c */", Comment.Multiline),
        ("let x = 0xff_u8;", "0xff_u8", Number.Hex),
        ("let x = 0b1010;", "0b1010", Number.Bin),
        ("let x = 0o17;", "0o17", Number.Oct),
        ("let x = 1_000i64;", "1_000i64", Number.Integer),
        ("let x = 1.5e3_f64;", "1.5e3_f64", Number.Float),
        ("let x = 2f32;", "2f32", Number.Float),
        ("for i in 0..10 {}", "0", Number.Integer),
        ("for i in 0..10 {}", "..", Operator),
        ("let y = t.0.1;", "0", Number.Integer),
        ("x?;", "?", Operator),
        ("let r#type = 1;", "r#type", Name),
        ("match x { _ => 1 }", "=>", Operator),
    ],
)
def test_rust_tokens(code, text, expected):
    assert type_of("rust", code, text) is expected


def test_rust_strings():
    tokens = visible("rust", r'let s = "a\n{} {x:?} {{b}}\u{1F600}";')
    assert (String.Escape, r"\n") in tokens
    assert (String.Interpol, "{}") in tokens
    assert (String.Interpol, "{x:?}") in tokens
    assert (String.Escape, "{{") in tokens
    assert (String.Escape, r"}}\u{1F600}") in tokens


def test_rust_raw_strings_end_at_the_matching_hashes():
    code = 'let s = r#"say "hi" \\n"#; let t = r"a\\"; let u = 1;'
    tokens = visible("rust", code)
    assert (String, 'r#"say "hi" \\n"#') in tokens
    assert (String, 'r"a\\"') in tokens
    assert tokens[-2] == (Number.Integer, "1")


def test_rust_attribute_with_nested_brackets_and_strings():
    code = '#[cfg(all(unix, feature = "x]"))]\nfn f() {}'
    tokens = visible("rust", code)
    assert (String, '"x]"') in tokens
    assert (Keyword.Declaration, "fn") in tokens


@pytest.mark.parametrize(
    "code, text, expected",
    [
        ("package com.example;", "package", Keyword.Namespace),
        ("package com.example;", "com.example", Name.Namespace),
        ("import java.util.*;", "java.util.*", Name.Namespace),
        ("import static java.lang.Math.max;", "static", Keyword),
        ("public class Foo {}", "public", Keyword),
        ("public class Foo {}", "class", Keyword.Declaration),
        ("public class Foo {}", "Foo", Name.Class),
        ("interface Shape {}", "Shape", Name.Class),
        ("enum Kind { A }", "Kind", Name.Class),
        ("record Point(int x) {}", "record", Keyword.Declaration),
        ("record Point(int x) {}", "Point", Name.Class),
        ("int record = 1;", "record", Name),
        ("@Override void run() {}", "@Override", Name.Decorator),
        ("@interface Marker {}", "@interface", Keyword.Declaration),
        ("void run() {}", "void", Keyword.Type),
        ("void run() {}", "run", Name.Function),
        ("list.add(x);", "add", Name.Function),
        ("List<String> xs = new ArrayList<>();", "List", Name.Class),
        ("List<String> xs = new ArrayList<>();", "new", Keyword),
        ("List<String> xs = new ArrayList<>();", "ArrayList", Name.Class),
        ("int n = MAX_VALUE;", "MAX_VALUE", Name.Constant),
        ("x = null;", "null", Keyword.Constant),
        ("this.x = x;", "this", Name.Builtin.Pseudo),
        ("char c = 'a';", "'a'", String.Char),
        ("long n = 1_000L;", "1_000L", Number.Integer),
        ("int n = 0x1F;", "0x1F", Number.Hex),
        ("int n = 0b101;", "0b101", Number.Bin),
        ("int n = 017;", "017", Number.Oct),
        ("float f = 1.5f;", "1.5f", Number.Float),
        ("double d = 1e-3;", "1e-3", Number.Float),
        ("Runnable r = () -> {};", "->", Operator),
        ("f(String::valueOf);", "::", Punctuation),
        ("void f(int... xs) {}", "...", Punctuation),
        ("// note", "// note", Comment.Single),
        ("/** doc */ int x;", "/** doc */", Comment.Doc),
        ("/* a */ int x;", "/* a */", Comment.Multiline),
    ],
)
def test_java_tokens(code, text, expected):
    assert type_of("java", code, text) is expected


def test_java_string_escapes_and_format():
    tokens = visible("java", r'String.format("a\t%-10s %d%n", x, y);')
    assert (String.Escape, r"\t") in tokens
    assert (String.Interpol, "%-10s") in tokens
    assert (String.Interpol, "%d%n") in tokens


def test_java_text_block():
    code = 'String s = """\n    say "hi"\n    """;\nint x;'
    tokens = visible("java", code)
    assert (String, '"""\n    say "hi"\n    """') in tokens
    assert tokens[-3:] == [(Keyword.Type, "int"), (Name, "x"), (Punctuation, ";")]
