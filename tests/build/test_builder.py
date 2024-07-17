from __future__ import annotations

import json
import os

import pytest

from inkstone import __version__
from inkstone.build import Builder, BuildReport
from inkstone.errors import BuildError, ConfigError, ContentError, PluginError
from inkstone.markdown import Markdown
from inkstone.tmpl import Environment, Markup

PHASES = [
    "setup",
    "load",
    "markdown",
    "generate",
    "lists",
    "assets",
    "templates",
    "write",
    "extras",
    "cleanup",
]


def test_full_build_writes_the_expected_files(blog):
    report = blog.build()
    assert blog.outputs() == [
        "2024/01/first/index.html",
        "2024/02/second/index.html",
        "2024/03/third/index.html",
        "404.html",
        "about/index.html",
        "atom.xml",
        "categories/index.html",
        "categories/news/index.html",
        "css/highlight.css",
        "css/theme.css",
        "index.html",
        "js/inkstone-search.js",
        "page/2/index.html",
        "posts/index.html",
        "posts/page/2/index.html",
        "posts/rss.xml",
        "robots.txt",
        "rss.xml",
        "search-index.json",
        "sitemap.xml",
        "tags/index.html",
        "tags/notes/index.html",
        "tags/python/index.html",
    ]
    assert isinstance(report, BuildReport)
    assert report.pages_written == 14
    assert report.pages_skipped == 0
    assert report.assets_copied == 3
    assert report.files_removed == 0
    assert report.warnings == []
    assert sorted(report.output_paths) == blog.outputs()


def test_nothing_is_written_outside_output_and_cache(blog):
    before = {path.name for path in blog.root.iterdir()}
    blog.build()
    after = {path.name for path in blog.root.iterdir()}
    assert after - before == {"public", ".inkstone-cache"}


def test_regular_page_is_rendered_through_the_theme(blog):
    blog.build()
    html = blog.read("about/index.html")
    assert html.startswith("<!doctype html>")
    assert '<html lang="en">' in html
    assert "<title>About | Test Site</title>" in html
    assert '<body class="kind-page">' in html
    assert "<h1>About</h1>" in html
    assert "<p>About <strong>me</strong>.</p>" in html
    assert '<link rel="stylesheet" href="/css/theme.css">' in html
    assert "<footer>tiny footer</footer>" in html


def test_home_page_lists_the_feed_section(blog):
    blog.build()
    html = blog.read("index.html")
    assert "<title>Home | Test Site</title>" in html
    assert "<p>Welcome to the <em>test</em> site.</p>" in html
    assert html.index("Third") < html.index("Second")
    assert "First" not in html
    assert '<a href="/2024/01/first/">First</a>' in blog.read("page/2/index.html")


def test_section_list_with_summaries_and_pagination(blog):
    blog.build()
    first = blog.read("posts/index.html")
    assert "<h1>Posts</h1>" in first
    assert "<p>Everything I wrote.</p>" in first
    assert '<a href="/2024/03/third/">Third</a>' in first
    assert '<a href="/2024/02/second/">Second</a> <p>The second post.</p>' in first
    assert "page 1 of 2" in first
    assert '<a rel="next" href="/posts/page/2/">older</a>' in first
    second = blog.read("posts/page/2/index.html")
    assert '<a href="/2024/01/first/">First</a> <p>The first post.</p>' in second
    assert "Its second paragraph" not in second
    assert "page 2 of 2" in second
    assert 'rel="next"' not in second


def test_more_marker_is_gone_from_the_page_but_the_text_stays(blog):
    blog.build()
    html = blog.read("2024/01/first/index.html")
    assert "<!-- more -->" not in html
    assert "<p>The first post.</p>" in html
    assert "<p>Its second paragraph.</p>" in html


def test_links_to_markdown_files_become_links_to_pages(blog):
    blog.build()
    html = blog.read("2024/03/third/index.html")
    assert '<a href="/2024/01/first/">the first</a>' in html


def test_prev_and_next_links(blog):
    blog.build()
    second = blog.read("2024/02/second/index.html")
    assert '<a class="prev" href="/2024/03/third/">Third</a>' in second
    assert '<a class="next" href="/2024/01/first/">First</a>' in second
    assert 'class="prev"' not in blog.read("2024/03/third/index.html")


