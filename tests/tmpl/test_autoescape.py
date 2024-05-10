from __future__ import annotations

import pytest

from inkstone.tmpl import (
    DictLoader,
    Environment,
    Markup,
    TemplateRuntimeError,
    escape,
    select_autoescape,
)


class Widget:
    def __html__(self):
        return "<widget/>"


def render_html(source, **context):
    return Environment(autoescape=True).from_string(source).render(**context)


def test_escape_function():
    assert escape("<a href=\"x\">Tom & 'Jerry'</a>") == (
        "&lt;a href=&#34;x&#34;&gt;Tom &amp; &#39;Jerry&#39;&lt;/a&gt;"
    )
    assert isinstance(escape("x"), Markup)
    assert escape(42) == "42"
    assert escape(Markup("<b>")) == "<b>"
    assert escape(Widget()) == "<widget/>"


def test_markup_is_a_str_that_stays_markup():
    value = Markup("<b>")
    assert isinstance(value, str)
    assert value == "<b>"
    assert value.__html__() is value
    assert repr(value) == "Markup('<b>')"
    assert Markup(Widget()) == "<widget/>"
    assert type(str(value)) is str


def test_markup_concatenation_escapes_the_other_side():
    assert Markup("<b>") + "<i>" == "<b>&lt;i&gt;"
    assert "<i>" + Markup("<b>") == "&lt;i&gt;<b>"
    assert isinstance("<i>" + Markup("<b>"), Markup)
    assert Markup("<b>") + Markup("<i>") == "<b><i>"
    assert Markup("-") * 3 == "---"
    assert isinstance(3 * Markup("-"), Markup)
    with pytest.raises(TypeError):
        Markup("a") + 1


def test_markup_formatting_escapes_arguments():
    assert Markup("<b>%s</b>") % "<x>" == "<b>&lt;x&gt;</b>"
    assert Markup("%s-%s") % ("<", Markup(">")) == "&lt;->"
    values = {"a": "&", "n": 7, "f": 1.25}
    assert Markup("%(a)s %(n)03d %(f).1f") % values == "&amp; 007 1.2"
    assert Markup("<b>{}</b>{name!s:>3}|").format("<x>", name="&") == (
        "<b>&lt;x&gt;</b>  &amp;|"
    )
    assert Markup("{}").format(Markup("<i>")) == "<i>"
    assert Markup("{0.real}").format(3) == "3"
    with pytest.raises(ValueError, match="can't be applied to markup"):
        Markup("{:>5}").format(Markup("<i>"))


def test_markup_join_and_split():
    assert Markup(", ").join(["<a>", Markup("<b>"), 3]) == "&lt;a&gt;, <b>, 3"
    parts = Markup("a<br>b<br>c").split("<br>")
    assert parts == ["a", "b", "c"]
    assert all(isinstance(part, Markup) for part in parts)
    assert Markup("a b c").rsplit(None, 1) == ["a b", "c"]
    assert all(isinstance(line, Markup) for line in Markup("a\nb").splitlines())
    head, sep, tail = Markup("a<hr>b").partition(Markup("<hr>"))
    assert (head, sep, tail) == ("a", "<hr>", "b")
    assert isinstance(tail, Markup)


@pytest.mark.parametrize(
    "method, args, expected",
    [
        ("upper", (), "<B>X</B>"),
        ("lower", (), "<b>x</b>"),
        ("title", (), "<B>X</B>"),
        ("strip", (), "<b>x</b>"),
        ("replace", ("x", "<y>"), "<b>&lt;y&gt;</b>"),
        ("replace", ("x", Markup("<y>")), "<b><y></b>"),
        ("center", (10,), " <b>x</b> "),
        ("ljust", (10, "."), "<b>x</b>.."),
        ("removeprefix", (Markup("<b>"),), "x</b>"),
        ("zfill", (10,), "00<b>x</b>"),
    ],
)
def test_markup_string_methods_return_markup(method, args, expected):
    result = getattr(Markup("<b>x</b>"), method)(*args)
    assert result == expected
    assert isinstance(result, Markup)


def test_markup_slicing_keeps_the_type():
    assert isinstance(Markup("<b>x</b>")[3:], Markup)
    assert isinstance(Markup("abc")[0], Markup)


def test_markup_unescape_and_striptags():
    assert Markup("&lt;b&gt; &amp; &#39;x&#39; &eacute;").unescape() == "<b> & 'x' é"
    assert Markup("<p>Hello <b>big</b>\n   world</p><!-- c -->&amp;").striptags() == (
        "Hello big world&"
    )
    assert type(Markup("<b>x</b>").striptags()) is str
    assert Markup.escape("<x>") == "&lt;x&gt;"


