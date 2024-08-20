from __future__ import annotations

import re

import pytest

from inkstone.content import Resource
from inkstone.errors import ContentError, PluginError
from inkstone.markdown import Markdown
from inkstone.plugins.builtin import shortcodes
from inkstone.plugins.builtin.shortcodes import Shortcodes
from inkstone.utils import log

from .helpers import make_config, make_page, make_site


@pytest.fixture
def plugin(config):
    return Shortcodes(config, {})


@pytest.fixture
def page():
    return make_page("A page", "/posts/a-page/", source_path="posts/a-page.md")


def render(plugin, page, text, **options):
    """What the builder does with a page: both hooks around the Markdown step."""
    source = plugin.page_markdown(page, text)
    html = Markdown(smart=True, **options).convert(source)
    return str(plugin.page_html(page, html))


def write_source(config, rel, text):
    path = config.content_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_text_without_shortcodes_is_returned_untouched(plugin, page):
    text = "Nothing to see, just {braces} and `code`.\n"
    assert plugin.page_markdown(page, text) is text
    assert plugin.page_html(page, "<p>x</p>") == "<p>x</p>"


def test_figure(plugin, page):
    html = render(
        plugin,
        page,
        '{{< figure src="/img/boat.jpg" alt="A <boat>" caption="At *dawn*" >}}',
    )
    assert html == (
        "<figure>\n"
        '<img src="/img/boat.jpg" alt="A &lt;boat&gt;" loading="lazy">\n'
        "<figcaption>At <em>dawn</em></figcaption>\n"
        "</figure>\n"
    )


def test_figure_positional_arguments_and_extras(plugin, page):
    html = render(
        plugin,
        page,
        '{{< figure a.png "Alt" class="wide" width=640 height=480 link="/big.png" '
        'loading="eager" >}}',
    )
    assert '<figure class="wide">' in html
    assert '<a href="/big.png"><img src="a.png" alt="Alt" width="640"' in html
    assert ' height="480" loading="eager"></a>' in html
    assert 'loading="eager"' in html
    assert "<figcaption>" not in html


def test_figure_caption_from_the_inner_text(plugin, page):
    html = render(plugin, page, "{{< figure src=a.png >}}Some `code`{{< /figure >}}")
    assert "<figcaption>Some <code>code</code></figcaption>" in html


def test_figure_resolves_bundle_resources(plugin):
    photo = Resource("photo.jpg", "/posts/trip/photo.jpg", "posts/trip/photo.jpg")
    page = make_page(
        "Trip", "/posts/trip/", source_path="posts/trip/index.md", resources=[photo]
    )
    html = render(plugin, page, '{{< figure src="photo.jpg" alt="" >}}')
    assert 'src="/posts/trip/photo.jpg"' in html
    assert 'src="other.jpg"' in render(plugin, page, "{{< figure src=other.jpg >}}")


def test_site_urls_get_the_base_path(tmp_path):
    config = make_config(tmp_path, base_url="https://example.com/blog/")
    plugin = Shortcodes(config, {})
    page = make_page("A", "/a/")
    text = "{{< figure src=/img/a.png >}} {{< button /about/ About >}}"
    html = render(plugin, page, text)
    assert 'src="/blog/img/a.png"' in html
    assert 'href="/blog/about/"' in html
    external = render(plugin, page, "{{< figure src=https://cdn.example/a.png >}}")
    assert 'src="https://cdn.example/a.png"' in external


@pytest.mark.parametrize(
    "tag, classes",
    [
        ("{{< note >}}", "note note--info"),
        ('{{< note type="info" >}}', "note note--info"),
        ("{{< note warning >}}", "note note--warning admonition warning"),
        ('{{< note type="tip" >}}', "note note--tip admonition tip"),
        ("{{< note CAUTION >}}", "note note--warning admonition warning"),
        ("{{< note hint >}}", "note note--tip admonition tip"),
    ],
)
def test_note_types(plugin, page, tag, classes):
    html = render(plugin, page, f"{tag}\nMind the *gap*.\n{{{{< /note >}}}}")
    assert html == (
        f'<div class="{classes}" role="note">\n<p>Mind the <em>gap</em>.</p>\n</div>\n'
    )