def test_taxonomy_and_term_pages(blog):
    blog.build()
    tags = blog.read("tags/index.html")
    assert "<h1>All tags</h1>" in tags
    assert '<li><a href="/tags/notes/">notes</a> (1)</li>' in tags
    assert '<li><a href="/tags/python/">python</a> (2)</li>' in tags
    assert tags.index("notes") < tags.index("python")
    term = blog.read("tags/python/index.html")
    assert "<h1>tag: python</h1>" in term
    assert term.index("Second") < term.index("First")
    assert "Third" not in term
    assert "<h1>category: News</h1>" in blog.read("categories/news/index.html")


def test_not_found_page(blog):
    blog.build()
    html = blog.read("404.html")
    assert "<h1>Not found</h1>" in html
    assert '<body class="kind-404">' in html


def test_not_found_page_from_content(blog):
    blog.page("404.md", "Try the [home page](/).\n", title="Lost")
    blog.build()
    html = blog.read("404.html")
    assert "<title>Lost | Test Site</title>" in html
    assert '<a href="/">home page</a>' in html
    assert not blog.exists("404/index.html")


def test_report_has_phases_duration_and_a_summary(blog):
    report = blog.build()
    assert list(report.phases) == PHASES
    assert all(seconds >= 0 for seconds in report.phases.values())
    assert report.duration >= sum(report.phases.values()) * 0.5
    summary = report.summary()
    assert summary.startswith("14 pages written, 3 assets, ")
    assert " in " in summary
    assert "warning" not in summary
    assert "templates" in report.phase_table()
    assert report.to_dict()["pages_written"] == 14
    assert report.changed is True


def test_output_paths_are_posix_and_relative(blog):
    report = blog.build()
    for path in report.output_paths:
        assert "\\" not in path and not path.startswith("/")
    assert "2024/01/first/index.html" in report.output_paths


def test_builder_attributes(blog):
    builder = blog.builder()
    assert builder.site is None
    assert isinstance(builder.env, Environment)
    assert builder.plugins.plugins == []
    assert builder.assets is not None
    assert isinstance(builder.markdown_for(None), Markdown)
    builder.build()
    assert builder.site.title == "Test Site"
    assert builder.config.title == "Test Site"
    about = builder.site.get_page("about.md")
    assert about.layout == "page.html"
    assert about.content == Markup("<p>About <strong>me</strong>.</p>\n")
    assert builder.site.get_page("posts").layout == "section.html"
    assert builder.site.home.layout == "index.html"
    assert builder.report.pages_written == 14


def test_render_markdown_uses_the_site_settings(blog):
    builder = blog.builder()
    html = builder.render_markdown('"Quoted" *text*')
    assert isinstance(html, Markup)
    assert html == "<p>“Quoted” <em>text</em></p>\n"


def test_page_objects_after_a_build(blog):
    builder = blog.builder()
    builder.build()
    first = builder.site.get_page("posts/2024-01-10-first.md")
    assert first.summary == Markup("<p>The first post.</p>\n")
    assert first.truncated is True
    assert first.word_count == 6
    assert first.reading_time == 1
    second = builder.site.get_page("posts/2024-02-10-second.md")
    assert [entry.title for entry in second.toc] == ["A heading"]
    assert 'href="#a-heading"' in second.toc_html
    assert second.summary == Markup("<p>The second post.</p>\n")
    all_urls = {page.url for page in builder.site.all_pages}
    assert {"/", "/posts/page/2/", "/tags/", "/tags/python/", "/404.html"} <= all_urls


def test_drafts_and_future_posts_are_built_on_request(blog):
    blog.page("posts/2024-04-01-draft.md", title="Draft", draft=True)
    blog.page("posts/2999-01-01-later.md", title="Later")
    blog.build()
    assert not blog.exists("2024/04/draft/index.html")
    assert not blog.exists("2999/01/later/index.html")
    assert "Draft" not in blog.read("posts/index.html")
    report = blog.build(drafts=True, future=True)
    assert blog.exists("2024/04/draft/index.html")
    assert blog.exists("2999/01/later/index.html")
    assert "2024/04/draft/index.html" in report.output_paths
    # and they go away again with the next ordinary build
    report = blog.build()
    assert not blog.exists("2024/04/draft/index.html")
    assert "2024/04/draft/index.html" in report.removed_paths


