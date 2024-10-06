from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from inkstone.build import generators
from inkstone.errors import BuildError
from inkstone.search import SearchIndex, client_script

ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


def rss_items(text):
    return ET.fromstring(text).find("channel").findall("item")


def test_rss_feed(blog):
    blog.build()
    root = ET.fromstring(blog.read("rss.xml"))
    channel = root.find("channel")
    assert channel.findtext("title") == "Test Site"
    assert channel.findtext("link") == "https://example.com/"
    assert channel.findtext("description") == "A site for tests."
    assert channel.findtext("language") == "en"
    items = channel.findall("item")
    assert [item.findtext("title") for item in items] == ["Third", "Second", "First"]
    first = items[-1]
    assert first.findtext("link") == "https://example.com/2024/01/first/"
    assert first.findtext("guid") == "https://example.com/2024/01/first/"
    assert first.findtext("pubDate").startswith("Wed, 10 Jan 2024")
    assert [c.text for c in first.findall("category")] == ["python", "notes"]
    assert first.findtext("description") == "The first post."
    assert "Its second paragraph." in first.findtext(f"{CONTENT}encoded")


def test_feed_content_has_absolute_links(blog):
    blog.build()
    third = rss_items(blog.read("rss.xml"))[0]
    body = third.findtext(f"{CONTENT}encoded")
    assert '<a href="https://example.com/2024/01/first/">the first</a>' in body


def test_atom_feed(blog):
    blog.build()
    root = ET.fromstring(blog.read("atom.xml"))
    assert root.findtext(f"{ATOM}title") == "Test Site"
    assert root.findtext(f"{ATOM}id") == "https://example.com/atom.xml"
    entries = root.findall(f"{ATOM}entry")
    assert len(entries) == 3
    assert entries[0].findtext(f"{ATOM}title") == "Third"
    assert root.find(f"{ATOM}author").findtext(f"{ATOM}name") == "Magdy"
    assert root.findtext(f"{ATOM}updated").startswith("2024-03-10")


def test_json_feed_is_off_by_default_and_can_be_enabled(blog):
    blog.build()
    assert not blog.exists("feed.json")
    blog.configure("feeds:\n  json: true\n")
    blog.build()
    feed = json.loads(blog.read("feed.json"))
    assert feed["title"] == "Test Site"
    assert feed["feed_url"] == "https://example.com/feed.json"
    assert [item["title"] for item in feed["items"]] == ["Third", "Second", "First"]


def test_feeds_can_be_switched_off(blog):
    blog.build()
    blog.configure("feeds:\n  rss: false\n  atom: false\n")
    report = blog.build()
    assert not blog.exists("rss.xml") and not blog.exists("atom.xml")
    assert not blog.exists("posts/rss.xml")
    assert {"rss.xml", "atom.xml", "posts/rss.xml"} <= set(report.removed_paths)


def test_feed_limit_and_summary_only(blog):
    blog.configure("feeds:\n  limit: 2\n  full_content: false\n")
    blog.build()
    items = rss_items(blog.read("rss.xml"))
    assert [item.findtext("title") for item in items] == ["Third", "Second"]
    assert len(rss_items(blog.read("posts/rss.xml"))) == 2
    body = "Lead.\n\n<!-- more -->\n\nHidden part.\n"
    blog.page("posts/2024-05-01-long.md", body, title="Long")
    blog.build()
    newest = rss_items(blog.read("rss.xml"))[0]
    assert newest.findtext(f"{CONTENT}encoded").strip() == "<p>Lead.</p>"


def test_section_feeds_for_the_configured_sections(blog):
    blog.page("notes/2024-06-01-a-note.md", "A note.\n", title="Note")
    blog.page("about.md", "About.\n", title="About", date="2024-06-02")
    blog.configure("feeds:\n  sections: [posts, notes, missing]\n")
    blog.build()
    notes = ET.fromstring(blog.read("notes/rss.xml")).find("channel")
    assert notes.findtext("title") == "Notes · Test Site"
    assert notes.findtext("link") == "https://example.com/notes/"
    assert [i.findtext("title") for i in notes.findall("item")] == ["Note"]
    main = rss_items(blog.read("rss.xml"))
    titles = [item.findtext("title") for item in main]
    assert titles == ["Note", "Third", "Second", "First"]
    assert not blog.exists("missing/rss.xml")