def test_note_title_and_markdown_body(plugin, page):
    text = '{{< note title="Careful **now**" >}}\n- one\n- two\n\nAfter.\n{{< /note >}}'
    html = render(plugin, page, text)
    assert '<p class="note__title">Careful <strong>now</strong></p>' in html
    assert "<li>one</li>" in html and "<p>After.</p>" in html
    assert "<p><div" not in html


def test_details(plugin, page):
    text = '{{< details summary="The `log`" >}}\nLong.\n{{< /details >}}'
    html = render(plugin, page, text)
    assert html == (
        "<details>\n<summary>The <code>log</code></summary>\n<p>Long.</p>\n</details>\n"
    )
    opened = render(plugin, page, "{{< details More open >}}x{{< /details >}}")
    assert opened.startswith("<details open>\n<summary>More</summary>")


@pytest.mark.parametrize(
    "given",
    [
        "SxdOUGdseq4",
        "https://www.youtube.com/watch?v=SxdOUGdseq4",
        "https://www.youtube.com/watch?list=PL1&v=SxdOUGdseq4&t=10",
        "https://youtu.be/SxdOUGdseq4",
        "https://www.youtube.com/embed/SxdOUGdseq4",
        "https://www.youtube-nocookie.com/embed/SxdOUGdseq4",
    ],
)
def test_youtube_uses_the_nocookie_host(plugin, page, given):
    html = render(plugin, page, f'{{{{< youtube id="{given}" title="A talk" >}}}}')
    assert html.startswith('<div class="video">\n<iframe ')
    assert 'src="https://www.youtube-nocookie.com/embed/SxdOUGdseq4"' in html
    assert 'title="A talk"' in html and 'loading="lazy"' in html
    assert " allowfullscreen>" in html
    assert "youtube.com/" not in html.replace("youtube-nocookie.com/", "")


def test_youtube_start_and_default_title(plugin, page):
    html = render(plugin, page, "{{< youtube SxdOUGdseq4 start=90 >}}")
    assert "embed/SxdOUGdseq4?start=90" in html
    assert 'title="YouTube video"' in html


def test_button(plugin, page):
    assert render(plugin, page, '{{< button href="/about/" text="About me" >}}') == (
        '<p><a class="button" href="/about/">About me</a></p>\n'
    )
    html = render(
        plugin,
        page,
        '{{< button href="https://example.org/" style="quiet" class="big" new_tab >}}'
        "Go **there**{{< /button >}}",
    )
    assert html == (
        '<p><a class="button button--quiet big" href="https://example.org/" '
        'target="_blank" rel="noopener">Go <strong>there</strong></a></p>\n'
    )


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("{{< kbd Ctrl C >}}", "<kbd>Ctrl</kbd>+<kbd>C</kbd>"),
        ('{{< kbd "Ctrl+Shift+P" >}}', "<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>"),
        ("{{< kbd Ctrl++ >}}", "<kbd>Ctrl</kbd>+<kbd>+</kbd>"),
        ("{{< kbd + >}}", "<kbd>+</kbd>"),
        ("{{< kbd Esc >}}", "<kbd>Esc</kbd>"),
        ('{{< kbd g g sep=" then " >}}', "<kbd>g</kbd> then <kbd>g</kbd>"),
        ('{{< kbd "<" >}}', "<kbd>&lt;</kbd>"),
        ("{{< kbd >}}Alt+F4{{< /kbd >}}", "<kbd>Alt</kbd>+<kbd>F4</kbd>"),
    ],
)
def test_kbd(plugin, page, tag, expected):
    html = render(plugin, page, f"Press {tag} now.")
    assert html == f"<p>Press {expected} now.</p>\n"


def test_inline_output_stays_inside_the_paragraph(plugin, page):
    html = render(plugin, page, "Save with {{< kbd Ctrl S >}}, *then* quit.")
    assert html == (
        "<p>Save with <kbd>Ctrl</kbd>+<kbd>S</kbd>, <em>then</em> quit.</p>\n"
    )


