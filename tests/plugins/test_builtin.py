"""The built-in plugins as a set: loading, settings, and a real build with
all of them switched on."""

from __future__ import annotations

import datetime as dt
import importlib
import json
import struct
from types import SimpleNamespace

import pytest

from inkstone.errors import ContentError, PluginError
from inkstone.plugins import Plugin, PluginManager
from inkstone.plugins.builtin import _common
from inkstone.plugins.manager import BUILTIN_NAMES

from .helpers import day, make_config, make_page

EVERYTHING = [
    "shortcodes",
    "toc",
    "reading_time",
    "related",
    "redirects",
    "archives",
    "external_links",
    "image_dims",
    "series",
    "minify",
    "drafts_banner",
    "footnote_previews",
    "git_dates",
]


def test_the_manager_knows_exactly_these_plugins():
    assert sorted(BUILTIN_NAMES) == sorted(EVERYTHING)


@pytest.mark.parametrize("name", EVERYTHING)
def test_each_module_defines_one_plugin_with_its_own_name(name):
    module = importlib.import_module(f"inkstone.plugins.builtin.{name}")
    classes = [
        obj
        for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin
    ]
    assert len(classes) == 1
    assert classes[0].name == name


def test_all_of_them_load_together(tmp_path):
    config = make_config(tmp_path, plugins=EVERYTHING)
    manager = PluginManager(config)
    manager.load()
    assert sorted(plugin.name for plugin in manager.plugins) == sorted(EVERYTHING)
    # shortcodes first, minify last, whatever the order in the config
    assert manager.plugins[0].name == "shortcodes"
    assert manager.plugins[-1].name == "minify"


def write_config(root, settings):
    # JSON, so that the tests do not depend on a Python that reads TOML
    (root / "inkstone.json").write_text(json.dumps(settings), encoding="utf-8")


def test_settings_come_from_the_plugin_table(tmp_path):
    settings = {
        "plugins": ["related", "reading_time"],
        "plugin": {"related": {"limit": 2}, "reading_time": {"words_per_minute": 100}},
    }
    write_config(tmp_path, settings)
    manager = PluginManager(make_config(tmp_path))
    manager.load()
    assert manager.get("related").limit == 2
    assert manager.get("reading_time").words_per_minute == 100


def test_a_bad_setting_stops_the_load_with_a_clear_message(tmp_path):
    settings = {"plugins": ["related"], "plugin": {"related": {"limit": "many"}}}
    write_config(tmp_path, settings)
    manager = PluginManager(make_config(tmp_path))
    with pytest.raises(PluginError) as caught:
        manager.load()
    assert str(caught.value) == (
        "[plugin.related] limit must be a whole number, got 'many'"
    )


class Dummy(Plugin):
    name = "dummy"


@pytest.mark.parametrize(
    "default, value, expected",
    [
        (5, 7, 7),
        (5, None, 5),
        (1.0, 2, 2.0),
        (0.5, 0.25, 0.25),
        (True, False, False),
        ("a", "b", "b"),
        ([], ["x"], ["x"]),
        ([], "x", ["x"]),
        ([], ("x", "y"), ["x", "y"]),
        ({}, {"k": 1}, {"k": 1}),
    ],
)
def test_setting_accepts(default, value, expected):
    plugin = Dummy(None, {"key": value})
    result = _common.setting(plugin, "key", default)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize(
    "default, value",
    [
        (5, "5"),
        (5, 5.0),
        (5, True),
        (1.0, "1"),
        (1.0, True),
        (True, 1),
        (True, "true"),
        ("a", 1),
        ([], 3),
        ({}, []),
    ],
)
def test_setting_rejects_the_wrong_type(default, value):
    plugin = Dummy(None, {"key": value})
    with pytest.raises(PluginError, match=r"\[plugin\.dummy\] key must be"):
        _common.setting(plugin, "key", default)


def test_setting_choices_and_minimum():
    plugin = Dummy(None, {"mode": "c", "count": 0})
    assert _common.setting(Dummy(None, {}), "mode", "a", choices=("a", "b")) == "a"
    with pytest.raises(PluginError, match="must be one of a, b; got 'c'"):
        _common.setting(plugin, "mode", "a", choices=("a", "b"))
    with pytest.raises(PluginError, match="cannot be less than 1, got 0"):
        _common.setting(plugin, "count", 5, minimum=1)


