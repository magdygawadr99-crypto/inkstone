from __future__ import annotations

import pytest

from inkstone.tmpl import Environment, StrictUndefined, Undefined, UndefinedError


@pytest.fixture
def strict():
    return Environment(autoescape=False, strict_undefined=True)


def strict_render(strict, source, **context):
    return strict.from_string(source).render(**context)


def test_undefined_object_behaves_like_nothing():
    undefined = Undefined(name="x")
    assert str(undefined) == ""
    assert not undefined
    assert len(undefined) == 0
    assert list(undefined) == []
    assert "a" not in undefined
    assert undefined == Undefined(name="y")
    assert undefined != None  # noqa: E711
    assert undefined != ""
    assert repr(undefined) == "Undefined"
    assert {undefined: 1}[Undefined()] == 1


def test_undefined_lookups_give_the_same_undefined():
    undefined = Undefined(name="page")
    assert undefined.author is undefined
    assert undefined["key"][0].deeper is undefined
    assert not hasattr(undefined, "__html__")
    assert not hasattr(undefined, "_private")


@pytest.mark.parametrize(
    "operation",
    [
        lambda u: u + 1,
        lambda u: 1 + u,
        lambda u: u - 1,
        lambda u: u * 2,
        lambda u: 2 / u,
        lambda u: u // 2,
        lambda u: u % 2,
        lambda u: u**2,
        lambda u: -u,
        lambda u: abs(u),
        lambda u: u < 1,
        lambda u: u >= 1,
        lambda u: u(),
        lambda u: u("arg", key=1),
    ],
)
def test_undefined_can_not_be_computed_with(operation):
    with pytest.raises(UndefinedError, match="'x' is undefined"):
        operation(Undefined(name="x"))


def test_undefined_messages():
    assert Undefined(name="x")._message == "'x' is undefined"
    assert Undefined(obj={}, name="k")._message == "'dict' object has no attribute 'k'"
    assert Undefined(obj=[], name=3)._message == "'list' object has no element 3"
    assert Undefined(obj=None, name="k")._message == "none has no attribute 'k'"
    assert Undefined(hint="because")._message == "because"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("[{{ nope }}]", "[]"),
        ("[{{ nope.a.b['c'][0] }}]", "[]"),
        ("{{ nope | default('d') }}", "d"),
        ("{{ nope | length }}", "0"),
        ("{{ nope | upper }}|{{ nope | trim }}|", "||"),
        ("{{ nope | list }}", "[]"),
        ("{{ nope | join(',') }}|", "|"),
        ("{{ nope | first is undefined }}", "True"),
        ("{{ nope ~ 'x' }}", "x"),
        ("{{ nope == nope2 }}", "True"),
        ("{{ nope == '' }}", "False"),
        ("{{ nope is defined }}", "False"),
        ("{{ 'yes' if nope else 'no' }}", "no"),
        ("{{ nope or 'fallback' }}", "fallback"),
        ("{{ nope and 'never' }}|", "|"),
        ("{% for x in nope %}x{% else %}empty{% endfor %}", "empty"),
        ("{{ 'a' in nope }}", "False"),
        ("{{ nope | tojson }}", "null"),
        ("{{ [nope, 1] | select | list }}", "[1]"),
        ("{{ d.nope | default(d.k) }}", "v"),
        ("{{ (d.nope or d).k }}", "v"),
    ],
)
def test_lenient_mode(render, source, expected):
    assert render(source, d={"k": "v"}) == expected


@pytest.mark.parametrize(
    "source, message",
    [
        ("{{ nope + 1 }}", "'nope' is undefined"),
        ("{{ 1 + d.nope }}", "'dict' object has no attribute 'nope'"),
        ("{{ nope() }}", "'nope' is undefined"),
        ("{{ d.nope.deeper() }}", "'dict' object has no attribute 'nope'"),
        ("{{ nope < 3 }}", "'nope' is undefined"),
        ("{{ [3, nope, 1] | sort }}", "'nope' is undefined"),
        ("{{ xs[5] * 2 }}", "'list' object has no element 5"),
        ("{{ nope | abs }}", "'nope' is undefined"),
        ("{{ -nope }}", "'nope' is undefined"),
    ],
)
def test_lenient_mode_still_refuses_nonsense(render, source, message):
    with pytest.raises(UndefinedError) as excinfo:
        render(source, d={}, xs=[1])
    assert excinfo.value.message == message


def test_environment_picks_the_undefined_class(env, strict):
    assert env.undefined is Undefined
    assert strict.undefined is StrictUndefined
    assert issubclass(StrictUndefined, Undefined)
    assert not env.strict_undefined
    assert strict.strict_undefined


