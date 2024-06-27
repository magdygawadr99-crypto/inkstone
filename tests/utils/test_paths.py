from __future__ import annotations

import os
from pathlib import Path

import pytest

from inkstone.utils import paths


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (("/blog", "post"), "/blog/post"),
        (("/blog/", "/post/"), "/blog/post/"),
        (("/", "a"), "/a"),
        (("", "a"), "a"),
        (("a", "", "b"), "a/b"),
        (("/a/b",), "/a/b"),
        (("https://example.com", "a", "b.html"), "https://example.com/a/b.html"),
        (("https://example.com/", "/a/", "/b/"), "https://example.com/a/b/"),
        (
            ("https://example.com/base", "x?q=1#top"),
            "https://example.com/base/x?q=1#top",
        ),
        (("/blog", "https://other.org/x"), "https://other.org/x"),
        (("/blog", "//cdn.example.com/lib.js"), "//cdn.example.com/lib.js"),
        (("/a", "b", "c", "d/"), "/a/b/c/d/"),
    ],
)
def test_url_join(parts, expected):
    assert paths.url_join(*parts) == expected


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        ("/", "/css/site.css", "css/site.css"),
        ("/index.html", "/css/site.css", "css/site.css"),
        ("/blog/post/", "/css/site.css", "../../css/site.css"),
        ("/blog/post/", "/blog/", "../"),
        ("/blog/post/", "/blog/other/", "../other/"),
        ("/blog/post/", "/blog/post/", "./"),
        ("/blog/post/", "/blog/post/image.png", "image.png"),
        ("/blog/post/", "/", "../../"),
        ("/blog/post.html", "/blog/other.html", "other.html"),
        ("/blog/post.html", "/about.html", "../about.html"),
        ("/a/b/c/", "/a/x/y/", "../../x/y/"),
        ("/blog/post/", "/tags/#python", "../../tags/#python"),
        ("/blog/post/", "/search/?q=x", "../../search/?q=x"),
        ("/blog/post/?page=2", "/blog/", "../"),
        ("/blog/post/", "/blog/post/#top", "./#top"),
        ("/blog/post/", "https://example.com/x", "https://example.com/x"),
        ("/blog/post/", "mailto:me@example.com", "mailto:me@example.com"),
        ("/blog/post/", "#fragment", "#fragment"),
        ("/blog/post/", "already/relative.html", "already/relative.html"),
    ],
)
def test_relative_url(source, target, expected):
    assert paths.relative_url(source, target) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("index.html", "/"),
        ("about/index.html", "/about/"),
        ("blog/2024/post/index.html", "/blog/2024/post/"),
        ("blog\\2024\\post\\index.html", "/blog/2024/post/"),
        ("feed.xml", "/feed.xml"),
        ("css/site.css", "/css/site.css"),
        ("./a/./b.html", "/a/b.html"),
        ("my file.html", "/my%20file.html"),
        ("über/straße.html", "/%C3%BCber/stra%C3%9Fe.html"),
        ("a/index.html.bak", "/a/index.html.bak"),
        ("", "/"),
    ],
)
def test_path_to_url(path, expected):
    assert paths.path_to_url(path) == expected


def test_path_to_url_accepts_path_objects_and_ugly_urls():
    assert paths.path_to_url(Path("blog") / "post" / "index.html") == "/blog/post/"
    assert paths.path_to_url("blog/index.html", pretty=False) == "/blog/index.html"
    assert paths.path_to_url("index.html", pretty=False) == "/index.html"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/", "index.html"),
        ("", "index.html"),
        ("/about/", "about/index.html"),
        ("/a/b/", "a/b/index.html"),
        ("/a/b.html", "a/b.html"),
        ("/a/b", "a/b"),
        ("/feed.xml", "feed.xml"),
        ("a/b/", "a/b/index.html"),
        ("/a//b/./c/", "a/b/c/index.html"),
        ("/a/x/../b/", "a/b/index.html"),
        ("/a/b/..", "a/index.html"),
        ("/my%20file.html", "my file.html"),
        ("/%C3%BCber/", "über/index.html"),
        ("/blog/?page=2#top", "blog/index.html"),
        ("/page.html#section", "page.html"),
        ("https://example.com/docs/", "docs/index.html"),
        ("https://example.com", "index.html"),
    ],
)
def test_url_to_path(url, expected):
    assert paths.url_to_path(url) == expected


def test_url_to_path_roundtrips_with_path_to_url():
    for path in ("index.html", "a/index.html", "a/b c.html", "é/x.css"):
        assert paths.url_to_path(paths.path_to_url(path)) == path