def test_drafts_from_the_config(blog):
    blog.page("posts/2024-04-01-draft.md", title="Draft", draft=True)
    blog.overrides["build.drafts"] = True
    blog.build()
    assert blog.exists("2024/04/draft/index.html")


def test_base_url_with_a_sub_path_prefixes_every_link(blog):
    blog.overrides["base_url"] = "https://example.com/blog/"
    blog.build()
    html = blog.read("posts/index.html")
    assert '<a href="/blog/2024/03/third/">Third</a>' in html
    assert 'href="/blog/css/theme.css"' in html
    assert 'href="/blog/posts/page/2/"' in html
    third = blog.read("2024/03/third/index.html")
    assert '<a href="/blog/2024/01/first/">the first</a>' in third
    # the files themselves do not move
    assert blog.exists("posts/index.html") and not blog.exists("blog/posts/index.html")
    assert "<loc>https://example.com/blog/about/</loc>" in blog.read("sitemap.xml")


def test_ugly_urls(blog):
    blog.overrides["build.pretty_urls"] = False
    blog.build()
    assert blog.exists("about.html")
    assert blog.exists("2024/01/first.html")
    assert blog.exists("posts/index.html")
    assert '<a href="/2024/03/third.html">Third</a>' in blog.read("posts/index.html")
    third = blog.read("2024/03/third.html")
    assert '<a href="/2024/01/first.html">the first</a>' in third


def test_static_files_from_theme_and_site(blog):
    blog.write("static/img/logo.svg", "<svg/>")
    blog.write("static/css/theme.css", "body { margin: 1px; }\n")
    blog.write("static/.nojekyll", "")
    report = blog.build()
    assert blog.read("img/logo.svg") == "<svg/>"
    # the site's file wins over the theme's
    assert blog.read("css/theme.css") == "body { margin: 1px; }\n"
    assert blog.exists(".nojekyll")
    assert report.assets_copied == 5
    assert "img/logo.svg" in report.output_paths


def test_bundle_resources_and_loose_files_are_copied(blog):
    blog.page(
        "posts/trip/index.md",
        "![Harbour](harbour.jpg)\n",
        title="Trip",
        date="2024-05-01",
    )
    blog.write("content/posts/trip/harbour.jpg", "jpeg")
    blog.write("content/posts/slides.pdf", "pdf")
    report = blog.build()
    assert blog.read("2024/05/trip/harbour.jpg") == "jpeg"
    assert blog.read("posts/slides.pdf") == "pdf"
    html = blog.read("2024/05/trip/index.html")
    assert '<img src="harbour.jpg" alt="Harbour"' in html
    assert "2024/05/trip/harbour.jpg" in report.output_paths
    blog.root.joinpath("content/posts/trip/harbour.jpg").unlink()
    report = blog.build()
    assert not blog.exists("2024/05/trip/harbour.jpg")
    assert report.removed_paths == ["2024/05/trip/harbour.jpg"]


def test_code_blocks_are_highlighted(blog):
    body = "```python\nprint('hi')\n```\n\n```\nplain\n```\n"
    blog.page("code.md", body, title="Code")
    blog.build()
    html = blog.read("code/index.html")
    assert '<div class="highlight' in html
    assert "<pre><code>plain\n</code></pre>" in html
    css = blog.read("css/highlight.css")
    assert ".highlight" in css


def test_highlighting_can_be_switched_off(blog):
    blog.configure("markdown:\n  highlight: false\n")
    blog.page("code.md", "```python\nprint('hi')\n```\n", title="Code")
    blog.build()
    assert '<code class="language-python">' in blog.read("code/index.html")
    assert not blog.exists("css/highlight.css")


def test_markdown_settings_are_applied(blog):
    blog.configure(
        "markdown:\n  smart: false\n  heading_ids: false\n  hard_wraps: true\n"
    )
    blog.page("m.md", '"Quotes"\nnext line\n\n## Heading\n', title="M")
    blog.build()
    html = blog.read("m/index.html")
    assert "&quot;Quotes&quot;<br" in html
    assert "<h2>Heading</h2>" in html


