from __future__ import annotations

import pytest

from inkstone.tmpl import Environment, TemplateRuntimeError, UndefinedError

GRADE = "{% if n >= 90 %}A{% elif n >= 80 %}B{% elif n >= 70 %}C{% else %}F{% endif %}"


@pytest.mark.parametrize(
    "n, grade", [(95, "A"), (90, "A"), (85, "B"), (70, "C"), (3, "F")]
)
def test_if_elif_else(render, n, grade):
    assert render(GRADE, n=n) == grade


def test_if_without_else(render):
    assert render("[{% if x %}yes{% endif %}]", x=True) == "[yes]"
    assert render("[{% if x %}yes{% endif %}]", x=False) == "[]"


@pytest.mark.parametrize(
    "value, truthy",
    [
        (True, True),
        (1, True),
        ("text", True),
        ([0], True),
        ({"a": 1}, True),
        (False, False),
        (0, False),
        ("", False),
        ([], False),
        ({}, False),
        (None, False),
    ],
)
def test_if_truthiness(render, value, truthy):
    expected = "T" if truthy else "F"
    assert render("{% if x %}T{% else %}F{% endif %}", x=value) == expected


def test_if_undefined_is_false(render):
    assert render("{% if nope %}T{% else %}F{% endif %}") == "F"
    assert render("{% if not nope.deeper %}T{% endif %}") == "T"


def test_nested_ifs(render):
    source = "{% if a %}{% if b %}ab{% else %}a{% endif %}{% else %}none{% endif %}"
    assert render(source, a=1, b=1) == "ab"
    assert render(source, a=1, b=0) == "a"
    assert render(source, a=0, b=1) == "none"


def test_if_with_complex_condition(render):
    source = "{% if user and user.age >= 18 and 'admin' in user.roles %}ok{% endif %}"
    assert render(source, user={"age": 30, "roles": ["admin"]}) == "ok"
    assert render(source, user={"age": 30, "roles": []}) == ""
    assert render(source) == ""


def test_for_basic(render):
    assert render("{% for x in xs %}<{{ x }}>{% endfor %}", xs=[1, 2, 3]) == "<1><2><3>"


def test_for_over_dict_items(render):
    source = "{% for k, v in d.items() %}{{ k }}={{ v }};{% endfor %}"
    assert render(source, d={"a": 1, "b": 2}) == "a=1;b=2;"


def test_for_over_a_dict_gives_keys(render):
    assert render("{% for k in d %}{{ k }}{% endfor %}", d={"a": 1, "b": 2}) == "ab"


def test_for_over_a_string_and_a_range(render):
    assert render("{% for c in 'abc' %}{{ c }}.{% endfor %}") == "a.b.c."
    assert render("{% for i in range(3) %}{{ i }}{% endfor %}") == "012"


def test_for_over_a_generator(render):
    source = "{% for x in g %}{{ x }}{{ loop.length }}{% endfor %}"
    assert render(source, g=iter("ab")) == "a2b2"
    assert render(source, g=(n * n for n in range(3))) == "031343"


def test_for_nested_unpacking(render):
    source = "{% for a, (b, c) in rows %}{{ a }}{{ b }}{{ c }} {% endfor %}"
    assert render(source, rows=[(1, (2, 3)), (4, (5, 6))]) == "123 456 "


def test_for_else(render):
    source = "{% for x in xs %}{{ x }}{% else %}empty{% endfor %}"
    assert render(source, xs=[1, 2]) == "12"
    assert render(source, xs=[]) == "empty"
    assert render(source) == "empty"


@pytest.mark.parametrize(
    "attribute, expected",
    [
        ("index", "1 2 3"),
        ("index0", "0 1 2"),
        ("revindex", "3 2 1"),
        ("revindex0", "2 1 0"),
        ("first", "True False False"),
        ("last", "False False True"),
        ("length", "3 3 3"),
        ("depth", "1 1 1"),
        ("depth0", "0 0 0"),
    ],
)
def test_loop_attributes(render, attribute, expected):
    source = "{% for x in 'abc' %}{{ loop." + attribute + " }} {% endfor %}"
    assert render(source).strip() == expected


def test_loop_cycle(render):
    source = "{% for x in range(5) %}{{ loop.cycle('odd', 'even') }} {% endfor %}"
    assert render(source) == "odd even odd even odd "
    with pytest.raises(TemplateRuntimeError, match="at least one value"):
        render("{% for x in 'a' %}{{ loop.cycle() }}{% endfor %}")


def test_loop_previtem_and_nextitem(render):
    source = (
        "{% for x in xs %}"
        "{{ loop.previtem | default('-') }}<{{ x }}>{{ loop.nextitem | default('-') }} "
        "{% endfor %}"
    )
    assert render(source, xs="abc") == "-<a>b a<b>c b<c>- "
    assert render("{% for x in 'a' %}[{{ loop.previtem }}]{% endfor %}") == "[]"


