from __future__ import annotations

import pytest

from inkstone.tmpl import TemplateNotFound, TemplateRuntimeError, UndefinedError
from inkstone.tmpl.interpreter import MAX_INCLUDE_DEPTH


def test_include_sees_the_current_context(make_env):
    env = make_env(
        {
            "page": "{% set local = 'L' %}<{% include 'part' %}>",
            "part": "{{ title }}{{ local }}",
        }
    )
    assert env.get_template("page").render(title="T") == "<TL>"


def test_include_sees_loop_variables(make_env):
    env = make_env(
        {
            "page": "{% for item in items %}{% include 'row' %}{% endfor %}",
            "row": "[{{ loop.index }}:{{ item }}]",
        }
    )
    assert env.get_template("page").render(items="ab") == "[1:a][2:b]"


def test_include_can_not_change_the_including_template(make_env):
    env = make_env(
        {
            "page": "{% set x = 'page' %}{% include 'part' %}{{ x }}[{{ y }}]",
            "part": "{% set x = 'part' %}{% set y = 1 %}{{ x }}>",
        }
    )
    assert env.get_template("page").render() == "part>page[]"


def test_include_without_context(make_env):
    env = make_env(
        {
            "page": (
                "{% include 'part' without context %}|"
                "{% include 'part' with context %}"
            ),
            "part": "[{{ title }}{{ site_name }}]",
        }
    )
    env.globals["site_name"] = "G"
    assert env.get_template("page").render(title="T") == "[G]|[TG]"


def test_include_missing_template(make_env):
    env = make_env({"page": "a\n{% include 'nope' %}"})
    with pytest.raises(TemplateNotFound) as excinfo:
        env.get_template("page").render()
    assert excinfo.value.name == "nope"
    assert str(excinfo.value) == "page:2: template 'nope' not found"


def test_include_ignore_missing(make_env):
    env = make_env(
        {
            "page": (
                "[{% include 'nope' ignore missing %}]"
                "[{% include 'part' ignore missing %}]"
                "[{% include 'nope' ignore missing without context %}]"
            ),
            "part": "ok",
        }
    )
    assert env.get_template("page").render() == "[][ok][]"


def test_ignore_missing_does_not_hide_a_missing_nested_include(make_env):
    env = make_env(
        {
            "page": "{% include 'part' ignore missing %}",
            "part": "{% include 'nope' %}",
        }
    )
    with pytest.raises(TemplateNotFound, match="'nope'"):
        env.get_template("page").render()


def test_include_takes_the_first_existing_of_a_list(make_env):
    env = make_env(
        {
            "page": "{% include ['special-' ~ kind, 'generic'] %}",
            "generic": "generic",
            "special-post": "post",
        }
    )
    template = env.get_template("page")
    assert template.render(kind="post") == "post"
    assert template.render(kind="page") == "generic"


def test_include_list_with_nothing_found(make_env):
    env = make_env(
        {
            "page": "{% include ['a', 'b'] %}",
            "quiet": "[{% include ['a'] ignore missing %}]",
        }
    )
    with pytest.raises(TemplateNotFound, match="none of the templates 'a', 'b'"):
        env.get_template("page").render()
    assert env.get_template("quiet").render() == "[]"


def test_include_with_dynamic_name_and_template_object(make_env):
    env = make_env({"page": "{% include name %}+{% include tpl %}", "part": "part"})
    tpl = env.from_string("{{ 1 + 1 }}")
    assert env.get_template("page").render(name="part", tpl=tpl) == "part+2"


def test_include_of_undefined_name(make_env):
    env = make_env({"page": "{% include page.sidebar %}"})
    with pytest.raises(UndefinedError, match="can't load a template"):
        env.get_template("page").render(page={})


def test_included_template_can_use_inheritance(make_env):
    env = make_env(
        {
            "page": "<{% include 'card' %}>",
            "frame": "[{% block body %}{% endblock %}]",
            "card": "{% extends 'frame' %}{% block body %}{{ title }}{% endblock %}",
        }
    )
    assert env.get_template("page").render(title="T") == "<[T]>"


