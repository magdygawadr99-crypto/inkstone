from __future__ import annotations

import base64
import hashlib

import pytest

from inkstone.assets import Manifest, content_hash, fingerprint_name, sri_hash
from inkstone.assets.fingerprint import (
    insert_hash,
    is_local_ref,
    map_ref,
    rewrite_css,
    rewrite_html,
    rewrite_srcset,
)


@pytest.fixture
def manifest():
    m = Manifest()
    for logical, output in [
        ("css/site.css", "css/site.11111111.css"),
        ("img/logo.png", "img/logo.22222222.png"),
        ("img/my pic.png", "img/my pic.33333333.png"),
        ("img/sprite.svg", "img/sprite.44444444.svg"),
        ("js/app.js", "js/app.55555555.js"),
        ("robots.txt", "robots.txt"),
    ]:
        m.add(logical, output, hash="0" * 64, size=1, integrity="sha384-" + output)
    return m


def test_content_hash():
    assert content_hash(b"hello") == "2cf24dba"
    assert content_hash(b"hello", 12) == "2cf24dba5fb0"
    assert content_hash(b"hello") != content_hash(b"hello ")


def test_fingerprint_name():
    assert fingerprint_name("style.css", b"hello") == "style.2cf24dba.css"
    assert fingerprint_name("style.css", b"hello", length=4) == "style.2cf2.css"


@pytest.mark.parametrize(
    "path, expected",
    [
        ("style.css", "style.HASH.css"),
        ("css/app.min.js", "css/app.min.HASH.js"),
        ("fonts/inter.woff2", "fonts/inter.HASH.woff2"),
        ("a/b/c/photo.final.jpeg", "a/b/c/photo.final.HASH.jpeg"),
        ("LICENSE", "LICENSE.HASH"),
        (".htaccess", ".htaccess.HASH"),
        ("dir.with.dots/file", "dir.with.dots/file.HASH"),
        ("img\\logo.png", "img/logo.HASH.png"),
    ],
)
def test_insert_hash(path, expected):
    assert insert_hash(path, "HASH") == expected


def test_sri_hash_known_values():
    assert sri_hash(b"") == (
        "sha384-OLBgp1GsljhM2TJ+sbHjaiH9txEUvgdDTAzHv2P24donTt6/529l+9Ua0vFImLlb"
    )
    assert sri_hash(b"", "sha256") == (
        "sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
    )


@pytest.mark.parametrize("algo, size", [("sha256", 32), ("sha384", 48), ("sha512", 64)])
def test_sri_hash_algorithms(algo, size):
    value = sri_hash(b"alert(1)", algo)
    prefix, _, encoded = value.partition("-")
    assert prefix == algo
    assert base64.b64decode(encoded) == hashlib.new(algo, b"alert(1)").digest()
    assert len(base64.b64decode(encoded)) == size


def test_sri_hash_rejects_weak_algorithms():
    with pytest.raises(ValueError, match="md5"):
        sri_hash(b"x", "md5")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("css/site.css", True),
        ("/css/site.css", True),
        ("../a.png", True),
        ("a.png?v=1#x", True),
        ("https://example.com/a.css", False),
        ("HTTP://example.com/a.css", False),
        ("//cdn.example.com/a.css", False),
        ("data:image/png;base64,AAAA", False),
        ("mailto:me@example.com", False),
        ("javascript:void(0)", False),
        ("#top", False),
        ("?page=2", False),
        ("", False),
        ("   ", False),
    ],
)
def test_is_local_ref(url, expected):
    assert is_local_ref(url) is expected


@pytest.mark.parametrize(
    "url, from_path, base_url, expected",
    [
        ("/css/site.css", "", "/", "/css/site.11111111.css"),
        ("css/site.css", "", "/", "css/site.11111111.css"),
        ("./css/site.css", "", "/", "./css/site.11111111.css"),
        ("../css/site.css", "blog/index.html", "/", "../css/site.11111111.css"),
        ("../../img/logo.png", "a/b/index.html", "/", "../../img/logo.22222222.png"),
        ("logo.png", "img/gallery.html", "/", "logo.22222222.png"),
        ("../img/logo.png", "css/site.css", "/", "../img/logo.22222222.png"),
        ("/css/site.css?v=3#top", "", "/", "/css/site.11111111.css?v=3#top"),
        ("/img/sprite.svg#icon-home", "", "/", "/img/sprite.44444444.svg#icon-home"),
        ("/img/my%20pic.png", "", "/", "/img/my%20pic.33333333.png"),
        ("  /css/site.css ", "", "/", "/css/site.11111111.css"),
        ("/blog/css/site.css", "", "/blog/", "/blog/css/site.11111111.css"),
        ("/blog/css/site.css", "", "/blog", "/blog/css/site.11111111.css"),
        ("/css/site.css", "", "/blog/", None),
        (
            "https://example.com/css/site.css",
            "",
            "https://example.com/",
            "https://example.com/css/site.11111111.css",
        ),
        ("/css/site.css", "", "https://example.com/", "/css/site.11111111.css"),
        ("/s/css/site.css", "", "https://example.com/s", "/s/css/site.11111111.css"),
        ("https://other.example/css/site.css", "", "/", None),
        ("//cdn.example.com/css/site.css", "", "/", None),
        ("data:image/png;base64,AAAA", "", "/", None),
        ("#top", "", "/", None),
        ("mailto:me@example.com", "", "/", None),
        ("", "", "/", None),
        ("/", "", "/", None),
        ("/robots.txt", "", "/", None),
        ("/missing.css", "", "/", None),
        ("../../../etc/passwd", "a/b.html", "/", None),
    ],
)
def test_map_ref(manifest, url, from_path, base_url, expected):
    assert map_ref(url, manifest, from_path=from_path, base_url=base_url) == expected


