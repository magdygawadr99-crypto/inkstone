from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.plugins.builtin.redirects import Redirects, normalise, redirect_page

from .helpers import make_config, make_page, make_site


def generate(config, pages, **settings):
    site = make_site(config, pages)
    plugin = Redirects(config, settings)
    plugin.content_loaded(site)
    generated = list(plugin.generate_pages(site))
    files = dict(plugin.extra_files(site))
    return generated, files


@pytest.mark.parametrize(
    "alias, url",
    [
        ("/old/", "/old/"),
        ("old/", "/old/"),
        ("/old", "/old"),
        ("/old.html", "/old.html"),
        (" /spaced/ ", "/spaced/"),
        ("/a//b/./c/", "/a/b/c/"),
        ("/old/?utm=1#frag", "/old/"),
        ("//double/", "/double/"),
        ("/", "/"),
    ],
)
def test_normalise(alias, url):
    assert normalise(alias) == url


def test_each_alias_becomes_a_page(config):
    post = make_page(
        "Moved post",
        "/2024/05/moved/",
        source_path="posts/moved.md",
        aliases=["/blog/moved/", "/2019/moved.html"],
    )
    generated, files = generate(config, [post, make_page("Other")])
    assert [(page.url, page.output_path) for page in generated] == [
        ("/2019/moved.html", "2019/moved.html"),
        ("/blog/moved/", "blog/moved/index.html"),
    ]
    assert files == {}
    for page in generated:
        assert page.kind == "virtual"
        assert page.template is None
        assert page.title == "Moved post"
        assert page.redirect_to == "/2024/05/moved/"


def test_redirect_document(config):
    post = make_page("A & B", "/new/", aliases=["/old/"])
    generated, _files = generate(config, [post])
    html = str(generated[0].content)
    target = "https://example.com/new/"
    assert html.startswith("<!doctype html>\n")
    assert f'<meta http-equiv="refresh" content="0; url={target}">' in html
    assert f'<link rel="canonical" href="{target}">' in html
    assert f'<a href="{target}">' in html
    assert f'location.replace("{target}" + location.hash)' in html
    assert "<title>A &amp; B</title>" in html
    assert '<meta name="robots" content="noindex">' in html


def test_redirect_page_escapes_what_it_is_given():
    html = redirect_page('https://example.com/?a=1&b="2"</script>', language="de")
    assert '<html lang="de">' in html
    assert 'href="https://example.com/?a=1&amp;b=&quot;2&quot;&lt;/script&gt;"' in html
    assert "</script>" not in html.split("<script>")[1].split("</script>\n")[0]
    assert "<title>This page has moved</title>" in html


def test_base_path_is_part_of_the_target(tmp_path):
    config = make_config(tmp_path, base_url="https://example.com/blog/")
    generated, _files = generate(config, [make_page("P", "/new/", aliases=["/old/"])])
    assert 'url=https://example.com/blog/new/"' in str(generated[0].content)


def test_map_from_the_config(config):
    pages = [make_page("Feed home", "/posts/", source_path="posts/_index.md")]
    mapping = {
        "/feed/": "/rss.xml",
        "talks": "https://example.org/talks/",
        "/blog/": "posts/_index.md",
    }
    generated, _files = generate(config, pages, map=mapping)
    targets = {page.url: page.redirect_to for page in generated}
    assert targets == {
        "/feed/": "/rss.xml",
        "/talks": "https://example.org/talks/",
        "/blog/": "/posts/",
    }
    external = next(page for page in generated if page.url == "/talks")
    assert 'url=https://example.org/talks/"' in str(external.content)


def test_unknown_content_path_in_the_map_is_used_as_a_url(config, capsys):
    generated, _files = generate(config, [], map={"/a/": "nowhere/else"})
    assert generated[0].redirect_to == "/nowhere/else"
    assert "no page found for 'nowhere/else'" in capsys.readouterr().err


def test_alias_of_an_existing_page_is_skipped_with_a_warning(config, capsys):
    about = make_page("About", "/about/", source_path="about.md")
    aliases = ["/about/", "/ok/"]
    post = make_page("Post", "/post/", source_path="post.md", aliases=aliases)
    generated, _files = generate(config, [about, post])
    assert [page.url for page in generated] == ["/ok/"]
    err = capsys.readouterr().err
    assert "post.md wants /about/, which is the URL of a page" in err


def test_alias_of_a_tag_page_is_skipped(config, capsys):
    aliases = ["/tags/python/", "/tags/"]
    post = make_page("Post", "/post/", tags=["python"], aliases=aliases)
    generated, _files = generate(config, [post])
    assert generated == []
    assert capsys.readouterr().err.count("which is the URL of a page") == 2


def test_alias_claimed_twice_goes_to_the_first(config, capsys):
    a = make_page("A", "/a/", aliases=["/same/"])
    b = make_page("B", "/b/", aliases=["/same/"])
    generated, _files = generate(config, [b, a])
    assert [(page.url, page.redirect_to) for page in generated] == [("/same/", "/a/")]
    err = capsys.readouterr().err
    assert "/same/ is redirected twice, keeping the one to /a/" in err


def test_alias_to_itself_is_ignored_quietly(config, capsys):
    generated, _files = generate(config, [make_page("A", "/a/", aliases=["/a/"])])
    assert generated == []
    assert capsys.readouterr().err == ""


def test_netlify_file(config):
    pages = [
        make_page("A", "/a/", aliases=["/old-a/"]),
        make_page("B", "/b/", aliases=["/a-much-longer-old-address/"]),
    ]
    mapping = {"/x/": "https://e.org/"}
    _generated, files = generate(config, pages, netlify=True, map=mapping)
    assert files == {
        "_redirects": (
            "/a-much-longer-old-address/  /b/  301\n"
            "/old-a/                      /a/  301\n"
            "/x/                          https://e.org/  301\n"
        )
    }


def test_netlify_status_and_no_html(config):
    pages = [make_page("A", "/a/", aliases=["/old/"])]
    generated, files = generate(config, pages, netlify=True, html=False, status=302)
    assert generated == []
    assert files == {"_redirects": "/old/  /a/  302\n"}


def test_nothing_to_redirect_writes_nothing(config):
    generated, files = generate(config, [make_page("A")], netlify=True)
    assert generated == [] and files == {}


def test_results_are_computed_once_per_build(config):
    site = make_site(config, [make_page("A", "/a/", aliases=["/old/"])])
    plugin = Redirects(config, {})
    first = plugin.collect(site)
    assert plugin.collect(site) is first
    plugin.content_loaded(site)
    assert plugin.collect(site) is not first


@pytest.mark.parametrize(
    "settings",
    [{"status": 200}, {"netlify": "yes"}, {"map": ["/a/", "/b/"]}, {"html": 1}],
)
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.redirects\]"):
        Redirects(config, settings)