def test_empty_sections_setting_means_every_dated_page(blog):
    blog.page("about.md", "About.\n", title="About", date="2024-06-02")
    blog.page("undated.md", "Nope.\n", title="Undated")
    blog.configure("feeds:\n  sections: []\n")
    blog.build()
    titles = [item.findtext("title") for item in rss_items(blog.read("rss.xml"))]
    assert titles == ["About", "Third", "Second", "First"]
    assert not blog.exists("posts/rss.xml")


def test_empty_feed_is_stable_between_builds(site):
    site.page("about.md", title="About")
    site.build()
    first = site.read("atom.xml")
    assert ET.fromstring(first).findall(f"{ATOM}entry") == []
    report = site.build(incremental=False)
    assert site.read("atom.xml") == first
    assert "atom.xml" not in report.output_paths


def test_feeds_and_sitemap_need_an_absolute_base_url(blog, capsys):
    blog.overrides["base_url"] = "/"
    blog.build()
    assert not blog.exists("rss.xml") and not blog.exists("atom.xml")
    assert not blog.exists("sitemap.xml")
    assert "absolute base_url" in capsys.readouterr().err
    robots = blog.read("robots.txt")
    assert "Sitemap:" not in robots
    assert blog.exists("search-index.json")


def test_page_author_and_image_in_feeds(blog):
    blog.page(
        "posts/2024-05-01-guest.md",
        "By a guest.\n",
        title="Guest",
        author="Sam Guest",
        image="/img/guest.png",
        description="A described post.",
    )
    blog.build()
    entry = ET.fromstring(blog.read("atom.xml")).findall(f"{ATOM}entry")[0]
    assert entry.find(f"{ATOM}author").findtext(f"{ATOM}name") == "Sam Guest"
    assert entry.findtext(f"{ATOM}summary") == "A described post."
    assert "https://example.com/img/guest.png" in blog.read("rss.xml")


def test_sitemap(blog):
    blog.build()
    root = ET.fromstring(blog.read("sitemap.xml"))
    urls = {url.findtext(f"{SITEMAP_NS}loc"): url for url in root}
    assert set(urls) == {
        "https://example.com/",
        "https://example.com/about/",
        "https://example.com/posts/",
        "https://example.com/posts/page/2/",
        "https://example.com/page/2/",
        "https://example.com/2024/01/first/",
        "https://example.com/2024/02/second/",
        "https://example.com/2024/03/third/",
        "https://example.com/tags/",
        "https://example.com/tags/python/",
        "https://example.com/tags/notes/",
        "https://example.com/categories/",
        "https://example.com/categories/news/",
    }
    post = urls["https://example.com/2024/01/first/"]
    assert post.findtext(f"{SITEMAP_NS}lastmod").startswith("2024-01-10")
    assert post.findtext(f"{SITEMAP_NS}changefreq") == "weekly"
    assert urls["https://example.com/about/"].find(f"{SITEMAP_NS}lastmod") is None
    # a list is as fresh as its newest member
    section = urls["https://example.com/posts/"]
    assert section.findtext(f"{SITEMAP_NS}lastmod").startswith("2024-03-10")


def test_sitemap_settings_and_opt_out(blog):
    blog.page("hidden.md", title="Hidden", sitemap=False)
    blog.page("posts/2024-04-01-u.md", title="U", updated="2024-04-20")
    blog.configure("sitemap:\n  changefreq: monthly\n")
    blog.build()
    text = blog.read("sitemap.xml")
    assert "/hidden/" not in text
    assert "<changefreq>monthly</changefreq>" in text
    assert "<lastmod>2024-04-20" in text
    blog.configure("sitemap:\n  enabled: false\n")
    report = blog.build()
    assert not blog.exists("sitemap.xml")
    assert "sitemap.xml" in report.removed_paths
    assert "Sitemap:" not in blog.read("robots.txt")


def test_robots_txt(blog):
    blog.build()
    assert blog.read("robots.txt") == (
        "User-agent: *\nDisallow:\n\nSitemap: https://example.com/sitemap.xml\n"
    )
    blog.configure("robots:\n  disallow: [/search/, /private/]\n")
    blog.build()
    robots = blog.read("robots.txt")
    assert "Disallow: /search/\nDisallow: /private/\n" in robots
    blog.configure("robots:\n  enabled: false\n")
    blog.build()
    assert not blog.exists("robots.txt")


def test_bad_robots_path_is_a_build_error(blog):
    blog.configure("robots:\n  disallow: [search]\n")
    with pytest.raises(BuildError, match="robots.disallow"):
        blog.build()


