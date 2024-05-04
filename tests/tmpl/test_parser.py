from __future__ import annotations

import pytest

from inkstone.tmpl import TemplateSyntaxError, nodes
from inkstone.tmpl.nodes import (
    And,
    BinOp,
    Call,
    Compare,
    Concat,
    CondExpr,
    Const,
    DictLit,
    Filter,
    Getattr,
    Getitem,
    ListLit,
    Name,
    Neg,
    Not,
    Or,
    Slice,
    TupleLit,
)
from inkstone.tmpl.parser import parse

a, b, c, d, e = (Name(letter) for letter in "abcde")


def expr(source):
    (output,) = parse("{{ " + source + " }}").body
    return output.expr


def stmt(source):
    (node,) = parse(source).body
    return node


def is_test(node, name, *args, negated=False):
    return nodes.Test(node, name, list(args), [], negated=negated)


def test_plain_text():
    assert parse("hello").body == [nodes.Data("hello")]


def test_empty_template():
    assert parse("").body == []


def test_output_between_text():
    assert parse("a {{ b }} c").body == [
        nodes.Data("a "),
        nodes.Output(Name("b")),
        nodes.Data(" c"),
    ]


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1 + 2 * 3", BinOp("+", Const(1), BinOp("*", Const(2), Const(3)))),
        ("(1 + 2) * 3", BinOp("*", BinOp("+", Const(1), Const(2)), Const(3))),
        ("a - b - c", BinOp("-", BinOp("-", a, b), c)),
        ("a / b // c % d", BinOp("%", BinOp("//", BinOp("/", a, b), c), d)),
        ("a ~ b + c", BinOp("+", Concat([a, b]), c)),
        ("a * b ~ c", Concat([BinOp("*", a, b), c])),
        ("a ~ b ~ c", Concat([a, b, c])),
        ("-a ** 2", BinOp("**", Neg(a), Const(2))),
        ("2 ** 3 ** 2", BinOp("**", BinOp("**", Const(2), Const(3)), Const(2))),
        ("a ** -b", BinOp("**", a, Neg(b))),
        ("a or b and c", Or(a, And(b, c))),
        ("a and b or c", Or(And(a, b), c)),
        ("a and not b", And(a, Not(b))),
        ("not a == b", Not(Compare(a, [("==", b)]))),
        ("not not a", Not(Not(a))),
        ("a + b < c * d", Compare(BinOp("+", a, b), [("<", BinOp("*", c, d))])),
        ("a < b <= c", Compare(a, [("<", b), ("<=", c)])),
        ("a in b", Compare(a, [("in", b)])),
        ("a not in b", Compare(a, [("not in", b)])),
        ("a == b and c != d", And(Compare(a, [("==", b)]), Compare(c, [("!=", d)]))),
        ("a if b else c", CondExpr(b, a, c)),
        ("a if b", CondExpr(b, a, None)),
        ("a if b else c if d else e", CondExpr(b, a, CondExpr(d, c, e))),
        ("a or b if c else d", CondExpr(c, Or(a, b), d)),
    ],
)
def test_operator_precedence(source, expected):
    assert expr(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a | f", Filter(a, "f", [], [])),
        ("a | f | g", Filter(Filter(a, "f", [], []), "g", [], [])),
        ("a + b | f", BinOp("+", a, Filter(b, "f", [], []))),
        ("a.b | f", Filter(Getattr(a, "b"), "f", [], [])),
        ("-a | f", Filter(Neg(a), "f", [], [])),
        ("a | f(1, x=b)", Filter(a, "f", [Const(1)], [("x", b)])),
        ("a | f(*b, **c)", Filter(a, "f", [], [], b, c)),
        ("a | ns.f", Filter(a, "ns.f", [], [])),
        ("a | f ~ b", Concat([Filter(a, "f", [], []), b])),
    ],
)
def test_filters_bind_tighter_than_operators(source, expected):
    assert expr(source) == expected