def test_rewrite_css(manifest):
    css = (
        "a{background:url(../img/logo.png)}\n"
        "b{background:url('/img/logo.png') , url(\"../img/my pic.png\")}\n"
        "c{background:url(https://example.com/img/logo.png) url(#frag) url(nope.png)}\n"
    )
    assert rewrite_css(css, manifest, css_path="css/site.css") == (
        "a{background:url(../img/logo.22222222.png)}\n"
        "b{background:url('/img/logo.22222222.png') , "
        'url("../img/my%20pic.33333333.png")}\n'
        "c{background:url(https://example.com/img/logo.png) url(#frag) url(nope.png)}\n"
    )


@pytest.mark.parametrize(
    "value, expected",
    [
        ("a.png", "A.png"),
        ("a.png 1x, b.png 2x", "A.png 1x, B.png 2x"),
        ("a.png 480w,\n   b.png 800w", "A.png 480w,\n   B.png 800w"),
        ("a.png, b.png", "A.png, B.png"),
        (" a.png  1.5x , c.png", " A.png  1.5x , c.png"),
        # without a space the comma belongs to the URL, as far as browsers care
        ("a.png,b.png", "a.png,b.png"),
        ("data:;base64,AA,BB 1x, b.png 2x", "data:;base64,AA,BB 1x, B.png 2x"),
        ("", ""),
        (" , ", " , "),
    ],
)
def test_rewrite_srcset(value, expected):
    names = {"a.png": "A.png", "b.png": "B.png"}
    assert rewrite_srcset(value, names.get) == expected


# @markers@ stand for references that should be rewritten; anything spelled
# out is expected to survive as it is.
TEMPLATE = """<!doctype html>
<html>
<head>
  <base href="/css/site.css">
  <link rel="stylesheet" href="@css@">
  <link rel=preload as=image href=@logo@ imagesrcset="@logo@ 1x, @logo@ 2x">
  <link rel="canonical" href="https://example.com/css/site.css">
  <style>
    body { background: url(@logo@) }  /* <img src="/img/logo.png"> */
  </style>
</head>
<body>
  <!-- <img src="/img/logo.png"> -->
  <img SRC='@logo@' alt="/img/logo.png" srcset="@logo@ 1x, /img/missing.png 2x">
  <video poster="@logo@" src="/missing.mp4"></video>
  <a href="@logo@?download#x">download</a> <a href="#top">top</a> <a href>none</a>
  <div style="background: url('@logo@')" data-src="@logo@"></div>
  <object data="@logo@"></object> <my-widget data="/img/logo.png"></my-widget>
  <svg><use xlink:href="@sprite@#home"/></svg>
  <script src="@js@" defer></script>
  <script>var logo = "/img/logo.png";</script>
  <textarea><img src="/img/logo.png"></textarea>
</body>
</html>
"""


def fill(css, logo, sprite, js):
    page = TEMPLATE.replace("@css@", css).replace("@logo@", logo)
    return page.replace("@sprite@", sprite).replace("@js@", js)


PAGE = fill("/css/site.css", "/img/logo.png", "/img/sprite.svg", "/js/app.js")


def test_rewrite_html(manifest):
    assert rewrite_html(PAGE, manifest) == fill(
        "/css/site.11111111.css",
        "/img/logo.22222222.png",
        "/img/sprite.44444444.svg",
        "/js/app.55555555.js",
    )


def test_rewrite_html_without_matches_is_identity(manifest):
    page = "<p class=a>Nothing <b>to</b> see < here &amp; there</p>\r\n<br/>"
    assert rewrite_html(page, manifest) == page
    assert rewrite_html(PAGE, Manifest()) == PAGE


def test_rewrite_html_relative_to_the_page(manifest):
    page = (
        '<link href="../../css/site.css"><img src="logo.png"><img src="img/logo.png">'
    )
    assert rewrite_html(page, manifest, page_path="blog/post/index.html") == (
        '<link href="../../css/site.11111111.css"><img src="logo.png">'
        '<img src="img/logo.png">'
    )
    assert rewrite_html(page, manifest) == (
        '<link href="../../css/site.css"><img src="logo.png">'
        '<img src="img/logo.22222222.png">'
    )


def test_rewrite_html_adds_integrity(manifest):
    page = (
        '<link rel="stylesheet" href="/css/site.css">'
        "<link rel=stylesheet href=/css/site.css>"
        '<link rel="icon" href="/img/logo.png">'
        '<script src="/js/app.js"></script>'
        '<script src="/js/app.js" integrity="sha384-mine"></script>'
        '<script src="https://cdn.example.com/x.js"></script>'
        '<img src="/img/logo.png">'
    )
    assert rewrite_html(page, manifest, integrity=True) == (
        '<link rel="stylesheet" href="/css/site.11111111.css"'
        ' integrity="sha384-css/site.11111111.css">'
        "<link rel=stylesheet href=/css/site.11111111.css"
        ' integrity="sha384-css/site.11111111.css">'
        '<link rel="icon" href="/img/logo.22222222.png">'
        '<script src="/js/app.55555555.js"'
        ' integrity="sha384-js/app.55555555.js"></script>'
        '<script src="/js/app.55555555.js" integrity="sha384-mine"></script>'
        '<script src="https://cdn.example.com/x.js"></script>'
        '<img src="/img/logo.22222222.png">'
    )