def test_unknown_markdown_extension_is_a_config_error(blog):
    blog.configure("markdown:\n  extensions: [tabels]\n")
    with pytest.raises(ConfigError, match="markdown.extensions: unknown.*'tables'"):
        blog.build()


def test_minify_and_fingerprint(blog):
    blog.overrides.update({"build.minify": True, "build.fingerprint": True})
    blog.build()
    html = blog.read("about/index.html")
    assert "\n\n" not in html
    names = [name for name in blog.outputs() if name.startswith("css/theme.")]
    assert len(names) == 1 and names[0] != "css/theme.css"
    assert f'href="/{names[0]}"' in html
    assert blog.read(names[0]) == "body{margin:0}"
    assert any(name.startswith("js/inkstone-search.") for name in blog.outputs())
    # fixed names stay fixed
    assert blog.exists("search-index.json") and blog.exists("robots.txt")


def test_asset_integrity_and_missing_assets(blog):
    blog.write(
        "templates/partials/footer.html",
        "<footer>{{ asset_integrity('css/theme.css') }}|{{ asset('css/nope.css') }}"
        "|{{ asset_integrity('nope.js') }}|</footer>\n",
    )
    report = blog.build()
    html = blog.read("about/index.html")
    assert "<footer>sha384-" in html
    assert "|/css/nope.css||</footer>" in html
    assert len(report.warnings) == 2
    assert "asset('css/nope.css')" in report.warnings[0]
    assert "(2 warnings)" in report.summary()


def test_site_templates_override_the_theme(blog):
    blog.write("templates/partials/footer.html", "<footer>site footer</footer>\n")
    blog.build()
    assert "<footer>site footer</footer>" in blog.read("about/index.html")
    assert "tiny footer" not in blog.read("posts/index.html")


def test_theme_params_and_site_params(blog):
    blog.configure("params:\n  footer: from the site\n")
    blog.build()
    assert "<footer>from the site</footer>" in blog.read("about/index.html")


@pytest.mark.parametrize(
    ("template", "source", "expected"),
    [
        ("posts/page.html", "posts/2024-01-10-first.md", "POSTS PAGE"),
        ("posts/section.html", "posts", "POSTS SECTION"),
        ("tags/term.html", "/tags/python/", "TAGS TERM"),
        ("tags/taxonomy.html", "/tags/", "TAGS TAXONOMY"),
    ],
)
def test_section_and_taxonomy_specific_templates(blog, template, source, expected):
    blog.write(f"templates/{template}", f"{expected} {{{{ page.title }}}}\n")
    builder = blog.builder()
    builder.build()
    page = builder.site.get_page(source)
    assert page.layout == template
    assert blog.read(page.output_path).startswith(expected)
    # everything else still uses the general template
    assert builder.site.get_page("about.md").layout == "page.html"
    assert builder.site.get_page("/categories/news/").layout == "term.html"


def test_template_from_front_matter(blog):
    blog.write("templates/landing.html", "LANDING {{ page.title }}\n")
    blog.page("promo.md", title="Promo", template="landing.html")
    blog.page("posts/_index.md", title="Posts", template="landing.html")
    builder = blog.builder()
    builder.build()
    assert blog.read("promo/index.html") == "LANDING Promo"
    assert blog.read("posts/index.html") == "LANDING Posts"
    promo = builder.site.get_page("promo.md")
    assert promo.template == "landing.html" and promo.layout == "landing.html"


def test_nested_sections_fall_back_to_the_parent_section_template(blog):
    blog.write("templates/docs/page.html", "DOCS {{ page.title }}\n")
    blog.page("docs/guide/steps.md", title="Steps")
    blog.page("docs/install.md", title="Install")
    blog.build()
    assert blog.read("docs/guide/steps/index.html") == "DOCS Steps"
    assert blog.read("docs/install/index.html") == "DOCS Install"


def test_theme_inheritance(blog):
    blog.write(
        "themes/child/theme.toml",
        'name = "child"\ninherit = "tiny"\n\n[params]\nfooter = "child footer"\n',
    )
    blog.write("themes/child/templates/404.html", "CHILD 404\n")
    blog.write("themes/child/static/css/child.css", "p { color: red; }\n")
    blog.configure("theme: child\n")
    builder = blog.builder()
    builder.build()
    assert [theme.name for theme in builder.themes] == ["child", "tiny"]
    assert blog.read("404.html") == "CHILD 404"
    # templates the child does not have come from the parent, with its params
    assert "<footer>child footer</footer>" in blog.read("about/index.html")
    assert blog.exists("css/child.css") and blog.exists("css/theme.css")


