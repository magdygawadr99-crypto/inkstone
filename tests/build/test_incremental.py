from __future__ import annotations

import json

import pytest

from inkstone.build.cache import CACHE_VERSION

ALL_PAGES = 14
POSTS = {
    "first": "2024/01/first/index.html",
    "second": "2024/02/second/index.html",
    "third": "2024/03/third/index.html",
}


def html_written(report):
    return sorted(path for path in report.output_paths if path.endswith(".html"))


def test_second_build_writes_nothing(blog):
    first = blog.build()
    second = blog.build()
    assert first.pages_written == ALL_PAGES
    assert second.pages_written == 0
    assert second.pages_skipped == ALL_PAGES
    assert second.pages_rendered == 0
    assert second.assets_copied == 0
    assert second.output_paths == []
    assert second.changed is False
    assert second.summary().startswith("0 pages written, 14 unchanged")


def test_output_files_keep_their_modification_time(blog):
    blog.build()
    before = {name: (blog.output / name).stat().st_mtime_ns for name in blog.outputs()}
    blog.build()
    after = {name: (blog.output / name).stat().st_mtime_ns for name in blog.outputs()}
    assert after == before


def test_editing_the_body_of_a_post_rewrites_only_that_post(blog):
    blog.build()
    blog.page(
        "posts/2024-02-10-second.md",
        "The second post.\n\n## A heading\n\nMore text, now with a fixed typo.\n",
        title="Second",
        tags=["python"],
    )
    report = blog.build()
    assert html_written(report) == [POSTS["second"]]
    assert report.pages_written == 1
    assert report.pages_skipped == ALL_PAGES - 1
    assert "fixed typo" in blog.read(POSTS["second"])
    # the feeds carry the full text, so they change as well
    assert "rss.xml" in report.output_paths
    assert "search-index.json" in report.output_paths


def test_changing_a_title_rewrites_the_post_and_the_lists_it_is_on(blog):
    blog.build()
    blog.page(
        "posts/2024-02-10-second.md",
        "The second post.\n\n## A heading\n\nMore text.\n",
        title="Second, retitled",
        tags=["python"],
    )
    report = blog.build()
    assert html_written(report) == [
        POSTS["first"],
        POSTS["second"],
        POSTS["third"],
        "index.html",
        "posts/index.html",
        "tags/python/index.html",
    ]
    assert "Second, retitled" in blog.read("posts/index.html")
    # neighbours show the title in their prev/next links
    assert "Second, retitled" in blog.read(POSTS["first"])


def test_changing_the_summary_rewrites_the_lists_that_show_it(blog):
    blog.build()
    blog.page(
        "posts/2024-01-10-first.md",
        "The first post, reworded.\n\n<!-- more -->\n\nIts second paragraph.\n",
        title="First",
        tags=["python", "notes"],
    )
    report = blog.build()
    written = html_written(report)
    assert POSTS["first"] in written
    assert "posts/page/2/index.html" in written
    assert "posts/index.html" not in written
    assert POSTS["third"] not in written
    assert "reworded" in blog.read("posts/page/2/index.html")


def test_text_after_the_more_marker_does_not_touch_the_lists(blog):
    blog.build()
    blog.page(
        "posts/2024-01-10-first.md",
        "The first post.\n\n<!-- more -->\n\nIts second paragraph, extended.\n",
        title="First",
        tags=["python", "notes"],
    )
    assert html_written(blog.build()) == [POSTS["first"]]


def test_adding_a_tag_updates_the_taxonomy_pages(blog):
    blog.build()
    blog.page(
        "posts/2024-03-10-third.md",
        "The third post links to [the first](2024-01-10-first.md).\n",
        title="Third",
        categories=["News"],
        tags=["python", "fresh"],
    )
    report = blog.build()
    written = html_written(report)
    assert "tags/fresh/index.html" in written
    assert "tags/python/index.html" in written
    assert "tags/index.html" in written
    assert "tags/notes/index.html" not in written
    assert "about/index.html" not in written
    assert "(3)" in blog.read("tags/index.html")