@pytest.mark.parametrize(
    "base_url, prefix",
    [
        ("https://example.com/", ""),
        ("https://example.com/blog/", "/blog"),
        ("https://example.com/a/b", "/a/b"),
        ("/", ""),
        ("/docs/", "/docs"),
    ],
)
def test_site_prefix_and_url_for(tmp_path, base_url, prefix):
    config = make_config(tmp_path, base_url=base_url)
    assert _common.site_prefix(config) == prefix
    assert _common.url_for(config, "/about/") == prefix + "/about/"
    assert _common.url_for(config, "relative/") == "relative/"
    assert _common.url_for(config, "https://other.example/") == "https://other.example/"
    assert _common.url_for(config, "//cdn.example/x") == "//cdn.example/x"


def test_helpers_also_take_plain_objects():
    bare = SimpleNamespace(base_url="https://example.com/sub/")
    assert _common.site_prefix(bare) == "/sub"
    assert _common.absolute_url(bare, "/x/") == "https://example.com/sub/x/"
    assert _common.absolute_url(bare, "https://o.example/") == "https://o.example/"
    assert _common.site_prefix({"base_url": "https://example.com/"}) == ""
    assert _common.lookup(None, "anything", "fallback") == "fallback"
    assert _common.lookup({"a": 1}, "a") == 1


def test_date_key_sorts_dates_datetimes_and_nothing():
    naive = make_page("Naive", date=dt.datetime(2024, 1, 2))
    aware = make_page("Aware", date=day(2024, 1, 3))
    plain = SimpleNamespace(date=dt.date(2024, 1, 1))
    undated = make_page("Undated")
    pages = sorted([aware, undated, naive, plain], key=_common.date_key)
    assert pages == [undated, plain, naive, aware]


def test_in_sections():
    posts = SimpleNamespace(name="posts")
    nested = SimpleNamespace(name="docs/guide")
    assert _common.in_sections(SimpleNamespace(section=posts), ["posts"])
    assert _common.in_sections(SimpleNamespace(section=nested), ["/docs/"])
    assert not _common.in_sections(SimpleNamespace(section=nested), ["doc"])
    assert not _common.in_sections(SimpleNamespace(section=None), ["posts"])


def test_display_path(tmp_path):
    config = make_config(tmp_path)
    path = config.content_path / "posts" / "x.md"
    with_file = make_page("X", source_path="posts/x.md", file_path=path)
    assert _common.display_path(with_file, config) == "content/posts/x.md"
    only_source = make_page("Y", source_path="posts/y.md")
    assert _common.display_path(only_source, config) == "content/posts/y.md"
    assert _common.display_path(make_page("Z"), config) is None


# From here on: a real build, through the real Builder.

POST_ONE = """\
---
title: Part one
date: 2024-03-01
tags: [sqlite, notes]
series: Storage
aliases: [/old/part-one/]
---

SQLite keeps a whole database in one file.[^1] See [the docs](https://sqlite.org/)
and [part two](part-two.md).

<!-- more -->

## Indexes

Press {{< kbd Ctrl F >}} to search.

![A diagram](/img/diagram.png)

{{< note warning title="Careful" >}}
Back up *first*.
{{< /note >}}

### Details

More about indexes and the query planner.

[^1]: With a journal next to it while writing.
"""

POST_TWO = """\
---
title: Part two
date: 2024-04-01
tags: [sqlite]
series: Storage
draft: true
---

More about SQLite, indexes and the query planner.

## Only heading
"""

ABOUT = "---\ntitle: About\n---\n\nNothing about databases here, only a person.\n"


def png(width, height):
    header = struct.pack(">I4sIIBBBBB", 13, b"IHDR", width, height, 8, 2, 0, 0, 0)
    end = struct.pack(">I4sI", 0, b"IEND", 0)
    return b"\x89PNG\r\n\x1a\n" + header + bytes(4) + end


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    build = pytest.importorskip("inkstone.build")
    root = tmp_path_factory.mktemp("site")
    settings = {
        "title": "Plugins",
        "base_url": "https://example.com/",
        "plugins": EVERYTHING,
        "plugin": {
            "toc": {"anchors": True},
            "redirects": {"netlify": True, "map": {"/feed/": "/rss.xml"}},
        },
    }
    write_config(root, settings)
    posts = root / "content" / "posts"
    posts.mkdir(parents=True)
    (posts / "part-one.md").write_text(POST_ONE, encoding="utf-8")
    (posts / "part-two.md").write_text(POST_TWO, encoding="utf-8")
    (root / "content" / "about.md").write_text(ABOUT, encoding="utf-8")
    (root / "static" / "img").mkdir(parents=True)
    (root / "static" / "img" / "diagram.png").write_bytes(png(320, 200))

    config = make_config(root, **{"build.drafts": True})
    builder = build.Builder(config)
    report = builder.build()
    return SimpleNamespace(
        root=root,
        output=config.output_path,
        builder=builder,
        report=report,
        site=builder.site,
        read=lambda rel: (config.output_path / rel).read_text(encoding="utf-8"),
    )


