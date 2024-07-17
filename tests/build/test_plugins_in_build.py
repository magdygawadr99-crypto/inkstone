from __future__ import annotations

import json
import sys

import pytest

from inkstone.errors import BuildError, PluginError

RECORDER = """
    import json

    from inkstone.content import Page
    from inkstone.plugins import Plugin


    class Recorder(Plugin):
        name = "recorder"

        def __init__(self, config, settings):
            super().__init__(config, settings)
            self.calls = []

        def setup(self, builder):
            self.calls.append("setup")
            self.builder = builder
            builder.env.filters["shout"] = lambda text: str(text).upper() + "!"
            builder.env.globals["answer"] = self.settings.get("answer", 0)

        def content_loaded(self, site):
            self.calls.append("content_loaded")
            for page in site.pages:
                page.badge = "seen:" + page.slug

        def page_markdown(self, page, text):
            self.calls.append("page_markdown:" + page.source_path)
            return text.replace("{{version}}", "1.2.3")

        def page_html(self, page, html):
            self.calls.append("page_html:" + page.source_path)
            page.shouted = page.title.upper()
            return html.replace("<p>", '<p class="x">')

        def generate_pages(self, site):
            self.calls.append("generate_pages")
            yield Page.virtual(
                "/archive/",
                title="Archive",
                template="archive.html",
                posts=site.pages.dated(),
            )
            yield Page.virtual("/old-about/", content="<html>moved</html>")
            yield Page.virtual("/feeds/all.xml", content="<feed/>")

        def template_context(self, page, context):
            context["extra"] = "ctx-" + page.kind

        def page_output(self, page, html):
            return html.replace("</body>", "<!-- recorder --></body>")

        def extra_files(self, site):
            self.calls.append("extra_files")
            yield "stats.json", json.dumps({"pages": len(site.pages)})
            yield "bin/blob.bin", b"\\x00\\x01"

        def build_finished(self, site, report):
            self.calls.append("build_finished:%d" % report.pages_written)
"""


@pytest.fixture
def plugged(blog):
    blog.write("plugins/recorder.py", RECORDER)
    blog.configure("plugins: [recorder]\nplugin:\n  recorder:\n    answer: 42\n")
    blog.write(
        "templates/archive.html",
        "{% extends 'base.html' %}{% block content %}"
        "{% for post in posts %}{{ post.title }},{% endfor %}"
        "{% endblock %}\n",
    )
    blog.write(
        "templates/partials/footer.html",
        "<footer>{{ extra }}|{{ answer }}|{{ 'hi' | shout }}"
        "|{{ page.badge }}|{{ page.shouted }}</footer>\n",
    )
    yield blog
    for name in [n for n in sys.modules if n.startswith("_inkstone_site_plugins.")]:
        del sys.modules[name]


def test_hooks_run_in_the_documented_order(plugged):
    builder = plugged.builder()
    builder.build()
    calls = builder.plugins.get("recorder").calls
    stages = [call.partition(":")[0] for call in calls]
    collapsed = [
        stage
        for index, stage in enumerate(stages)
        if stages[index - 1 : index] != [stage]
    ]
    assert collapsed[:2] == ["setup", "content_loaded"]
    assert collapsed[-3:] == ["generate_pages", "extra_files", "build_finished"]
    assert set(collapsed[2:-3]) == {"page_markdown", "page_html"}
    assert stages.index("page_html") > stages.index("page_markdown")
    assert calls[-1] == "build_finished:17"


def test_setup_sees_the_builder_and_registers_filters_and_globals(plugged):
    builder = plugged.builder()
    builder.build()
    plugin = builder.plugins.get("recorder")
    assert plugin.builder is builder
    assert plugin.settings == {"answer": 42}
    html = plugged.read("about/index.html")
    assert "<footer>ctx-page|42|HI!|seen:about|ABOUT</footer>" in html


def test_markdown_and_html_hooks_transform_the_content(plugged):
    plugged.page("version.md", "This is {{version}}.\n", title="Version")
    plugged.build()
    assert '<p class="x">This is 1.2.3.</p>' in plugged.read("version/index.html")
    # summaries are made from the HTML the plugins returned
    assert '<p class="x">The second post.</p>' in plugged.read("posts/index.html")


def test_page_output_hook_sees_the_whole_document(plugged):
    plugged.build()
    html = plugged.read("about/index.html")
    assert html.rstrip().endswith("<!-- recorder --></body>\n</html>")
    assert "<!-- recorder -->" in plugged.read("posts/index.html")


def test_generated_pages_with_and_without_a_template(plugged):
    builder = plugged.builder()
    builder.build()
    archive = plugged.read("archive/index.html")
    assert "Third,Second,First," in archive
    assert "<title>Archive | Test Site</title>" in archive
    assert "ctx-virtual" in archive
    # no template: written exactly as given, no hooks, no theme
    assert plugged.read("old-about/index.html") == "<html>moved</html>"
    assert plugged.read("feeds/all.xml") == "<feed/>"
    page = builder.site.get_page("/archive/")
    assert page.layout == "archive.html"
    assert page.site is builder.site
    assert page not in builder.site.pages


def test_virtual_pages_stay_out_of_sitemap_and_search(plugged):
    plugged.build()
    sitemap = plugged.read("sitemap.xml")
    assert "/archive/" not in sitemap and "old-about" not in sitemap
    index = plugged.read("search-index.json")
    assert "/archive/" not in index


def test_extra_files_are_written_and_tracked(plugged):
    report = plugged.build()
    assert json.loads(plugged.read("stats.json")) == {"pages": 4}
    assert (plugged.output / "bin/blob.bin").read_bytes() == b"\x00\x01"
    assert "stats.json" in report.output_paths
    plugged.configure("plugins: []\n")
    plugged.write("templates/partials/footer.html", "<footer></footer>\n")
    report = plugged.build()
    assert not plugged.exists("stats.json")
    assert not plugged.exists("archive/index.html")
    gone = {"stats.json", "bin/blob.bin", "archive/index.html"}
    assert gone <= set(report.removed_paths)


