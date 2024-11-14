"""The Markdown documentation: links between pages, anchors, and a few
checks that the docs keep up with the things they describe."""

from __future__ import annotations

import re

import pytest

from . import layout

DOC_FILES = sorted(layout.DOCS.glob("*.md"))
EXPECTED_DOCS = {
    "getting-started.md",
    "content.md",
    "templates.md",
    "configuration.md",
    "markdown.md",
    "plugins.md",
    "search.md",
    "deploying.md",
    "internals.md",
    "faq.md",
}

LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Every key of the default configuration, as dotted paths. configuration.md
# has to mention each one; a new option without documentation fails here.
CONFIG_KEYS = [
    "title",
    "base_url",
    "description",
    "language",
    "timezone",
    "theme",
    "content_dir",
    "output_dir",
    "static_dir",
    "data_dir",
    "templates_dir",
    "themes_dir",
    "plugins_dir",
    "cache_dir",
    "ignore",
    "plugins",
    "author.name",
    "author.email",
    "author.url",
    "build.drafts",
    "build.future",
    "build.incremental",
    "build.minify",
    "build.fingerprint",
    "build.pretty_urls",
    "build.jobs",
    "markdown.extensions",
    "markdown.smart",
    "markdown.heading_ids",
    "markdown.highlight",
    "markdown.highlight_style",
    "markdown.hard_wraps",
    "permalinks",
    "taxonomies",
    "pagination.per_page",
    "pagination.path",
    "feeds.rss",
    "feeds.atom",
    "feeds.json",
    "feeds.limit",
    "feeds.sections",
    "feeds.full_content",
    "search.enabled",
    "search.fields",
    "sitemap.enabled",
    "sitemap.changefreq",
    "robots.enabled",
    "robots.disallow",
    "server.host",
    "server.port",
    "server.livereload",
    "server.open",
    "menus",
    "params",
    "plugin",
]