def test_adding_a_post_updates_lists_and_neighbours(blog):
    blog.build()
    blog.page("posts/2024-04-10-fourth.md", "Number four.\n", title="Fourth")
    report = blog.build()
    written = html_written(report)
    assert "2024/04/fourth/index.html" in written
    assert "posts/index.html" in written and "posts/page/2/index.html" in written
    assert "index.html" in written
    # the previously newest post gets a "prev" link
    assert POSTS["third"] in written
    assert "about/index.html" not in written
    assert POSTS["first"] not in written
    assert 'class="prev" href="/2024/04/fourth/"' in blog.read(POSTS["third"])


def test_deleting_a_post_removes_its_output(blog):
    blog.build()
    (blog.root / "content/posts/2024-01-10-first.md").unlink()
    report = blog.build()
    assert not blog.exists(POSTS["first"])
    assert not (blog.output / "2024/01").exists()
    assert POSTS["first"] in report.removed_paths
    # with two posts left there is no second list page, and no "notes" tag
    assert "posts/page/2/index.html" in report.removed_paths
    assert "tags/notes/index.html" in report.removed_paths
    assert not blog.exists("posts/page/2/index.html")
    assert "First" not in blog.read("posts/index.html")
    assert report.files_removed == len(report.removed_paths) >= 4
    # and the next build is quiet again
    assert blog.build().changed is False


def test_changing_the_base_template_rewrites_everything(blog):
    blog.build()
    path = blog.root / "themes/tiny/templates/base.html"
    path.write_text(
        path.read_text(encoding="utf-8").replace("<body", '<body data-v="2"'),
        encoding="utf-8",
    )
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert 'data-v="2"' in blog.read("about/index.html")
    assert 'data-v="2"' in blog.read("404.html")


def test_changing_a_partial_rewrites_the_pages_that_include_it(blog):
    blog.write("templates/partials/note.html", "<aside>note v1</aside>\n")
    blog.write(
        "templates/page.html",
        "{% extends 'base.html' %}{% block content %}{{ page.content }}"
        "{% include 'partials/note.html' %}{% endblock %}\n",
    )
    blog.build()
    blog.write("templates/partials/note.html", "<aside>note v2</aside>\n")
    report = blog.build()
    assert html_written(report) == [
        POSTS["first"],
        POSTS["second"],
        POSTS["third"],
        "about/index.html",
    ]
    assert "note v2" in blog.read("about/index.html")


def test_a_new_override_in_the_site_templates_is_noticed(blog):
    blog.build()
    blog.write("templates/partials/footer.html", "<footer>overridden</footer>\n")
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert "overridden" in blog.read("index.html")
    (blog.root / "templates/partials/footer.html").unlink()
    assert blog.build().pages_written == ALL_PAGES
    assert "tiny footer" in blog.read("index.html")


def test_changing_the_config_rewrites_everything(blog):
    blog.build()
    blog.configure("title: Another Title\n")
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert "| Another Title</title>" in blog.read("about/index.html")


def test_server_settings_do_not_invalidate_pages(blog):
    blog.build()
    blog.configure("server:\n  port: 9999\n")
    assert blog.build().pages_written == 0


def test_changing_theme_params_rewrites_everything(blog):
    blog.build()
    blog.write(
        "themes/tiny/theme.toml",
        'name = "tiny"\n\n[params]\nfooter = "new footer"\nwide = false\n',
    )
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert "new footer" in blog.read("about/index.html")


def test_changing_a_data_file_rewrites_everything(blog):
    blog.write("data/links.json", '[{"name": "a"}]')
    blog.write(
        "templates/partials/footer.html",
        "<footer>{% for link in site.data.links %}{{ link.name }}{% endfor %}"
        "</footer>\n",
    )
    blog.build()
    blog.write("data/links.json", '[{"name": "b"}]')
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert "<footer>b</footer>" in blog.read("about/index.html")


def test_drafts_flag_is_part_of_the_cache_key(blog):
    blog.build()
    report = blog.build(drafts=True)
    # nothing new to show, but every page was rendered for the other mode
    assert report.pages_rendered == ALL_PAGES
    assert report.pages_written == 0


def test_templates_that_list_site_pages_follow_other_pages(blog):
    blog.write(
        "templates/partials/footer.html",
        "<footer>{% for p in site.pages %}{{ p.title }};{% endfor %}</footer>\n",
    )
    blog.build()
    blog.page("about.md", "About **me**.\n", title="About, renamed")
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert "About, renamed;" in blog.read(POSTS["first"])