def test_block_output_is_lifted_out_of_the_paragraph(plugin, page):
    text = "Before.\n{{< figure src=a.png >}}\nAfter."
    html = render(plugin, page, text)
    assert html == (
        "<p>Before.</p>\n"
        '<figure>\n<img src="a.png" alt="" loading="lazy">\n</figure>\n'
        "<p>After.</p>\n"
    )


def test_block_output_with_hard_wraps_leaves_no_stray_breaks(plugin, page):
    text = "Before.\n{{< figure src=a.png >}}\nAfter."
    html = render(plugin, page, text, hard_wraps=True)
    assert "<br" not in html
    assert html.count("<p>") == 2


def test_block_output_in_list_items_and_quotes(plugin, page):
    text = "- {{< figure src=a.png >}}\n\n> {{< youtube SxdOUGdseq4 >}}"
    html = render(plugin, page, text)
    assert "<li><figure>" in html
    assert '<blockquote>\n<div class="video">' in html


def test_markdown_does_not_touch_shortcode_output(plugin, page):
    output = "<div>\n\n*not emphasis*\n\n    indented\n</div>"
    shortcodes.register("raw", lambda call: output)
    try:
        html = render(plugin, page, "{{< raw >}}")
    finally:
        shortcodes.unregister("raw")
    assert html == output + "\n"


def test_shortcodes_in_indented_code_are_shown_as_written(plugin, page):
    html = render(plugin, page, "Example:\n\n    {{< kbd Ctrl C >}}\n")
    assert "<pre><code>{{&lt; kbd Ctrl C &gt;}}\n</code></pre>" in html


def test_fenced_code_is_left_alone(plugin, page):
    html = render(plugin, page, "```\n{{< nosuchthing >}}\n```\n")
    assert "{{&lt; nosuchthing &gt;}}" in html


def test_shortcode_as_a_link_target_becomes_its_text(plugin, page):
    # not what kbd is for, but it must not leave a placeholder behind
    html = render(plugin, page, "[go]({{< kbd F5 >}})")
    assert html == '<p><a href="F5">go</a></p>\n'


def test_text_that_looks_like_a_placeholder_is_left_alone(plugin, page):
    # the private-use characters placeholders are made of, typed by hand
    stray = chr(0xE000) + chr(0xE019) + chr(0xE001)
    html = render(plugin, page, f"Odd {stray} text, {{{{< kbd K >}}}}.")
    assert html == f"<p>Odd {stray} text, <kbd>K</kbd>.</p>\n"


def test_shortcode_in_a_heading_keeps_the_id_and_toc_clean(plugin, page):
    converter = Markdown()
    source = plugin.page_markdown(page, "## Press {{< kbd F1 >}} for help")
    html = converter.convert(source)
    page.toc = converter.toc
    page.toc_html = converter.render_toc()
    html = plugin.page_html(page, html)
    assert html == '<h2 id="press-for-help">Press <kbd>F1</kbd> for help</h2>\n'
    assert page.toc[0].title == "Press F1 for help"
    assert "Press F1 for help</a>" in page.toc_html


def test_nested_shortcodes(plugin, page):
    text = (
        '{{< details summary="Keys" >}}\n'
        "{{< note warning >}}\nUse {{< kbd Ctrl Z >}} with care.\n{{< /note >}}\n"
        "{{< /details >}}"
    )
    html = render(plugin, page, text)
    assert html == (
        "<details>\n<summary>Keys</summary>\n"
        '<div class="note note--warning admonition warning" role="note">\n'
        "<p>Use <kbd>Ctrl</kbd>+<kbd>Z</kbd> with care.</p>\n"
        "</div>\n</details>\n"
    )


def test_registered_function_gets_a_call(plugin, page):
    seen = []

    def probe(call):
        seen.append(call)
        return f"<span>{call.get('who', 0, 'nobody')}</span>"

    plugin.register("probe", probe)
    html = render(plugin, page, 'Hi {{< probe Ada >}} and {{< probe who="Bob" x >}}.')
    assert html == "<p>Hi <span>Ada</span> and <span>Bob</span>.</p>\n"
    first, second = seen
    assert (first.name, first.args, first.kwargs) == ("probe", ["Ada"], {})
    assert second.kwargs == {"who": "Bob"} and second.args == ["x"]
    assert first.page is page and first.config is plugin.config
    assert first.inner is None and not first.paired and not first.markdown
    assert first.line == 1


