from __future__ import annotations

from pathlib import Path

import pytest

from inkstone import tomlw
from inkstone.build import Theme, available_themes, find_theme, theme_chain
from inkstone.build.templates import (
    TemplateFingerprints,
    ThemeNotFound,
    make_environment,
    parse_simple_toml,
    select_template,
    static_search_path,
    template_candidates,
    template_search_path,
)
from inkstone.content import Page, Section, Taxonomy
from inkstone.errors import BuildError, ConfigError


def test_find_a_local_theme(site):
    theme = find_theme("tiny", site.root / "themes")
    assert isinstance(theme, Theme)
    assert theme.name == "tiny"
    assert theme.path == site.root / "themes" / "tiny"
    assert theme.description == "Just enough templates to build a site."
    assert theme.version == "0.1.0"
    assert theme.inherit is None
    assert theme.params == {"footer": "tiny footer", "wide": False}
    assert theme.builtin is False
    assert theme.templates_path == theme.path / "templates"
    assert theme.static_path == theme.path / "static"


def test_theme_directory_without_a_theme_file(site):
    site.write("themes/bare/templates/page.html", "x")
    theme = find_theme("bare", site.root / "themes")
    assert theme.params == {} and theme.inherit is None and theme.version == ""


def test_unknown_theme_lists_what_there_is(site):
    with pytest.raises(ThemeNotFound) as excinfo:
        find_theme("nope", site.root / "themes")
    assert isinstance(excinfo.value, ConfigError)
    assert "theme 'nope' not found" in excinfo.value.message
    assert "tiny" in excinfo.value.message


@pytest.mark.parametrize("name", ["../tiny", "a/b", "", ".hidden", "a b", None])
def test_theme_names_cannot_be_paths(site, name):
    with pytest.raises(ConfigError, match="not a valid theme name"):
        find_theme(name, site.root / "themes")


def test_available_themes_includes_local_ones(site):
    site.write("themes/second/theme.toml", 'name = "second"\n')
    site.write("themes/.git/config", "")
    names = available_themes(site.root / "themes")
    assert {"tiny", "second"} <= set(names)
    assert ".git" not in names
    assert names == sorted(names)
    assert "tiny" not in available_themes()


def test_theme_chain_follows_inherit(site):
    site.write("themes/child/theme.toml", 'name = "child"\ninherit = "tiny"\n')
    site.write("themes/grandchild/theme.toml", 'inherit = "child"\n')
    site.configure("theme: grandchild\n")
    chain = theme_chain(site.config())
    assert [theme.name for theme in chain] == ["grandchild", "child", "tiny"]


def test_inheritance_loops_are_an_error(site):
    site.write("themes/a/theme.toml", 'inherit = "b"\n')
    site.write("themes/b/theme.toml", 'inherit = "a"\n')
    site.configure("theme: a\n")
    with pytest.raises(ConfigError, match="in a circle: a -> b -> a"):
        site.builder().build()


def test_missing_parent_theme_says_who_wanted_it(site):
    site.write("themes/child/theme.toml", 'inherit = "ghost"\n')
    site.configure("theme: child\n")
    with pytest.raises(ThemeNotFound, match="'ghost' not found.*inherited by.*'child'"):
        site.builder().build()


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("inherit = 3\n", "inherit has to be the name of a theme"),
        ('params = "x"\n', r"\[params\] has to be a table"),
    ],
)
def test_malformed_theme_file(site, text, message):
    path = site.write("themes/odd/theme.toml", text)
    with pytest.raises(ConfigError, match=message) as excinfo:
        find_theme("odd", site.root / "themes")
    assert Path(excinfo.value.path) == path


def test_search_paths(site):
    site.write("themes/child/theme.toml", 'inherit = "tiny"\n')
    site.configure("theme: child\n")
    config = site.config()
    chain = theme_chain(config)
    themes = site.root.resolve() / "themes"
    assert template_search_path(config, chain) == [
        site.root.resolve() / "templates",
        themes / "child" / "templates",
        themes / "tiny" / "templates",
    ]
    # static files the other way round: the pipeline lets later sources win
    assert static_search_path(config, chain) == [
        themes / "tiny" / "static",
        themes / "child" / "static",
        site.root.resolve() / "static",
    ]


def test_environment_escapes_html_but_not_text_templates(site):
    site.write("templates/t.html", "{{ value }}")
    site.write("templates/t.txt", "{{ value }}")
    site.write("templates/t.xml", "<a>{{ value }}</a>")
    config = site.config()
    env = make_environment(config, theme_chain(config))
    assert env.get_template("t.html").render(value="<b>") == "&lt;b&gt;"
    assert env.get_template("t.txt").render(value="<b>") == "<b>"
    assert env.get_template("t.xml").render(value="a & b") == "<a>a &amp; b</a>"
    assert "page.html" in env.list_templates()


def section(name, parent=None):
    made = Section(name)
    made.parent = parent
    return made


def page(kind="page", section_obj=None, template=None, **context):
    made = Page(kind=kind, template=template, extra_context=context)
    made.section = section_obj
    return made