def test_cached_pages_keep_what_plugins_attached(plugged):
    builder = plugged.builder()
    builder.build()
    first_calls = list(builder.plugins.get("recorder").calls)
    assert sum(call.startswith("page_html:") for call in first_calls) == 6

    again = plugged.builder()
    report = again.build()
    calls = again.plugins.get("recorder").calls
    # nothing changed, so no page went through the Markdown hooks...
    assert not any(call.startswith("page_") for call in calls)
    assert report.pages_written == 0
    # ...and still has what the hooks left on it last time
    about = again.site.get_page("about.md")
    assert about.shouted == "ABOUT"
    assert about.badge == "seen:about"
    assert 'class="x"' in about.content


def test_only_the_edited_page_goes_through_the_hooks_again(plugged):
    plugged.build()
    plugged.page("about.md", "About **me**, edited.\n", title="About")
    builder = plugged.builder()
    builder.build()
    calls = [c for c in builder.plugins.get("recorder").calls if c.startswith("page_")]
    assert calls == ["page_markdown:about.md", "page_html:about.md"]


def test_editing_a_plugin_invalidates_everything(plugged):
    plugged.build()
    path = plugged.root / "plugins/recorder.py"
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace('class="x"', 'class="changed"'), encoding="utf-8")
    report = plugged.build()
    # every page with a template is rendered again; the ones without a
    # paragraph in them come out the same and are not written
    assert report.pages_rendered == 15
    assert 0 < report.pages_written < 15
    assert 'class="changed"' in plugged.read("about/index.html")


def test_long_running_builder_reloads_changed_plugins(plugged):
    builder = plugged.builder()
    builder.build()
    old_plugin = builder.plugins.get("recorder")
    path = plugged.root / "plugins/recorder.py"
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace('class="x"', 'class="reloaded"'), encoding="utf-8")
    builder.build(changed=[path])
    assert builder.plugins.get("recorder") is not old_plugin
    assert 'class="reloaded"' in plugged.read("about/index.html")


def test_plugin_error_in_a_page_hook_names_plugin_hook_and_file(blog):
    blog.write(
        "plugins/broken.py",
        """
        from inkstone.plugins import Plugin


        class Broken(Plugin):
            name = "broken"

            def page_html(self, page, html):
                if page.slug == "about":
                    raise ZeroDivisionError("bad maths")
                return html
        """,
    )
    blog.configure("plugins: [broken]\n")
    with pytest.raises(PluginError) as excinfo:
        blog.build()
    error = excinfo.value
    assert "plugin 'broken' failed in page_html()" in error.message
    assert "ZeroDivisionError: bad maths" in error.message
    assert str(error).startswith("content/about.md: ")
    del sys.modules["_inkstone_site_plugins.broken"]


def test_plugin_error_while_rendering_templates_names_the_page(blog):
    blog.write(
        "plugins/ctx.py",
        """
        from inkstone.plugins import Plugin


        class Ctx(Plugin):
            name = "ctx"

            def template_context(self, page, context):
                if page.kind == "section":
                    raise RuntimeError("no context for you")
        """,
    )
    blog.configure("plugins: [ctx]\n")
    with pytest.raises(PluginError) as excinfo:
        blog.build()
    assert "'ctx' failed in template_context()" in excinfo.value.message
    assert "content/posts/_index.md" in str(excinfo.value)
    del sys.modules["_inkstone_site_plugins.ctx"]


@pytest.mark.parametrize(
    ("hook", "body", "message"),
    [
        ("generate_pages", "return ['not a page']", "has to return Page objects"),
        ("extra_files", "return ['just-a-name.txt']", "expected (output_path, text"),
        ("extra_files", "return [('a.txt', 3)]", "expected (output_path, text"),
        ("extra_files", "return [('../x.txt', 'x')]", "outside the output directory"),
    ],
)
def test_wrong_return_values_are_build_errors(blog, hook, body, message):
    blog.write(
        "plugins/wrong.py",
        f"""
        from inkstone.plugins import Plugin


        class Wrong(Plugin):
            name = "wrong"

            def {hook}(self, site):
                {body}
        """,
    )
    blog.configure("plugins: [wrong]\n")
    with pytest.raises(BuildError) as excinfo:
        blog.build()
    assert message in excinfo.value.message
    assert not (blog.root / "x.txt").exists()
    del sys.modules["_inkstone_site_plugins.wrong"]


def test_plugins_can_change_pages_before_lists_are_made(blog):
    blog.write(
        "plugins/retag.py",
        """
        from inkstone.plugins import Plugin


        class Retag(Plugin):
            name = "retag"

            def content_loaded(self, site):
                for page in site.pages:
                    if page.section is not None:
                        page.tags = ["everything"]
        """,
    )
    blog.configure("plugins: [retag]\n")
    blog.build()
    assert blog.exists("tags/everything/index.html")
    assert not blog.exists("tags/python/index.html")
    assert "(3)" in blog.read("tags/index.html")
    del sys.modules["_inkstone_site_plugins.retag"]


def test_build_without_the_builtin_plugin_package(blog, monkeypatch):
    from inkstone.plugins import manager

    monkeypatch.setattr(manager, "BUILTIN_PACKAGE", "inkstone.plugins.not_there")
    assert blog.build().pages_written == 14
    blog.configure("plugins: [toc]\n")
    with pytest.raises(PluginError, match="built-in plugin 'toc' is not available"):
        blog.build()