def test_url_to_path_options_and_escapes():
    assert paths.url_to_path("/docs/", index="default.htm") == "docs/default.htm"
    for url in ("/../secret", "/a/../../b", "/%2e%2e/x", "..\\x"):
        with pytest.raises(ValueError, match="outside the site"):
            paths.url_to_path(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/", True),
        ("http://example.com", True),
        ("//cdn.example.com/x.js", True),
        ("mailto:me@example.com", True),
        ("tel:+123", True),
        ("data:text/plain,hi", True),
        ("ftp://host/file", True),
        ("/local/path/", False),
        ("relative/path.html", False),
        ("../up.html", False),
        ("#fragment", False),
        ("?query=1", False),
        ("", False),
        ("C:\\site\\index.html", False),
        ("c:/site/index.html", False),
        ("/path/with:colon", False),
    ],
)
def test_is_external(url, expected):
    assert paths.is_external(url) is expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/a/b/", "/a/b/"),
        ("/a//b///c", "/a/b/c"),
        ("/a/./b/../c/", "/a/c/"),
        ("/a/b/..", "/a/"),
        ("/../../a", "/a"),
        ("/", "/"),
        ("a/../b", "b"),
        ("a/..", "./"),
        ("../a/./b", "../a/b"),
        ("", ""),
        ("/a/b/?q=1&r=2#frag", "/a/b/?q=1&r=2#frag"),
        ("/a/../b#x/../y", "/b#x/../y"),
        ("HTTP://Example.COM/Path/", "http://example.com/Path/"),
        ("https://example.com:443/a/../b", "https://example.com/b"),
        ("http://example.com:80", "http://example.com/"),
        ("http://example.com:8080//x", "http://example.com:8080/x"),
        ("https://User:Pw@Example.com/x", "https://User:Pw@example.com/x"),
        ("//CDN.example.com/a/./b.js", "//cdn.example.com/a/b.js"),
        ("https://example.com/a?b=C#D", "https://example.com/a?b=C#D"),
        ("MAILTO:Me@Example.com", "mailto:Me@Example.com"),
    ],
)
def test_normalize_url(url, expected):
    assert paths.normalize_url(url) == expected


def test_safe_join_stays_inside_root(tmp_path):
    root = tmp_path.resolve()
    assert paths.safe_join(tmp_path, "a", "b.html") == root / "a" / "b.html"
    assert paths.safe_join(tmp_path, "a/b/../c.html") == root / "a" / "c.html"
    assert paths.safe_join(tmp_path, "/lead/slash.html") == root / "lead" / "slash.html"
    assert paths.safe_join(tmp_path, "a\\b.html") == root / "a" / "b.html"
    assert paths.safe_join(tmp_path) == root
    assert paths.safe_join(tmp_path, "a/..") == root
    assert paths.safe_join(str(tmp_path), Path("x"), "y") == root / "x" / "y"


@pytest.mark.parametrize(
    "parts",
    [
        ("..",),
        ("../outside.txt",),
        ("a", "..", "..", "b"),
        ("a/../../b",),
        ("..\\..\\windows",),
        ("/../etc/passwd",),
        ("a", "../../etc"),
    ],
)
def test_safe_join_refuses_to_escape(tmp_path, parts):
    with pytest.raises(ValueError, match="escapes"):
        paths.safe_join(tmp_path, *parts)


def test_safe_join_does_not_confuse_sibling_prefixes(tmp_path):
    root = tmp_path / "site"
    (tmp_path / "site-backup").mkdir()
    with pytest.raises(ValueError):
        paths.safe_join(root, "../site-backup/x")


@pytest.mark.skipif(os.name != "nt", reason="drive letters are a Windows thing")
def test_safe_join_refuses_other_drives(tmp_path):
    with pytest.raises(ValueError):
        paths.safe_join(tmp_path, "C:/Windows/system.ini")
    with pytest.raises(ValueError):
        paths.safe_join(tmp_path, "Z:secret.txt")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_safe_join_follows_symlinks(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks needs extra privileges here")
    with pytest.raises(ValueError):
        paths.safe_join(root, "link/file.txt")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("post.md", "post"),
        ("a/b/post.md", "a/b/post"),
        ("a\\b\\post.md", "a\\b\\post"),
        ("archive.tar.gz", "archive.tar"),
        ("no-extension", "no-extension"),
        (".htaccess", ".htaccess"),
        ("dir/.gitignore", "dir/.gitignore"),
        ("dir.with.dots/file", "dir.with.dots/file"),
        ("dir.with.dots/file.txt", "dir.with.dots/file"),
        ("trailing.", "trailing"),
        ("", ""),
    ],
)
def test_strip_ext(path, expected):
    assert paths.strip_ext(path) == expected


def test_strip_ext_accepts_path_objects():
    assert paths.strip_ext(Path("a") / "b.html") == str(Path("a") / "b")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/a", "/a/"),
        ("/a/", "/a/"),
        ("", "/"),
        ("/a?x=1", "/a/?x=1"),
        ("/a#top", "/a/#top"),
        ("/a/?x=1#top", "/a/?x=1#top"),
        ("https://example.com/docs", "https://example.com/docs/"),
    ],
)
def test_ensure_trailing_slash(url, expected):
    assert paths.ensure_trailing_slash(url) == expected