def test_filter_with_keyword_arguments():
    assert expr('x | truncate(20, end="…")') == Filter(
        Name("x"), "truncate", [Const(20)], [("end", Const("…"))]
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a is defined", is_test(a, "defined")),
        ("a is not defined", is_test(a, "defined", negated=True)),
        ("a is divisibleby 3", is_test(a, "divisibleby", Const(3))),
        ("a is divisibleby(3)", is_test(a, "divisibleby", Const(3))),
        ("a is sameas b.c", is_test(a, "sameas", Getattr(b, "c"))),
        ("a is in [b]", is_test(a, "in", ListLit([b]))),
        ("a is none", is_test(a, "none")),
        ("a is defined and b", And(is_test(a, "defined"), b)),
        ("a is defined or b", Or(is_test(a, "defined"), b)),
        ("not a is none", Not(is_test(a, "none"))),
        ("a + b is odd", BinOp("+", a, is_test(b, "odd"))),
        ("a if b is defined else c", CondExpr(is_test(b, "defined"), a, c)),
        ("a | f is string", is_test(Filter(a, "f", [], []), "string")),
    ],
)
def test_is_tests(source, expected):
    assert expr(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("true", Const(True)),
        ("False", Const(False)),
        ("none", Const(None)),
        ("42", Const(42)),
        ("1.5", Const(1.5)),
        ("'a' \"b\" 'c'", Const("abc")),
        ("[]", ListLit([])),
        ("[a, 1,]", ListLit([a, Const(1)])),
        ("{}", DictLit([])),
        ("{'k': a, b: 2}", DictLit([(Const("k"), a), (b, Const(2))])),
        ("()", TupleLit([])),
        ("(a,)", TupleLit([a])),
        ("(a)", a),
        ("a, b", TupleLit([a, b])),
        ("(a, (b, c))", TupleLit([a, TupleLit([b, c])])),
        ("[[a], {}]", ListLit([ListLit([a]), DictLit([])])),
    ],
)
def test_literals(source, expected):
    assert expr(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a.b", Getattr(a, "b")),
        ("a.b.c", Getattr(Getattr(a, "b"), "c")),
        ("a['b']", Getitem(a, Const("b"))),
        ("a[b]", Getitem(a, b)),
        ("a.0", Getitem(a, Const(0))),
        ("a.b[0].c", Getattr(Getitem(Getattr(a, "b"), Const(0)), "c")),
        ("a[1:2]", Getitem(a, Slice(Const(1), Const(2), None))),
        ("a[:2]", Getitem(a, Slice(None, Const(2), None))),
        ("a[1:]", Getitem(a, Slice(Const(1), None, None))),
        ("a[::2]", Getitem(a, Slice(None, None, Const(2)))),
        ("a[1:2:3]", Getitem(a, Slice(Const(1), Const(2), Const(3)))),
        ("a[:]", Getitem(a, Slice(None, None, None))),
        ("a[b:c]", Getitem(a, Slice(b, c, None))),
        ("a[1, 2]", Getitem(a, TupleLit([Const(1), Const(2)]))),
        ("'x'.upper", Getattr(Const("x"), "upper")),
    ],
)
def test_subscripts(source, expected):
    assert expr(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a()", Call(a, [], [])),
        ("a(1, b)", Call(a, [Const(1), b], [])),
        ("a(b, x=1, y=c)", Call(a, [b], [("x", Const(1)), ("y", c)])),
        ("a(*b)", Call(a, [], [], b)),
        ("a(**b)", Call(a, [], [], None, b)),
        ("a(1, *b, x=2, **c)", Call(a, [Const(1)], [("x", Const(2))], b, c)),
        ("a(1,)", Call(a, [Const(1)], [])),
        ("a.b(c)", Call(Getattr(a, "b"), [c], [])),
        ("a()()", Call(Call(a, [], []), [], [])),
        ("a(b)[0]", Getitem(Call(a, [b], []), Const(0))),
        ("a(b if c else d)", Call(a, [CondExpr(c, b, d)], [])),
    ],
)
def test_calls(source, expected):
    assert expr(source) == expected


def test_if_elif_else():
    node = stmt("{% if a %}1{% elif b %}2{% elif c %}3{% else %}4{% endif %}")
    assert node == nodes.If(
        [
            (a, [nodes.Data("1")]),
            (b, [nodes.Data("2")]),
            (c, [nodes.Data("3")]),
        ],
        [nodes.Data("4")],
    )


