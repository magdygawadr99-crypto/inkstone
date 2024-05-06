from __future__ import annotations

import pytest

from inkstone.tmpl import TemplateNotFound, TemplateRuntimeError, UndefinedError

BASE = (
    "<title>{% block title %}Site{% endblock %}</title>"
    "<main>{% block content %}default content{% endblock %}</main>"
    "<footer>{% block footer %}(c) {{ year }}{% endblock %}</footer>"
)


@pytest.fixture
def site(make_env):
    return make_env(
        {
            "base.html": BASE,
            "page.html": (
                "{% extends 'base.html' %}"
                "{% block title %}{{ title }} | {{ super() }}{% endblock %}"
                "{% block content %}<h1>{{ title }}</h1>{% endblock %}"
            ),
            "post.html": (
                "{% extends 'page.html' %}"
                "{% block content %}{{ super() }}<article>{{ body }}</article>"
                "{% endblock %}"
            ),
        }
    )


def test_base_template_renders_its_block_defaults(site):
    assert site.get_template("base.html").render(year=2024) == (
        "<title>Site</title><main>default content</main><footer>(c) 2024</footer>"
    )


def test_child_overrides_blocks_and_keeps_the_rest(site):
    assert site.get_template("page.html").render(title="About", year=2024) == (
        "<title>About | Site</title><main><h1>About</h1></main>"
        "<footer>(c) 2024</footer>"
    )


def test_three_levels_with_super_at_each(site):
    out = site.get_template("post.html").render(title="Hi", body="text", year=1)
    assert out == (
        "<title>Hi | Site</title>"
        "<main><h1>Hi</h1><article>text</article></main>"
        "<footer>(c) 1</footer>"
    )


def test_super_super_skips_a_level(make_env):
    env = make_env(
        {
            "a": "{% block b %}A{% endblock %}",
            "b": "{% extends 'a' %}{% block b %}B{% endblock %}",
            "c": "{% extends 'b' %}{% block b %}C{{ super.super() }}{% endblock %}",
            "d": (
                "{% extends 'b' %}"
                "{% block b %}{{ super() }}{{ super.super() }}{% endblock %}"
            ),
        }
    )
    assert env.get_template("c").render() == "CA"
    assert env.get_template("d").render() == "BA"


def test_super_without_a_parent_block(make_env):
    env = make_env({"a": "{% block b %}{{ super() }}{% endblock %}"})
    with pytest.raises(UndefinedError, match="block 'b' has no parent block"):
        env.get_template("a").render()
    env = make_env(
        {
            "a": "{% block b %}A{% endblock %}",
            "b": "{% extends 'a' %}{% block b %}{{ super.super() }}{% endblock %}",
        }
    )
    with pytest.raises(UndefinedError, match="no block 'b' further up"):
        env.get_template("b").render()


def test_text_outside_blocks_in_a_child_is_dropped(make_env):
    env = make_env(
        {
            "base": "[{% block a %}{% endblock %}]",
            "child": (
                "{% extends 'base' %} noise "
                "{% block a %}x{% endblock %} more {{ 1 }}"
            ),
        }
    )
    assert env.get_template("child").render() == "[x]"


def test_text_before_extends_is_printed(make_env):
    env = make_env(
        {
            "base": "[{% block a %}{% endblock %}]",
            "child": "<!-- hi -->{% extends 'base' %}{% block a %}x{% endblock %}",
        }
    )
    assert env.get_template("child").render() == "<!-- hi -->[x]"


def test_block_in_child_that_the_parent_does_not_have_is_ignored(make_env):
    env = make_env(
        {
            "base": "[{% block a %}a{% endblock %}]",
            "child": "{% extends 'base' %}{% block other %}{{ boom() }}{% endblock %}",
        }
    )
    assert env.get_template("child").render() == "[a]"


def test_nested_blocks_can_be_overridden_separately(make_env):
    env = make_env(
        {
            "base": (
                "{% block outer %}<{% block inner %}in{% endblock %}>{% endblock %}"
            ),
            "inner_only": "{% extends 'base' %}{% block inner %}IN{% endblock %}",
            "outer_only": (
                "{% extends 'base' %}{% block outer %}[{{ super() }}]{% endblock %}"
            ),
            "new_inner": (
                "{% extends 'base' %}"
                "{% block outer %}({% block extra %}x{% endblock %}){% endblock %}"
            ),
        }
    )
    assert env.get_template("base").render() == "<in>"
    assert env.get_template("inner_only").render() == "<IN>"
    assert env.get_template("outer_only").render() == "[<in>]"
    assert env.get_template("new_inner").render() == "(x)"


def test_top_level_set_in_child_is_visible_in_parent_and_blocks(make_env):
    env = make_env(
        {
            "base": "{{ layout }}:{% block a %}{% endblock %}",
            "child": (
                "{% extends 'base' %}{% set layout = 'wide' %}{% set n = 2 %}"
                "{% block a %}{{ layout }}{{ n }}{% endblock %}"
            ),
        }
    )
    assert env.get_template("child").render() == "wide:wide2"


def test_macros_and_imports_of_the_child_work_in_its_blocks(make_env):
    env = make_env(
        {
            "base": "{% block a %}{% endblock %}",
            "lib": "{% macro em(x) %}<em>{{ x }}</em>{% endmacro %}",
            "child": (
                "{% extends 'base' %}{% import 'lib' as lib %}"
                "{% macro b(x) %}<b>{{ x }}</b>{% endmacro %}"
                "{% block a %}{{ b(1) }}{{ lib.em(2) }}{% endblock %}"
            ),
        }
    )
    assert env.get_template("child").render() == "<b>1</b><em>2</em>"