def test_unknown_theme_is_a_config_error(blog):
    blog.configure("theme: nowhere\n")
    with pytest.raises(ConfigError, match="theme 'nowhere' not found.*tiny"):
        blog.build()


def test_missing_page_template_is_a_build_error(blog):
    blog.root.joinpath("themes/tiny/templates/page.html").unlink()
    with pytest.raises(BuildError) as excinfo:
        blog.build()
    message = str(excinfo.value)
    assert "no template found for the page page" in message
    assert "tried: page.html" in message


def test_themes_without_list_templates_just_have_no_such_pages(blog):
    for name in ("taxonomy.html", "term.html", "404.html"):
        blog.root.joinpath("themes/tiny/templates", name).unlink()
    builder = blog.builder()
    report = builder.build()
    assert not blog.exists("tags/index.html")
    assert not blog.exists("tags/python/index.html")
    assert not blog.exists("404.html")
    assert blog.exists("about/index.html")
    assert report.pages_written == 8
    assert "/tags/" not in {page.url for page in builder.site.all_pages}
    assert "tags" not in blog.read("sitemap.xml")


def test_template_error_names_the_template_line_and_the_page(blog):
    blog.write(
        "templates/page.html",
        "{% extends 'base.html' %}\n{% block content %}\n{{ page.title | nofilter }}\n"
        "{% endblock %}\n",
    )
    with pytest.raises(BuildError) as excinfo:
        blog.build()
    error = excinfo.value
    assert "no filter named 'nofilter'" in error.message
    assert "while rendering content/" in error.message
    assert str(error.path).replace("\\", "/").endswith("templates/page.html")
    assert error.line == 3


def test_template_syntax_error_names_the_template(blog):
    blog.write("templates/partials/footer.html", "{% if %}\n")
    with pytest.raises(Exception) as excinfo:
        blog.build()
    assert "footer.html" in str(excinfo.value)
    assert hasattr(excinfo.value, "message")


def test_exception_inside_a_template_function_is_not_a_bare_traceback(blog):
    blog.write("templates/landing.html", "{{ page.params.count + 1 }}\n")
    blog.page("promo.md", title="Promo", template="landing.html", count="three")
    with pytest.raises(BuildError) as excinfo:
        blog.build()
    assert "content/promo.md" in str(excinfo.value)
    assert "landing.html" in str(excinfo.value)


def test_bad_front_matter_stops_the_build_with_the_file_name(blog):
    blog.write("content/posts/bad.md", "---\ndate: tomorrowish\n---\n")
    with pytest.raises(ContentError) as excinfo:
        blog.build()
    assert str(excinfo.value).startswith("content/posts/bad.md:2: bad date")


def test_duplicate_urls_stop_the_build(blog):
    blog.page("one.md", title="One", url="/same/")
    blog.page("two.md", title="Two", url="/same/")
    with pytest.raises(ContentError, match="duplicate URL: .*one.md.*two.md"):
        blog.build()


def test_page_colliding_with_a_generated_page_stops_the_build(blog):
    blog.page("tags.md", title="My tags")
    with pytest.raises(ContentError, match="duplicate URL.*generated taxonomy page"):
        blog.build()


def test_stale_outputs_are_removed_but_foreign_files_stay(blog):
    blog.build()
    keep = blog.output / "google-verification.html"
    keep.write_text("mine", encoding="utf-8")
    blog.root.joinpath("content/about.md").unlink()
    report = blog.build()
    assert not blog.exists("about/index.html")
    assert not (blog.output / "about").exists()
    assert keep.read_text(encoding="utf-8") == "mine"
    assert report.removed_paths == ["about/index.html"]
    assert report.files_removed == 1
    assert "1 removed" in report.summary()