def test_inner_is_raw_for_angle_form_and_html_for_percent_form(plugin, page):
    seen = {}

    def box(call):
        seen[call.markdown] = call.inner
        return f"<div>{call.inner}</div>"

    plugin.register("box", box)
    render(plugin, page, "{{< box >}}\n  some *text*\n{{< /box >}}")
    render(plugin, page, "{{% box %}}\n  some *text*\n{{% /box %}}")
    assert seen[False] == "some *text*"
    assert seen[True] == "<p>some <em>text</em></p>"


def test_text_shortcodes_go_into_the_markdown(plugin, page):
    plugin.register("today", lambda call: "**2024-05-03**", text=True)
    assert plugin.page_markdown(page, "On {{< today >}}.") == "On **2024-05-03**."
    assert render(plugin, page, "On {{< today >}}.") == (
        "<p>On <strong>2024-05-03</strong>.</p>\n"
    )


def test_module_level_register_is_a_decorator_too():
    @shortcodes.register("shout")
    def shout(call):
        return call.args[0].upper()

    try:
        assert "shout" in shortcodes.registered()
        assert shortcodes._registry["shout"].fn is shout
    finally:
        shortcodes.unregister("shout")
    assert "shout" not in shortcodes.registered()
    with pytest.raises(ValueError):
        shortcodes.register("not a name", shout)


def test_builtins_are_registered():
    shipped = "figure note youtube details ref include button kbd".split()
    assert set(shipped) <= set(shortcodes.registered())


def test_unknown_shortcode_names_file_and_line(config):
    body = "First line.\n\nSee {{< figrue src=a.png >}} here.\n"
    front_matter = "---\ntitle: Typo\ndate: 2024-05-03\n---\n"
    path = write_source(config, "posts/typo.md", front_matter + body)
    page = make_page("Typo", source_path="posts/typo.md", file_path=path, raw=body)
    with pytest.raises(ContentError) as caught:
        Shortcodes(config, {}).page_markdown(page, body)
    error = caught.value
    assert error.path == "content/posts/typo.md"
    assert error.line == 7
    assert str(error) == (
        "content/posts/typo.md:7: unknown shortcode 'figrue', did you mean 'figure'?"
    )


def test_syntax_errors_are_located_too(config):
    body = "\n\n\n{{< note >}}\ntext\n{{% /note %}}\n"
    path = write_source(config, "about.md", "+++\ntitle = 'About'\n+++\n" + body)
    page = make_page("About", source_path="about.md", file_path=path, raw=body)
    with pytest.raises(ContentError) as caught:
        Shortcodes(config, {}).page_markdown(page, body)
    assert (caught.value.path, caught.value.line) == ("content/about.md", 9)


def test_errors_without_a_source_file_keep_body_lines(plugin):
    page = make_page("Virtual", "/v/")
    with pytest.raises(ContentError) as caught:
        plugin.page_markdown(page, "a\n{{< nope >}}")
    assert caught.value.line == 2
    assert caught.value.path is None


@pytest.mark.parametrize(
    "text, message",
    [
        ("{{< figure >}}", "shortcode 'figure': 'src' is missing"),
        ("{{< note >}}", "needs a body"),
        ("{{< note type=loud >}}x{{< /note >}}", "unknown type 'loud'"),
        ("{{< details >}}", "needs a body"),
        ("{{< youtube >}}", "'id' is missing"),
        ('{{< youtube id="no good" >}}', "does not look like a video id"),
        ("{{< youtube SxdOUGdseq4 start=soon >}}", "start must be a number"),
        ("{{< button >}}", "'href' is missing"),
        ("{{< kbd >}}", "no keys given"),
        ("{{< ref >}}", "'path' is missing"),
        ("{{< include >}}", "'file' is missing"),
        ("{{< include nothing.md >}}", "cannot find 'nothing.md'"),
    ],
)
def test_bad_arguments_are_content_errors(plugin, page, text, message):
    with pytest.raises(ContentError) as caught:
        plugin.page_markdown(page, "line one\n" + text)
    assert message in caught.value.message
    assert caught.value.line == 2


