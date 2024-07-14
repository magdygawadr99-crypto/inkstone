from __future__ import annotations

import threading

import pytest

from inkstone.build.markdown import (
    MarkdownRenderer,
    make_highlighter,
    make_markdown,
    markdown_link_targets,
    resolve_source,
    split_target,
)
from inkstone.content import load_site
from inkstone.errors import ConfigError
from inkstone.markdown import Markdown, TocEntry


@pytest.fixture
def linked(site):
    site.page("about.md", title="About")
    site.page("posts/2024-01-10-first.md", title="First")
    site.page("posts/trip/index.md", title="Trip", date="2024-05-01")
    site.page("docs/guide/setup.md", title="Setup")
    site.page("docs/_index.md", title="Docs")
    config = site.config()
    renderer = MarkdownRenderer(config)
    renderer.site = load_site(config)
    return renderer


def render(renderer, text, source):
    page = renderer.site.get_page(source)
    return renderer.render(text, page).html


def test_render_returns_html_and_toc(site):
    renderer = MarkdownRenderer(site.config())
    rendered = renderer.render("# Title\n\nText.\n\n## Part\n")
    assert rendered.html.startswith('<h1 id="title">Title</h1>')
    assert [entry.title for entry in rendered.toc] == ["Title"]
    assert isinstance(rendered.toc[0], TocEntry)
    assert rendered.toc[0].children[0].id == "part"
    assert '<a href="#part">Part</a>' in rendered.toc_html
    assert renderer.render("No headings.\n").toc_html == ""


def test_render_inline(site):
    renderer = MarkdownRenderer(site.config())
    assert renderer.render_inline("Some *emphasis*") == "Some <em>emphasis</em>"


@pytest.mark.parametrize(
    ("link", "source", "expected"),
    [
        ("about.md", "posts/2024-01-10-first.md", None),
        ("../about.md", "posts/2024-01-10-first.md", "/about/"),
        ("/about.md", "docs/guide/setup.md", "/about/"),
        ("posts/2024-01-10-first.md", "about.md", "/2024/01/first/"),
        ("./posts/2024-01-10-first.md", "about.md", "/2024/01/first/"),
        ("posts/trip/index.md", "about.md", "/2024/05/trip/"),
        ("../../posts/trip/index.md", "docs/guide/setup.md", "/2024/05/trip/"),
        ("docs/_index.md", "about.md", "/docs/"),
        ("docs/guide/setup.md#step-2", "about.md", "/docs/guide/setup/#step-2"),
        ("docs/guide/setup.md?x=1#y", "about.md", "/docs/guide/setup/?x=1#y"),
        ("setup.md", "docs/guide/setup.md", "/docs/guide/setup/"),
    ],
)
def test_links_between_content_files(linked, link, source, expected):
    html = render(linked, f"[text]({link})", source)
    wanted = expected if expected is not None else link
    assert html == f'<p><a href="{wanted}">text</a></p>\n'


@pytest.mark.parametrize(
    "link",
    [
        "https://example.org/readme.md",
        "//cdn.example/readme.md",
        "mailto:me@example.com",
        "#section",
        "/about/",
        "notes.txt",
        "../../../outside.md",
        "missing.md",
    ],
)
def test_other_links_are_left_alone(linked, link):
    html = render(linked, f"[text]({link})", "about.md")
    assert f'href="{link}"' in html


def test_reference_style_links_and_images(linked):
    text = "See [the post][p] and ![pic](about.md).\n\n[p]: posts/2024-01-10-first.md\n"
    html = render(linked, text, "about.md")
    assert '<a href="/2024/01/first/">the post</a>' in html
    # only links are rewritten; an image of a Markdown file is nobody's intent
    assert '<img src="about.md"' in html


def test_links_get_the_base_path(site):
    site.page("about.md", title="About")
    site.page("other.md", title="Other")
    config = site.config()
    renderer = MarkdownRenderer(config, url_for=lambda url: "/blog" + url)
    renderer.site = load_site(config)
    html = renderer.render("[a](about.md)", renderer.site.get_page("other.md")).html
    assert 'href="/blog/about/"' in html


def test_links_are_not_touched_without_a_page(linked):
    assert 'href="about.md"' in linked.render("[a](about.md)").html


def test_unresolved_link_is_reported_once(linked, capsys):
    render(linked, "[a](missing.md) [b](missing.md)", "about.md")
    render(linked, "[a](missing.md)", "about.md")
    err = capsys.readouterr().err
    assert err.count("about.md: link to missing.md") == 1


