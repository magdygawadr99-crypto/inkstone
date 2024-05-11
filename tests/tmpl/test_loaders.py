from __future__ import annotations

import os

import pytest

from inkstone.tmpl import (
    BaseLoader,
    ChoiceLoader,
    DictLoader,
    Environment,
    FileSystemLoader,
    TemplateError,
    TemplateNotFound,
    TemplateSyntaxError,
)
from inkstone.tmpl.loaders import split_template_path


def write(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)
    return path


def touch_later(path, seconds=10):
    # don't depend on the clock resolution of the file system
    info = os.stat(path)
    os.utime(path, (info.st_atime + seconds, info.st_mtime + seconds))


@pytest.fixture
def dirs(tmp_path):
    theme = tmp_path / "theme"
    site = tmp_path / "site"
    write(theme / "base.html", "theme base")
    write(theme / "page.html", "theme page")
    write(theme / "partials" / "nav.html", "theme nav")
    write(site / "page.html", "site page")
    write(site / "extra.html", "site extra")
    return site, theme


def test_filesystem_loader_reads_a_template(tmp_path):
    write(tmp_path / "hello.html", "Hello {{ name }}!")
    env = Environment(FileSystemLoader(tmp_path))
    template = env.get_template("hello.html")
    assert template.render(name="x") == "Hello x!"
    assert template.name == "hello.html"
    assert template.filename == os.path.join(str(tmp_path), "hello.html")


def test_filesystem_loader_accepts_str_and_pathlike(tmp_path):
    write(tmp_path / "a.txt", "a")
    assert FileSystemLoader(str(tmp_path)).get_source("a.txt")[0] == "a"
    assert FileSystemLoader([tmp_path]).get_source("a.txt")[0] == "a"
    assert FileSystemLoader(tmp_path).searchpath == [str(tmp_path)]


def test_search_path_order(dirs):
    site, theme = dirs
    env = Environment(FileSystemLoader([site, theme]))
    assert env.get_template("page.html").render() == "site page"
    assert env.get_template("base.html").render() == "theme base"
    assert env.get_template("partials/nav.html").render() == "theme nav"
    env = Environment(FileSystemLoader([theme, site]))
    assert env.get_template("page.html").render() == "theme page"


def test_missing_template(dirs):
    env = Environment(FileSystemLoader(dirs))
    with pytest.raises(TemplateNotFound) as excinfo:
        env.get_template("nope.html")
    assert excinfo.value.name == "nope.html"
    assert str(excinfo.value) == "template 'nope.html' not found"


def test_a_directory_is_not_a_template(dirs):
    env = Environment(FileSystemLoader(dirs))
    with pytest.raises(TemplateNotFound):
        env.get_template("partials")


def test_missing_search_directory_is_skipped(tmp_path, dirs):
    site, _ = dirs
    env = Environment(FileSystemLoader([tmp_path / "does-not-exist", site]))
    assert env.get_template("extra.html").render() == "site extra"
    assert env.list_templates() == ["extra.html", "page.html"]


@pytest.mark.parametrize(
    "name",
    [
        "../secret.txt",
        "partials/../../secret.txt",
        "..",
        "",
        "/",
        "a\x00b",
    ],
)
def test_names_can_not_escape_the_search_path(tmp_path, name):
    write(tmp_path / "secret.txt", "secret")
    write(tmp_path / "templates" / "ok.html", "ok")
    env = Environment(FileSystemLoader(tmp_path / "templates"))
    with pytest.raises(TemplateNotFound):
        env.get_template(name)


def test_backslash_is_not_a_separator_in_template_names(tmp_path):
    write(tmp_path / "partials" / "nav.html", "nav")
    loader = FileSystemLoader(tmp_path)
    with pytest.raises(TemplateNotFound):
        loader.get_source("partials\\nav.html")
    assert loader.get_source("partials/nav.html")[0] == "nav"


@pytest.mark.parametrize(
    "name, parts",
    [
        ("a.html", ["a.html"]),
        ("a/b/c.html", ["a", "b", "c.html"]),
        ("./a//b.html", ["a", "b.html"]),
    ],
)
def test_split_template_path(name, parts):
    assert split_template_path(name) == parts


