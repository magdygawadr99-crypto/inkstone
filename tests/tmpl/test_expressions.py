from __future__ import annotations

import pytest

from inkstone.tmpl import Environment, TemplateRuntimeError, UndefinedError


class Author:
    def __init__(self, name):
        self.name = name
        self.tags = ["a", "b"]
        self._secret = "hidden"

    def greet(self, greeting="Hello", punctuation="!"):
        return f"{greeting}, {self.name}{punctuation}"

    def _private(self):
        return "nope"

    def __getitem__(self, key):
        if key == "via_item":
            return "item value"
        raise KeyError(key)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ 1 + 2 }}", "3"),
        ("{{ 7 - 10 }}", "-3"),
        ("{{ 2 * 3 }}", "6"),
        ("{{ 7 / 2 }}", "3.5"),
        ("{{ 7 // 2 }}", "3"),
        ("{{ 7 % 3 }}", "1"),
        ("{{ 2 ** 10 }}", "1024"),
        ("{{ -3 + 1 }}", "-2"),
        ("{{ +3 }}", "3"),
        ("{{ - -3 }}", "3"),
        ("{{ 1.5 + 1 }}", "2.5"),
        ("{{ 'ab' * 2 }}", "abab"),
        ("{{ 'a' + 'b' }}", "ab"),
        ("{{ [1] + [2] }}", "[1, 2]"),
        ("{{ '%s-%03d' % ('x', 7) }}", "x-007"),
    ],
)
def test_arithmetic(render, source, expected):
    assert render(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ 1 + 2 * 3 }}", "7"),
        ("{{ (1 + 2) * 3 }}", "9"),
        ("{{ 10 - 4 - 3 }}", "3"),
        ("{{ 2 * 3 % 4 }}", "2"),
        ("{{ 2 * 3 ** 2 }}", "18"),
        ("{{ 2 ** 3 ** 2 }}", "64"),
        ("{{ -2 ** 2 }}", "4"),
        ("{{ 'a' ~ 1 * 2 }}", "a2"),
        ("{{ 1 + 1 == 2 }}", "True"),
        ("{{ not 1 == 2 }}", "True"),
        ("{{ true or false and false }}", "True"),
        ("{{ (true or false) and false }}", "False"),
        ("{{ not false and false }}", "False"),
        ("{{ not (false and false) }}", "True"),
        ("{{ 1 if false else 2 if false else 3 }}", "3"),
        ("{{ 'x' if 1 > 2 or 3 > 2 else 'y' }}", "x"),
        ("{{ 3 | string ~ 4 }}", "34"),
        ("{{ -3 | abs }}", "3"),
        ("{{ 2 + 30 | string | length }}", "4"),
        ("{{ 5 - 3 is odd }}", "4"),
        ("{{ 1 in [1, 2] and 3 not in [1, 2] }}", "True"),
        ("{{ 1 + 2 in [3] }}", "True"),
        ("{{ [1, 2] | length * 2 }}", "4"),
    ],
)
def test_precedence(render, source, expected):
    assert render(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1 == 1", True),
        ("1 == 2", False),
        ("1 != 2", True),
        ("1 < 2", True),
        ("2 <= 2", True),
        ("1 > 2", False),
        ("2 >= 3", False),
        ("'a' < 'b'", True),
        ("1 == 1.0", True),
        ("'1' == 1", False),
        ("1 < 2 < 3", True),
        ("1 < 3 < 2", False),
        ("3 > 2 >= 2 != 1", True),
        ("[1, 2] == [1, 2]", True),
        ("none == none", True),
        ("missing == none", False),
    ],
)
def test_comparisons(render, source, expected):
    assert render("{{ " + source + " }}") == str(expected)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("2 in [1, 2, 3]", True),
        ("5 in [1, 2, 3]", False),
        ("5 not in [1, 2, 3]", True),
        ("'ell' in 'hello'", True),
        ("'k' in {'k': 1}", True),
        ("1 in {'k': 1}", False),
        ("2 in (1, 2)", True),
        ("'x' in missing", False),
        ("'x' not in missing", True),
    ],
)
def test_membership(render, source, expected):
    assert render("{{ " + source + " }}") == str(expected)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ '' or 'fallback' }}", "fallback"),
        ("{{ 'first' or 'second' }}", "first"),
        ("{{ 'a' and 'b' }}", "b"),
        ("{{ 0 and 1 }}", "0"),
        ("{{ none or 0 }}", "0"),
        ("{{ missing or 'default' }}", "default"),
        ("{{ [] or [1] }}", "[1]"),
        ("{{ not '' }}", "True"),
        ("{{ not [0] }}", "False"),
    ],
)
def test_and_or_return_their_operands(render, source, expected):
    assert render(source) == expected


