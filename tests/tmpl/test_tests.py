from __future__ import annotations

import pytest

from inkstone.tmpl import Markup, TemplateRuntimeError
from inkstone.tmpl.tests_builtin import TESTS


def check(render, expression, **context):
    return render("{{ " + expression + " }}", **context) == "True"


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("x is defined", True),
        ("nope is defined", False),
        ("nope is undefined", True),
        ("nope is not defined", True),
        ("d.missing is defined", False),
        ("d.k is defined", True),
        ("d.k.deeper is undefined", True),
        ("none is defined", True),
        ("none is none", True),
        ("x is none", False),
        ("x is not none", True),
        ("nope is none", False),
    ],
)
def test_defined_and_none(render, expression, expected):
    assert check(render, expression, x=1, d={"k": "v"}) is expected


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("true is boolean", True),
        ("1 is boolean", False),
        ("true is true", True),
        ("1 is true", False),
        ("false is false", True),
        ("0 is false", False),
        ("1 is integer", True),
        ("1.0 is integer", False),
        ("true is integer", False),
        ("1.5 is float", True),
        ("1 is float", False),
        ("1 is number", True),
        ("1.5 is number", True),
        ("'1' is number", False),
        ("true is number", False),
        ("'a' is string", True),
        ("1 is string", False),
        ("{} is mapping", True),
        ("[] is mapping", False),
        ("[] is sequence", True),
        ("(1, 2) is sequence", True),
        ("'abc' is sequence", True),
        ("{} is sequence", True),
        ("1 is sequence", False),
        ("nope is sequence", False),
        ("[] is iterable", True),
        ("'abc' is iterable", True),
        ("range(3) is iterable", True),
        ("1 is iterable", False),
        ("nope is iterable", False),
        ("range is callable", True),
        ("'abc'.upper is callable", True),
        ("1 is callable", False),
        ("nope is callable", False),
    ],
)
def test_type_tests(render, expression, expected):
    assert check(render, expression) is expected


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("2 is even", True),
        ("3 is even", False),
        ("3 is odd", True),
        ("0 is odd", False),
        ("-3 is odd", True),
        ("9 is divisibleby 3", True),
        ("9 is divisibleby(2)", False),
        ("3 is eq 3", True),
        ("3 is equalto 4", False),
        ("3 is ne 4", True),
        ("3 is lt 4", True),
        ("3 is lessthan 3", False),
        ("3 is le 3", True),
        ("3 is gt 2", True),
        ("3 is greaterthan 3", False),
        ("3 is ge 3", True),
        ("'a' is eq 'a'", True),
        ("3 is in [1, 2, 3]", True),
        ("'z' is in 'abc'", False),
        ("3 is not in [1, 2]", True),
        ("'abc' is lower", True),
        ("'aBc' is lower", False),
        ("'ABC' is upper", True),
        ("'posts/hello.md' is startingwith 'posts/'", True),
        ("'posts/hello.md' is startingwith('pages/')", False),
        ("'posts/hello.md' is endingwith '.md'", True),
        ("'photo.jpg' is endingwith(('.png', '.jpg'))", True),
        ("[1, 2] is containing 2", True),
        ("'hello' is containing 'ell'", True),
        ("{'k': 1} is containing 'v'", False),
        ("'post-2024-03' is matching '\\\\d{4}-\\\\d{2}$'", True),
        ("'post' is matching '^\\\\d+$'", False),
        ("'upper' is filter", True),
        ("'nope' is filter", False),
        ("'defined' is test", True),
        ("'nope' is test", False),
    ],
)
def test_value_tests(render, expression, expected):
    assert check(render, expression) is expected


def test_sameas(render):
    marker = object()
    assert check(render, "a is sameas b", a=marker, b=marker)
    assert not check(render, "a is sameas b", a=[1], b=[1])
    assert check(render, "x is sameas none", x=None)
    assert check(render, "x is sameas false", x=False)
    assert not check(render, "x is sameas false", x=0)


def test_escaped(render):
    assert check(render, "x is escaped", x=Markup("<b>"))
    assert not check(render, "x is escaped", x="<b>")
    assert check(render, "(x | safe) is escaped", x="<b>")
    assert check(render, "(x | e) is escaped", x="<b>")


@pytest.mark.parametrize(
    "name, expected",
    [
        ("==", True),
        ("!=", False),
        ("<", False),
        ("<=", True),
        (">", False),
        (">=", True),
    ],
)
def test_comparison_tests_also_go_by_their_symbols(env, name, expected):
    assert env.call_test(name, 2, [2]) is expected


def test_tests_in_conditions(render):
    source = (
        "{% if x is defined and x is not none and x is string %}text"
        "{% elif x is number %}number{% else %}other{% endif %}"
    )
    assert render(source, x="a") == "text"
    assert render(source, x=3) == "number"
    assert render(source, x=None) == "other"
    assert render(source) == "other"


def test_test_result_can_be_negated_and_combined(render):
    assert check(render, "not 3 is even")
    assert check(render, "3 is odd and 4 is even")
    assert check(render, "3 is even or 4 is even")
    assert check(render, "(3 is even) == false")


def test_unknown_test(render):
    with pytest.raises(TemplateRuntimeError) as excinfo:
        render("{{ 3 is evn }}")
    assert excinfo.value.message == "no test named 'evn', did you mean 'even'?"


def test_custom_test(env):
    env.tests["longer_than"] = lambda value, n: len(value) > n
    template = env.from_string(
        "{{ 'abc' is longer_than 2 }} {{ 'abc' is longer_than(5) }}"
        " {{ words | select('longer_than', 3) | join(',') }}"
    )
    assert template.render(words=["a", "four", "seven"]) == "True False four,seven"


def test_test_results_are_booleans(env):
    env.tests["truthy_string"] = lambda value: "yes" if value else ""
    assert env.from_string("{{ 1 is truthy_string }}").render() == "True"
    assert env.from_string("{{ 0 is truthy_string }}").render() == "False"


def test_builtin_tests_table(env):
    assert env.tests == TESTS
    assert env.tests is not TESTS
    expected = (
        "defined undefined none string number mapping sequence iterable even odd "
        "divisibleby sameas in eq ne lt gt startingwith"
    )
    assert set(expected.split()) <= set(TESTS)