def test_loop_changed(render):
    source = "{% for x in xs %}{% if loop.changed(x) %}{{ x }}{% endif %}{% endfor %}"
    assert render(source, xs=[1, 1, 2, 2, 2, 3, 1]) == "1231"


def test_loop_filter(render):
    source = (
        "{% for x in xs if x is odd %}{{ x }}:{{ loop.index }}/{{ loop.length }} "
        "{% else %}none{% endfor %}"
    )
    assert render(source, xs=[1, 2, 3, 4, 5]) == "1:1/3 3:2/3 5:3/3 "
    assert render(source, xs=[2, 4]) == "none"


def test_loop_filter_with_unpacking(render):
    source = "{% for k, v in d.items() if v > 1 %}{{ k }}{% endfor %}"
    assert render(source, d={"a": 1, "b": 2, "c": 3}) == "bc"


def test_nested_loops_have_their_own_loop_variable(render):
    source = (
        "{% for row in rows %}{% set outer = loop %}"
        "{% for cell in row %}{{ outer.index }}.{{ loop.index }} {% endfor %}"
        "{% endfor %}"
    )
    assert render(source, rows=[[1, 2], [3]]) == "1.1 1.2 2.1 "


def test_loop_variables_do_not_leak(render):
    source = (
        "{% for x in xs %}{% set seen = x %}{% endfor %}"
        "[{{ x }}{{ seen }}{{ loop }}]"
    )
    assert render(source, xs=[1, 2]) == "[]"


def test_loop_body_starts_fresh_every_iteration(render):
    source = "{% for x in xs %}[{{ prev }}]{% set prev = x %}{% endfor %}"
    assert render(source, xs=[1, 2, 3]) == "[][][]"


def test_loop_sees_and_shadows_outer_variables(render):
    source = "{% set x = 'outer' %}{% for x in 'ab' %}{{ x }}{{ y }}{% endfor %}{{ x }}"
    assert render(source, y="!") == "a!b!outer"


def test_namespace_carries_state_out_of_a_loop(render):
    source = (
        "{% set ns = namespace(total=0, seen=[]) %}"
        "{% for x in xs %}{% set ns.total = ns.total + x %}{% endfor %}"
        "{{ ns.total }}"
    )
    assert render(source, xs=[1, 2, 3]) == "6"


def test_namespace_assignment_needs_a_namespace(render):
    with pytest.raises(TemplateRuntimeError, match="'d' is not a namespace"):
        render("{% set d.x = 1 %}", d={})


def test_recursive_loop(render):
    tree = [
        {"name": "a", "children": [{"name": "a1", "children": []}]},
        {"name": "b", "children": [{"name": "b1", "children": [{"name": "b1x"}]}]},
    ]
    source = (
        "{% for node in tree recursive %}"
        "{{ node.name }}@{{ loop.depth }}"
        "{% if node.children %}({{ loop(node.children) }}){% endif %}"
        "{% if not loop.last %},{% endif %}"
        "{% endfor %}"
    )
    assert render(source, tree=tree) == "a@1(a1@2),b@1(b1@2(b1x@3))"


def test_calling_loop_without_recursive(render):
    with pytest.raises(TemplateRuntimeError, match="marked 'recursive'"):
        render("{% for x in [1] %}{{ loop([2]) }}{% endfor %}")


def test_break_and_continue(render):
    source = (
        "{% for x in range(10) %}"
        "{% if x is odd %}{% continue %}{% endif %}"
        "{% if x > 6 %}{% break %}{% endif %}"
        "{{ x }}"
        "{% endfor %}"
    )
    assert render(source) == "0246"


def test_break_only_leaves_the_inner_loop(render):
    source = (
        "{% for a in 'xy' %}{% for b in '123' %}"
        "{% if b == '2' %}{% break %}{% endif %}{{ a }}{{ b }} "
        "{% endfor %}{% endfor %}"
    )
    assert render(source) == "x1 y1 "


def test_break_inside_with_restores_scopes(render):
    source = (
        "{% for x in 'abc' %}{% with y = x %}{% break %}{% endwith %}{% endfor %}"
        "[{{ y }}{{ x }}]"
    )
    assert render(source) == "[]"


def test_for_over_something_that_is_not_iterable(render):
    with pytest.raises(TemplateRuntimeError, match="can't loop over 'int' object"):
        render("{% for x in 5 %}{% endfor %}")
    with pytest.raises(TemplateRuntimeError, match="can't loop over none"):
        render("{% for x in nothing %}{% endfor %}", nothing=None)


def test_for_unpacking_mismatch(render):
    source = "{% for a, b in rows %}{% endfor %}"
    with pytest.raises(TemplateRuntimeError, match="expected 2 values.*got 3"):
        render(source, rows=[(1, 2, 3)])
    with pytest.raises(TemplateRuntimeError, match="can't unpack 'int' object"):
        render(source, rows=[1])


