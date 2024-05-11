from __future__ import annotations

import pytest

import inkstone.tmpl as tmpl
from inkstone.tmpl import (
    Context,
    DictLoader,
    Environment,
    Markup,
    Template,
    TemplateNotFound,
    TemplateRuntimeError,
    pass_context,
    pass_environment,
)
from inkstone.tmpl.lexer import DATA, NAME


def test_public_names_are_importable():
    for name in (
        "Environment",
        "Template",
        "FileSystemLoader",
        "DictLoader",
        "ChoiceLoader",
        "TemplateError",
        "TemplateSyntaxError",
        "TemplateNotFound",
        "UndefinedError",
        "Markup",
        "escape",
        "Undefined",
    ):
        assert hasattr(tmpl, name)
        assert name in tmpl.__all__


def test_from_string():
    env = Environment()
    template = env.from_string("Hello {{ name }}")
    assert isinstance(template, Template)
    assert template.render(name="x") == "Hello x"
    assert template.name is None
    assert template.filename is None
    assert repr(template) == "<Template '<string>'>"
    assert repr(env.from_string("", name="n.html")) == "<Template 'n.html'>"


def test_render_takes_a_dict_and_or_keywords(env):
    template = env.from_string("{{ a }}{{ b }}{{ c }}")
    assert template.render({"a": 1, "b": 2}) == "12"
    assert template.render(a=1, c=3) == "13"
    assert template.render({"a": 1, "b": 2}, b="B", c=3) == "1B3"
    assert template.render() == ""
    assert template.render(None) == ""


def test_render_does_not_modify_the_given_dict(env):
    context = {"a": 1}
    env.from_string("{% set a = 2 %}{% set b = 3 %}{{ a }}").render(context)
    assert context == {"a": 1}


def test_context_variable_named_like_a_parameter(env):
    template = env.from_string("{{ context }}{{ self }}")
    assert template.render(context="c", self="s") == "cs"


def test_render_result_is_a_plain_str():
    out = Environment().from_string("{{ x }}").render(x=Markup("<b>"))
    assert type(out) is str


def test_globals_are_visible_everywhere(make_env):
    env = make_env(
        {
            "page": (
                "{{ site }}{% include 'part' %}"
                "{% import 'lib' as lib %}{{ lib.m() }}"
            ),
            "part": "[{{ site }}]",
            "lib": "{% macro m() %}<{{ site }}>{% endmacro %}",
        }
    )
    env.globals["site"] = "S"
    assert env.get_template("page").render() == "S[S]<S>"


def test_render_variables_win_over_globals(env):
    env.globals["x"] = "global"
    template = env.from_string("{{ x }}")
    assert template.render() == "global"
    assert template.render(x="local") == "local"


def test_global_functions(env):
    def url_for(name, **params):
        return f"/{name}/{params.get('page', '')}"

    env.globals["url_for"] = url_for
    assert env.from_string("{{ url_for('posts', page=2) }}").render() == "/posts/2"
    assert env.from_string("{{ url_for('about') }}").render() == "/about/"


def test_environments_do_not_share_their_tables():
    one, two = Environment(), Environment()
    one.filters["only_one"] = str
    one.tests["only_one"] = bool
    one.globals["only_one"] = 1
    assert "only_one" not in two.filters
    assert "only_one" not in two.tests
    assert "only_one" not in two.globals


def test_custom_filter(env):
    env.filters["shout"] = lambda value, mark="!": str(value).upper() + mark
    template = env.from_string(
        "{{ 'hi' | shout }} {{ 'hi' | shout('?') }} {{ 'hi' | shout(mark='.') }}"
    )
    assert template.render() == "HI! HI? HI."


def test_custom_filter_can_replace_a_builtin(env):
    env.filters["upper"] = lambda value: "custom"
    assert env.from_string("{{ 'x' | upper }}").render() == "custom"
    assert Environment().from_string("{{ 'x' | upper }}").render() == "X"


def test_pass_context_filter(env):
    @pass_context
    def relative(ctx, url):
        assert isinstance(ctx, Context)
        return "../" * ctx.get("depth", 0) + url

    env.filters["relative"] = relative
    template = env.from_string("{{ 'style.css' | relative }}")
    assert template.render(depth=2) == "../../style.css"
    assert template.render() == "style.css"


