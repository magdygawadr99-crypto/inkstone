from __future__ import annotations

import pytest

from inkstone.markdown import HtmlRenderer, Markdown, render

safe = Markdown(safe=True, heading_ids=False)


def test_html_blocks_are_escaped():
    assert safe.convert("<script>alert(1)</script>\n") == (
        "&lt;script&gt;alert(1)&lt;/script&gt;\n"
    )
    assert safe.convert("<div onclick=\"x()\">\n*text*\n</div>\n") == (
        "&lt;div onclick=&quot;x()&quot;&gt;\n*text*\n&lt;/div&gt;\n"
    )


def test_inline_html_is_escaped():
    assert safe.convert("a <b onclick=\"x()\">bold</b> <!-- c --> word\n") == (
        "<p>a &lt;b onclick=&quot;x()&quot;&gt;bold&lt;/b&gt; "
        "&lt;!-- c --&gt; word</p>\n"
    )


def test_markdown_inside_escaped_html_still_separates_blocks():
    html = safe.convert("<div>\n\n*emphasis*\n\n</div>\n")
    assert html == "&lt;div&gt;\n<p><em>emphasis</em></p>\n&lt;/div&gt;\n"


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "JaVaScRiPt:alert(1)",
        "vbscript:msgbox(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "data:image/svg+xml,xyz",
        "file:///etc/passwd",
        "&#106;avascript:alert(1)",
        "&#x6A;avascript:alert(1)",
        "javascript&colon;alert(1)",
    ],
)
def test_dangerous_link_targets_are_dropped(target):
    html = safe.convert(f"[click](<{target}>)\n")
    assert html == '<p><a href="">click</a></p>\n'


@pytest.mark.parametrize(
    "target",
    [
        "/relative/path",
        "https://example.com/?q=javascript:",
        "mailto:me@example.com",
        "#fragment",
        "page.html",
        "ftp://example.com/file",
        "javascript.html",
        "data/file.csv",
    ],
)
def test_ordinary_link_targets_are_kept(target):
    html = safe.convert(f"[click]({target})\n")
    assert f'href="{target}"' in html


@pytest.mark.parametrize(
    "source, href",
    [
        ("[a](<  javascript:alert(1)>)", "%20%20javascript:alert(1)"),
        ("[a](<java\tscript:alert(1)>)", "java%09script:alert(1)"),
        ("[a](\\javascript:alert(1))", "%5Cjavascript:alert(1)"),
    ],
)
def test_mangled_schemes_end_up_as_inert_relative_urls(source, href):
    # Percent-encoding leaves nothing a browser would take for a scheme.
    assert safe.convert(source) == f'<p><a href="{href}">a</a></p>\n'


def test_reference_links_and_autolinks_are_checked_too():
    assert safe.convert("[a][r]\n\n[r]: javascript:alert(1)\n") == (
        '<p><a href="">a</a></p>\n'
    )
    assert safe.convert("<javascript:alert(1)>\n") == (
        '<p><a href="">javascript:alert(1)</a></p>\n'
    )


def test_dangerous_image_sources_are_dropped():
    blocked = '<p><img src="" alt="x" /></p>\n'
    assert safe.convert("![x](javascript:alert(1))\n") == blocked
    assert safe.convert("![x](data:text/html,hi)\n") == blocked


@pytest.mark.parametrize("kind", ["png", "gif", "jpeg", "webp"])
def test_inline_image_data_is_allowed_for_images_only(kind):
    url = f"data:image/{kind};base64,AAAA"
    assert safe.convert(f"![x]({url})\n") == f'<p><img src="{url}" alt="x" /></p>\n'
    assert safe.convert(f"[x]({url})\n") == '<p><a href="">x</a></p>\n'


def test_link_titles_and_text_are_escaped_regardless():
    html = safe.convert('[<b>x</b>](/u "a \\" onmouseover=\\"evil")\n')
    assert html == (
        '<p><a href="/u" title="a &quot; onmouseover=&quot;evil">'
        "&lt;b&gt;x&lt;/b&gt;</a></p>\n"
    )


def test_event_handlers_and_styles_are_stripped_from_heading_attributes():
    html = safe.convert(
        '## T {#ok .cls onclick="evil()" ONLOAD=x style="x" data-n=1}\n'
    )
    assert html == '<h2 id="ok" class="cls" data-n="1">T</h2>\n'


def test_event_handlers_are_stripped_from_code_block_attributes():
    html = safe.convert('```py {#c onmouseover="evil()" title="fine"}\nx\n```\n')
    assert html == (
        '<pre id="c" title="fine"><code class="language-py">x\n</code></pre>\n'
    )


def test_attribute_values_cannot_break_out_of_their_quotes():
    html = Markdown().convert("## T {title='\"><script>'}\n")
    assert "<script>" not in html
    assert 'title="&quot;&gt;&lt;script&gt;"' in html


def test_admonition_titles_and_code_languages_are_always_escaped():
    html = render('!!! note "<img src=x onerror=alert(1)>"\n    body\n')
    assert "<img" not in html
    html = render('```"><script>\ncode\n```\n')
    assert "<script>" not in html


def test_toc_and_alt_text_are_always_escaped():
    md = Markdown()
    html = md.convert("# A `<script>` tag\n\n![<b>alt</b> \"q\"](x.png)\n")
    assert "<script>" not in md.render_toc()
    assert 'alt="alt &quot;q&quot;"' in html


def test_unsafe_mode_passes_everything_through():
    md = Markdown(heading_ids=False)
    assert md.convert("<script>alert(1)</script>\n") == "<script>alert(1)</script>\n"
    assert md.convert("[a](javascript:alert(1))\n") == (
        '<p><a href="javascript:alert(1)">a</a></p>\n'
    )
    assert md.convert("a <b>c</b>\n") == "<p>a <b>c</b></p>\n"


def test_safe_is_a_renderer_setting():
    doc = Markdown().parse("<b>x</b> [a](javascript:x)\n")
    assert HtmlRenderer(safe=True).render(doc) == (
        '<p>&lt;b&gt;x&lt;/b&gt; <a href="">a</a></p>\n'
    )
    assert HtmlRenderer().render(doc) == (
        '<p><b>x</b> <a href="javascript:x">a</a></p>\n'
    )


def test_safe_mode_keeps_the_rest_of_markdown_working():
    html = Markdown(safe=True).convert(
        "# Title\n\n*a* **b** `c<d>` [l](/x) www.example.com\n\n"
        "| t |\n|---|\n| <i>x</i> |\n\n- [x] done\n"
    )
    assert '<h1 id="title">Title</h1>' in html
    assert "<code>c&lt;d&gt;</code>" in html
    assert '<a href="http://www.example.com">' in html
    assert "<td>&lt;i&gt;x&lt;/i&gt;</td>" in html
    assert 'type="checkbox"' in html