def test_and_or_short_circuit(render):
    calls = []

    def boom():
        calls.append(1)
        return True

    source = "{{ false and boom() }}{{ true or boom() }}"
    assert render(source, boom=boom) == "FalseTrue"
    assert calls == []
    render("{{ true and boom() }}{{ false or boom() }}", boom=boom)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ [1, 2.5, 'a', true, false, none] }}", "[1, 2.5, 'a', True, False, None]"),
        ("{{ {'a': 1, 'b': [2]} }}", "{'a': 1, 'b': [2]}"),
        ("{{ (1, 'two') }}", "(1, 'two')"),
        ("{{ (1,) }}", "(1,)"),
        ("{{ () }}", "()"),
        ("{{ 1, 2 }}", "(1, 2)"),
        ("{{ {'a': 1}['a'] }}", "1"),
        ("{{ {1: 'one'}[1] }}", "one"),
        ("{{ 1_000 + 0x10 }}", "1016"),
        ("{{ 'multi' 'part' }}", "multipart"),
        ("{{ \"it's\" }}", "it's"),
        ("{{ 'line\\nbreak' }}", "line\nbreak"),
        ("{{ True }}|{{ False }}", "True|False"),
        ("{{ 1e2 }}", "100.0"),
        ("{{ [[1, 2], [3]][0][1] }}", "2"),
    ],
)
def test_literals(render, source, expected):
    assert render(source) == expected


def test_none_prints_as_nothing(render):
    assert render("[{{ none }}][{{ value }}]", value=None) == "[][]"


def test_concatenation(render):
    assert render("{{ 'a' ~ 1 ~ 2.5 ~ true }}") == "a12.5True"
    assert render("{{ 'a' ~ none ~ missing ~ 'b' }}") == "ab"
    assert render("{{ name ~ '!' }}", name="World") == "World!"


def test_ternary(render):
    assert render("{{ 'yes' if x else 'no' }}", x=1) == "yes"
    assert render("{{ 'yes' if x else 'no' }}", x=0) == "no"
    assert render("[{{ 'yes' if x }}]", x=0) == "[]"
    assert render("{{ ('a' if x) is defined }}", x=0) == "False"


def test_ternary_only_evaluates_the_chosen_branch(render):
    source = "{{ 1 if x else boom() }}{{ boom() if not x else 2 }}"
    assert render(source, x=True) == "12"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ author.name }}", "Ada"),
        ("{{ author['name'] }}", "Ada"),
        ("{{ author.tags[1] }}", "b"),
        ("{{ author.tags.0 }}", "a"),
        ("{{ author.tags[-1] }}", "b"),
        ("{{ author.via_item }}", "item value"),
        ("{{ page.title }}", "Home"),
        ("{{ page['title'] }}", "Home"),
        ("{{ page.meta.tags.1 }}", "y"),
        ("{{ page['meta']['tags'][0] }}", "x"),
        ("{{ page[key] }}", "Home"),
        ("{{ page.meta[page.which] }}", "['x', 'y']"),
        ("{{ rows[0][1] }}", "2"),
        ("{{ rows.1.0 }}", "3"),
        ("{{ 'abc'[1] }}", "b"),
    ],
)
def test_attribute_and_item_access(render, source, expected):
    context = {
        "author": Author("Ada"),
        "page": {"title": "Home", "meta": {"tags": ["x", "y"]}, "which": "tags"},
        "key": "title",
        "rows": [[1, 2], [3, 4]],
    }
    assert render(source, **context) == expected