def test_list_templates(dirs):
    env = Environment(FileSystemLoader(dirs))
    assert env.list_templates() == [
        "base.html",
        "extra.html",
        "page.html",
        "partials/nav.html",
    ]


def test_template_is_cached(dirs):
    env = Environment(FileSystemLoader(dirs))
    assert env.get_template("page.html") is env.get_template("page.html")


def test_cache_is_invalidated_when_the_file_changes(dirs):
    site, _ = dirs
    env = Environment(FileSystemLoader(dirs))
    first = env.get_template("page.html")
    assert first.is_up_to_date()
    write(site / "page.html", "changed")
    touch_later(site / "page.html")
    assert not first.is_up_to_date()
    second = env.get_template("page.html")
    assert second is not first
    assert second.render() == "changed"
    assert env.get_template("page.html") is second


def test_cache_notices_a_file_that_starts_shadowing(dirs):
    site, _ = dirs
    env = Environment(FileSystemLoader(dirs))
    assert env.get_template("base.html").render() == "theme base"
    write(site / "base.html", "site base")
    assert env.get_template("base.html").render() == "site base"


def test_cache_notices_a_deleted_file(dirs):
    site, _ = dirs
    env = Environment(FileSystemLoader(dirs))
    assert env.get_template("page.html").render() == "site page"
    (site / "page.html").unlink()
    assert env.get_template("page.html").render() == "theme page"
    assert env.get_template("extra.html").render() == "site extra"
    (site / "extra.html").unlink()
    with pytest.raises(TemplateNotFound):
        env.get_template("extra.html")


def test_auto_reload_can_be_switched_off(dirs):
    site, _ = dirs
    env = Environment(FileSystemLoader(dirs), auto_reload=False)
    first = env.get_template("page.html")
    write(site / "page.html", "changed")
    touch_later(site / "page.html")
    assert env.get_template("page.html") is first
    env.clear_cache()
    assert env.get_template("page.html").render() == "changed"


def test_parents_and_includes_are_reloaded_on_their_own(tmp_path):
    page_source = "{% extends 'base.html' %}{% block a %}x{% endblock %}"
    write(tmp_path / "base.html", "v1:{% block a %}{% endblock %}")
    write(tmp_path / "page.html", page_source)
    env = Environment(FileSystemLoader(tmp_path))
    page = env.get_template("page.html")
    assert page.render() == "v1:x"
    write(tmp_path / "base.html", "v2:{% block a %}{% endblock %}")
    touch_later(tmp_path / "base.html")
    assert page.render() == "v2:x"
    assert env.get_template("page.html") is page


def test_syntax_error_names_the_file(tmp_path):
    path = write(tmp_path / "broken.html", "line one\n{% if x %}\nno end")
    env = Environment(FileSystemLoader(tmp_path))
    with pytest.raises(TemplateSyntaxError) as excinfo:
        env.get_template("broken.html")
    assert excinfo.value.path == str(path)
    assert excinfo.value.line == 3
    assert str(excinfo.value).startswith(f"{path}:3: unexpected end of template")


def test_broken_template_is_not_cached(tmp_path):
    path = write(tmp_path / "t.html", "{% if %}")
    env = Environment(FileSystemLoader(tmp_path))
    with pytest.raises(TemplateSyntaxError):
        env.get_template("t.html")
    write(path, "fixed")
    assert env.get_template("t.html").render() == "fixed"


def test_files_are_read_as_utf8(tmp_path):
    write(tmp_path / "t.html", "café {{ 'ü' }} ☃")
    env = Environment(FileSystemLoader(tmp_path))
    assert env.get_template("t.html").render() == "café ü ☃"


def test_other_encodings(tmp_path):
    write(tmp_path / "t.html", "café", encoding="latin-1")
    env = Environment(FileSystemLoader(tmp_path, encoding="latin-1"))
    assert env.get_template("t.html").render() == "café"


def test_undecodable_file_is_a_template_error(tmp_path):
    path = write(tmp_path / "t.html", "café", encoding="latin-1")
    env = Environment(FileSystemLoader(tmp_path))
    with pytest.raises(TemplateError) as excinfo:
        env.get_template("t.html")
    assert excinfo.value.path == str(path)
    assert "can't read the template as utf-8" in excinfo.value.message