def test_variables_are_escaped():
    assert render_html("<p>{{ text }}</p>", text="<b>&</b>") == (
        "<p>&lt;b&gt;&amp;&lt;/b&gt;</p>"
    )
    source = "{{ n }} {{ flag }} [{{ nothing }}]"
    assert render_html(source, n=3, flag=True, nothing=None) == "3 True []"


def test_template_text_and_markup_are_left_alone():
    assert render_html("<p>{{ html }}</p>", html=Markup("<b>x</b>")) == (
        "<p><b>x</b></p>"
    )
    assert render_html("{{ widget }}", widget=Widget()) == "<widget/>"


def test_string_literals_in_templates_are_escaped_too():
    assert render_html("{{ '<br>' }}") == "&lt;br&gt;"
    assert render_html("{{ '<br>' | safe }}") == "<br>"


def test_safe_and_escape_filters():
    assert render_html("{{ text | safe }}", text="<b>") == "<b>"
    assert render_html("{{ text | e }}", text="<b>") == "&lt;b&gt;"
    assert render_html("{{ text | escape | escape }}", text="<b>") == "&lt;b&gt;"
    assert render_html("{{ text | safe | escape }}", text="<b>") == "<b>"
    assert render_html("{{ text | safe | forceescape }}", text="<b>") == "&lt;b&gt;"
    assert render_html("{{ text | e | forceescape }}", text="<b>") == (
        "&amp;lt;b&amp;gt;"
    )
    assert render_html("[{{ none | e }}{{ missing | e }}]") == "[]"


def test_escape_filter_works_without_autoescape(render):
    assert render("{{ text }} {{ text | e }}", text="<b>") == "<b> &lt;b&gt;"


def test_filters_on_unsafe_text_stay_unsafe():
    assert render_html("{{ text | upper }}", text="<b>") == "&lt;B&gt;"
    source = "{{ text | trim | truncate(8, true) }}"
    assert render_html(source, text=" <b>long text</b> ") == "&lt;b&gt;lo..."
    assert render_html("{{ text | striptags }}", text="<b>a &amp; b</b>") == "a &amp; b"


def test_filters_on_safe_text_stay_safe():
    assert render_html("{{ html | upper }}", html=Markup("<b>x</b>")) == "<B>X</B>"
    assert render_html("{{ html | trim | lower }}", html=Markup(" <B>x</B> ")) == (
        "<b>x</b>"
    )
    assert render_html("{{ html | indent(2) }}", html=Markup("<p>\n<b>")) == (
        "<p>\n  <b>"
    )


def test_concat_with_markup_escapes_the_unsafe_parts():
    out = render_html("{{ '<' ~ html ~ text }}", html=Markup("<b>"), text="&")
    assert out == "&lt;<b>&amp;"
    assert render_html("{{ (text ~ text) | safe }}", text="<") == "<<"


def test_concat_without_autoescape_does_not_escape(render):
    assert render("{{ '<' ~ html }}", html=Markup("<b>")) == "<<b>"


def test_join_is_autoescape_aware():
    items = ["<a>", Markup("<b>"), "c"]
    assert render_html("{{ items | join(', ') }}", items=items) == "&lt;a&gt;, <b>, c"
    assert render_html("{{ items | join('<br>') }}", items=["x", "<y>"]) == (
        "x&lt;br&gt;&lt;y&gt;"
    )
    assert render_html("{{ items | join('<br>' | safe) }}", items=["x", "<y>"]) == (
        "x<br>&lt;y&gt;"
    )


def test_replace_is_autoescape_aware():
    assert render_html("{{ text | replace('b', '<i>') }}", text="<b>") == (
        "&lt;&lt;i&gt;&gt;"
    )
    assert render_html("{{ text | replace('b', '<i>' | safe) }}", text="<b>") == (
        "&lt;<i>&gt;"
    )
    assert render_html("{{ html | replace('b', 'i') }}", html=Markup("<b>")) == "<i>"


def test_macro_output_is_markup():
    source = (
        "{% macro tag(name, text) %}<{{ name }}>{{ text }}</{{ name }}>{% endmacro %}"
        "{{ tag('b', '<x>') }}|{{ tag('i', tag('b', '&')) }}"
    )
    assert render_html(source) == "<b>&lt;x&gt;</b>|<i><b>&amp;</b></i>"


def test_caller_set_block_and_super_are_markup():
    source = (
        "{% macro wrap() %}<div>{{ caller() }}</div>{% endmacro %}"
        "{% call wrap() %}<p>{{ text }}</p>{% endcall %}"
        "{% set block %}<i>{{ text }}</i>{% endset %}{{ block }}"
    )
    assert render_html(source, text="&") == "<div><p>&amp;</p></div><i>&amp;</i>"
    templates = {
        "base": "{% block a %}<b>{{ text }}</b>{% endblock %}",
        "child": "{% extends 'base' %}{% block a %}{{ super() }}!{% endblock %}",
    }
    env = Environment(DictLoader(templates))
    assert env.get_template("child").render(text="<") == "<b>&lt;</b>!"


