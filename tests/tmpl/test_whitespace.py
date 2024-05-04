from __future__ import annotations

import pytest

from inkstone.tmpl import Environment

LIST = """\
<ul>
  {% for item in items %}
  <li>{{ item }}</li>
  {% endfor %}
</ul>
"""


def render(source, env=None, **context):
    env = env or Environment(autoescape=False)
    return env.from_string(source).render(**context)


def test_tags_leave_their_lines_behind_by_default():
    assert render(LIST, items=[1, 2]) == (
        "<ul>\n  \n  <li>1</li>\n  \n  <li>2</li>\n  \n</ul>"
    )


def test_trim_blocks():
    env = Environment(autoescape=False, trim_blocks=True)
    assert render(LIST, env, items=[1, 2]) == (
        "<ul>\n    <li>1</li>\n    <li>2</li>\n  </ul>"
    )


def test_lstrip_blocks():
    env = Environment(autoescape=False, lstrip_blocks=True)
    assert render(LIST, env, items=[1, 2]) == (
        "<ul>\n\n  <li>1</li>\n\n  <li>2</li>\n\n</ul>"
    )


def test_trim_and_lstrip_blocks_give_clean_output():
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render(LIST, env, items=[1, 2]) == "<ul>\n  <li>1</li>\n  <li>2</li>\n</ul>"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a  {{ 1 }}  b", "a  1  b"),
        ("a  {{- 1 }}  b", "a1  b"),
        ("a  {{ 1 -}}  b", "a  1b"),
        ("a  {{- 1 -}}  b", "a1b"),
        ("a \n\t {{- 1 -}} \n\n b", "a1b"),
        ("a  {%- if true %}  x  {% endif -%}  b", "a  x  b"),
        ("a  {% if true -%}  x  {%- endif %}  b", "a  x  b"),
        ("a  {%- if true -%}  x  {%- endif -%}  b", "axb"),
        ("a  {#- gone -#}  b", "ab"),
        ("{{- 1 }}", "1"),
        ("{{ 1 -}}", "1"),
        ("{{ 1 -}}\n\n", "1"),
        ("  {%- set x = 1 -%}  {{ x }}", "1"),
    ],
)
def test_minus_signs(source, expected):
    assert render(source) == expected


def test_minus_sign_in_a_loop():
    source = "{% for x in xs -%}\n  {{ x }}\n{%- endfor %}"
    assert render(source, xs=[1, 2, 3]) == "123"
    source = "{% for x in xs %}\n  {{ x }}\n{%- endfor %}"
    assert render(source, xs=[1, 2, 3]) == "\n  1\n  2\n  3"


def test_minus_sign_only_affects_its_own_side():
    source = "<p>\n  {%- if x %}\n  yes\n  {%- endif %}\n</p>"
    assert render(source, x=True) == "<p>\n  yes\n</p>"
    assert render(source, x=False) == "<p>\n</p>"


def test_plus_sign_keeps_whitespace_despite_the_settings():
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render("  {% if x %}\nyes\n  {% endif %}\nend", env, x=1) == "yes\nend"
    assert render("  {%+ if x +%}\nyes\n  {% endif %}\nend", env, x=1) == "  \nyes\nend"


def test_minus_sign_beats_the_settings():
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render("a\n\n  {%- if x -%}\n\n  yes\n{% endif %}", env, x=1) == "ayes\n"


def test_settings_do_not_touch_variable_tags():
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render("  {{ a }}\n  {{ b }}\n", env, a=1, b=2) == "  1\n  2"


def test_lstrip_blocks_only_on_otherwise_empty_lines():
    env = Environment(autoescape=False, lstrip_blocks=True)
    assert render("x  {% if true %}y{% endif %}", env) == "x  y"
    assert render("{{ 1 }}  {% if true %}y{% endif %}", env) == "1  y"
    assert render("\t {% if true %}y{% endif %}", env) == "y"


def test_trim_blocks_with_inline_tags():
    env = Environment(autoescape=False, trim_blocks=True)
    source = "{% if true %}a{% endif %} b\n{% if true %}\nc\n{% endif %}\nd"
    assert render(source, env) == "a b\nc\nd"


def test_comments_follow_the_same_rules():
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render("a\n  {# note #}\nb", env) == "a\nb"
    assert render("a\n  {# note #}\nb") == "a\n  \nb"


def test_raw_block_keeps_inner_whitespace():
    assert render("{% raw %}  {{ x }}\n  {% endraw %}|") == "  {{ x }}\n  |"
    assert render("a {%- raw %}  {{ x }}  {% endraw -%} b") == "a  {{ x }}  b"
    env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
    assert render("<pre>\n  {% raw %}\n  {{ x }}\n  {% endraw %}\n</pre>", env) == (
        "<pre>\n  {{ x }}\n</pre>"
    )


def test_trailing_newline():
    assert render("line\n") == "line"
    assert render("line\n\n") == "line\n"
    env = Environment(autoescape=False, keep_trailing_newline=True)
    assert render("line\n", env) == "line\n"


def test_whitespace_inside_tags_does_not_matter():
    source = "{{1+1}}{%if true%}a{%endif%}{{\n  'b'\n}}{%  if   true  %}c{%  endif  %}"
    assert render(source) == "2abc"


def test_whitespace_control_in_set_and_macro_blocks():
    source = (
        "{% macro item(x) -%}\n"
        "  <li>{{ x }}</li>\n"
        "{%- endmacro %}"
        "{% set block -%}\n  text\n{%- endset %}"
        "[{{ item(1) }}][{{ block }}]"
    )
    assert render(source) == "[<li>1</li>][text]"


def test_included_template_loses_its_trailing_newline(make_env):
    env = make_env({"page": "<{% include 'part' %}>", "part": "x\n"})
    assert env.get_template("page").render() == "<x>"