BUILTIN_PLUGINS = [
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

HOOKS = [
    "setup",
    "content_loaded",
    "page_markdown",
    "page_html",
    "generate_pages",
    "template_context",
    "page_output",
    "extra_files",
    "build_finished",
]

GLOBALS = [
    "url_for",
    "absolute_url",
    "asset",
    "asset_integrity",
    "get_page",
    "get_section",
    "get_data",
    "highlight_css",
]

FILTERS = [
    "markdown",
    "date",
    "slugify",
    "absolute_url",
    "relative_url",
    "strip_html",
    "truncate_html",
    "reading_time",
    "humanize_bytes",
]


def doc(name):
    return layout.read(layout.DOCS / name)


def prose_lines(text):
    """Lines outside fenced code blocks."""
    fence = None
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif line.strip() == fence:
                fence = None
            continue
        if fence is None:
            yield line


def github_slug(heading):
    """The anchor GitHub (and inkstone) gives a heading."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path):
    found = []
    for line in prose_lines(layout.read(path)):
        match = re.match(r"^#{1,6}\s+(.*?)\s*#*$", line)
        if not match:
            continue
        slug = github_slug(match.group(1))
        # repeated headings get -1, -2, ...
        candidate, n = slug, 0
        while candidate in found:
            n += 1
            candidate = f"{slug}-{n}"
        found.append(candidate)
    return set(found)


def links(path):
    found = []
    for line in prose_lines(layout.read(path)):
        # Link syntax quoted in a code span is an example, not a link. Code
        # spans used as link text ([`toc`](#toc)) have to survive, though.
        parts = line.split("`")
        for index in range(1, len(parts), 2):
            if "](" in parts[index]:
                parts[index] = ""
        found += LINK_RE.findall("`".join(parts))
    return found


def test_all_documents_exist():
    assert {path.name for path in DOC_FILES} == EXPECTED_DOCS


@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: p.name)
def test_document_shape(path):
    text = layout.read(path)
    lines = text.splitlines()
    assert lines[0].startswith("# "), "first line is not the title"
    headings = [line for line in prose_lines(text) if line.startswith("#")]
    assert sum(1 for h in headings if h.startswith("# ")) == 1, "more than one h1"
    assert len(headings) >= 5
    for previous, current in zip(headings, headings[1:]):
        jump = len(current.split()[0]) - len(previous.split()[0])
        assert jump <= 1, f"heading level skipped before {current!r}"
    assert len(lines) >= 120, "suspiciously short"


@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: p.name)
def test_code_fences_are_closed(path):
    fence = None
    for number, line in enumerate(layout.read(path).splitlines(), 1):
        match = FENCE_RE.match(line)
        if not match:
            continue
        if fence is None:
            fence = (match.group(1), number)
        elif line.strip() == fence[0]:
            fence = None
    assert fence is None, f"{path.name}:{fence[1]}: fence is never closed"


@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: p.name)
def test_internal_links_resolve(path):
    for target in links(path):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):
            continue
        file_part, _, fragment = target.partition("#")
        destination = (path.parent / file_part).resolve() if file_part else path
        assert destination.exists(), f"{path.name}: broken link {target}"
        if fragment and destination.suffix == ".md":
            assert fragment in anchors(
                destination
            ), f"{path.name}: no heading for #{fragment} in {destination.name}"


def test_readme_links_into_docs_resolve():
    readme = layout.ROOT / "README.md"
    targets = [t for t in links(readme) if t.startswith(("docs/", "examples/"))]
    assert len(targets) >= 6
    for target in targets:
        assert (layout.ROOT / target.partition("#")[0]).exists(), target


def test_every_document_is_reachable_from_getting_started():
    linked = {t.partition("#")[0] for t in links(layout.DOCS / "getting-started.md")}
    assert EXPECTED_DOCS - {"getting-started.md"} <= linked


def test_table_rows_have_the_same_number_of_cells():
    for path in DOC_FILES:
        rows = []
        for line in list(prose_lines(layout.read(path))) + [""]:
            if line.startswith("|"):
                cells = re.sub(r"`[^`]*`", "x", line.replace("\\|", "x"))
                rows.append(cells.strip().strip("|").count("|") + 1)
                continue
            if rows:
                assert len(set(rows)) == 1, f"{path.name}: ragged table near {rows}"
                assert len(rows) >= 3, f"{path.name}: table without body rows"
            rows = []


@pytest.mark.parametrize("key", CONFIG_KEYS)
def test_configuration_documents_every_key(key):
    text = doc("configuration.md")
    section, _, name = key.rpartition(".")
    if section:
        heading = f"## `[{section}]`"
        assert heading in text, f"no section for [{section}]"
        body = text.split(heading, 1)[1].split("\n## ", 1)[0]
        assert f"| `{name}` |" in body, f"{key} has no row under [{section}]"
    else:
        assert f"`{name}`" in text or f"`[{name}]`" in text, key


def test_configuration_defaults_match_the_contract():
    text = doc("configuration.md")
    for row in (
        '| `title` | `"My Site"` |',
        '| `base_url` | `"http://localhost:8000/"` |',
        '| `theme` | `"default"` |',
        '| `plugins` | `["shortcodes", "toc", "reading_time"]` |',
        "| `incremental` | `true` |",
        "| `pretty_urls` | `true` |",
        '| `highlight_style` | `"dusk"` |',
        "| `per_page` | `10` |",
        "| `limit` | `20` |",
        '| `sections` | `["posts"]` |',
        "| `port` | `8000` |",
        '| `cache_dir` | `".inkstone-cache"` |',
    ):
        assert row in text, row
    assert "INKSTONE_BUILD__DRAFTS" in text


@pytest.mark.parametrize("plugin", BUILTIN_PLUGINS)
def test_plugins_doc_covers_every_builtin(plugin):
    text = doc("plugins.md")
    assert f"\n### {plugin}\n" in text
    assert f"[`{plugin}`](#{plugin})" in text


@pytest.mark.parametrize("hook", HOOKS)
def test_plugins_doc_covers_every_hook(hook):
    assert f"| `{hook}(self, " in doc("plugins.md")


def test_plugin_example_in_docs_is_valid_python():
    blocks = re.findall(r"```python\n(.*?)```", doc("plugins.md"), re.S)
    assert len(blocks) >= 3
    for block in blocks:
        if block.lstrip().startswith("Page.virtual("):
            continue
        compile(block, "plugins.md", "exec")


@pytest.mark.parametrize("name", GLOBALS + FILTERS)
def test_templates_doc_covers_globals_and_filters(name):
    assert f"| `{name}" in doc("templates.md")


def test_templates_doc_matches_the_default_theme():
    text = doc("templates.md")
    for name in layout.own_templates("default"):
        if name == "partials/macros.html" or not name.startswith("partials/"):
            continue
        assert f"`{name}`" in text or name.rsplit("/", 1)[1] in text, name
    for block in layout.BLOCK_RE.findall(layout.source_of("default", "base.html")):
        assert f"| `{block}` |" in text, f"block {block} is not documented"
    params = re.findall(
        r"^([a-z_]+) = ", layout.read(layout.THEMES / "default" / "theme.toml"), re.M
    )
    documented = text.split("### Theme settings", 1)[1].split("\n## ", 1)[0]
    for param in params:
        if param in ("name", "description", "version", "license"):
            continue
        assert f"`{param}`" in documented or f"social.{param}`" in documented, param


def test_markdown_doc_lists_real_extensions():
    markdown = pytest.importorskip("inkstone.markdown")
    text = doc("markdown.md")
    for name in markdown.available_extensions():
        assert f"`{name}`" in text or f'"{name}"' in text, name
    listed = re.search(r"extensions = \[(.*?)\]", text, re.S).group(1)
    for name in re.findall(r'"(\w+)"', listed):
        assert name in markdown.available_extensions(), name


def test_markdown_examples_render():
    markdown = pytest.importorskip("inkstone.markdown")
    text = doc("markdown.md")
    examples = re.findall(r"^```markdown\n(.*?)^```$", text, re.S | re.M)
    examples += re.findall(r"^````markdown\n(.*?)^````$", text, re.S | re.M)
    assert len(examples) >= 15
    converter = markdown.Markdown(smart=True)
    for example in examples:
        html = converter.convert(example)
        assert html.strip(), example
    html = converter.convert("\n\n".join(examples))
    for tag in (
        "<table>",
        "<dl>",
        'class="footnotes"',
        'class="task-list"',
        'class="admonition note"',
        "<details",
        "<del>",
        "<blockquote>",
    ):
        assert tag in html, tag


def test_docs_do_not_mention_things_that_are_not_shipped():
    everything = "\n".join(layout.read(path) for path in DOC_FILES)
    for theme in re.findall(r'theme = "(\w+)"', everything):
        assert theme in layout.THEME_NAMES or theme == "mytheme", theme
    for path in re.findall(r"\]\(\.\./(examples/[^)#]+)\)", everything):
        assert (layout.ROOT / path).exists(), path
    assert "lorem ipsum" not in everything.lower()


@pytest.mark.parametrize("path", DOC_FILES, ids=lambda p: p.name)
def test_docs_are_tidy(path):
    layout.assert_tidy(path, path.name)