def test_blocks_of_included_templates_are_separate(make_env):
    env = make_env(
        {
            "page": "{% block a %}page{% endblock %}|{% include 'part' %}",
            "part": "{% block a %}part{% endblock %}",
        }
    )
    assert env.get_template("page").render() == "page|part"


def test_recursive_include_with_changing_data(make_env):
    env = make_env(
        {
            "tree": (
                "{{ node.name }}"
                "{% for node in node.children %}({% include 'tree' %}){% endfor %}"
            )
        }
    )
    node = {
        "name": "a",
        "children": [{"name": "b", "children": [{"name": "c"}]}, {"name": "d"}],
    }
    assert env.get_template("tree").render(node=node) == "a(b(c))(d)"


def test_circular_include_is_stopped(make_env):
    env = make_env({"a": "a{% include 'b' %}", "b": "b\n{% include 'a' %}"})
    with pytest.raises(TemplateRuntimeError) as excinfo:
        env.get_template("a").render()
    message = excinfo.value.message
    assert f"more than {MAX_INCLUDE_DEPTH} levels deep" in message
    assert "circular include" in message
    assert "a -> b -> a" in message


def test_self_include_is_stopped(make_env):
    env = make_env({"a": "{% include 'a' %}"})
    with pytest.raises(TemplateRuntimeError, match="circular include"):
        env.get_template("a").render()


def test_macro_basics(render):
    source = (
        "{% macro field(name, value='', type='text') %}"
        '<input type="{{ type }}" name="{{ name }}" value="{{ value }}">'
        "{% endmacro %}"
        "{{ field('user') }}{{ field('pw', type='password') }}"
        "{{ field('n', 1, 'number') }}"
    )
    assert render(source) == (
        '<input type="text" name="user" value="">'
        '<input type="password" name="pw" value="">'
        '<input type="number" name="n" value="1">'
    )


def test_macro_defaults_are_evaluated_per_call(render):
    source = (
        "{% macro m(a, b=a ~ '!', c=fallback) %}{{ a }}{{ b }}{{ c }}{% endmacro %}"
        "{{ m('x') }} {% set fallback = 'late' %}{{ m('y', c='-') }} {{ m('z') }}"
    )
    assert render(source, fallback="early") == "xx!early yy!- zz!late"


def test_macro_missing_argument_is_undefined(render):
    source = (
        "{% macro m(a, b) %}[{{ a }}{{ b }}]{{ b is defined }}{% endmacro %}"
        "{{ m(1) }}"
    )
    assert render(source) == "[1]False"


def test_macro_scope(render):
    source = (
        "{% set outer = 'O' %}"
        "{% macro m(x) %}{% set inner = x %}{{ outer }}{{ inner }}{{ later }}"
        "{% endmacro %}"
        "{% set later = 'L' %}"
        "{{ m('a') }}[{{ inner }}{{ x }}]"
    )
    assert render(source) == "OaL[]"


def test_macro_does_not_see_the_callers_locals(render):
    source = (
        "{% macro m() %}[{{ item }}]{% endmacro %}"
        "{% for item in 'ab' %}{{ m() }}{% endfor %}"
    )
    assert render(source) == "[][]"


def test_macros_can_call_each_other_and_themselves(render):
    source = (
        "{% macro countdown(n) %}"
        "{{ n }}{% if n > 0 %} {{ countdown(n - 1) }}{% endif %}"
        "{% endmacro %}"
        "{% macro twice(x) %}{{ later(x) }}{{ later(x) }}{% endmacro %}"
        "{% macro later(x) %}<{{ x }}>{% endmacro %}"
        "{{ countdown(3) }}|{{ twice('a') }}"
    )
    assert render(source) == "3 2 1 0|<a><a>"