def test_byte_order_mark_is_dropped(tmp_path):
    write(tmp_path / "t.html", "\ufeff<p>x</p>")
    env = Environment(FileSystemLoader(tmp_path))
    assert env.get_template("t.html").render() == "<p>x</p>"


def test_windows_line_endings_are_normalised(tmp_path):
    (tmp_path / "t.html").write_bytes(b"a\r\n{% if x %}\r\nb\r\n{% endif %}\r\nc\r\n")
    env = Environment(FileSystemLoader(tmp_path), trim_blocks=True)
    assert env.get_template("t.html").render(x=1) == "a\nb\nc"


def test_dict_loader(make_env):
    env = make_env({"a.html": "A{{ x }}", "dir/b.html": "B"})
    assert env.get_template("a.html").render(x=1) == "A1"
    assert env.get_template("a.html").filename is None
    assert env.list_templates() == ["a.html", "dir/b.html"]
    with pytest.raises(TemplateNotFound):
        env.get_template("c.html")


def test_dict_loader_notices_changes():
    templates = {"a": "one"}
    env = Environment(DictLoader(templates))
    first = env.get_template("a")
    assert env.get_template("a") is first
    templates["a"] = "two"
    assert env.get_template("a").render() == "two"
    del templates["a"]
    with pytest.raises(TemplateNotFound):
        env.get_template("a")


def test_choice_loader(tmp_path):
    write(tmp_path / "page.html", "from disk")
    write(tmp_path / "disk-only.html", "disk only")
    loader = ChoiceLoader(
        [
            DictLoader({"page.html": "from dict", "dict-only.html": "dict only"}),
            FileSystemLoader(tmp_path),
        ]
    )
    env = Environment(loader)
    assert env.get_template("page.html").render() == "from dict"
    assert env.get_template("disk-only.html").render() == "disk only"
    assert env.get_template("dict-only.html").render() == "dict only"
    assert env.list_templates() == ["dict-only.html", "disk-only.html", "page.html"]
    with pytest.raises(TemplateNotFound):
        env.get_template("nope.html")


def test_choice_loader_keeps_uptodate_of_the_loader_that_answered(tmp_path):
    path = write(tmp_path / "page.html", "v1")
    env = Environment(ChoiceLoader([DictLoader({}), FileSystemLoader(tmp_path)]))
    first = env.get_template("page.html")
    write(path, "v2")
    touch_later(path)
    assert env.get_template("page.html") is not first


def test_base_loader_has_nothing():
    loader = BaseLoader()
    assert loader.list_templates() == []
    with pytest.raises(TemplateNotFound):
        loader.get_source("x")


def test_custom_loader(env):
    class UpperLoader(BaseLoader):
        def get_source(self, name):
            if not name.startswith("gen/"):
                raise TemplateNotFound(name)
            return name[4:].upper() + " {{ x }}", None, None

    env.loader = UpperLoader()
    template = env.get_template("gen/hello")
    assert template.render(x=1) == "HELLO 1"
    assert template.is_up_to_date()
    assert env.get_template("gen/hello") is template


def test_environment_without_loader(env):
    with pytest.raises(TemplateNotFound, match="has no loader"):
        env.get_template("a.html")
    assert env.list_templates() == []


def test_user_templates_override_parts_of_a_theme(tmp_path):
    theme = tmp_path / "theme"
    user = tmp_path / "user"
    write(theme / "base.html", "<body>{% block body %}{% endblock %}</body>")
    write(
        theme / "page.html",
        "{% extends 'base.html' %}"
        "{% block body %}{% include 'partials/title.html' %}{% endblock %}",
    )
    write(theme / "partials" / "title.html", "<h1>{{ page.title }}</h1>")
    write(user / "partials" / "title.html", "<h1 class=mine>{{ page.title }}</h1>")
    env = Environment(FileSystemLoader([user, theme]))
    out = env.get_template("page.html").render({"page": {"title": "Hi"}})
    assert out == "<body><h1 class=mine>Hi</h1></body>"