@pytest.mark.parametrize(
    ("made", "expected"),
    [
        (page(), ["page.html"]),
        (page(section_obj=section("posts")), ["posts/page.html", "page.html"]),
        (
            page(section_obj=section("docs/guide", section("docs"))),
            ["docs/guide/page.html", "docs/page.html", "page.html"],
        ),
        (
            page(section_obj=section("posts"), template="special.html"),
            ["special.html", "posts/page.html", "page.html"],
        ),
        (page(template="page.html"), ["page.html"]),
        (page("section", section("posts")), ["posts/section.html", "section.html"]),
        (
            page("section", section("posts"), template="list.html"),
            ["list.html", "posts/section.html", "section.html"],
        ),
        (page("home"), ["index.html"]),
        (page("home", template="landing.html"), ["landing.html", "index.html"]),
        (
            page("taxonomy", taxonomy=Taxonomy("tags", "tag")),
            ["tags/taxonomy.html", "taxonomy.html"],
        ),
        (
            page("term", taxonomy=Taxonomy("tags", "tag")),
            ["tags/term.html", "term.html"],
        ),
        (page("term"), ["term.html"]),
        (page("404"), ["404.html"]),
        (page("virtual", template="archive.html"), ["archive.html"]),
        (page("virtual"), []),
    ],
)
def test_template_candidates(made, expected):
    assert template_candidates(made) == expected


def test_select_template_takes_the_first_that_exists(site):
    site.write("templates/posts/page.html", "posts page")
    config = site.config()
    env = make_environment(config, theme_chain(config))
    in_posts = page(section_obj=section("posts"))
    assert select_template(env, in_posts).name == "posts/page.html"
    assert select_template(env, page(section_obj=section("notes"))).name == "page.html"


def test_select_template_reports_what_it_tried(site):
    config = site.config()
    env = make_environment(config, theme_chain(config))
    missing = Page.virtual("/x/", template="nope.html")
    missing.source_path = "x.md"
    with pytest.raises(BuildError) as excinfo:
        select_template(env, missing)
    assert "tried: nope.html" in excinfo.value.message
    assert excinfo.value.path == "x.md"
    with pytest.raises(BuildError, match="no template given"):
        select_template(env, Page.virtual("/raw/"))


def test_fingerprints_cover_included_and_extended_templates(site):
    config = site.config()
    env = make_environment(config, theme_chain(config))
    prints = TemplateFingerprints(env)
    assert prints.dependencies("page.html") == [
        "base.html",
        "page.html",
        "partials/footer.html",
    ]
    before = prints.fingerprint("page.html")
    assert prints.fingerprint("page.html") == before
    assert prints.source_hash("nope.html") == ""

    footer = site.root / "themes/tiny/templates/partials/footer.html"
    footer.write_text("<footer>changed</footer>\n", encoding="utf-8")
    assert prints.fingerprint("page.html") == before
    prints.reset()
    after = prints.fingerprint("page.html")
    assert after != before
    assert prints.fingerprint("section.html") != prints.fingerprint("page.html")


def test_fingerprint_changes_when_a_template_is_shadowed(site):
    config = site.config()
    env = make_environment(config, theme_chain(config))
    prints = TemplateFingerprints(env)
    before = prints.fingerprint("page.html")
    site.write("templates/base.html", "{% block content %}{% endblock %}")
    prints.reset()
    assert prints.fingerprint("page.html") != before


def test_reset_drops_stale_parses_from_the_environment(site):
    path = site.write("templates/plain.html", "version one")
    config = site.config()
    env = make_environment(config, theme_chain(config))
    # as if the file system clock were too coarse to show the edit
    env.auto_reload = False
    prints = TemplateFingerprints(env)
    prints.fingerprint("plain.html")
    first = env.get_template("plain.html")
    prints.reset()
    assert env.get_template("plain.html") is first
    prints.fingerprint("plain.html")
    path.write_text("version two", encoding="utf-8")
    assert env.get_template("plain.html").render() == "version one"
    prints.reset()
    assert env.get_template("plain.html").render() == "version two"


SIMPLE_TOML = """\
# a comment
name = "paper"          # trailing comment
description = 'single # quoted'
version = "0.2.0"
inherit = "default"
count = 3
ratio = 1.5

[params]
show_toc = false
accent = "#8c3b2a"
custom_css = ["a.css", "b.css"]
empty = []

[params.social]
rss = true
"""


def test_simple_toml_reader_for_python_310():
    data = parse_simple_toml(SIMPLE_TOML)
    assert data == {
        "name": "paper",
        "description": "single # quoted",
        "version": "0.2.0",
        "inherit": "default",
        "count": 3,
        "ratio": 1.5,
        "params": {
            "show_toc": False,
            "accent": "#8c3b2a",
            "custom_css": ["a.css", "b.css"],
            "empty": [],
            "social": {"rss": True},
        },
    }
    if tomlw.tomllib is not None:
        assert data == tomlw.loads(SIMPLE_TOML)


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("name = \n", 1),
        ("ok = 1\njust words\n", 2),
        ('ok = 1\n\nwhen = 2024-05-03\n', 3),
        ('a = 1\n[a.b]\nc = 2\n', 2),
        ('multi = """\ntext\n"""\n', 1),
    ],
)
def test_simple_toml_reader_refuses_what_it_does_not_know(text, line):
    with pytest.raises(tomlw.TomlError) as excinfo:
        parse_simple_toml(text)
    assert excinfo.value.line == line


def test_theme_files_are_read_without_tomllib(site, monkeypatch):
    monkeypatch.setattr(tomlw, "tomllib", None)
    site.write("themes/child/theme.toml", 'inherit = "tiny"\n\n[params]\nwide = true\n')
    site.configure("theme: child\n")
    config = site.config()
    assert [theme.name for theme in theme_chain(config)] == ["child", "tiny"]
    assert config.params.wide is True
    assert config.params.footer == "tiny footer"