def test_build_with_every_plugin(built):
    assert built.report.warnings == []
    assert (built.output / "2024" / "03" / "part-one" / "index.html").is_file()


def test_shortcodes_in_a_real_page(built):
    html = built.read("2024/03/part-one/index.html")
    assert "<kbd>Ctrl</kbd>+<kbd>F</kbd>" in html
    assert 'class="note note--warning admonition warning"' in html
    assert "<p>Back up <em>first</em>.</p>" in html
    assert "{{<" not in html and "\ue000" not in html


def test_summary_and_feed_carry_no_placeholders(built):
    page = built.site.get_page("posts/part-one.md")
    assert "SQLite keeps a whole database" in page.summary
    assert "kbd" not in page.summary
    for name in ("rss.xml", "atom.xml", "search-index.json"):
        assert "\ue000" not in built.read(name)
    assert "Ctrl" in built.read("rss.xml")


def test_toc_in_a_real_page(built):
    page = built.site.get_page("posts/part-one.md")
    assert [entry.id for entry in page.toc] == ["indexes"]
    assert [child.id for child in page.toc[0].children] == ["details"]
    html = built.read("2024/03/part-one/index.html")
    assert 'class="heading-anchor" href="#indexes"' in html


def test_reading_time_and_git_dates_leave_sane_values(built):
    page = built.site.get_page("posts/part-one.md")
    assert page.reading_time == 1
    assert 30 < page.word_count < 80
    # the temporary directory is not a git repository
    assert page.updated is None


def test_related_and_series_in_a_real_page(built):
    one = built.site.get_page("posts/part-one.md")
    two = built.site.get_page("posts/part-two.md")
    assert one.related == [two] and two.related == [one]
    assert built.site.get_page("about.md").related == []
    assert (one.series.index, one.series.total, one.series.next) == (1, 2, two)
    # and the default theme shows both boxes
    html = built.read("2024/03/part-one/index.html")
    box = html[html.index('<aside class="series"') :].split("</aside>")[0]
    assert "<strong>Storage</strong>" in box
    assert '<a href="/2024/04/part-two/">Part two</a>' in box
    assert "related__title" in html


def test_generated_pages_are_written(built):
    for rel in (
        "archive/index.html",
        "archive/2024/index.html",
        "archive/2024/03/index.html",
        "series/index.html",
        "series/storage/index.html",
        "old/part-one/index.html",
        "feed/index.html",
    ):
        assert (built.output / rel).is_file(), rel
    archive = built.read("archive/index.html")
    assert "Part one" in archive and "<title>Archive" in archive
    assert "kind-virtual" in archive


def test_redirects_in_a_real_build(built):
    stub = built.read("old/part-one/index.html")
    assert 'content="0; url=https://example.com/2024/03/part-one/"' in stub
    # written as it is: no theme around it, no banner, not minified
    assert stub.startswith("<!doctype html>\n<html")
    assert "site-header" not in stub
    assert built.read("_redirects").splitlines() == [
        "/feed/          /rss.xml  301",
        "/old/part-one/  /2024/03/part-one/  301",
    ]


def test_links_images_and_footnotes_are_post_processed(built):
    html = built.read("2024/03/part-one/index.html")
    assert 'href="https://sqlite.org/" rel="noopener noreferrer"' in html
    assert 'href="/2024/04/part-two/"' in html
    assert 'width="320" height="200"' in html
    assert 'data-footnote-preview="With a journal next to it while writing."' in html


def test_draft_banner_and_minified_output(built):
    draft = built.read("2024/04/part-two/index.html")
    assert "Draft: not published" in draft
    assert "draft-banner" not in built.read("2024/03/part-one/index.html")
    # the minify plugin ran last: no indentation left between tags
    assert "\n  <" not in draft


def test_a_second_build_changes_nothing(built):
    again = built.builder.build()
    assert again.pages_written == 0
    assert again.warnings == []
    page = built.builder.site.get_page("posts/part-one.md")
    assert "<kbd>Ctrl</kbd>" in page.content
    assert page.series.total == 2 and len(page.related) == 1


