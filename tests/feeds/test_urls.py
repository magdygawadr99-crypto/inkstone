from __future__ import annotations

import pytest

from inkstone.feeds import absolutize_html
from inkstone.feeds.urls import absolutize, has_scheme, is_absolute, to_uri

BASE = "https://example.com/blog/post/"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/about/", "https://example.com/about/"),
        ("img/a.png", "https://example.com/blog/post/img/a.png"),
        ("./a.png", "https://example.com/blog/post/a.png"),
        ("../other/", "https://example.com/blog/other/"),
        ("../../../too/far", "https://example.com/too/far"),
        ("#fn1", "https://example.com/blog/post/#fn1"),
        ("?page=2", "https://example.com/blog/post/?page=2"),
        ("//cdn.example.net/x.js", "https://cdn.example.net/x.js"),
        ("https://other.example/x", "https://other.example/x"),
        ("http://other.example/x", "http://other.example/x"),
        ("mailto:ada@example.com", "mailto:ada@example.com"),
        ("tel:+15551234", "tel:+15551234"),
        ("data:image/png;base64,AAAA", "data:image/png;base64,AAAA"),
        ("javascript:void(0)", "javascript:void(0)"),
        ("  /padded/  ", "https://example.com/padded/"),
        ("", ""),
        ("   ", ""),
        ("/a b/ü.png", "https://example.com/a b/ü.png"),
    ],
)
def test_absolutize(url, expected):
    assert absolutize(url, BASE) == expected


def test_absolutize_against_a_page_rather_than_a_directory():
    assert (
        absolutize("a.png", "https://example.com/post.html")
        == "https://example.com/a.png"
    )


def test_absolutize_gives_up_on_urls_it_cannot_parse():
    assert absolutize("http://[broken", BASE) == "http://[broken"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ('<a href="/about/">x</a>', '<a href="https://example.com/about/">x</a>'),
        ("<a href='/about/'>x</a>", '<a href="https://example.com/about/">x</a>'),
        ("<a href=/about/>x</a>", '<a href="https://example.com/about/">x</a>'),
        ('<A HREF="/about/">x</A>', '<A HREF="https://example.com/about/">x</A>'),
        ('<a href = "/about/">x</a>', '<a href = "https://example.com/about/">x</a>'),
        (
            '<a class="b" href="up.html" title="t">x</a>',
            '<a class="b" href="https://example.com/blog/post/up.html" title="t">x</a>',
        ),
        ('<img src="a.png">', '<img src="https://example.com/blog/post/a.png">'),
        ('<img src="a.png"/>', '<img src="https://example.com/blog/post/a.png"/>'),
        (
            '<video src="v.mp4" poster="/p.jpg">',
            f'<video src="{BASE}v.mp4" poster="https://example.com/p.jpg">',
        ),
        (
            '<a href="/a"><img src="/b.png"></a>',
            '<a href="https://example.com/a"><img src="https://example.com/b.png"></a>',
        ),
        ('<a href="#fn1">1</a>', '<a href="https://example.com/blog/post/#fn1">1</a>'),
        (
            '<a title="use href=/x or src=/y" href="/real">x</a>',
            '<a title="use href=/x or src=/y" href="https://example.com/real">x</a>',
        ),
        (
            '<a href="/s?a=1&amp;b=2">x</a>',
            '<a href="https://example.com/s?a=1&amp;b=2">x</a>',
        ),
    ],
)
def test_relative_urls_in_html_are_made_absolute(html, expected):
    assert absolutize_html(html, BASE) == expected


@pytest.mark.parametrize(
    "html",
    [
        '<a href="https://other.example/x">x</a>',
        '<a href="mailto:ada@example.com">mail</a>',
        '<img src="data:image/gif;base64,R0lGODlh">',
        '<a href="">empty</a>',
        '<img data-src="lazy.png">',
        '<a title="href=/not/an/attribute">x</a>',
        "<p>Write href=\"/x\" or src='/y' in your template.</p>",
        "<code>&lt;a href=&quot;/x&quot;&gt;</code>",
        "plain text, no tags at all",
        "a < b and c > d, href=/x",
        "",
    ],
)
def test_everything_else_in_html_is_left_alone(html):
    assert absolutize_html(html, BASE) == html


