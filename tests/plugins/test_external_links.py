from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.plugins.builtin.external_links import ExternalLinks

from .helpers import make_config, make_page


def rewrite(config, html, **settings):
    return ExternalLinks(config, settings).page_html(make_page("P"), html)


@pytest.mark.parametrize(
    "href",
    [
        "https://other.example/page",
        "http://other.example/",
        "//cdn.other.example/file.js",
        "https://sub.example.com/",
        "HTTPS://OTHER.EXAMPLE/",
        "https://example.com.evil.test/",
        " https://other.example/ ",
    ],
)
def test_external(config, href):
    html = rewrite(config, f'<a href="{href}">x</a>')
    assert html == f'<a href="{href}" rel="noopener noreferrer">x</a>'


@pytest.mark.parametrize(
    "href",
    [
        "/about/",
        "../other/",
        "page.html",
        "#section",
        "?page=2",
        "https://example.com/about/",
        "http://example.com/",
        "https://www.example.com/",
        "//example.com/x",
        "https://EXAMPLE.com:443/",
        "mailto:me@other.example",
        "tel:+15551234",
        "javascript:void(0)",
        "",
        "http://[broken",
    ],
)
def test_not_external(config, href):
    html = f'<a href="{href}">x</a>'
    assert rewrite(config, html) == html


def test_links_without_href_are_ignored(config):
    html = '<a id="anchor">x</a><a name="old">y</a>'
    assert rewrite(config, html) == html


def test_existing_rel_values_are_kept(config):
    html = rewrite(config, '<a rel="nofollow me" href="https://o.example/">x</a>')
    assert html == (
        '<a rel="nofollow me noopener noreferrer" href="https://o.example/">x</a>'
    )
    complete = '<a href="https://o.example/" rel="noreferrer noopener">x</a>'
    assert rewrite(config, complete) == complete


def test_rel_setting(config):
    html = rewrite(config, '<a href="https://o.example/">x</a>', rel="nofollow")
    assert html == '<a href="https://o.example/" rel="nofollow">x</a>'
    untouched = '<a href="https://o.example/">x</a>'
    assert rewrite(config, untouched, rel="") == untouched


def test_target_blank(config):
    html = rewrite(config, '<a href="https://o.example/">x</a>', target_blank=True)
    assert html == (
        '<a href="https://o.example/" rel="noopener noreferrer" target="_blank">x</a>'
    )
    kept = rewrite(
        config, '<a target="_self" href="https://o.example/">x</a>', target_blank=True
    )
    assert 'target="_self"' in kept and "_blank" not in kept


def test_target_blank_always_gets_noopener(config):
    link = '<a href="https://o.example/">x</a>'
    html = rewrite(config, link, target_blank=True, rel="")
    assert html == '<a href="https://o.example/" rel="noopener" target="_blank">x</a>'


def test_class_setting(config):
    settings = {"class": "external out"}
    html = rewrite(config, '<a class="btn" href="https://o.example/">x</a>', **settings)
    assert 'class="btn external out"' in html
    html = rewrite(config, '<a href="https://o.example/">x</a>', **settings)
    assert html == (
        '<a href="https://o.example/" rel="noopener noreferrer" '
        'class="external out">x</a>'
    )


def test_more_internal_hosts(config):
    settings = {"internal": ["cdn.example.net", "https://old.example.org/blog/"]}
    html = (
        '<a href="https://cdn.example.net/a.zip">a</a>'
        '<a href="https://old.example.org/x/">b</a>'
        '<a href="https://new.example.org/">c</a>'
    )
    out = rewrite(config, html, **settings)
    assert out.count("rel=") == 1
    assert '<a href="https://new.example.org/" rel="noopener noreferrer">c</a>' in out


def test_code_is_not_touched(config):
    html = (
        '<pre><code>&lt;a href="https://o.example/"&gt;</code></pre>'
        '<code><a href="https://o.example/">in code</a></code>'
        '<p><a href="https://o.example/">real</a></p>'
    )
    out = rewrite(config, html)
    assert out.count("rel=") == 1
    assert out.endswith(
        '<p><a href="https://o.example/" rel="noopener noreferrer">real</a></p>'
    )


def test_the_rest_of_the_markup_is_byte_for_byte_the_same(config):
    html = (
        "<p>Text with <em>markup</em>, an <img src='a.png' alt=x> and\n"
        '<a  href="/local/"   class=plain >a local link</a>.</p>\n'
        '<a href="https://o.example/">out</a>\n'
    )
    out = rewrite(config, html)
    assert out == html.replace(
        '<a href="https://o.example/">',
        '<a href="https://o.example/" rel="noopener noreferrer">',
    )


def test_without_a_host_in_base_url_every_absolute_link_is_external(tmp_path):
    config = make_config(tmp_path, base_url="/")
    html = rewrite(config, '<a href="https://example.com/">x</a><a href="/y/">y</a>')
    assert html.count("rel=") == 1


def test_scope_content_leaves_the_document_alone(config):
    plugin = ExternalLinks(config, {})
    document = '<body><a href="https://o.example/">x</a></body>'
    assert plugin.page_output(make_page("P"), document) == document


def test_scope_page_works_on_the_whole_document(config):
    plugin = ExternalLinks(config, {"scope": "page"})
    page = make_page("P")
    fragment = '<a href="https://o.example/">x</a>'
    assert plugin.page_html(page, fragment) == fragment
    document = f"<html><body><nav>{fragment}</nav></body></html>"
    assert 'rel="noopener noreferrer"' in plugin.page_output(page, document)


def test_scope_page_skips_files_that_are_not_html(config):
    plugin = ExternalLinks(config, {"scope": "page"})
    feed = make_page("Feed", "/feed.xml")
    xml = '<link><a href="https://o.example/">x</a></link>'
    assert plugin.page_output(feed, xml) == xml


@pytest.mark.parametrize(
    "settings",
    [
        {"target_blank": "yes"},
        {"rel": ["noopener"]},
        {"scope": "site"},
        {"internal": 5},
    ],
)
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.external_links\]"):
        ExternalLinks(config, settings)