def test_clean_removes_output_and_cache(blog):
    builder = blog.builder()
    builder.build()
    assert blog.output.is_dir() and (blog.root / ".inkstone-cache").is_dir()
    builder.clean()
    assert not blog.output.exists()
    assert not (blog.root / ".inkstone-cache").exists()
    assert (blog.root / "content" / "about.md").is_file()
    # and the same builder can build again afterwards
    assert builder.build().pages_written == 14


def test_clean_does_not_need_a_working_theme(blog):
    blog.build()
    blog.configure("theme: nowhere\nplugins: [not_installed_anywhere]\n")
    blog.builder().clean()
    assert not blog.output.exists()


def test_builder_can_be_reused(blog):
    builder = blog.builder()
    first = builder.build()
    blog.page("new.md", title="New")
    second = builder.build()
    assert first.pages_written == 14
    assert "new/index.html" in second.output_paths
    assert blog.exists("new/index.html")
    assert builder.report is second
    assert builder.site.get_page("new.md") is not None


def test_builder_reloads_a_changed_config(blog):
    builder = blog.builder()
    builder.build()
    blog.configure("title: Renamed Site\n")
    report = builder.build(changed=[str(blog.config_path)])
    assert builder.config.title == "Renamed Site"
    assert "<title>About | Renamed Site</title>" in blog.read("about/index.html")
    assert report.pages_written == 14


def test_reload_keeps_the_overrides_the_builder_was_made_with(blog):
    blog.page("posts/2024-04-01-draft.md", title="Draft", draft=True)
    blog.overrides["build.drafts"] = True
    builder = blog.builder()
    builder.build()
    blog.configure("title: Renamed Site\n")
    builder.build(changed=[blog.config_path])
    assert builder.config.build.drafts is True
    assert "Renamed Site" in blog.read("2024/04/draft/index.html")


def test_config_change_is_noticed_without_a_hint(blog):
    builder = blog.builder()
    builder.build()
    blog.configure("title: Renamed Site\n")
    # make sure the file looks different even on a coarse file system clock
    stamp = blog.config_path.stat().st_mtime_ns + 5_000_000_000
    os.utime(blog.config_path, ns=(stamp, stamp))
    builder.build()
    assert "<title>About | Renamed Site</title>" in blog.read("about/index.html")


def test_changed_hint_accepts_paths_and_change_sets(blog):
    from inkstone.server import ChangeSet

    builder = blog.builder()
    builder.build()
    path = blog.page("about.md", "Changed.\n", title="About")
    report = builder.build(changed=ChangeSet(modified=[path]))
    assert report.output_paths == ["about/index.html", "search-index.json"]
    report = builder.build(changed=[blog.root / "content" / "nothing.md"])
    assert report.output_paths == []


def test_worker_threads_give_the_same_output(blog):
    for index in range(12):
        name = f"posts/2023-01-{index + 1:02d}-n{index}.md"
        blog.page(name, f"Post {index}.\n", title=f"N{index}")
    blog.build()
    pages = [name for name in blog.outputs() if name.endswith(".html")]
    single = {name: blog.read(name) for name in pages}
    builder = blog.builder(incremental=False)
    builder.config.set("build.jobs", 4)
    assert builder.jobs == 4
    report = builder.build()
    assert report.pages_rendered == len(single)
    # every page went through its template again and came out the same
    assert report.pages_written == 0
    for name, html in single.items():
        assert blog.read(name) == html


def test_jobs_auto_is_at_least_one(blog):
    assert blog.builder().jobs >= 1


def test_search_index_and_generator_version(blog):
    blog.build()
    index = json.loads(blog.read("search-index.json"))
    assert index["version"] >= 1
    assert f"inkstone {__version__}" in blog.read("rss.xml")


def test_content_dir_can_be_missing(site):
    (site.root / "content").rmdir()
    report = site.build()
    assert site.exists("index.html")
    assert any("does not exist" in warning for warning in report.warnings)


def test_config_warnings_end_up_in_the_report(blog):
    blog.configure("titel: Oops\n")
    report = blog.build()
    assert report.warnings == ["unknown setting 'titel', did you mean 'title'?"]


def test_plugin_that_cannot_be_found_stops_the_build(blog):
    blog.configure("plugins: [does_not_exist_anywhere]\n")
    with pytest.raises(PluginError, match="plugin 'does_not_exist_anywhere' not found"):
        blog.build()