def test_for_with_everything():
    node = stmt(
        "{% for a, b in c if a recursive %}x{% else %}y{% endfor %}",
    )
    assert node == nodes.For(
        TupleLit([a, b]),
        c,
        [nodes.Data("x")],
        [nodes.Data("y")],
        test=a,
        recursive=True,
    )


def test_for_target_can_be_nested():
    node = stmt("{% for a, (b, c) in d %}{% endfor %}")
    assert node.target == TupleLit([a, TupleLit([b, c])])


def test_for_over_a_bare_tuple():
    node = stmt("{% for a in b, c %}{% endfor %}")
    assert node.iter == TupleLit([b, c])


def test_set_forms():
    assert stmt("{% set a = b %}") == nodes.Set(a, b)
    assert stmt("{% set a, b = c %}") == nodes.Set(TupleLit([a, b]), c)
    assert stmt("{% set a = b, c %}") == nodes.Set(a, TupleLit([b, c]))
    assert stmt("{% set a.b = c %}") == nodes.Set(nodes.NSRef("a", "b"), c)
    assert stmt("{% set a %}x{% endset %}") == nodes.SetBlock(
        a, None, [nodes.Data("x")]
    )
    assert stmt("{% set a | f | g(1) %}x{% endset %}") == nodes.SetBlock(
        a,
        Filter(Filter(None, "f", [], []), "g", [Const(1)], []),
        [nodes.Data("x")],
    )


def test_with():
    assert stmt("{% with a = 1, b = c %}x{% endwith %}") == nodes.With(
        [a, b], [Const(1), c], [nodes.Data("x")]
    )
    assert stmt("{% with %}{% endwith %}") == nodes.With([], [], [])


def test_block_modifiers():
    assert stmt("{% block a %}x{% endblock %}") == nodes.Block("a", [nodes.Data("x")])
    assert stmt("{% block a scoped %}{% endblock a %}") == nodes.Block(
        "a", [], scoped=True
    )
    assert stmt("{% block a required %} {% endblock %}").required


def test_extends_include_import():
    assert stmt("{% extends 'base.html' %}") == nodes.Extends(Const("base.html"))
    assert stmt("{% include a %}") == nodes.Include(a, True, False)
    assert stmt("{% include a ignore missing %}") == nodes.Include(a, True, True)
    assert stmt("{% include a without context %}") == nodes.Include(a, False, False)
    assert stmt("{% include a ignore missing with context %}") == nodes.Include(
        a, True, True
    )
    assert stmt("{% import a as b %}") == nodes.Import(a, "b", False)
    assert stmt("{% import a as b with context %}") == nodes.Import(a, "b", True)


def test_from_import():
    assert stmt("{% from a import b %}") == nodes.FromImport(a, [("b", "b")])
    assert stmt("{% from a import b as c, d %}") == nodes.FromImport(
        a, [("b", "c"), ("d", "d")]
    )
    assert stmt("{% from a import b, c, %}").names == [("b", "b"), ("c", "c")]
    assert stmt("{% from a import b with context %}") == nodes.FromImport(
        a, [("b", "b")], True
    )
    assert stmt("{% from a import b, c without context %}").with_context is False


def test_macro():
    node = stmt("{% macro m(a, b=1, c=d) %}x{% endmacro %}")
    assert node == nodes.Macro("m", ["a", "b", "c"], [Const(1), d], [nodes.Data("x")])


def test_macro_notices_the_special_names_it_uses():
    plain = stmt("{% macro m() %}{{ x }}{% endmacro %}")
    assert not (plain.catch_varargs or plain.catch_kwargs or plain.uses_caller)
    node = stmt(
        "{% macro m() %}{{ varargs }}{% if x %}{{ kwargs | length }}{% endif %}"
        "{{ caller() }}{% endmacro %}"
    )
    assert node.catch_varargs and node.catch_kwargs and node.uses_caller


def test_call_block():
    node = stmt("{% call(a, b=1) c(d) %}x{% endcall %}")
    assert node == nodes.CallBlock(
        Call(c, [d], []), ["a", "b"], [Const(1)], [nodes.Data("x")]
    )
    assert stmt("{% call c() %}{% endcall %}").params == []


