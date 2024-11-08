from __future__ import annotations

import http.server
import threading

import pytest

from inkstone.build import LinkChecker, Problem


class Tree:
    """A hand-made output directory."""

    def __init__(self, root):
        self.root = root

    def write(self, relpath: str, text: str = ""):
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def check(self, **options) -> list[Problem]:
        return LinkChecker(self.root, **options).run()


@pytest.fixture
def tree(tmp_path):
    out = Tree(tmp_path / "public")
    out.write("index.html", '<a href="/about/">About</a> <a href="posts/">Posts</a>')
    out.write("about/index.html", '<h1 id="top-of-page">About</h1><a href="/">Home</a>')
    out.write("posts/index.html", '<a href="hello/">Hello</a><a href="../about/">A</a>')
    out.write("posts/hello/index.html", '<h2 id="intro">I</h2><a href="#intro">up</a>')
    out.write("css/main.css", "body {}")
    return out


def summary(problems):
    return [(p.kind, p.source, p.target) for p in problems]


def test_clean_tree_has_no_problems(tree):
    checker = LinkChecker(tree.root)
    assert checker.run() == []
    assert checker.checked == 6
    assert sorted(checker.html_files()) == [
        "about/index.html",
        "index.html",
        "posts/hello/index.html",
        "posts/index.html",
    ]


def test_missing_output_directory_is_just_empty(tmp_path):
    assert LinkChecker(tmp_path / "nowhere").run() == []


def test_broken_absolute_and_relative_links(tree):
    tree.write(
        "broken/index.html",
        '<p>\n<a href="/nope/">a</a>\n<a href="missing.html">b</a>\n'
        '<a href="../posts/gone/">c</a>\n<a href="/about/">fine</a></p>',
    )
    problems = tree.check()
    assert summary(problems) == [
        ("broken-link", "broken/index.html", "/nope/"),
        ("broken-link", "broken/index.html", "missing.html"),
        ("broken-link", "broken/index.html", "../posts/gone/"),
    ]
    assert [problem.line for problem in problems] == [2, 3, 4]
    assert all(isinstance(problem, Problem) for problem in problems)
    assert str(problems[0]) == (
        "broken/index.html:2: broken-link: no such page or file (/nope/)"
    )


@pytest.mark.parametrize(
    "href",
    [
        "/about",
        "/about/",
        "/about/index.html",
        "/about/?utm=1",
        "/about/#top-of-page",
        "/css/main.css",
        "../../about/",
        "../hello/",
        "./",
        ".",
        "?page=2",
        "/",
        "",
        "#",
        "#top",
    ],
)
def test_links_a_static_host_would_serve(tree, href):
    tree.write("posts/extra/index.html", f'<a href="{href}">x</a>')
    assert tree.check() == []


def test_extensionless_link_to_an_html_file(tree):
    tree.write("contact.html", "<p>hi</p>")
    links = '<a href="/contact">c</a> <a href="/contact.html">d</a>'
    tree.write("links/index.html", links)
    assert tree.check() == []


def test_missing_anchors(tree):
    tree.write(
        "anchors/index.html",
        '<h2 id="here">Here</h2>\n<a href="#here">ok</a>\n<a href="#gone">bad</a>\n'
        '<a href="/posts/hello/#intro">ok</a>\n<a href="/posts/hello/#outro">bad</a>\n'
        '<a name="legacy"></a><a href="#legacy">ok</a>\n<a href="#caf%C3%A9">bad</a>',
    )
    problems = tree.check()
    assert summary(problems) == [
        ("missing-anchor", "anchors/index.html", "#gone"),
        ("missing-anchor", "anchors/index.html", "/posts/hello/#outro"),
        ("missing-anchor", "anchors/index.html", "#caf%C3%A9"),
    ]
    assert "nothing with id 'gone' on this page" in problems[0].message
    assert "on posts/hello/index.html" in problems[1].message
    assert "'café'" in problems[2].message