def test_without_such_templates_other_pages_are_left_alone(blog):
    blog.build()
    blog.page("about.md", "About **me**.\n", title="About, renamed")
    assert html_written(blog.build()) == ["about/index.html"]


def test_moving_a_page_rewrites_the_pages_that_link_to_it(blog):
    blog.build()
    blog.page(
        "posts/2024-01-10-first.md",
        "The first post.\n\n<!-- more -->\n\nIts second paragraph.\n",
        title="First",
        tags=["python", "notes"],
        slug="premier",
    )
    report = blog.build()
    assert '<a href="/2024/01/premier/">the first</a>' in blog.read(POSTS["third"])
    assert POSTS["first"] in report.removed_paths
    assert blog.exists("2024/01/premier/index.html")


def test_no_incremental_renders_everything_again(blog):
    blog.build()
    report = blog.build(incremental=False)
    assert report.incremental is False
    assert report.pages_rendered == ALL_PAGES
    # identical bytes are still not written a second time
    assert report.pages_written == 0
    assert report.pages_skipped == ALL_PAGES
    assert report.output_paths == []


def test_no_incremental_still_removes_stale_outputs(blog):
    blog.build()
    (blog.root / "content/about.md").unlink()
    report = blog.build(incremental=False)
    assert report.removed_paths == ["about/index.html"]


def test_incremental_can_be_switched_off_in_the_config(blog):
    blog.configure("build:\n  incremental: false\n")
    blog.build()
    assert blog.build().pages_rendered == ALL_PAGES


def test_deleted_output_file_is_written_again(blog):
    blog.build()
    (blog.output / "about/index.html").unlink()
    (blog.output / "rss.xml").unlink()
    (blog.output / "search-index.json").unlink()
    report = blog.build()
    assert report.output_paths == ["about/index.html", "rss.xml", "search-index.json"]
    assert report.pages_written == 1


def test_deleted_output_directory_is_rebuilt_from_the_cache(blog):
    import shutil

    blog.build()
    shutil.rmtree(blog.output)
    report = blog.build()
    assert report.pages_written == ALL_PAGES
    assert report.assets_copied == 3
    assert blog.exists("css/theme.css") and blog.exists("sitemap.xml")


@pytest.mark.parametrize(
    "damage",
    [
        "not json at all {",
        "[]",
        '{"version": 0, "outputs": ["about/index.html"]}',
        '{"version": %d, "outputs": {"about/index.html": "oops"}}' % CACHE_VERSION,
        '{"version": %d, "inkstone": "0.0.1", "outputs": {}}' % CACHE_VERSION,
        "",
    ],
)
def test_damaged_or_old_cache_means_a_full_rebuild(blog, damage):
    blog.build()
    cache_file = blog.root / ".inkstone-cache" / "build.json"
    assert cache_file.is_file()
    cache_file.write_text(damage, encoding="utf-8")
    report = blog.build()
    assert report.pages_rendered == ALL_PAGES
    assert report.pages_written == 0
    # and the cache is good again afterwards
    state = json.loads(cache_file.read_text(encoding="utf-8"))
    assert state["version"] == CACHE_VERSION
    assert blog.build().pages_rendered == 0


def test_damaged_render_cache_only_costs_a_render(blog):
    blog.build()
    renders = blog.root / ".inkstone-cache" / "renders"
    for path in renders.iterdir():
        path.write_text("{broken", encoding="utf-8")
    blog.page("about.md", "About **me**, again.\n", title="About")
    report = blog.build()
    assert html_written(report) == ["about/index.html"]
    assert "again" in blog.read("about/index.html")


def test_render_cache_is_pruned_when_sources_go_away(blog):
    blog.build()
    renders = blog.root / ".inkstone-cache" / "renders"
    count = len(list(renders.iterdir()))
    assert count == 6
    (blog.root / "content/about.md").unlink()
    blog.build()
    assert len(list(renders.iterdir())) == count - 1