def test_dict_methods_win_over_keys_for_dot_access(render):
    data = {"items": "the key", "other": 1}
    assert render("{{ d['items'] }}", d=data) == "the key"
    assert render("{{ d.items() | list | length }}", d=data) == "2"


@pytest.mark.parametrize(
    "source",
    [
        "{{ page.nope }}",
        "{{ page['nope'] }}",
        "{{ page.nope.deeper.still }}",
        "{{ page.nope[0]['x'] }}",
        "{{ items[10] }}",
        "{{ items['key'] }}",
        "{{ author.nope }}",
        "{{ nothing.attr }}",
        "{{ 3.real_typo }}",
        "{{ missing }}",
        "{{ missing.attr }}",
    ],
)
def test_missing_things_print_as_nothing(render, source):
    context = {"page": {}, "items": [1], "author": Author("Ada"), "nothing": None}
    assert render("[" + source + "]", **context) == "[]"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("{{ xs[1:3] }}", "[1, 2]"),
        ("{{ xs[:2] }}", "[0, 1]"),
        ("{{ xs[3:] }}", "[3, 4]"),
        ("{{ xs[::2] }}", "[0, 2, 4]"),
        ("{{ xs[::-1] }}", "[4, 3, 2, 1, 0]"),
        ("{{ xs[1:4:2] }}", "[1, 3]"),
        ("{{ xs[-2:] }}", "[3, 4]"),
        ("{{ xs[:] }}", "[0, 1, 2, 3, 4]"),
        ("{{ xs[a:b] }}", "[1, 2, 3]"),
        ("{{ 'hello'[1:3] }}", "el"),
        ("{{ 'hello'[:-1] | upper }}", "HELL"),
    ],
)
def test_slices(render, source, expected):
    assert render(source, xs=[0, 1, 2, 3, 4], a=1, b=4) == expected


def test_function_calls(render):
    def describe(*args, **kwargs):
        return f"{args} {sorted(kwargs.items())}"

    assert render("{{ f() }}", f=describe) == "() []"
    assert render("{{ f(1, 'a') }}", f=describe) == "(1, 'a') []"
    assert render("{{ f(1, x=2, y=3) }}", f=describe) == "(1,) [('x', 2), ('y', 3)]"
    assert render("{{ f(*xs) }}", f=describe, xs=[1, 2]) == "(1, 2) []"
    assert render("{{ f(0, *xs, **kw) }}", f=describe, xs=[1], kw={"k": "v"}) == (
        "(0, 1) [('k', 'v')]"
    )
    assert render("{{ f(a=1, **kw) }}", f=describe, kw={"b": 2}) == (
        "() [('a', 1), ('b', 2)]"
    )


def test_method_calls(render):
    author = Author("Ada")
    assert render("{{ a.greet() }}", a=author) == "Hello, Ada!"
    assert render("{{ a.greet('Hi', punctuation='?') }}", a=author) == "Hi, Ada?"
    assert render("{{ 'a,b'.split(',') }}") == "['a', 'b']"
    assert render("{{ ' x '.strip().upper() }}") == "X"
    assert render("{{ d.get('k', 'dflt') }}{{ d.get('a') }}", d={"a": 1}) == "dflt1"
    assert render("{{ '{}-{}'.format(1, 2) }}") == "1-2"
    assert render("{{ 'a-b' | replace('-', '+') | upper }}") == "A+B"


def test_calling_the_result_of_a_call(render):
    def adder(x):
        return lambda y: x + y

    assert render("{{ adder(1)(2) }}", adder=adder) == "3"


def test_duplicate_keyword_from_double_star(render):
    with pytest.raises(TemplateRuntimeError, match="more than one value.*'a'"):
        render("{{ f(a=1, **kw) }}", f=dict, kw={"a": 2})


def test_calling_something_that_is_not_callable(render):
    with pytest.raises(TemplateRuntimeError, match="'int' object is not callable"):
        render("{{ x() }}", x=3)
    with pytest.raises(TemplateRuntimeError, match="none is not callable"):
        render("{{ x() }}", x=None)