def test_not_strict_leaves_unknown_shortcodes_and_warns(config, page, capsys):
    # the warning is given once per name, and the log remembers across tests
    log.reset()
    plugin = Shortcodes(config, {"strict": False})
    text = "A {{< mystery x=1 >}}, {{< mystery >}} and {{< kbd K >}}."
    assert render(plugin, page, text) == (
        "<p>A {{&lt; mystery x=1 &gt;}}, {{&lt; mystery &gt;}} and <kbd>K</kbd>.</p>\n"
    )
    assert capsys.readouterr().err.count("unknown shortcode 'mystery'") == 1


def test_settings_are_checked(config):
    with pytest.raises(PluginError, match=r"\[plugin.shortcodes\] strict"):
        Shortcodes(config, {"strict": "yes"})


class TestTemplates:
    @pytest.fixture
    def site_templates(self, config):
        directory = config.templates_path / "shortcodes"
        directory.mkdir(parents=True)
        return directory

    def test_a_template_adds_a_shortcode(self, config, page, site_templates):
        (site_templates / "badge.html").write_text(
            '<span class="badge badge--{{ kwargs.kind | default("plain") }}">'
            "{{ args[0] }}</span>",
            encoding="utf-8",
        )
        plugin = Shortcodes(config, {})
        html = render(plugin, page, 'New {{< badge "<b>" kind="hot" >}} thing.')
        assert html == (
            '<p>New <span class="badge badge--hot">&lt;b&gt;</span> thing.</p>\n'
        )

    def test_a_template_overrides_a_builtin(self, config, page, site_templates):
        (site_templates / "kbd.html").write_text(
            "<kbd class=key>{{ args | join(' ') }}</kbd>", encoding="utf-8"
        )
        plugin = Shortcodes(config, {})
        assert render(plugin, page, "{{< kbd Ctrl C >}}") == (
            "<p><kbd class=key>Ctrl C</kbd></p>\n"
        )

    def test_template_variables(self, config, site_templates):
        (site_templates / "dump.html").write_text(
            "<div>{{ name }}|{{ page.title }}|{{ site.title }}|{{ config.language }}"
            "|{{ args | length }}|{{ kwargs.a }}|{{ inner }}</div>",
            encoding="utf-8",
        )
        page = make_page("The <page>", "/p/")
        site = make_site(config, [page])
        plugin = Shortcodes(config, {})
        plugin.content_loaded(site)
        html = render(plugin, page, "{{% dump one two a=b %}}\n*in*\n{{% /dump %}}")
        assert html == (
            "<div>dump|The &lt;page&gt;|My Site|en|2|b|<p><em>in</em></p></div>\n"
        )

    def test_inner_of_the_angle_form_is_not_escaped(self, config, page, site_templates):
        (site_templates / "wrap.html").write_text(
            "<section>{{ inner }}</section>", encoding="utf-8"
        )
        plugin = Shortcodes(config, {})
        text = "{{< wrap >}}<b>bold</b> {{< kbd K >}}{{< /wrap >}}"
        html = render(plugin, page, text)
        assert html == "<section><b>bold</b> <kbd>K</kbd></section>\n"

    def test_template_errors_point_at_the_page(self, config, page, site_templates):
        (site_templates / "broken.html").write_text(
            "{{ args | nosuchfilter }}", encoding="utf-8"
        )
        plugin = Shortcodes(config, {})
        with pytest.raises(ContentError) as caught:
            plugin.page_markdown(page, "\n{{< broken >}}")
        assert caught.value.line == 2
        assert "nosuchfilter" in caught.value.message

    def test_new_templates_are_seen_next_time(self, config, page, site_templates):
        plugin = Shortcodes(config, {})
        with pytest.raises(ContentError):
            plugin.page_markdown(page, "{{< late >}}")
        (site_templates / "late.html").write_text("<i>late</i>", encoding="utf-8")
        plugin.content_loaded(make_site(config, [page]))
        assert render(plugin, page, "{{< late >}}") == "<p><i>late</i></p>\n"

    def test_template_names_are_suggested(self, config, page, site_templates):
        (site_templates / "callout.html").write_text("x", encoding="utf-8")
        plugin = Shortcodes(config, {})
        assert "callout" in plugin.names()
        with pytest.raises(ContentError, match="did you mean 'callout'"):
            plugin.page_markdown(page, "{{< calout >}}")

    def test_the_template_directory_is_a_setting(self, config, page):
        directory = config.templates_path / "sc"
        directory.mkdir(parents=True)
        (directory / "hi.html").write_text("<i>hi</i>", encoding="utf-8")
        plugin = Shortcodes(config, {"templates": "sc/"})
        assert render(plugin, page, "{{< hi >}}") == "<p><i>hi</i></p>\n"