@pytest.mark.parametrize(
    ("srcset", "expected"),
    [
        ("a.png", "https://example.com/blog/post/a.png"),
        ("a.png 2x", "https://example.com/blog/post/a.png 2x"),
        (
            "small.png 480w, /large.png 1080w",
            f"{BASE}small.png 480w, https://example.com/large.png 1080w",
        ),
        (
            "/a.png 1x,\n   /b.png 2x",
            "https://example.com/a.png 1x, https://example.com/b.png 2x",
        ),
        (
            "/a.png, /b.png 2x",
            "https://example.com/a.png, https://example.com/b.png 2x",
        ),
        ("/w_100,h_100/a.png 1x", "https://example.com/w_100,h_100/a.png 1x"),
        (
            "data:image/png;base64,AAAA 1x, /b.png 2x",
            "data:image/png;base64,AAAA 1x, https://example.com/b.png 2x",
        ),
        ("https://cdn.example.net/a.png 1x", "https://cdn.example.net/a.png 1x"),
        (" , /a.png 1x ,", "https://example.com/a.png 1x"),
    ],
)
def test_srcset_candidates(srcset, expected):
    html = absolutize_html(f'<img srcset="{srcset}" src="/fallback.png">', BASE)
    assert html == f'<img srcset="{expected}" src="https://example.com/fallback.png">'


def test_html_outside_the_patched_attributes_is_byte_for_byte_the_same():
    html = (
        "<p  class='x'>Tom &amp; Jerry<br/>\n"
        '<a\n   href="one.html"\n   rel=nofollow>one</a> &mdash; <!-- note -->\n'
        "</p>"
    )
    patched = absolutize_html(html, BASE)
    assert patched.replace("https://example.com/blog/post/one.html", "one.html") == html


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/", True),
        ("http://example.com", True),
        ("HTTPS://EXAMPLE.COM/x", True),
        ("//example.com/x", False),
        ("/x", False),
        ("x.html", False),
        ("ftp://example.com/x", False),
        ("mailto:ada@example.com", False),
        ("https://", False),
        ("https:/x", False),
        ("http://[broken", False),
        ("", False),
    ],
)
def test_is_absolute(url, expected):
    assert is_absolute(url) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com/x", True),
        ("urn:uuid:1234", True),
        ("tag:example.com,2024:post", True),
        ("/posts/a/", False),
        ("posts/a", False),
        ("12:30", False),
        ("note: with a space", False),
        ("", False),
    ],
)
def test_has_scheme(value, expected):
    assert has_scheme(value) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://example.com/plain/path?x=1#y",
            "https://example.com/plain/path?x=1#y",
        ),
        ("https://example.com/café/", "https://example.com/caf%C3%A9/"),
        ("https://example.com/a b.png", "https://example.com/a%20b.png"),
        ("https://example.com/caf%C3%A9/ü", "https://example.com/caf%C3%A9/%C3%BC"),
        ("https://example.com/s?q=日本", "https://example.com/s?q=%E6%97%A5%E6%9C%AC"),
        ("https://example.com/a#ünchor", "https://example.com/a#%C3%BCnchor"),
        ("https://bücher.example/x", "https://xn--bcher-kva.example/x"),
        (
            "https://user@bücher.example:8080/ü",
            "https://user@xn--bcher-kva.example:8080/%C3%BC",
        ),
        (
            "https://example.com/a;b=c,d/(e)!$'*+",
            "https://example.com/a;b=c,d/(e)!$'*+",
        ),
    ],
)
def test_to_uri(url, expected):
    assert to_uri(url) == expected
    assert to_uri(expected) == expected