def test_calling_an_undefined_name(render):
    with pytest.raises(UndefinedError, match="'nope' is undefined"):
        render("{{ nope() }}")
    with pytest.raises(UndefinedError, match="has no attribute 'nope'"):
        render("{{ page.nope(1) }}", page={})


@pytest.mark.parametrize(
    "source",
    [
        "{{ author._secret }}",
        "{{ author['_secret'] }}",
        "{{ author.__class__ }}",
        "{{ author['__class__'] }}",
        "{{ author.__dict__ }}",
        "{{ author | attr('_secret') }}",
        "{{ author | attr('__class__') }}",
        "{{ 'x'.__class__.__mro__ }}",
        "{{ [author] | map(attribute='_secret') | join }}",
    ],
)
def test_private_attributes_are_invisible(render, source):
    assert render("[" + source + "]", author=Author("Ada")) == "[]"


@pytest.mark.parametrize(
    "source",
    [
        "{{ author._private() }}",
        "{{ author['_private']() }}",
        "{{ author.__init__('x') }}",
        "{{ ''.__class__() }}",
        "{{ author.greet.__call__() }}",
        "{{ data._fn() }}",
    ],
)
def test_private_attributes_can_not_be_called(render, source):
    with pytest.raises(TemplateRuntimeError, match="refusing to call"):
        render(source, author=Author("Ada"), data={"_fn": lambda: "x"})


def test_underscore_keys_of_dicts_are_plain_data(render):
    doc = {"_id": 7, "__meta__": "m"}
    source = "{{ doc._id }}/{{ doc['_id'] }}/{{ doc.__meta__ }}"
    assert render(source, doc=doc) == "7/7/m"


def test_underscore_variables_are_fine(render):
    assert render("{{ _name }}{{ _f() }}", _name="x", _f=lambda: "y") == "xy"


def test_strict_mode_reports_private_access():
    env = Environment(strict_undefined=True)
    with pytest.raises(UndefinedError, match="'_secret' is private"):
        env.from_string("{{ author._secret }}").render(author=Author("Ada"))


def test_default_globals(render):
    assert render("{{ range(3) | list }}") == "[0, 1, 2]"
    assert render("{{ range(1, 10, 4) | join(',') }}") == "1,5,9"
    assert render("{{ dict(a=1, b=2) }}") == "{'a': 1, 'b': 2}"
    assert render("{{ dict(a=1).a }}") == "1"


def test_cycler(render):
    source = (
        "{% set c = cycler('odd', 'even') %}"
        "{{ c.next() }} {{ c.next() }} {{ c.current }} {{ c.next() }}"
        "{% do c.reset() %} {{ c.next() }}"
    )
    assert render(source) == "odd even odd odd odd"
    with pytest.raises(TemplateRuntimeError, match="at least one value"):
        render("{{ cycler() }}")


def test_joiner(render):
    source = (
        "{% set comma = joiner(', ') %}"
        "{% for x in xs %}{{ comma() }}{{ x }}{% endfor %}"
    )
    assert render(source, xs=[1, 2, 3]) == "1, 2, 3"


def test_expressions_can_span_lines(render):
    source = "{{ [\n  1,\n  2,\n] |\n  sum\n}}"
    assert render(source) == "3"


def test_filter_arguments(render):
    assert render('{{ "hello wonderful world" | truncate(12, end="…") }}') == (
        "hello…"
    )
    assert render("{{ xs | join(', ') }}", xs=[1, 2]) == "1, 2"
    assert render("{{ xs | sort(reverse=true) | first }}", xs=[2, 9, 4]) == "9"
    assert render("{{ 3.14159 | round(2) }}") == "3.14"
    assert render("{{ x | default(y | upper) }}", y="fallback") == "FALLBACK"
    assert render("{{ 'a b' | replace(*args) }}", args=(" ", "_")) == "a_b"
    assert render("{{ 5 | round(**kw) }}", kw={"method": "floor"}) == "5.0"