def test_pass_context_sees_local_scopes_and_template_name(make_env):
    @pass_context
    def where(ctx):
        return f"{ctx.name}:{ctx.resolve('x')}:{'y' in ctx}:{ctx.autoescape}"

    env = make_env({"page": "{% for x in 'ab' %}{{ where() }} {% endfor %}"})
    env.globals["where"] = where
    assert env.get_template("page").render() == "page:a:False:False page:b:False:False "


def test_context_lookup_api(env):
    seen = {}

    @pass_context
    def spy(ctx):
        seen["get"] = (ctx.get("a"), ctx.get("nope"), ctx.get("nope", 5))
        seen["item"] = ctx["a"]
        seen["global"] = ctx["range"]
        seen["undefined"] = ctx.resolve("nope")
        with pytest.raises(KeyError):
            ctx["nope"]
        return ""

    env.globals["spy"] = spy
    env.from_string("{{ spy() }}").render(a=1)
    assert seen["get"] == (1, None, 5)
    assert seen["item"] == 1
    assert seen["global"] is range
    assert isinstance(seen["undefined"], env.undefined)


def test_pass_environment(env):
    @pass_environment
    def count_filters(environment, value):
        return f"{value}:{environment is env}"

    env.filters["probe"] = count_filters
    assert env.from_string("{{ 'x' | probe }}").render() == "x:True"


def test_pass_context_test(env):
    @pass_context
    def is_current(ctx, url):
        return url == ctx.get("current_url")

    env.tests["current"] = is_current
    template = env.from_string("{% for u in urls %}{{ u is current }} {% endfor %}")
    assert template.render(urls=["/a", "/b"], current_url="/b") == "False True "


def test_call_filter_and_test_from_python(env):
    assert env.call_filter("upper", "x") == "X"
    text = "a long sentence here"
    assert env.call_filter("truncate", text, [9], {"end": ""}) == "a long"
    assert env.call_filter("join", ["<a>", Markup("<b>")], [", "]) == "<a>, <b>"
    assert env.call_test("divisibleby", 9, [3]) is True
    with pytest.raises(TemplateRuntimeError, match="no filter named"):
        env.call_filter("nope", 1)


def test_getattr_and_getitem_rules(env):
    class Thing:
        attr = "attribute"

        def __getitem__(self, key):
            return {"attr": "item", "only_item": "item"}[key]

    thing = Thing()
    assert env.getattr(thing, "attr") == "attribute"
    assert env.getitem(thing, "attr") == "item"
    assert env.getattr(thing, "only_item") == "item"
    assert env.getitem({"a": 1}, "a") == 1
    assert env.getitem("abc", "upper")() == "ABC"
    assert isinstance(env.getattr(thing, "nope"), env.undefined)
    assert isinstance(env.getitem([1], 5), env.undefined)
    assert isinstance(env.getattr(thing, "__class__"), env.undefined)
    assert isinstance(env.getitem(thing, "__class__"), env.undefined)


def test_tokenize_and_parse_use_the_environment_settings():
    source = "{% if x %}\n{{ y }}{% endif %}"

    def if_body(env):
        return env.parse(source).body[0].branches[0][1]

    trimming = Environment(trim_blocks=True)
    tokens = trimming.tokenize(source)
    assert [t.value for t in tokens if t.type == NAME] == ["if", "x", "y", "endif"]
    assert [t.type for t in tokens].count(DATA) == 0
    assert len(if_body(trimming)) == 1
    assert len(if_body(Environment())) == 2


def test_get_template_passes_template_objects_through(env):
    template = env.from_string("x")
    assert env.get_template(template) is template
    with pytest.raises(TemplateRuntimeError, match="has to be a string"):
        env.get_template(42)


def test_select_template(make_env):
    env = make_env({"b": "B", "c": "C"})
    assert env.select_template(["a", "b", "c"]).render() == "B"
    assert env.select_template(["c"]).name == "c"
    with pytest.raises(TemplateNotFound) as excinfo:
        env.select_template(["x", "y"])
    assert excinfo.value.name == "y"
    assert "none of the templates 'x', 'y' was found" in excinfo.value.message
    with pytest.raises(TemplateNotFound, match="no template names"):
        env.select_template([])