def test_link_signature_follows_the_targets(linked):
    page = linked.site.get_page("about.md")
    page.raw = "[a](posts/2024-01-10-first.md) and [b](missing.md#x) and [c](/about/)\n"
    assert linked.link_signature(page) == [
        ("missing.md", ""),
        ("posts/2024-01-10-first.md", "/2024/01/first/"),
    ]
    linked.site.get_page("posts/2024-01-10-first.md").url = "/moved/"
    assert ("posts/2024-01-10-first.md", "/moved/") in linked.link_signature(page)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[a](b.md)", ["b.md"]),
        ("[a](../x/b.md#frag) and [c](d.markdown)", ["../x/b.md", "d.markdown"]),
        ("[a]( <b c.md> )", []),
        ("[ref]: other.md\n", ["other.md"]),
        ("  [ref]: <other.md> 'title'\n", ["other.md"]),
        ("[a](b.html) [c](https://x/y.mdx)", []),
        ("plain text about readme.md", []),
        ("[a](b.md) [again](b.md)", ["b.md"]),
    ],
)
def test_markdown_link_targets(raw, expected):
    assert markdown_link_targets(raw) == expected


@pytest.mark.parametrize(
    ("target", "source", "expected"),
    [
        ("b.md", "a.md", "b.md"),
        ("b.md", "posts/a.md", "posts/b.md"),
        ("../b.md", "posts/a.md", "b.md"),
        ("/b.md", "posts/deep/a.md", "b.md"),
        ("./x/../b.md", "posts/a.md", "posts/b.md"),
        ("../../b.md", "posts/a.md", None),
        ("..", "a.md", None),
    ],
)
def test_resolve_source(target, source, expected):
    assert resolve_source(target, source) == expected


@pytest.mark.parametrize(
    ("dest", "expected"),
    [
        ("a.md", ("a.md", "")),
        ("a.md#x", ("a.md", "#x")),
        ("a.md?q=1#x", ("a.md", "?q=1#x")),
        ("#x", ("", "#x")),
    ],
)
def test_split_target(dest, expected):
    assert split_target(dest) == expected


def test_highlighter(site):
    highlight = make_highlighter(site.config())
    html = highlight("x = 1\n", "python")
    assert html.startswith('<div class="highlight')
    assert highlight("plain\n", None) is None
    assert highlight("plain\n", "") is None
    # an unknown language is still wrapped, just not coloured
    assert "no-such-language" not in highlight("text\n", "no-such-language")


def test_highlighter_passes_fence_attributes_on(site):
    highlight = make_highlighter(site.config())
    attrs = {"linenos": True, "linenostart": "5"}
    numbered = highlight("a\nb\n", "python", attrs=attrs)
    assert "5" in numbered and "6" in numbered
    assert numbered != highlight("a\nb\n", "python")
    marked = highlight("a\nb\n", "python", attrs={"hl_lines": "2"})
    assert marked != highlight("a\nb\n", "python")
    titled = highlight("a\n", "python", attrs={"title": "example.py"})
    assert "example.py" in titled
    unnumbered = highlight("a\n", "python", attrs={"linenos": "false"})
    assert unnumbered == highlight("a\n", "python")


def test_highlighter_survives_bad_attributes(site, capsys):
    highlight = make_highlighter(site.config())
    assert highlight("a\n", "python", attrs={"hl_lines": "x-y"}) is None
    assert "not highlighted" in capsys.readouterr().err
    assert highlight("a\n", "python", attrs={"linenostart": "many"}) is not None


def test_no_highlighter_when_switched_off(site):
    site.configure("markdown:\n  highlight: false\n")
    config = site.config()
    assert make_highlighter(config) is None
    markdown = make_markdown(config)
    assert markdown.highlight is None
    assert '<code class="language-python">' in markdown.convert("```python\nx\n```\n")


def test_make_markdown_applies_the_settings(site):
    site.configure(
        "markdown:\n  extensions: [tables]\n  smart: false\n  heading_ids: false\n"
    )
    markdown = make_markdown(site.config())
    assert isinstance(markdown, Markdown)
    assert markdown.extension_names == ["tables"]
    assert markdown.smart is False
    assert markdown.convert("## T\n") == "<h2>T</h2>\n"
    assert "~~x~~" in markdown.convert("~~x~~\n")


def test_empty_extension_list_means_the_default_set(site):
    markdown = make_markdown(site.config())
    assert "tables" in markdown.extension_names
    assert "smart" in markdown.extension_names


def test_unknown_extension_is_a_config_error(site):
    site.configure("markdown:\n  extensions: [footnote]\n")
    with pytest.raises(ConfigError) as excinfo:
        MarkdownRenderer(site.config())
    assert "markdown.extensions" in excinfo.value.message
    assert "'footnotes'" in excinfo.value.message


def test_every_thread_gets_its_own_converter(site):
    renderer = MarkdownRenderer(site.config())
    mine = renderer.converter()
    assert renderer.converter() is mine
    seen = []
    thread = threading.Thread(target=lambda: seen.append(renderer.converter()))
    thread.start()
    thread.join()
    assert seen[0] is not mine
