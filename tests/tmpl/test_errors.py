from __future__ import annotations

import sys

import pytest

from inkstone.errors import BuildError, InkstoneError
from inkstone.tmpl import (
    Environment,
    FileSystemLoader,
    TemplateError,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    UndefinedError,
)


def failure(template, exception=TemplateError, **context):
    with pytest.raises(exception) as excinfo:
        template.render(**context)
    return excinfo.value


def test_error_hierarchy():
    assert issubclass(TemplateError, InkstoneError)
    for cls in (TemplateSyntaxError, TemplateNotFound, TemplateRuntimeError):
        assert issubclass(cls, TemplateError)
    assert issubclass(UndefinedError, TemplateRuntimeError)


def test_error_string_format():
    assert str(TemplateError("boom", path="a.html", line=3)) == "a.html:3: boom"
    assert str(TemplateError("boom", path="a.html")) == "a.html: boom"
    assert str(TemplateError("boom")) == "boom"
    assert str(TemplateNotFound("x.html")) == "template 'x.html' not found"
    assert TemplateNotFound("x.html", "custom").message == "custom"


def test_syntax_error_in_from_string(env):
    with pytest.raises(TemplateSyntaxError) as excinfo:
        env.from_string("ok\n{{ 1 +\n }}")
    assert excinfo.value.path == "<string>"
    assert excinfo.value.line == 3
    assert str(excinfo.value) == "<string>:3: expected an expression, got '}}'"


def test_syntax_error_uses_the_given_name(env):
    with pytest.raises(TemplateSyntaxError) as excinfo:
        env.from_string("{% nope %}", name="inline.html")
    assert excinfo.value.path == "inline.html"


def test_syntax_error_in_loaded_template(make_env):
    env = make_env({"bad.html": "a\nb\n{% endfor %}"})
    with pytest.raises(TemplateSyntaxError) as excinfo:
        env.get_template("bad.html")
    assert (excinfo.value.path, excinfo.value.line) == ("bad.html", 3)


def test_syntax_errors_surface_when_the_template_is_loaded_not_rendered(make_env):
    env = make_env({"page": "fine {% include 'bad' %}", "bad": "\n{{ }}"})
    template = env.get_template("page")
    error = failure(template, TemplateSyntaxError)
    assert (error.path, error.line) == ("bad", 2)


@pytest.mark.parametrize(
    "source, line",
    [
        ("{{ 1 / 0 }}", 1),
        ("a\nb\n{{ 1 / 0 }}", 3),
        ("{% if true %}\n\n{{ 1 / 0 }}\n{% endif %}", 3),
        ("{% for x in [1] %}\n{% if x %}\n  {{ x / 0 }}\n{% endif %}\n{% endfor %}", 3),
        ("{{ [1,\n 2,\n 3 / 0] }}", 3),
        ("{% set x =\n 1 / 0 %}", 2),
        ("{{ 'a'\n | upper\n | nope }}", 3),
        ("\n{% if 1 / 0 %}{% endif %}", 2),
        ("{% if false %}\n{% elif 1 / 0 %}\n{% endif %}", 2),
        ("{% for x in 1 / 0 %}{% endfor %}", 1),
        ("{% with a = 1,\n b = 1 / 0 %}{% endwith %}", 2),
        ("{% macro m() %}\n{{ 1 / 0 }}\n{% endmacro %}\n\n{{ m() }}", 2),
        ("{% filter upper %}\n\n{{ 1 / 0 }}{% endfilter %}", 3),
        ("{% set b %}\n{{ 1 / 0 }}{% endset %}", 2),
        ("{# a\n multi-line\n comment #}{{ 1 / 0 }}", 3),
        ("{% raw %}\n\n{% endraw %}\n{{ 1 / 0 }}", 4),
        ("{{ 'a\nb' }}{{ 1 / 0 }}", 2),
        ("line\n{%- if true -%}\n\n   {{ 1 / 0 }}{% endif %}", 4),
    ],
)
def test_runtime_error_line_numbers(env, source, line):
    error = failure(env.from_string(source, name="page.html"), TemplateRuntimeError)
    assert error.line == line
    assert error.path == "page.html"