def test_filter_block_output_is_escaped_once():
    source = "{% filter upper %}<p>{{ text }}</p>{% endfilter %}"
    assert render_html(source, text="a&b") == "<P>A&AMP;B</P>"


def test_includes_and_recursive_loops_are_not_double_escaped():
    env = Environment(
        DictLoader(
            {
                "page": "<main>{% include 'part' %}</main>",
                "part": "<p>{{ text }}</p>",
            }
        )
    )
    assert env.get_template("page").render(text="<>") == "<main><p>&lt;&gt;</p></main>"
    source = (
        "{% for n in tree recursive %}<li>{{ n.t }}"
        "{% if n.kids %}<ul>{{ loop(n.kids) }}</ul>{% endif %}</li>{% endfor %}"
    )
    tree = [{"t": "<a>", "kids": [{"t": "&"}]}]
    assert render_html(source, tree=tree) == "<li>&lt;a&gt;<ul><li>&amp;</li></ul></li>"


def test_autoescape_block_switches_escaping_off_and_on(render):
    source = (
        "{{ text }}"
        "{% autoescape true %}{{ text }}{% autoescape false %}{{ text }}"
        "{% endautoescape %}{{ text }}{% endautoescape %}"
        "{{ text }}"
    )
    assert render(source, text="<") == "<&lt;<&lt;<"
    source = "{% autoescape false %}{{ t }}{% endautoescape %}{{ t }}"
    assert render_html(source, t="<") == "<&lt;"


def test_autoescape_block_takes_an_expression(render):
    source = "{% autoescape on %}{{ text }}{% endautoescape %}"
    assert render(source, text="<", on=True) == "&lt;"
    assert render(source, text="<", on=False) == "<"


def test_error_inside_an_autoescape_block_does_not_stick(env):
    template = env.from_string(
        "{% autoescape true %}{{ text }}{{ 1 / n }}{% endautoescape %}{{ text }}"
    )
    with pytest.raises(TemplateRuntimeError):
        template.render(text="<", n=0)
    assert template.render(text="<", n=1) == "&lt;1.0<"


def test_macro_keeps_the_escaping_of_its_definition(render):
    source = (
        "{% macro raw(x) %}{{ x }}{% endmacro %}"
        "{% autoescape true %}{% macro esc(x) %}{{ x }}{% endmacro %}"
        "{{ raw('<') }}{% endautoescape %}{{ esc('<') }}"
    )
    assert render(source) == "&lt;&lt;"


def test_tojson_and_xmlattr_are_safe():
    assert render_html("{{ value | tojson }}", value={"a": "<b>"}) == (
        '{"a": "\\u003cb\\u003e"}'
    )
    assert render_html("<a{{ attrs | xmlattr }}>", attrs={"title": "<&>"}) == (
        '<a title="&lt;&amp;&gt;">'
    )


def test_urlize_escapes_text_but_not_its_own_links():
    assert render_html("{{ text | urlize }}", text="<b> http://x.org") == (
        '&lt;b&gt; <a href="http://x.org">http://x.org</a>'
    )


def test_autoescape_can_depend_on_the_template_name():
    names = ["page.html", "feed.XML", "robots.txt"]
    env = Environment(
        DictLoader(dict.fromkeys(names, "{{ t }}")),
        autoescape=select_autoescape(),
    )
    assert env.get_template("page.html").render(t="<") == "&lt;"
    assert env.get_template("feed.XML").render(t="<") == "&lt;"
    assert env.get_template("robots.txt").render(t="<") == "<"
    assert env.from_string("{{ t }}").render(t="<") == "&lt;"


def test_select_autoescape_options():
    choose = select_autoescape(["htm", ".tpl"], default=False, default_for_string=False)
    assert choose("a.htm") and choose("b.TPL")
    assert not choose("a.html")
    assert not choose(None)
    assert select_autoescape((), default=True)("anything.txt")


def test_included_template_uses_its_own_autoescape_setting():
    templates = {
        "page.html": "{{ t }}{% include 'raw.txt' %}",
        "raw.txt": "{{ t }}",
    }
    env = Environment(DictLoader(templates), autoescape=select_autoescape())
    assert env.get_template("page.html").render(t="<") == "&lt;<"


def test_autoescape_is_on_by_default():
    assert Environment().from_string("{{ t }}").render(t="<") == "&lt;"