def test_macro_varargs_and_kwargs(render):
    source = (
        "{% macro m(first) %}{{ first }}|{{ varargs | join(',') }}|"
        "{% for k, v in kwargs | dictsort %}{{ k }}={{ v }};{% endfor %}{% endmacro %}"
        "{{ m(1, 2, 3, b='B', a='A') }}"
    )
    assert render(source) == "1|2,3|a=A;b=B;"


@pytest.mark.parametrize(
    "call, message",
    [
        ("m(1, 2, 3)", "takes at most 2 positional argument\\(s\\), got 3"),
        ("m(1, c=3)", "unexpected keyword argument 'c'"),
        ("m(1, a=2)", "got two values for argument 'a'"),
    ],
)
def test_macro_call_errors(render, call, message):
    source = "{% macro m(a, b=0) %}{% endmacro %}{{ " + call + " }}"
    with pytest.raises(TemplateRuntimeError, match=message):
        render(source)


def test_macro_attributes(render):
    source = "{% macro m(a, b=1) %}{% endmacro %}{{ m.name }}{{ m.arguments }}"
    assert render(source) == "m('a', 'b')"


def test_macro_defined_in_a_loop_keeps_its_iteration(render):
    source = (
        "{% set ns = namespace(macros=[]) %}"
        "{% for x in 'ab' %}{% macro show() %}{{ x }}{% endmacro %}"
        "{% do ns.macros.append(show) %}{% endfor %}"
        "{% for m in ns.macros %}{{ m() }}{% endfor %}"
    )
    assert render(source) == "ab"


def test_macro_result_can_be_filtered_and_mapped(render):
    source = (
        "{% macro shout(x) %}{{ x | upper }}!{% endmacro %}"
        "{{ shout('a') | replace('!', '?') }} {{ shout('b') | length }}"
    )
    assert render(source) == "A? 2"


def test_call_block(render):
    source = (
        "{% macro box(title) %}<div><h2>{{ title }}</h2>{{ caller() }}</div>"
        "{% endmacro %}"
        "{% call box('T') %}body {{ value }}{% endcall %}"
    )
    assert render(source, value=1) == "<div><h2>T</h2>body 1</div>"


def test_call_block_with_arguments(render):
    source = (
        "{% macro each(items) %}{% for item in items %}{{ caller(item, loop.index) }}"
        "{% endfor %}{% endmacro %}"
        "{% call(item, n, sep=';') each(['a', 'b']) %}"
        "{{ n }}={{ item }}{{ sep }}"
        "{% endcall %}"
    )
    assert render(source) == "1=a;2=b;"


def test_call_block_body_sees_the_callers_scope(render):
    source = (
        "{% macro wrap() %}{% set hidden = 'no' %}[{{ caller() }}]{% endmacro %}"
        "{% for x in 'ab' %}"
        "{% call wrap() %}{{ x }}{{ hidden }}{% endcall %}"
        "{% endfor %}"
    )
    assert render(source) == "[a][b]"


def test_call_block_needs_a_macro_that_uses_caller(render):
    source = "{% macro plain() %}x{% endmacro %}{% call plain() %}body{% endcall %}"
    with pytest.raises(TemplateRuntimeError, match="never calls caller"):
        render(source)


def test_caller_is_undefined_outside_a_call_block(render):
    source = "{% macro m() %}{{ caller is defined }}{% endmacro %}{{ m() }}"
    assert render(source) == "False"
    source = "{% macro m() %}{{ caller() }}{% endmacro %}{{ m() }}"
    with pytest.raises(UndefinedError, match="not used in a call block"):
        render(source)


LIB = (
    "{% set version = '1.0' %}{% set _private = 'p' %}"
    "{% macro em(x) %}<em>{{ x }}</em>{% endmacro %}"
    "{% macro badge(x) %}[{{ em(x) }}{{ version }}{{ title }}]{% endmacro %}"
    "ignored output"
)


@pytest.fixture
def with_lib(make_env):
    def render(source, **context):
        env = make_env({"lib": LIB, "page": source})
        return env.get_template("page").render(**context)

    return render