def test_line_numbers_with_trim_and_lstrip_blocks():
    env = Environment(trim_blocks=True, lstrip_blocks=True)
    source = "a\n  {% if true %}\n  b\n  {% endif %}\n{{ 1 / 0 }}"
    assert failure(env.from_string(source)).line == 5


def test_python_exceptions_are_wrapped_with_their_cause(env):
    error = failure(env.from_string("{{ 1 / 0 }}"), TemplateRuntimeError)
    assert error.message == "ZeroDivisionError: division by zero"
    assert isinstance(error.__cause__, ZeroDivisionError)
    assert str(error) == "<string>:1: ZeroDivisionError: division by zero"


def test_exception_from_a_called_function(env):
    def explode(arg):
        raise ValueError(f"bad value: {arg}")

    error = failure(env.from_string("x\n{{ f('a') }}"), f=explode)
    assert error.message == "ValueError: bad value: a"
    assert error.line == 2
    assert isinstance(error.__cause__, ValueError)


def test_exception_from_a_property(env):
    class Page:
        @property
        def title(self):
            raise RuntimeError("no title yet")

    error = failure(env.from_string("{{ page.title }}"), page=Page())
    assert error.message == "RuntimeError: no title yet"


def test_inkstone_errors_pass_through_untouched(env):
    def build_step():
        raise BuildError("the asset pipeline failed", path="style.css")

    with pytest.raises(BuildError) as excinfo:
        env.from_string("\n\n{{ f() }}").render(f=build_step)
    assert str(excinfo.value) == "style.css: the asset pipeline failed"
    assert not isinstance(excinfo.value, TemplateError)


def test_template_errors_raised_by_functions_get_a_location(env):
    def check(value):
        raise TemplateRuntimeError(f"{value} is not allowed here")

    error = failure(env.from_string("\n{{ check(3) }}", name="t"), check=check)
    assert str(error) == "t:2: 3 is not allowed here"


def test_keyboard_interrupt_is_not_swallowed(env):
    def interrupt():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        env.from_string("{{ f() }}").render(f=interrupt)


@pytest.mark.parametrize(
    "source, message",
    [
        ("{{ 1 + 'a' }}", "TypeError: unsupported operand"),
        ("{{ 'a' < 1 }}", "TypeError: '<' not supported"),
        ("{{ [1, 'a'] | sort }}", "TypeError"),
        ("{{ {[1]: 2} }}", "unhashable type"),
        ("{{ 1 in 5 }}", "TypeError: argument of type 'int'"),
        ("{{ [1] | join(1, 2, 3) }}", "TypeError"),
        ("{{ x() }}", "'str' object is not callable"),
        ("{{ f(*5) }}", "TypeError"),
        ("{{ 'abc' | int | nope }}", "no filter named 'nope'"),
        ("{{ 3 is nope }}", "no test named 'nope'"),
        ("{% for a, b in [1] %}{% endfor %}", "can't unpack 'int' object into 2 names"),
        ("{% include 5 %}", "a template name has to be a string, not int"),
    ],
)
def test_runtime_error_messages(env, source, message):
    error = failure(env.from_string(source), TemplateRuntimeError, x="s", f=print)
    assert message in error.message
    assert error.line == 1