def test_blocks_see_render_variables_but_not_loop_variables(make_env):
    env = make_env(
        {
            "base": (
                "{% for item in items %}"
                "{% block row %}[{{ item }}{{ prefix }}]{% endblock %}"
                "{% endfor %}"
            ),
        }
    )
    assert env.get_template("base").render(items=[1, 2], prefix="-") == "[-][-]"


def test_scoped_block_sees_loop_variables(make_env):
    env = make_env(
        {
            "base": (
                "{% for item in items %}"
                "{% block row scoped %}[{{ item }}]{% endblock %}"
                "{% endfor %}"
            ),
            "child": (
                "{% extends 'base' %}"
                "{% block row %}"
                "<{{ item }}:{{ loop.index }}|{{ super() }}>"
                "{% endblock %}"
            ),
        }
    )
    assert env.get_template("base").render(items="ab") == "[a][b]"
    assert env.get_template("child").render(items="ab") == "<a:1|[a]><b:2|[b]>"


def test_set_inside_a_block_stays_inside(make_env):
    env = make_env(
        {"base": "{% block a %}{% set x = 1 %}{{ x }}{% endblock %}[{{ x }}]"}
    )
    assert env.get_template("base").render() == "1[]"


def test_self_renders_a_block_again(make_env):
    env = make_env(
        {
            "base": (
                "<title>{% block title %}Base{% endblock %}</title>"
                "<h1>{{ self.title() }}</h1>"
            ),
            "child": "{% extends 'base' %}{% block title %}Child{% endblock %}",
        }
    )
    assert env.get_template("base").render() == "<title>Base</title><h1>Base</h1>"
    assert env.get_template("child").render() == "<title>Child</title><h1>Child</h1>"


def test_self_with_unknown_block(make_env):
    env = make_env({"base": "{{ self.nope() }}"})
    with pytest.raises(UndefinedError, match="no attribute 'nope'"):
        env.get_template("base").render()


def test_required_block(make_env):
    env = make_env(
        {
            "base": "[{% block body required %}{% endblock %}]",
            "good": "{% extends 'base' %}{% block body %}ok{% endblock %}",
            "bad": "{% extends 'base' %}",
        }
    )
    assert env.get_template("good").render() == "[ok]"
    with pytest.raises(TemplateRuntimeError, match="block 'body' is required"):
        env.get_template("bad").render()
    with pytest.raises(TemplateRuntimeError, match="block 'body' is required"):
        env.get_template("base").render()


def test_extends_with_an_expression(make_env):
    env = make_env(
        {
            "wide": "wide:{% block a %}{% endblock %}",
            "narrow": "narrow:{% block a %}{% endblock %}",
            "child": (
                "{% extends layout if layout is defined else 'narrow' %}"
                "{% block a %}x{% endblock %}"
            ),
        }
    )
    template = env.get_template("child")
    assert template.render(layout="wide") == "wide:x"
    assert template.render() == "narrow:x"


def test_extends_a_template_object(make_env):
    env = make_env({"child": "{% extends parent %}{% block a %}x{% endblock %}"})
    parent = env.from_string("<{% block a %}{% endblock %}>")
    assert env.get_template("child").render(parent=parent) == "<x>"


def test_extends_picks_the_first_existing_template_of_a_list(make_env):
    env = make_env(
        {
            "base": "base:{% block a %}{% endblock %}",
            "child": "{% extends ['custom', 'base'] %}{% block a %}x{% endblock %}",
        }
    )
    assert env.get_template("child").render() == "base:x"


def test_extends_missing_template(make_env):
    env = make_env({"child": "\n{% extends 'nope.html' %}"})
    with pytest.raises(TemplateNotFound) as excinfo:
        env.get_template("child").render()
    assert excinfo.value.name == "nope.html"
    assert (excinfo.value.path, excinfo.value.line) == ("child", 2)


def test_extends_undefined_name(make_env):
    env = make_env({"child": "{% extends layout %}"})
    with pytest.raises(UndefinedError, match="can't load a template: 'layout' is"):
        env.get_template("child").render()


def test_circular_extends_is_detected(make_env):
    env = make_env(
        {
            "a": "{% extends 'b' %}",
            "b": "{% extends 'c' %}",
            "c": "\n\n{% extends 'a' %}",
            "self": "{% extends 'self' %}",
        }
    )
    with pytest.raises(TemplateRuntimeError) as excinfo:
        env.get_template("a").render()
    assert excinfo.value.message == "circular extends: a -> b -> c -> a"
    assert (excinfo.value.path, excinfo.value.line) == ("c", 3)
    with pytest.raises(TemplateRuntimeError, match="circular extends: self -> self"):
        env.get_template("self").render()


def test_rendering_twice_gives_the_same_result(site):
    template = site.get_template("post.html")
    first = template.render(title="T", body="b", year=1)
    assert template.render(title="T", body="b", year=1) == first


def test_block_with_include_and_loop(make_env):
    env = make_env(
        {
            "base": "<ul>{% block items %}{% endblock %}</ul>",
            "item": "<li>{{ item }}</li>",
            "child": (
                "{% extends 'base' %}{% block items %}"
                "{% for item in items %}{% include 'item' %}{% endfor %}"
                "{% endblock %}"
            ),
        }
    )
    assert env.get_template("child").render(items=[1, 2]) == (
        "<ul><li>1</li><li>2</li></ul>"
    )