def test_static_file_wins_over_a_generated_one(blog):
    blog.write("static/robots.txt", "User-agent: *\nDisallow: /\n")
    report = blog.build()
    assert blog.read("robots.txt") == "User-agent: *\nDisallow: /\n"
    (warning,) = report.warnings
    assert "robots.txt exists in static/" in warning
    assert blog.build().output_paths == []


def test_search_index_can_be_searched(blog):
    blog.build()
    index = SearchIndex.from_json(blog.read("search-index.json"))
    hits = index.search("second")
    assert hits[0].doc_id == "/2024/02/second/"
    assert hits[0].stored["title"] == "Second"
    assert hits[0].stored["url"] == "/2024/02/second/"
    assert hits[0].stored["summary"] == "The second post."
    assert hits[0].stored["date"] == "2024-02-10"
    assert {hit.doc_id for hit in index.search("tags:python")} == {
        "/2024/01/first/",
        "/2024/02/second/",
    }
    # list pages are not indexed
    assert index.search("Everything") == []
    assert {hit.doc_id for hit in index.search("paragraph")} == {"/2024/01/first/"}


def test_search_index_respects_the_base_path_and_opt_out(blog):
    blog.overrides["base_url"] = "https://example.com/blog/"
    blog.page("secret.md", "Findable words.\n", title="Secret", search=False)
    blog.build()
    index = SearchIndex.from_json(blog.read("search-index.json"))
    assert index.search("second")[0].stored["url"] == "/blog/2024/02/second/"
    assert index.search("findable") == []


def test_search_client_is_shipped_next_to_the_index(blog):
    blog.build()
    assert blog.read("js/inkstone-search.js") == client_script()


def test_search_can_be_switched_off(blog):
    blog.build()
    blog.configure("search:\n  enabled: false\n")
    report = blog.build()
    assert not blog.exists("search-index.json")
    assert not blog.exists("js/inkstone-search.js")
    assert "search-index.json" in report.removed_paths


def test_search_fields_from_the_config(blog):
    blog.configure("search:\n  fields:\n    title: 2\n    description: 1\n")
    blog.page("d.md", "Body words.\n", title="D", description="Unusual phrasing.")
    blog.build()
    index = SearchIndex.from_json(blog.read("search-index.json"))
    assert [hit.doc_id for hit in index.search("unusual")] == ["/d/"]
    assert index.search("body") == []


def test_bad_search_weight_is_a_build_error(blog):
    blog.configure("search:\n  fields:\n    title: 0\n")
    with pytest.raises(BuildError, match="search index"):
        blog.build()


def test_highlight_css_light_only(blog):
    blog.build()
    css = blog.read("css/highlight.css")
    assert ".highlight" in css
    assert "prefers-color-scheme" not in css
    assert css == generators.highlight_css(blog.config())


def test_highlight_css_with_a_dark_style(blog):
    blog.configure(
        "markdown:\n  highlight_style: paper\nparams:\n  highlight_style_dark: dusk\n"
    )
    blog.build()
    css = blog.read("css/highlight.css")
    light, _, dark = css.partition("@media (prefers-color-scheme: dark)")
    assert ".highlight" in light and dark
    assert ':root:not([data-theme="light"]) .highlight' in dark
    assert '[data-theme="dark"] .highlight' in dark
    system = dark.index(':root:not([data-theme="light"])')
    assert system < dark.index('\n[data-theme="dark"]')


def test_highlight_css_for_a_named_style(blog):
    config = blog.config()
    css = generators.highlight_css(config, style="paper", selector="pre.code")
    assert "pre.code" in css and ".highlight" not in css
    with pytest.raises(BuildError, match="highlight CSS"):
        generators.highlight_css(config, style="no-such-style")


def test_generated_assets_follow_the_config(blog):
    assert sorted(generators.generated_assets(blog.config())) == [
        "css/highlight.css",
        "js/inkstone-search.js",
    ]
    blog.configure("search:\n  enabled: false\nmarkdown:\n  highlight: false\n")
    assert generators.generated_assets(blog.config()) == {}


def test_site_static_file_replaces_a_generated_asset(blog):
    blog.write("static/css/highlight.css", "/* mine */\n")
    blog.build()
    assert blog.read("css/highlight.css") == "/* mine */\n"


def test_absolute_base_detection(blog):
    assert generators.has_absolute_base(blog.config())
    blog.overrides["base_url"] = "/docs/"
    assert not generators.has_absolute_base(blog.config())