def test_error_in_parent_template_names_the_parent(make_env):
    env = make_env(
        {
            "base.html": "top\n{% block a %}{% endblock %}\n{{ 1 / 0 }}",
            "page.html": "{% extends 'base.html' %}\n{% block a %}fine{% endblock %}",
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("base.html", 3)


def test_error_in_overridden_block_names_the_child(make_env):
    env = make_env(
        {
            "base.html": "top\n{% block a %}{% endblock %}",
            "page.html": (
                "{% extends 'base.html' %}\n"
                "{% block a %}\n\n{{ 1 / 0 }}{% endblock %}"
            ),
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("page.html", 4)


def test_error_in_super_block_names_the_parent(make_env):
    env = make_env(
        {
            "base.html": "top\n{% block a %}{{ 1 / 0 }}{% endblock %}",
            "page.html": (
                "{% extends 'base.html' %}\n\n"
                "{% block a %}{{ super() }}{% endblock %}"
            ),
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("base.html", 2)


def test_error_in_included_template_names_the_include(make_env):
    env = make_env(
        {
            "page.html": "a\nb\n{% include 'part.html' %}",
            "part.html": "\n{{ missing_function() }}",
        }
    )
    error = failure(env.get_template("page.html"), UndefinedError)
    assert str(error) == "part.html:2: 'missing_function' is undefined"


def test_error_in_imported_macro_names_the_library(make_env):
    env = make_env(
        {
            "page.html": "{% import 'lib.html' as lib %}\n\n\n{{ lib.broken(0) }}",
            "lib.html": "{% macro broken(n) %}\n{{ 1 / n }}\n{% endmacro %}",
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("lib.html", 2)


def test_error_in_macro_call_arguments_names_the_caller(make_env):
    env = make_env(
        {
            "page.html": "{% import 'lib.html' as lib %}\n{{ lib.m(1, 2, 3) }}",
            "lib.html": "{% macro m(a) %}{% endmacro %}",
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("page.html", 2)
    assert "macro 'm' takes at most 1 positional" in error.message


def test_error_in_call_block_body_names_the_caller(make_env):
    env = make_env(
        {
            "page.html": (
                "{% from 'lib.html' import wrap %}\n"
                "{% call wrap() %}\n{{ 1 / 0 }}\n{% endcall %}"
            ),
            "lib.html": "{% macro wrap() %}{{ caller() }}{% endmacro %}",
        }
    )
    error = failure(env.get_template("page.html"))
    assert (error.path, error.line) == ("page.html", 3)


def test_error_in_file_template_has_the_file_path(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("one\ntwo\n{{ page.title.nope() }}\n", encoding="utf-8")
    env = Environment(FileSystemLoader(tmp_path))
    error = failure(env.get_template("page.html"), UndefinedError, page={"title": "T"})
    assert error.path == str(path)
    assert error.line == 3
    assert str(error) == f"{path}:3: 'str' object has no attribute 'nope'"


def test_missing_include_inside_a_file_template(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("\n{% include 'gone.html' %}", encoding="utf-8")
    env = Environment(FileSystemLoader(tmp_path))
    error = failure(env.get_template("page.html"), TemplateNotFound)
    assert error.name == "gone.html"
    assert (error.path, error.line) == (str(path), 2)


def test_absurdly_deep_nesting_is_a_syntax_error(env):
    depth = sys.getrecursionlimit()
    with pytest.raises(TemplateSyntaxError, match="nested too deeply"):
        env.from_string("{{ " + "(" * depth + "1" + ")" * depth + " }}")


def test_absurdly_long_expression_fails_cleanly(env):
    terms = sys.getrecursionlimit() * 2
    template = env.from_string("{{ " + " + ".join(["1"] * terms) + " }}")
    error = failure(template, TemplateRuntimeError)
    assert error.message == "maximum recursion depth exceeded"
    assert env.from_string("{{ " + " + ".join(["1"] * 50) + " }}").render() == "50"


def test_unknown_filter_inside_a_dead_branch_is_not_an_error(env):
    assert env.from_string("{% if false %}{{ x | nope }}{% endif %}ok").render() == "ok"


def test_error_does_not_break_later_renders(env):
    template = env.from_string(
        "{% for x in xs %}{% with y = 10 / x %}{{ y }}{% endwith %}{% endfor %}"
    )
    failure(template, xs=[1, 0])
    assert template.render(xs=[5, 2]) == "2.05.0"