def test_set(render):
    assert render("{% set x = 1 + 2 %}{{ x }}") == "3"
    assert render("{% set x = 'a' %}{% set x = x ~ 'b' %}{{ x }}") == "ab"
    assert render("{% set a, b = 1, 2 %}{{ a }}{{ b }}") == "12"
    assert render("{% set a, (b, c) = p %}{{ a }}{{ b }}{{ c }}", p=(1, "23")) == "123"
    assert render("{% set xs = [1, 2] %}{% set d = {'k': xs} %}{{ d.k[1] }}") == "2"


def test_set_overrides_render_variables_only_inside_the_template(render):
    context = {"x": "given"}
    assert render("{% set x = 'changed' %}{{ x }}", **context) == "changed"
    assert context == {"x": "given"}


def test_set_inside_if_is_visible_afterwards(render):
    source = (
        "{% if flag %}{% set x = 'yes' %}{% else %}{% set x = 'no' %}{% endif %}"
        "{{ x }}"
    )
    assert render(source, flag=True) == "yes"
    assert render(source, flag=False) == "no"


def test_set_block(render):
    source = "{% set greeting %}Hello {{ name }}!{% endset %}[{{ greeting }}]"
    assert render(source, name="Ada") == "[Hello Ada!]"


def test_set_block_with_filters(render):
    source = "{% set title | trim | upper %}  some {{ what }}  {% endset %}{{ title }}"
    assert render(source, what="text") == "SOME TEXT"
    source = "{% set t | replace('a', 'o') | center(8) %}banana{% endset %}[{{ t }}]"
    assert render(source) == "[ bonono ]"


def test_set_block_has_its_own_scope(render):
    source = "{% set a %}{% set inner = 1 %}{{ inner }}{% endset %}{{ a }}[{{ inner }}]"
    assert render(source) == "1[]"


def test_set_unpacking_errors(render):
    with pytest.raises(TemplateRuntimeError, match="expected 2 values"):
        render("{% set a, b = 1, 2, 3 %}")


def test_with(render):
    # b is computed before the with scope exists, so it does not see the new a
    source = (
        "{% with a = 1, b = a | default('outer') %}{{ a }}{{ b }}{% endwith %}"
        "[{{ a }}]"
    )
    assert render(source) == "1outer[]"


def test_with_shadows_and_restores(render):
    source = "{% with x = 'inner' %}{{ x }}{% set y = 1 %}{% endwith %}{{ x }}[{{ y }}]"
    assert render(source, x="outer") == "innerouter[]"


def test_with_without_assignments_is_just_a_scope(render):
    assert render("{% with %}{% set x = 1 %}{{ x }}{% endwith %}[{{ x }}]") == "1[]"


def test_with_unpacking(render):
    source = "{% with (a, b) = pair %}{{ a }}-{{ b }}{% endwith %}"
    assert render(source, pair=[1, 2]) == "1-2"


def test_raw(render):
    source = "{% raw %}{{ not }} {% evaluated %} {# at all #}{% endraw %}{{ 1 }}"
    assert render(source) == "{{ not }} {% evaluated %} {# at all #}1"


def test_comments_are_dropped(render):
    assert render("a{# {{ boom() }} {% endif %} #}b") == "ab"
    assert render("a{#\n multi\n line\n#}b") == "ab"


def test_filter_block(render):
    source = "{% filter upper %}hello {{ name }}{% endfilter %}"
    assert render(source, name="x") == "HELLO X"


def test_filter_block_with_chain_and_arguments(render):
    source = "{% filter trim | replace('a', 'o') | center(10) %} banana {% endfilter %}"
    assert render(source) == "  bonono  "


def test_filter_block_body_has_its_own_scope(render):
    source = "{% filter upper %}{% set x = 'in' %}{{ x }}{% endfilter %}[{{ x }}]"
    assert render(source) == "IN[]"


def test_do(render):
    source = "{% set xs = [1] %}{% do xs.append(2) %}{% do xs.extend([3, 4]) %}{{ xs }}"
    assert render(source) == "[1, 2, 3, 4]"


def test_statements_nest_freely(render):
    source = (
        "{% for group in groups %}"
        "{% with items = group.entries | sort %}"
        "{% if items %}{{ group.name }}: "
        "{% for item in items %}"
        "{{ item }}{% if not loop.last %}, {% endif %}"
        "{% endfor %}"
        "{% else %}{{ group.name }}: -{% endif %}"
        "{% endwith %}\n"
        "{% endfor %}"
    )
    groups = [{"name": "A", "entries": [3, 1, 2]}, {"name": "B", "entries": []}]
    assert render(source, groups=groups) == "A: 1, 2, 3\nB: -\n"


def test_undefined_in_strict_loop_is_an_error():
    env = Environment(strict_undefined=True)
    with pytest.raises(UndefinedError, match="'xs' is undefined"):
        env.from_string("{% for x in xs %}{% endfor %}").render()