def test_dependencies(make_env):
    env = make_env(
        {
            "page": (
                "{% extends 'base' %}{% import 'macros' as m %}"
                "{% from 'forms' import field %}"
                "{% block a %}{% include 'nav' %}{% include 'nav' %}"
                "{% if x %}{% include ['special', 'generic'] ignore missing %}"
                "{% endif %}"
                "{% include dynamic %}{% include 'a' if x else 'b' %}"
                "{% endblock %}"
            ),
            "plain": "no references {{ 'base' }}",
        }
    )
    assert env.get_template("page").dependencies == (
        "base",
        "macros",
        "forms",
        "nav",
        "special",
        "generic",
        "a",
        "b",
    )
    assert env.get_template("plain").dependencies == ()


def test_all_dependencies_follows_the_chain(make_env):
    env = make_env(
        {
            "post": "{% extends 'page' %}{% include 'meta' %}",
            "page": "{% extends 'base' %}",
            "base": "{% include 'nav' %}{% include 'gone' ignore missing %}",
            "meta": "{% import 'macros' as m %}",
            "macros": "{% include 'post' ignore missing %}",
            "nav": "",
        }
    )
    post = env.get_template("post")
    assert post.dependencies == ("page", "meta")
    assert post.all_dependencies() == {
        "page",
        "meta",
        "base",
        "nav",
        "gone",
        "macros",
        "post",
    }
    assert env.get_template("nav").all_dependencies() == set()


def test_blocks_are_listed(env):
    template = env.from_string(
        "{% block a %}{% block b %}{% endblock %}{% endblock %}"
        "{% block c %}{% endblock %}"
    )
    assert list(template.blocks) == ["a", "b", "c"]


def test_cache_can_be_cleared(make_env):
    env = make_env({"a": "A"})
    first = env.get_template("a")
    env.clear_cache()
    assert env.get_template("a") is not first


def test_from_string_templates_can_use_the_loader():
    env = Environment(DictLoader({"base": "<{% block a %}{% endblock %}>"}))
    template = env.from_string("{% extends 'base' %}{% block a %}x{% endblock %}")
    assert template.render() == "<x>"
    assert template.dependencies == ("base",)


def test_same_template_renders_independently_with_different_data(env):
    template = env.from_string(
        "{% set items = [] %}{% do items.append(x) %}{{ items }}"
    )
    assert template.render(x=1) == "[1]"
    assert template.render(x=2) == "[2]"


def test_a_small_site_end_to_end():
    env = Environment(
        DictLoader(
            {
                "base.html": (
                    "<!doctype html>\n"
                    "<title>{% block title %}{{ site.name }}{% endblock %}</title>\n"
                    "<nav>{% include 'nav.html' %}</nav>\n"
                    "<main>{% block content %}{% endblock %}</main>\n"
                ),
                "nav.html": (
                    "{% for item in site.nav -%}\n"
                    '<a href="{{ item.url }}"{% if item.url == page.url %} class="on"'
                    "{% endif %}>{{ item.label }}</a>\n"
                    "{%- endfor %}"
                ),
                "macros.html": (
                    "{% macro tag_list(tags) %}"
                    "{% for tag in tags | sort %}<span>{{ tag }}</span>{% endfor %}"
                    "{% endmacro %}"
                ),
                "post.html": (
                    "{% extends 'base.html' %}\n"
                    "{% from 'macros.html' import tag_list %}\n"
                    "{% block title %}{{ page.title }} - {{ super() }}{% endblock %}\n"
                    "{% block content %}\n"
                    "<h1>{{ page.title }}</h1>\n"
                    "{{ page.content }}\n"
                    "{{ tag_list(page.tags) }}\n"
                    "{% endblock %}\n"
                ),
            }
        ),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    site = {
        "name": "Ink & Stone",
        "nav": [{"url": "/", "label": "Home"}, {"url": "/blog/", "label": "Blog"}],
    }
    page = {
        "url": "/blog/",
        "title": "Tom & Jerry",
        "content": Markup("<p>Hello</p>"),
        "tags": ["b", "a"],
    }
    assert env.get_template("post.html").render({"page": page}, site=site) == (
        "<!doctype html>\n"
        "<title>Tom &amp; Jerry - Ink &amp; Stone</title>\n"
        '<nav><a href="/">Home</a><a href="/blog/" class="on">Blog</a></nav>\n'
        "<main><h1>Tom &amp; Jerry</h1>\n"
        "<p>Hello</p>\n"
        "<span>a</span><span>b</span>\n"
        "</main>"
    )