def test_filter_block_and_autoescape():
    assert stmt("{% filter f | g(a) %}x{% endfilter %}") == nodes.FilterBlock(
        Filter(Filter(None, "f", [], []), "g", [a], []), [nodes.Data("x")]
    )
    assert stmt("{% autoescape false %}x{% endautoescape %}") == nodes.Autoescape(
        Const(False), [nodes.Data("x")]
    )


def test_do_and_loop_controls():
    assert stmt("{% do a.append(b) %}") == nodes.Do(Call(Getattr(a, "append"), [b], []))
    loop = stmt("{% for a in b %}{% break %}{% continue %}{% endfor %}")
    assert loop.body == [nodes.Break(), nodes.Continue()]


def test_nodes_remember_their_line():
    tree = parse("a\n{% if x %}\n  {{ y\n  | f }}\n{% endif %}\n{{ z }}")
    data, branch, _, output = tree.body
    assert (data.lineno, branch.lineno, output.lineno) == (1, 2, 6)
    inner = branch.branches[0][1][1]
    assert inner.lineno == 3
    assert inner.expr.lineno == 4
    assert inner.expr.node.lineno == 3


def test_line_numbers_do_not_affect_equality():
    assert parse("{{ a }}").body == parse("\n\n{{ a }}").body[1:]


def test_find_all_walks_the_whole_tree_in_source_order():
    tree = parse(
        "{% for a in b %}{% if c %}{{ d.x | f(e) }}{% endif %}{% endfor %}{{ a }}"
    )
    assert [n.name for n in tree.find_all(Name)] == ["a", "b", "c", "d", "e", "a"]
    assert len(list(tree.find_all((nodes.If, nodes.For)))) == 2
    assert list(tree.find_all(nodes.Macro)) == []


@pytest.mark.parametrize(
    "source, message, line",
    [
        ("{{ }}", "expected an expression, got '}}'", 1),
        ("{{ a b }}", "expected '}}', got 'b'", 1),
        ("{{ a + }}", "expected an expression, got '}}'", 1),
        ("{{ a\n+\n* b }}", "expected an expression, got '*'", 3),
        ("{{ a | }}", "expected a filter name", 1),
        ("{{ a | 1 }}", "expected a filter name, got number 1", 1),
        ("{{ a is }}", "expected a test name", 1),
        ("{{ a is b is c }}", "tests can't be chained", 1),
        ("{{ a[] }}", "expected an index or a slice", 1),
        ("{{ a. }}", "expected a name or number after '.'", 1),
        ("{{ a.'b' }}", "expected a name or number after '.'", 1),
        ("{{ f(a=1, 2) }}", "invalid order of arguments", 1),
        ("{{ f(**a, *b) }}", "invalid order of arguments", 1),
        ("{{ f(a=1, a=2) }}", "keyword argument 'a' repeated", 1),
        ("{{ f(a b) }}", "expected ',', got 'b'", 1),
        ("{{ {1 2} }}", "expected ':'", 1),
        ("{{ [1 2] }}", "expected ',', got number 2", 1),
        ("{{ 'a' 1 }}", "expected '}}', got number 1", 1),
    ],
)
def test_expression_syntax_errors(source, message, line):
    with pytest.raises(TemplateSyntaxError) as excinfo:
        parse(source, "page.html")
    assert message in excinfo.value.message
    assert excinfo.value.line == line
    assert excinfo.value.path == "page.html"