def test_unknown_shortcode_fails_the_build_with_file_and_line(tmp_path):
    build = pytest.importorskip("inkstone.build")
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "oops.md").write_text(
        "---\ntitle: Oops\n---\n\nSome text.\n\n{{< nonesuch >}}\n", encoding="utf-8"
    )
    builder = build.Builder(make_config(tmp_path))
    with pytest.raises(ContentError) as caught:
        builder.build()
    assert str(caught.value) == "content/oops.md:7: unknown shortcode 'nonesuch'"


class Workshop:
    """A small site that is built again and again, as `inkstone serve` does."""

    def __init__(self, root):
        self.build = pytest.importorskip("inkstone.build")
        self.root = root
        self.builder = None
        self.page("plain", "No shortcodes here.")

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def page(self, name, body, front_matter=""):
        text = f"---\ntitle: {name.title()}\n{front_matter}---\n\n{body}\n"
        self.write(f"content/{name}.md", text)

    def rebuild(self, fresh=False):
        if self.builder is None or fresh:
            self.builder = self.build.Builder(make_config(self.root))
        return self.builder.build()

    def read(self, rel):
        return (self.root / "public" / rel).read_text(encoding="utf-8")


@pytest.fixture
def workshop(tmp_path):
    return Workshop(tmp_path)


@pytest.mark.parametrize("fresh", [False, True], ids=["same builder", "new builder"])
def test_editing_a_shortcode_template_reaches_the_pages_that_use_it(workshop, fresh):
    workshop.write("templates/shortcodes/badge.html", "<b>one</b>")
    workshop.page("uses", "A {{< badge >}} here.")
    workshop.rebuild()
    assert "A <b>one</b> here." in workshop.read("uses/index.html")

    workshop.write("templates/shortcodes/badge.html", "<b>two</b>")
    report = workshop.rebuild(fresh)
    assert "A <b>two</b> here." in workshop.read("uses/index.html")
    # and nothing else had to be written again
    assert "uses/index.html" in report.output_paths
    assert "plain/index.html" not in report.output_paths


def test_a_template_pulled_in_by_a_shortcode_template_counts_too(workshop):
    workshop.write("templates/shortcodes/badge.html", '{% include "parts/b.html" %}')
    workshop.write("templates/parts/b.html", "<b>one</b>")
    workshop.page("uses", "{{< badge >}}")
    workshop.rebuild()
    workshop.write("templates/parts/b.html", "<b>two</b>")
    workshop.rebuild()
    assert "<b>two</b>" in workshop.read("uses/index.html")


def test_a_new_template_takes_over_from_the_builtin_shortcode(workshop):
    workshop.page("uses", "Press {{< kbd X >}}.")
    workshop.rebuild()
    assert "<kbd>X</kbd>" in workshop.read("uses/index.html")
    template = "<kbd class=key>{{ args[0] }}</kbd>"
    workshop.write("templates/shortcodes/kbd.html", template)
    workshop.rebuild()
    assert "<kbd class=key>X</kbd>" in workshop.read("uses/index.html")


def test_editing_an_included_file_reaches_the_pages_that_include_it(workshop):
    workshop.write("content/parts/note.md", "The *first* wording.\n")
    workshop.page("uses", "{{< include parts/note.md >}}")
    workshop.rebuild()
    assert "The <em>first</em> wording." in workshop.read("uses/index.html")

    workshop.write("content/parts/note.md", "The *second* wording.\n")
    report = workshop.rebuild()
    assert "The <em>second</em> wording." in workshop.read("uses/index.html")
    assert "plain/index.html" not in report.output_paths


def test_moving_a_page_updates_the_refs_to_it(workshop):
    workshop.page("target", "Here.")
    workshop.page("uses", '[go]({{< ref "target.md" >}})')
    workshop.rebuild()
    assert '<a href="/target/">go</a>' in workshop.read("uses/index.html")

    workshop.page("target", "Here.", "url: /moved/\n")
    workshop.rebuild()
    assert '<a href="/moved/">go</a>' in workshop.read("uses/index.html")


def test_the_note_for_the_cache_never_reaches_the_output(workshop):
    workshop.write("templates/shortcodes/badge.html", "<b>one</b>")
    workshop.page("uses", "A {{< badge >}} here.")
    workshop.rebuild()
    page = workshop.builder.site.get_page("uses.md")
    assert "<!-- shortcodes:" in page.raw
    assert "shortcodes:" not in workshop.read("uses/index.html")
    assert "shortcodes:" not in workshop.read("search-index.json")
    # pages without anything to note are left exactly as they were written
    plain = workshop.builder.site.get_page("plain.md")
    assert plain.raw == "\nNo shortcodes here.\n"