def test_import_as_module(with_lib):
    source = "{% import 'lib' as lib %}{{ lib.em('a') }}{{ lib.version }}"
    assert with_lib(source) == "<em>a</em>1.0"


def test_imported_macros_use_their_own_template_scope(with_lib):
    source = "{% import 'lib' as lib %}{{ lib.badge('a') }}"
    assert with_lib(source, title="T") == "[<em>a</em>1.0]"


def test_import_with_context(with_lib):
    source = "{% import 'lib' as lib with context %}{{ lib.badge('a') }}"
    assert with_lib(source, title="T") == "[<em>a</em>1.0T]"


def test_import_does_not_export_private_or_context_names(with_lib):
    source = (
        "{% import 'lib' as lib with context %}"
        "[{{ lib._private }}{{ lib.title }}{{ lib.nope }}]"
    )
    assert with_lib(source, title="T") == "[]"


def test_from_import(with_lib):
    source = "{% from 'lib' import em, version as v %}{{ em(v) }}[{{ version }}]"
    assert with_lib(source) == "<em>1.0</em>[]"


def test_from_import_of_a_missing_name(with_lib):
    assert with_lib("{% from 'lib' import nope %}[{{ nope }}]") == "[]"
    with pytest.raises(UndefinedError, match="'lib' does not export 'nope'"):
        with_lib("{% from 'lib' import nope %}{{ nope() }}")


def test_from_import_with_context(with_lib):
    source = "{% from 'lib' import badge with context %}{{ badge(1) }}"
    assert with_lib(source, title="T") == "[<em>1</em>1.0T]"


def test_import_sees_globals(make_env):
    env = make_env(
        {
            "lib": "{% macro m() %}{{ site_name }}{% endmacro %}",
            "page": "{% from 'lib' import m %}{{ m() }}",
        }
    )
    env.globals["site_name"] = "My Site"
    assert env.get_template("page").render() == "My Site"


def test_import_inside_a_macro_is_local(with_lib):
    source = (
        "{% macro m() %}{% import 'lib' as lib %}{{ lib.em(1) }}{% endmacro %}"
        "{{ m() }}[{{ lib }}]"
    )
    assert with_lib(source) == "<em>1</em>[]"


def test_import_missing_template(make_env):
    env = make_env({"page": "{% import 'nope' as n %}"})
    with pytest.raises(TemplateNotFound, match="'nope'"):
        env.get_template("page").render()


def test_circular_import_is_detected(make_env):
    env = make_env(
        {
            "a": "{% import 'b' as b %}",
            "b": "{% from 'a' import x %}",
        }
    )
    with pytest.raises(TemplateRuntimeError) as excinfo:
        env.get_template("b").make_module()
    assert excinfo.value.message == "circular import: b -> a -> b"


def test_imports_in_macros_of_two_templates_are_not_circular(make_env):
    env = make_env(
        {
            "a": "{% macro one() %}{% import 'b' as b %}1{{ b.two() }}{% endmacro %}",
            "b": (
                "{% macro two() %}2{% endmacro %}"
                "{% macro both() %}{% import 'a' as a %}{{ a.one() }}{% endmacro %}"
            ),
            "page": "{% import 'b' as b %}{{ b.both() }}",
        }
    )
    assert env.get_template("page").render() == "12"


def test_module_from_python(make_env):
    env = make_env({"lib": LIB})
    module = env.get_template("lib").module
    assert module.em("x") == "<em>x</em>"
    assert module.version == "1.0"
    assert str(module) == "ignored output"
    assert not hasattr(module, "_private")
    assert repr(module) == "<TemplateModule 'lib'>"
    assert env.get_template("lib").make_module({"title": "T"}).badge(1) == (
        "[<em>1</em>1.0T]"
    )


def test_infinite_macro_recursion_is_reported(render):
    source = "{% macro again(n) %}{{ again(n + 1) }}{% endmacro %}{{ again(0) }}"
    with pytest.raises(TemplateRuntimeError, match="maximum recursion depth"):
        render(source)