@pytest.mark.parametrize(
    "source, message",
    [
        ("{{ nope }}", "'nope' is undefined"),
        ("{{ d.nope }}", "'dict' object has no attribute 'nope'"),
        ("{{ d['nope'] }}", "'dict' object has no attribute 'nope'"),
        ("{{ xs[3] }}", "'list' object has no element 3"),
        ("{{ nope.attr }}", "'nope' is undefined"),
        ("{{ nope['key'] }}", "'nope' is undefined"),
        ("{% if nope %}{% endif %}", "'nope' is undefined"),
        ("{% if not d.nope %}{% endif %}", "has no attribute 'nope'"),
        ("{{ nope or 'x' }}", "'nope' is undefined"),
        ("{{ 'x' if nope else 'y' }}", "'nope' is undefined"),
        ("{% for x in nope %}{% endfor %}", "'nope' is undefined"),
        ("{{ nope ~ 'x' }}", "'nope' is undefined"),
        ("{{ nope == 1 }}", "'nope' is undefined"),
        ("{{ 1 in nope }}", "'nope' is undefined"),
        ("{{ nope | upper }}", "'nope' is undefined"),
        ("{{ nope | length }}", "'nope' is undefined"),
        ("{{ nope | int }}", "'nope' is undefined"),
        ("{{ nope | join }}", "'nope' is undefined"),
        ("{{ [nope] | join }}", "'nope' is undefined"),
        ("{{ nope | e }}", "'nope' is undefined"),
        ("{{ nope | items }}", "'nope' is undefined"),
        ("{{ {'a': nope} | tojson }}", "'nope' is undefined"),
        ("{{ 'a' if false }}", "the inline if was false"),
        ("{% macro m(a) %}{{ a }}{% endmacro %}{{ m() }}", "without its argument 'a'"),
        ("{% for x in [1] %}{{ loop.previtem }}{% endfor %}", "no previous item"),
        ("{{ [] | first }}", "first: the sequence is empty"),
        ("{{ [] | max }}", "max: the sequence is empty"),
    ],
)
def test_strict_mode_raises(strict, source, message):
    with pytest.raises(UndefinedError) as excinfo:
        strict_render(strict, source, d={}, xs=[1])
    assert message in excinfo.value.message


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ nope is defined }}", "False"),
        ("{{ nope is undefined }}", "True"),
        ("{{ d.nope is defined }}", "False"),
        ("{{ nope | default('d') }}", "d"),
        ("{{ d.nope | default('d') }}", "d"),
        ("{{ d.nope | d('') }}|", "|"),
        ("{% if nope is defined %}yes{% else %}no{% endif %}", "no"),
        ("{{ d.k }}{{ value }}", "v1"),
        ("[{{ none }}]", "[]"),
        ("{{ d.get('nope', 'x') }}", "x"),
        ("{% set maybe = nope %}{{ maybe is defined }}", "False"),
        ("{{ [nope] | length }}", "1"),
    ],
)
def test_strict_mode_allows_asking(strict, source, expected):
    assert strict_render(strict, source, d={"k": "v"}, value=1) == expected


def test_strict_error_has_the_line(strict):
    source = "a\nb {{ page.title }}\n{{ page.subtitle }}"
    with pytest.raises(UndefinedError) as excinfo:
        strict_render(strict, source, page={"title": 1})
    assert str(excinfo.value) == "<string>:3: 'dict' object has no attribute 'subtitle'"


def test_strict_undefined_with_autoescape():
    env = Environment(autoescape=True, strict_undefined=True)
    with pytest.raises(UndefinedError, match="'nope' is undefined"):
        env.from_string("{{ nope }}").render()
    assert env.from_string("{{ nope | default('<') }}").render() == "&lt;"


def test_strict_undefined_object():
    undefined = StrictUndefined(name="x")
    for operation in (str, bool, len, list, hash, int, float):
        with pytest.raises(UndefinedError):
            operation(undefined)
    with pytest.raises(UndefinedError):
        undefined.attr
    with pytest.raises(UndefinedError):
        undefined == 1
    assert repr(undefined) == "Undefined"
    assert not hasattr(undefined, "__html__")


def test_undefined_from_a_missing_key_differs_from_none(render):
    data = {"a": None}
    assert render("{{ d.a is none }} {{ d.a is defined }}", d=data) == "True True"
    assert render("{{ d.b is none }} {{ d.b is defined }}", d=data) == "False False"