def test_percent_encoded_anchor_matches_the_id(tree):
    tree.write("u/index.html", '<h2 id="café">x</h2><a href="#caf%C3%A9">ok</a>')
    assert tree.check() == []


def test_text_fragments_are_not_anchors(tree):
    tree.write("t/index.html", '<a href="/about/#:~:text=About">x</a>')
    assert tree.check() == []


def test_missing_images_and_srcset(tree):
    tree.write("img/a.png", "png")
    tree.write(
        "gallery/index.html",
        '<img src="/img/a.png">\n<img src="/img/b.png">\n'
        '<img src="/img/a.png" srcset="/img/a.png 1x, /img/a@2x.png 2x">\n'
        '<picture><source srcset="../img/c.webp"><img src="../img/a.png"></picture>\n'
        '<video poster="/img/poster.jpg" src="/img/a.png"></video>',
    )
    problems = tree.check()
    assert summary(problems) == [
        ("missing-image", "gallery/index.html", "/img/b.png"),
        ("missing-image", "gallery/index.html", "/img/a@2x.png"),
        ("missing-image", "gallery/index.html", "../img/c.webp"),
        ("missing-image", "gallery/index.html", "/img/poster.jpg"),
    ]
    assert problems[0].message == "image not found"


def test_scripts_stylesheets_and_iframes_are_checked(tree):
    tree.write(
        "assets/index.html",
        '<link rel="stylesheet" href="/css/main.css">\n'
        '<link rel="stylesheet" href="/css/gone.css">\n'
        '<script src="/js/gone.js"></script>\n<iframe src="/embed/"></iframe>',
    )
    assert summary(tree.check()) == [
        ("broken-link", "assets/index.html", "/css/gone.css"),
        ("broken-link", "assets/index.html", "/js/gone.js"),
        ("broken-link", "assets/index.html", "/embed/"),
    ]


def test_schemes_that_are_not_links_to_check(tree):
    tree.write(
        "contact/index.html",
        '<a href="mailto:me@example.com">m</a> <a href="tel:+123">t</a>'
        ' <a href="javascript:void(0)">j</a> <img src="data:image/png;base64,AAAA">'
        ' <link rel="canonical" href="https://example.com/contact/">'
        ' <link rel="preconnect" href="https://fonts.example">',
    )
    assert tree.check() == []


def test_a_link_is_reported_once_per_page(tree):
    tree.write("twice/index.html", '<a href="/nope/">a</a>\n<a href="/nope/">b</a>')
    tree.write("thrice/index.html", '<a href="/nope/">c</a>')
    problems = tree.check()
    assert summary(problems) == [
        ("broken-link", "thrice/index.html", "/nope/"),
        ("broken-link", "twice/index.html", "/nope/"),
    ]


def test_links_to_the_own_host_are_internal(tree):
    tree.write(
        "abs/index.html",
        '<a href="https://example.com/about/">ok</a>\n'
        '<a href="https://example.com/nope/">bad</a>\n'
        '<a href="//example.com/posts/">ok</a>\n'
        '<a href="https://other.example/nope/">external, not checked</a>',
    )
    problems = tree.check(base_url="https://example.com/")
    assert summary(problems) == [
        ("broken-link", "abs/index.html", "https://example.com/nope/")
    ]


def test_site_below_a_sub_path(tmp_path):
    out = Tree(tmp_path / "public")
    out.write("index.html", '<a href="/blog/about/">About</a>')
    out.write("about/index.html", '<a href="/blog/">Home</a>')
    out.write(
        "sub/index.html",
        '<a href="/blog/about/">ok</a>\n<a href="/blog">ok</a>\n'
        '<a href="/blog/nope/">bad</a>\n<a href="/about/">outside the site</a>\n'
        '<a href="../about/">ok</a>\n'
        '<a href="https://example.com/blog/about/#x">bad</a>',
    )
    problems = out.check(base_url="https://example.com/blog/")
    assert summary(problems) == [
        ("broken-link", "sub/index.html", "/blog/nope/"),
        ("broken-link", "sub/index.html", "/about/"),
        ("missing-anchor", "sub/index.html", "https://example.com/blog/about/#x"),
    ]