class TestRef:
    @pytest.fixture
    def site(self, config):
        pages = [
            make_page("Hello", "/2024/05/hello/", source_path="posts/hello.md"),
            make_page("Other", "/2024/06/other/", source_path="posts/other.md"),
            make_page("About", "/about/", source_path="about.md"),
        ]
        return make_site(config, pages)

    @pytest.mark.parametrize(
        "tag, url",
        [
            ('{{< ref "about.md" >}}', "/about/"),
            ('{{< ref "posts/other.md" >}}', "/2024/06/other/"),
            ('{{< ref "other.md" >}}', "/2024/06/other/"),
            ('{{< ref "../about.md" >}}', "/about/"),
            ('{{< ref "/about/" >}}', "/about/"),
            ('{{< ref path="about" >}}', "/about/"),
            ('{{< ref "about.md#contact" >}}', "/about/#contact"),
            ('{{< ref "#top" >}}', "/2024/05/hello/#top"),
            ('{{< ref "about.md" absolute >}}', "https://example.com/about/"),
        ],
    )
    def test_ref_gives_the_url(self, config, site, tag, url):
        plugin = Shortcodes(config, {})
        plugin.content_loaded(site)
        page = site.get_page("posts/hello.md")
        assert plugin.page_markdown(page, f"[x]({tag})") == f"[x]({url})"

    def test_ref_to_a_missing_page_fails(self, config, site):
        plugin = Shortcodes(config, {})
        plugin.content_loaded(site)
        with pytest.raises(ContentError, match="no page found for 'nope.md'"):
            plugin.page_markdown(site.get_page("about.md"), '{{< ref "nope.md" >}}')

    def test_ref_honours_a_base_path(self, tmp_path):
        config = make_config(tmp_path, base_url="https://example.com/blog/")
        about = make_page("About", "/about/", source_path="about.md")
        site = make_site(config, [about])
        plugin = Shortcodes(config, {})
        plugin.content_loaded(site)
        page = site.get_page("about.md")
        assert plugin.page_markdown(page, '{{< ref "about.md" >}}') == "/blog/about/"