@pytest.mark.parametrize(
    "source, message, line",
    [
        ("{% foo %}", "unknown tag 'foo'", 1),
        ("a\nb\n{% unless x %}", "unknown tag 'unless'", 3),
        ("{% 123 %}", "expected a tag name, got number 123", 1),
        ("{% %}", "expected a tag name, got '%}'", 1),
        ("{% if %}{% endif %}", "expected an expression", 1),
        ("{% if x %}", "the 'if' block opened on line 1 is never closed", 1),
        ("a\n{% for x in y %}\nb\n", "'for' block opened on line 2 is never", 3),
        ("{% if x %}a{% else %}b", "expected 'endif'", 1),
        ("{% endif %}", "unexpected 'endif', there is no open block", 1),
        ("a{% else %}", "unexpected 'else', there is no open block", 1),
        ("{% if x %}\n{% endfor %}", "unexpected 'endfor', the 'if' block", 2),
        ("{% if x %}{% endfor %}", "needs 'elif', 'else' or 'endif'", 1),
        ("{% for x in y %}{% endif %}", "needs 'else' or 'endfor'", 1),
        ("{% if a %}{% else %}{% else %}{% endif %}", "needs 'endif'", 1),
        ("{% if a %}{% else %}{% elif b %}{% endif %}", "unexpected 'elif'", 1),
        ("{% if x %}{% endif extra %}", "expected '%}', got 'extra'", 1),
        ("{% for x %}{% endfor %}", "expected 'in', got '%}'", 1),
        ("{% for 1 in x %}{% endfor %}", "can't assign to a literal", 1),
        ("{% for x.y in z %}{% endfor %}", "expected 'in', got '.'", 1),
        ("{% for () in x %}{% endfor %}", "can't assign to an empty tuple", 1),
        ("{% set true = 1 %}", "can't assign to a literal", 1),
        ("{% set a, b %}x{% endset %}", "needs a single name", 1),
        ("{% set a = %}", "expected an expression", 1),
        ("{% with a %}{% endwith %}", "expected '=', got '%}'", 1),
        ("{% with a = 1 b = 2 %}{% endwith %}", "expected ',', got 'b'", 1),
        ("{% block %}{% endblock %}", "expected a block name", 1),
        ("{% block a-b %}{% endblock %}", "can't contain hyphens", 1),
        ("{% block a %}{% endblock b %}", "'endblock b' doesn't match", 1),
        (
            "{% block a %}{% endblock %}\n{% block a %}{% endblock %}",
            "block 'a' is defined twice, first on line 1",
            2,
        ),
        ("{% block a required %}text{% endblock %}", "required block can only", 1),
        ("{% block a required %}{{ x }}{% endblock %}", "required block can only", 1),
        ("{% if x %}{% extends 'a' %}{% endif %}", "has to be at the top level", 1),
        ("{% extends 'a' %}\n{% extends 'b' %}", "an 'extends' on line 1", 2),
        ("{% extends %}", "expected an expression", 1),
        ("{% include %}", "expected an expression", 1),
        ("{% import 'a' %}", "expected 'as', got '%}'", 1),
        ("{% import 'a' as none %}", "'none' can't be used as a name", 1),
        ("{% from 'a' import %}", "expected the names to import", 1),
        ("{% from 'a' import _x %}", "private", 1),
        ("{% from 'a' x %}", "expected 'import', got 'x'", 1),
        ("{% macro m(a=1, b) %}{% endmacro %}", "'b' without a default", 1),
        ("{% macro m(a, a) %}{% endmacro %}", "duplicate parameter 'a'", 1),
        ("{% macro (a) %}{% endmacro %}", "expected a name, got '('", 1),
        ("{% macro m %}{% endmacro %}", "expected '(', got '%}'", 1),
        ("{% macro m() %}", "'macro' block opened on line 1 is never closed", 1),
        ("{% call foo %}{% endcall %}", "'call' needs a macro call", 1),
        ("{% filter %}{% endfilter %}", "expected a filter name", 1),
        ("{% break %}", "'break' outside of a for loop", 1),
        ("{% if x %}{% continue %}{% endif %}", "'continue' outside of a for loop", 1),
        (
            "{% for x in y %}{% macro m() %}{% break %}{% endmacro %}{% endfor %}",
            "'break' outside of a for loop",
            1,
        ),
        (
            "{% for x in y %}{% else %}{% break %}{% endfor %}",
            "'break' outside of a for loop",
            1,
        ),
        ("{% endraw %}", "unexpected 'endraw'", 1),
    ],
)
def test_statement_syntax_errors(source, message, line):
    with pytest.raises(TemplateSyntaxError) as excinfo:
        parse(source, "page.html")
    assert message in excinfo.value.message
    assert excinfo.value.line == line
    assert excinfo.value.path == "page.html"


def test_break_is_fine_inside_if_inside_for():
    parse("{% for x in y %}{% if x %}{% break %}{% endif %}{% endfor %}")


def test_syntax_error_string_has_path_and_line():
    with pytest.raises(TemplateSyntaxError) as excinfo:
        parse("\n{% foo %}", "themes/x/page.html")
    assert str(excinfo.value) == "themes/x/page.html:2: unknown tag 'foo'"