def test_base_url_given_as_a_path(tmp_path):
    out = Tree(tmp_path / "public")
    out.write("about/index.html", "<p>About</p>")
    links = '<a href="/docs/about/">ok</a> <a href="/docs/zzz/">bad</a>'
    out.write("p/index.html", links)
    problems = out.check(base_url="/docs/")
    assert summary(problems) == [("broken-link", "p/index.html", "/docs/zzz/")]


def test_links_cannot_escape_the_output_directory(tree):
    (tree.root.parent / "secret.html").write_text("x", encoding="utf-8")
    tree.write("esc/index.html", '<a href="../../secret.html">x</a>')
    assert summary(tree.check()) == [
        ("broken-link", "esc/index.html", "../../secret.html")
    ]


def test_base_element_changes_how_relative_links_resolve(tree):
    tree.write("deep/down/index.html", '<base href="/posts/"><a href="hello/">ok</a>')
    assert tree.check() == []


def test_non_html_files_are_not_scanned(tree):
    tree.write("feed.xml", '<a href="/nope/">x</a>')
    tree.write("notes.txt", '<a href="/nope/">x</a>')
    assert tree.check() == []


def test_external_links_are_skipped_unless_asked(tree):
    tree.write("ext/index.html", '<a href="http://127.0.0.1:9/never">x</a>')
    assert tree.check() == []


class _Handler(http.server.BaseHTTPRequestHandler):
    def _answer(self):
        if self.path.startswith("/ok"):
            self.send_response(200)
        elif self.path.startswith("/get-only") and self.command == "GET":
            self.send_response(200)
        elif self.path.startswith("/get-only"):
            self.send_response(405)
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_HEAD = do_GET = _answer

    def log_message(self, *args):
        pass


@pytest.fixture
def web():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_external_links_are_fetched_on_request(tree, web):
    tree.write(
        "ext/index.html",
        f'<a href="{web}/ok">ok</a>\n<a href="{web}/gone">gone</a>\n'
        f'<a href="{web}/get-only">picky</a>\n<a href="{web}/ok#frag">ok</a>\n'
        f'<img src="{web}/gone.png">',
    )
    problems = tree.check(external=True, timeout=5)
    assert summary(problems) == [
        ("external-link", "ext/index.html", f"{web}/gone"),
        ("external-link", "ext/index.html", f"{web}/gone.png"),
    ]
    assert problems[0].message == "HTTP 404"
    assert problems[0].line == 2


def test_unreachable_external_host(tree):
    tree.write("ext/index.html", '<a href="http://127.0.0.1:9/never">x</a>')
    (problem,) = tree.check(external=True, timeout=2)
    assert problem.kind == "external-link"
    assert problem.message.startswith("cannot connect")


def test_built_site_passes_its_own_link_check(blog):
    blog.page(
        "posts/trip/index.md",
        "![Harbour](harbour.jpg)\n",
        title="Trip",
        date="2024-05-01",
    )
    blog.write("content/posts/trip/harbour.jpg", "jpeg")
    blog.page(
        "notes.md",
        "See [the heading](posts/2024-02-10-second.md#a-heading) and [[1]](#fn).\n",
        title="Notes",
    )
    blog.build()
    problems = LinkChecker(blog.output, base_url="https://example.com/").run()
    assert summary(problems) == [("missing-anchor", "notes/index.html", "#fn")]
    assert '<a href="/2024/02/second/#a-heading">' in blog.read("notes/index.html")


def test_built_site_below_a_sub_path_passes_too(blog):
    blog.overrides["base_url"] = "https://example.com/blog/"
    blog.build()
    assert LinkChecker(blog.output, base_url="https://example.com/blog/").run() == []
    # checked against the wrong base, every absolute link is off
    assert LinkChecker(blog.output, base_url="https://example.com/").run() != []