class TestInclude:
    @pytest.fixture
    def page(self, config):
        body = "Start.\n"
        path = write_source(config, "posts/host.md", "---\ntitle: Host\n---\n" + body)
        return make_page("Host", source_path="posts/host.md", file_path=path, raw=body)

    def test_include_next_to_the_page(self, config, page):
        part = "---\ntitle: Part\n---\nIncluded *text*.\n"
        write_source(config, "posts/part.md", part)
        plugin = Shortcodes(config, {})
        assert plugin.page_markdown(page, "A\n\n{{< include part.md >}}\n\nB") == (
            "A\n\nIncluded *text*.\n\nB"
        )

    def test_include_falls_back_to_content_and_site_root(self, config, page):
        write_source(config, "shared/note.md", "From content.\n")
        snippets = config.root / "snippets"
        snippets.mkdir()
        (snippets / "x.txt").write_text("From root.\n", encoding="utf-8")
        plugin = Shortcodes(config, {})

        def include(name):
            return plugin.page_markdown(page, f'{{{{< include "{name}" >}}}}')

        assert include("shared/note.md") == "From content."
        assert include("snippets/x.txt") == "From root."
        assert include("/snippets/x.txt") == "From root."
        assert include("../shared/note.md") == "From content."

    def test_shortcodes_in_included_markdown_are_expanded(self, config, page):
        write_source(config, "posts/keys.md", "Press {{< kbd Q >}}.\n")
        plugin = Shortcodes(config, {})
        assert render(plugin, page, "{{< include keys.md >}}") == (
            "<p>Press <kbd>Q</kbd>.</p>\n"
        )

    def test_include_as_code(self, config, page):
        write_source(config, "posts/hello.py", "print('hi')\n")
        plugin = Shortcodes(config, {})
        assert plugin.page_markdown(page, "{{< include hello.py code >}}") == (
            "```py\nprint('hi')\n```"
        )
        assert plugin.page_markdown(page, '{{< include hello.py code="python" >}}') == (
            "```python\nprint('hi')\n```"
        )

    def test_code_fence_is_longer_than_any_in_the_file(self, config, page):
        fenced = "---\na: 1\n---\n````\n```\nx\n```\n````\n"
        write_source(config, "posts/doc.md", fenced)
        plugin = Shortcodes(config, {})
        out = plugin.page_markdown(page, '{{< include doc.md code="markdown" >}}')
        assert out.startswith("`````markdown\n---\na: 1\n---\n")
        assert out.endswith("\n`````")

    @pytest.mark.parametrize(
        "lines, expected",
        [
            ("2-3", "two\nthree"),
            ("3-", "three\nfour"),
            ("-2", "one\ntwo"),
            ("4", "four"),
        ],
    )
    def test_include_a_range_of_lines(self, config, page, lines, expected):
        write_source(config, "posts/four.txt", "one\ntwo\nthree\nfour")
        plugin = Shortcodes(config, {})
        text = f"{{{{< include four.txt lines={lines} >}}}}"
        assert plugin.page_markdown(page, text) == expected

    @pytest.mark.parametrize("lines", ["x", "3-2", "0-1", "-"])
    def test_bad_line_ranges(self, config, page, lines):
        write_source(config, "posts/four.txt", "one\ntwo\nthree\nfour")
        with pytest.raises(ContentError, match="lines="):
            Shortcodes(config, {}).page_markdown(
                page, f'{{{{< include four.txt lines="{lines}" >}}}}'
            )

    def test_include_refuses_to_leave_the_site(self, config, page, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside") / "secret.md"
        outside.write_text("secret", encoding="utf-8")
        plugin = Shortcodes(config, {})
        for name in (outside.as_posix(), "../../../" + outside.name):
            with pytest.raises(ContentError, match="cannot find"):
                plugin.page_markdown(page, f'{{{{< include "{name}" >}}}}')

    def test_include_cycles_are_caught(self, config, page):
        write_source(config, "posts/a.md", "{{< include b.md >}}\n")
        write_source(config, "posts/b.md", "{{< include a.md >}}\n")
        with pytest.raises(ContentError, match="ends up including itself") as caught:
            Shortcodes(config, {}).page_markdown(page, "{{< include a.md >}}")
        assert caught.value.path == "content/posts/b.md"

    def test_a_page_cannot_include_itself(self, config, page):
        with pytest.raises(ContentError, match="including itself"):
            Shortcodes(config, {}).page_markdown(page, "{{< include host.md >}}")

    def test_errors_inside_an_included_file_name_that_file(self, config, page):
        write_source(config, "posts/bad.md", "ok\n\n{{< nonsense >}}\n")
        with pytest.raises(ContentError) as caught:
            Shortcodes(config, {}).page_markdown(page, "{{< include bad.md >}}")
        assert (caught.value.path, caught.value.line) == ("content/posts/bad.md", 3)

    def test_error_lines_count_the_included_front_matter(self, config, page):
        text = "---\ntitle: Part\n---\nok\n\n{{< nonsense >}}\n"
        write_source(config, "posts/bad.md", text)
        with pytest.raises(ContentError) as caught:
            Shortcodes(config, {}).page_markdown(page, "{{< include bad.md >}}")
        assert (caught.value.path, caught.value.line) == ("content/posts/bad.md", 6)

    def test_unreadable_front_matter_in_an_included_file(self, config, page):
        write_source(config, "posts/open.md", "---\ntitle: never closed\n")
        with pytest.raises(ContentError) as caught:
            Shortcodes(config, {}).page_markdown(page, "x\n{{< include open.md >}}")
        assert "'open.md': front matter is never closed" in caught.value.message
        assert caught.value.line == 2


class TestNoteForTheBuildCache:
    """Pages that take something from outside get a note at the end of their
    text, so that the build cache renders them again when that thing changes."""

    NOTE = re.compile(r"\n<!-- shortcodes:([0-9a-f]{12}) -->\Z")

    def source(self, config, name, body):
        path = write_source(config, f"{name}.md", f"---\ntitle: {name}\n---\n{body}")
        return make_page(name, source_path=f"{name}.md", file_path=path, raw=body)

    def note(self, config, page, others=()):
        plugin = Shortcodes(config, {})
        plugin.content_loaded(make_site(config, [page, *others]))
        found = self.NOTE.search(page.raw)
        return found.group(1) if found else None

    @pytest.fixture
    def badge(self, config):
        path = config.templates_path / "shortcodes" / "badge.html"
        path.parent.mkdir(parents=True)
        path.write_text("<b>one</b>", encoding="utf-8")
        return path

    def test_only_pages_with_outside_inputs_are_marked(self, config, badge):
        uses = self.source(config, "uses", "A {{< badge >}} here.\n")
        builtin = self.source(config, "builtin", "Press {{< kbd K >}}.\n")
        plain = self.source(config, "plain", "Just {{ braces }}.\n")
        assert self.note(config, uses, [builtin, plain]) is not None
        assert builtin.raw == "Press {{< kbd K >}}.\n"
        assert plain.raw == "Just {{ braces }}.\n"

    def test_shortcodes_in_code_do_not_count(self, config, badge):
        page = self.source(config, "doc", "```\n{{< badge >}}\n```\n")
        assert self.note(config, page) is None

    def test_the_note_follows_the_template(self, config, badge):
        page = self.source(config, "uses", "A {{< badge >}} here.\n")
        before = self.note(config, page)
        assert self.note(config, page) == before
        badge.write_text("<b>two</b>", encoding="utf-8")
        assert self.note(config, page) != before

    def test_the_note_follows_an_included_file(self, config):
        part = write_source(config, "part.md", "one\n")
        page = self.source(config, "uses", "{{< include part.md >}}\n")
        before = self.note(config, page)
        part.write_text("two\n", encoding="utf-8")
        changed = self.note(config, page)
        assert before and changed and before != changed
        part.unlink()
        assert self.note(config, page) not in (before, changed)

    def test_the_note_follows_the_page_a_ref_points_at(self, config):
        target = self.source(config, "target", "Here.\n")
        page = self.source(config, "uses", '[x]({{< ref "target.md#top" >}})\n')
        before = self.note(config, page, [target])
        target.url = "/somewhere/else/"
        assert self.note(config, page, [target]) != before

    def test_loading_twice_leaves_one_note(self, config, badge):
        page = self.source(config, "uses", "A {{< badge >}} here.\n")
        plugin = Shortcodes(config, {})
        site = make_site(config, [page])
        plugin.content_loaded(site)
        plugin.content_loaded(site)
        assert page.raw.count("<!-- shortcodes:") == 1

    def test_the_note_is_gone_before_markdown_sees_the_text(self, config, badge):
        page = self.source(config, "uses", "A {{< badge >}} here.\n")
        plugin = Shortcodes(config, {})
        plugin.content_loaded(make_site(config, [page]))
        assert render(plugin, page, page.raw) == "<p>A <b>one</b> here.</p>\n"
        # also when there turn out to be no shortcodes in what is left
        noted = "Text.\n<!-- shortcodes:0123abcd -->"
        assert plugin.page_markdown(page, noted) == "Text."

    def test_error_lines_are_not_thrown_off_by_the_note(self, config, badge):
        page = self.source(config, "uses", "A {{< badge >}}.\n\n{{< nonesuch >}}\n")
        plugin = Shortcodes(config, {})
        plugin.content_loaded(make_site(config, [page]))
        with pytest.raises(ContentError) as caught:
            plugin.page_markdown(page, page.raw)
        assert (caught.value.path, caught.value.line) == ("content/uses.md", 6)

    def test_pages_that_do_not_parse_are_left_for_the_renderer(self, config, badge):
        body = "{{< badge >}} and {{< /oops >}}\n"
        page = self.source(config, "broken", body)
        assert self.note(config, page) is None
        assert page.raw == body