def test_cache_records_outputs_and_dependencies(blog):
    builder = blog.builder()
    builder.build()
    cache = builder.cache
    assert set(cache.outputs) >= {"about/index.html", "rss.xml", "search-index.json"}
    assert cache.outputs["about/index.html"]["kind"] == "page"
    assert cache.outputs["rss.xml"]["kind"] == "file"
    deps = cache.graph.dependencies("output:about/index.html")
    assert "source:about.md" in deps
    assert {"template:page.html", "template:base.html"} <= deps
    assert "template:partials/footer.html" in deps
    assert "config" in deps
    listing = cache.graph.dependencies("output:posts/index.html")
    assert "source:posts/_index.md" in listing
    assert "source:posts/2024-03-10-third.md" in listing
    affected = cache.graph.affected_outputs(["template:section.html"])
    assert "posts/index.html" in affected and "about/index.html" not in affected
    first = "source:posts/2024-01-10-first.md"
    affected = cache.graph.affected_outputs([first])
    assert {POSTS["first"], "posts/page/2/index.html"} <= affected


def test_builder_can_say_what_a_changed_file_reaches(blog):
    builder = blog.builder()
    assert builder.affected_outputs([blog.root / "content/about.md"]) == set()
    builder.build()
    content = blog.root / "content"
    assert builder.affected_outputs([content / "about.md"]) == {
        "about/index.html",
        "atom.xml",
        "posts/rss.xml",
        "rss.xml",
        "search-index.json",
        "sitemap.xml",
    }
    reached = builder.affected_outputs([content / "posts/2024-03-10-third.md"])
    assert {POSTS["third"], "posts/index.html", "index.html"} <= reached
    assert "about/index.html" not in reached and "robots.txt" not in reached
    templates = blog.root / "themes/tiny/templates"
    assert "about/index.html" in builder.affected_outputs([templates / "page.html"])
    assert len(builder.affected_outputs([templates / "base.html"])) == ALL_PAGES
    assert builder.affected_outputs([content / "never-seen.md"]) == set()
    assert builder.affected_outputs([blog.root / "static/css/theme.css"]) == set()
    # config, data and plugins can reach anything
    assert builder.affected_outputs([blog.config_path]) is None
    assert builder.affected_outputs([blog.root / "data/links.json"]) is None
    assert builder.affected_outputs([blog.root / "plugins/x.py"]) is None
    assert builder.affected_outputs([blog.root / "themes/tiny/theme.toml"]) is None


def test_fingerprinted_asset_change_rewrites_the_pages_that_link_it(blog):
    blog.overrides["build.fingerprint"] = True
    blog.build()
    old = [name for name in blog.outputs() if name.startswith("css/theme.")]
    blog.write("static/css/theme.css", "body { margin: 2px; }\n")
    report = blog.build()
    new = [name for name in blog.outputs() if name.startswith("css/theme.")]
    assert len(old) == len(new) == 1 and old != new
    assert report.pages_written == ALL_PAGES
    assert f'href="/{new[0]}"' in blog.read("about/index.html")
    assert old[0] in report.removed_paths


def test_plain_asset_change_leaves_the_pages_alone(blog):
    blog.build()
    blog.write("static/css/theme.css", "body { margin: 2px; }\n")
    report = blog.build()
    assert report.pages_written == 0
    assert report.assets_copied == 1
    assert report.output_paths == ["css/theme.css"]
    assert blog.read("css/theme.css") == "body { margin: 2px; }\n"


def test_removed_static_file_is_removed_from_the_output(blog):
    blog.write("static/img/logo.svg", "<svg/>")
    blog.build()
    (blog.root / "static/img/logo.svg").unlink()
    report = blog.build()
    assert not blog.exists("img/logo.svg")
    assert "img/logo.svg" in report.removed_paths


def test_long_running_builder_sees_template_edits(blog):
    builder = blog.builder()
    builder.build()
    path = blog.root / "themes/tiny/templates/partials/footer.html"
    # same length, written at once: only the content tells the two apart
    path.write_text("<footer>{{ config.params.footer }}!</footer>\n", encoding="utf-8")
    first = builder.build()
    path.write_text("<footer>{{ config.params.footer }}?</footer>\n", encoding="utf-8")
    second = builder.build()
    assert first.pages_written == ALL_PAGES
    assert second.pages_written == ALL_PAGES
    assert "tiny footer?</footer>" in blog.read("about/index.html")


def test_long_running_builder_follows_content_changes(blog):
    builder = blog.builder()
    builder.build()
    blog.page("about.md", "Edited once.\n", title="About")
    assert html_written(builder.build()) == ["about/index.html"]
    (blog.root / "content/about.md").unlink()
    report = builder.build()
    assert report.removed_paths == ["about/index.html"]
    assert builder.build().changed is False
