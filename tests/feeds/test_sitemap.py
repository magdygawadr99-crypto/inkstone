from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import pytest

from inkstone.feeds import (
    FeedError,
    Sitemap,
    SitemapUrl,
    render_sitemap,
    render_sitemap_index,
)
from inkstone.feeds.sitemap import MAX_BYTES, MAX_URLS

SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
XHTML = "{http://www.w3.org/1999/xhtml}"
IMAGE = "{http://www.google.com/schemas/sitemap-image/1.1}"


def parse(xml: str) -> ET.Element:
    return ET.fromstring(xml.encode("utf-8"))


def locs(xml: str) -> list[str]:
    return [element.text for element in parse(xml).iter(SM + "loc")]


def site_urls(count: int) -> list[str]:
    return [f"https://example.com/page-{n}/" for n in range(count)]


def test_urlset_structure():
    urls = [
        SitemapUrl("https://example.com/", date(2024, 1, 15), "daily", 1.0),
        SitemapUrl("https://example.com/about/"),
    ]
    root = parse(render_sitemap(urls))
    assert root.tag == SM + "urlset"
    home, about = root.findall(SM + "url")
    assert [(child.tag[len(SM) :], child.text) for child in home] == [
        ("loc", "https://example.com/"),
        ("lastmod", "2024-01-15"),
        ("changefreq", "daily"),
        ("priority", "1.0"),
    ]
    assert [child.tag[len(SM) :] for child in about] == ["loc"]


def test_plain_strings_are_accepted_as_urls():
    assert locs(render_sitemap(site_urls(3))) == site_urls(3)


def test_only_the_namespaces_in_use_are_declared():
    plain = render_sitemap(["https://example.com/"])
    assert "xmlns:xhtml" not in plain and "xmlns:image" not in plain
    alternates = {"en": "https://example.com/", "de": "https://example.com/de/"}
    assert "xmlns:xhtml" in render_sitemap(
        [SitemapUrl("https://example.com/", alternates=alternates)]
    )
    images = ["https://example.com/a.png"]
    assert "xmlns:image" in render_sitemap(
        [SitemapUrl("https://example.com/", images=images)]
    )


@pytest.mark.parametrize(
    ("lastmod", "expected"),
    [
        (date(2024, 2, 29), "2024-02-29"),
        (datetime(2024, 2, 29, 13, 5, 9), "2024-02-29T13:05:09Z"),
        (datetime(2024, 2, 29, 13, 5, 9, tzinfo=timezone.utc), "2024-02-29T13:05:09Z"),
        (
            datetime(2024, 2, 29, 13, 5, tzinfo=timezone(timedelta(hours=-8))),
            "2024-02-29T13:05:00-08:00",
        ),
    ],
)
def test_lastmod_formats(lastmod, expected):
    root = parse(render_sitemap([SitemapUrl("https://example.com/", lastmod)]))
    assert root.findtext(f"{SM}url/{SM}lastmod") == expected


@pytest.mark.parametrize(
    ("priority", "expected"),
    [
        (0, "0.0"),
        (0.0, "0.0"),
        (0.5, "0.5"),
        (0.85, "0.85"),
        (0.8, "0.8"),
        (1, "1.0"),
        (1.0, "1.0"),
    ],
)
def test_priority_formats(priority, expected):
    root = parse(
        render_sitemap([SitemapUrl("https://example.com/", priority=priority)])
    )
    assert root.findtext(f"{SM}url/{SM}priority") == expected


def test_hreflang_alternates():
    alternates = {
        "en": "https://example.com/",
        "de-AT": "https://example.com/de/",
        "x-default": "https://example.com/",
    }
    root = parse(
        render_sitemap([SitemapUrl("https://example.com/", alternates=alternates)])
    )
    links = root.findall(f"{SM}url/{XHTML}link")
    assert [link.attrib for link in links] == [
        {"rel": "alternate", "hreflang": "en", "href": "https://example.com/"},
        {"rel": "alternate", "hreflang": "de-AT", "href": "https://example.com/de/"},
        {"rel": "alternate", "hreflang": "x-default", "href": "https://example.com/"},
    ]


def test_images():
    images = ["https://example.com/a.png", "https://cdn.example.net/b c.jpg"]
    root = parse(render_sitemap([SitemapUrl("https://example.com/", images=images)]))
    found = [e.text for e in root.findall(f"{SM}url/{IMAGE}image/{IMAGE}loc")]
    assert found == ["https://example.com/a.png", "https://cdn.example.net/b%20c.jpg"]


def test_urls_are_escaped_for_xml_and_as_uris():
    urls = ["https://example.com/search?q=a&b=<c>", "https://example.com/café/ü ber/"]
    xml = render_sitemap(urls)
    assert "q=a&amp;b=&lt;c&gt;" in xml
    assert locs(xml) == [
        "https://example.com/search?q=a&b=<c>",
        "https://example.com/caf%C3%A9/%C3%BC%20ber/",
    ]


@pytest.mark.parametrize(
    "url",
    [
        SitemapUrl("/relative/"),
        SitemapUrl("example.com/page"),
        SitemapUrl("ftp://example.com/file"),
        SitemapUrl(""),
        SitemapUrl(None),
        SitemapUrl("https://example.com/" + "x" * 2048),
        SitemapUrl("https://example.com/", priority=1.5),
        SitemapUrl("https://example.com/", priority=-0.1),
        SitemapUrl("https://example.com/", priority="high"),
        SitemapUrl("https://example.com/", priority=True),
        SitemapUrl("https://example.com/", changefreq="sometimes"),
        SitemapUrl("https://example.com/", changefreq="Daily"),
        SitemapUrl("https://example.com/", alternates={"de": "/de/"}),
        SitemapUrl(
            "https://example.com/", alternates={"german": "https://example.com/de/"}
        ),
        SitemapUrl("https://example.com/", alternates={"": "https://example.com/de/"}),
        SitemapUrl("https://example.com/", images=["a.png"]),
    ],
)
def test_invalid_entries_are_refused(url):
    with pytest.raises(FeedError):
        render_sitemap([url])
    with pytest.raises(FeedError):
        Sitemap().add(url)


@pytest.mark.parametrize(
    "changefreq", ["always", "hourly", "daily", "weekly", "monthly", "yearly", "never"]
)
def test_every_changefreq_value_is_accepted(changefreq):
    xml = render_sitemap([SitemapUrl("https://example.com/", changefreq=changefreq)])
    assert parse(xml).findtext(f"{SM}url/{SM}changefreq") == changefreq


def test_error_messages_name_the_url():
    with pytest.raises(
        FeedError, match=r"priority of https://example\.com/a is not within"
    ):
        Sitemap().add("https://example.com/a", priority=7)
    with pytest.raises(FeedError, match="absolute http"):
        Sitemap().add("/a")


def test_sitemap_collects_urls():
    sitemap = Sitemap()
    first = sitemap.add("https://example.com/", priority=1.0, changefreq="daily")
    second = sitemap.add(SitemapUrl("https://example.com/about/", date(2024, 1, 1)))
    sitemap.extend(["https://example.com/a/", SitemapUrl("https://example.com/b/")])
    assert len(sitemap) == 4
    assert list(sitemap)[:2] == [first, second]
    assert first == SitemapUrl("https://example.com/", None, "daily", 1.0)
    assert "https://example.com/a/" in sitemap
    assert "https://example.com/zzz/" not in sitemap


def test_adding_a_url_again_replaces_it_in_place():
    sitemap = Sitemap()
    sitemap.extend(site_urls(3))
    sitemap.add("https://example.com/page-1/", priority=0.3)
    assert len(sitemap) == 3
    assert locs(sitemap.render()) == site_urls(3)
    assert list(sitemap)[1].priority == 0.3


def test_fields_cannot_be_combined_with_a_sitemap_url():
    with pytest.raises(FeedError, match="not both"):
        Sitemap().add(SitemapUrl("https://example.com/"), priority=0.5)


def test_small_sitemap_is_a_single_file():
    sitemap = Sitemap()
    sitemap.extend(site_urls(3))
    files = sitemap.render_files("https://example.com/")
    assert list(files) == ["sitemap.xml"]
    assert files["sitemap.xml"] == sitemap.render()
    assert locs(files["sitemap.xml"]) == site_urls(3)


def test_empty_sitemap_is_still_a_document():
    files = Sitemap().render_files("https://example.com/")
    root = parse(files["sitemap.xml"])
    assert root.tag == SM + "urlset" and len(root) == 0


def test_splitting_by_url_count():
    sitemap = Sitemap(max_urls=2)
    sitemap.extend(site_urls(5))
    files = sitemap.render_files("https://example.com")
    assert list(files) == [
        "sitemap.xml",
        "sitemap-1.xml",
        "sitemap-2.xml",
        "sitemap-3.xml",
    ]
    index = parse(files["sitemap.xml"])
    assert index.tag == SM + "sitemapindex"
    assert locs(files["sitemap.xml"]) == [
        "https://example.com/sitemap-1.xml",
        "https://example.com/sitemap-2.xml",
        "https://example.com/sitemap-3.xml",
    ]
    assert [len(locs(files[f"sitemap-{n}.xml"])) for n in (1, 2, 3)] == [2, 2, 1]
    everything = [loc for n in (1, 2, 3) for loc in locs(files[f"sitemap-{n}.xml"])]
    assert everything == site_urls(5)


def test_exactly_the_limit_is_not_split():
    sitemap = Sitemap(max_urls=4)
    sitemap.extend(site_urls(4))
    assert list(sitemap.render_files("https://example.com/")) == ["sitemap.xml"]
    sitemap.add("https://example.com/one-more/")
    assert len(sitemap.render_files("https://example.com/")) == 3


def test_default_limit_splits_after_50000_urls():
    assert (MAX_URLS, MAX_BYTES) == (50_000, 52_428_800)
    sitemap = Sitemap(pretty=False)
    sitemap.extend(site_urls(MAX_URLS + 1))
    files = sitemap.render_files("https://example.com/")
    assert list(files) == ["sitemap.xml", "sitemap-1.xml", "sitemap-2.xml"]
    assert files["sitemap-1.xml"].count("<url>") == MAX_URLS
    assert locs(files["sitemap-2.xml"]) == [f"https://example.com/page-{MAX_URLS}/"]
    assert all(len(xml.encode("utf-8")) <= MAX_BYTES for xml in files.values())


def test_index_carries_the_newest_lastmod_of_each_file():
    sitemap = Sitemap(max_urls=2)
    sitemap.add("https://example.com/a/", lastmod=date(2024, 1, 1))
    sitemap.add("https://example.com/b/", lastmod=datetime(2024, 3, 1, 12, 0))
    sitemap.add("https://example.com/c/", lastmod=date(2023, 6, 1))
    sitemap.add("https://example.com/d/")
    sitemap.add("https://example.com/e/")
    files = sitemap.render_files("https://example.com/")
    entries = parse(files["sitemap.xml"]).findall(SM + "sitemap")
    assert [entry.findtext(SM + "lastmod") for entry in entries] == [
        "2024-03-01T12:00:00Z",
        "2023-06-01",
        None,
    ]


def test_file_names_and_location_can_be_chosen():
    sitemap = Sitemap(max_urls=1)
    sitemap.extend(site_urls(2))
    files = sitemap.render_files("https://example.com/maps/", name="pages")
    assert list(files) == ["pages.xml", "pages-1.xml", "pages-2.xml"]
    assert locs(files["pages.xml"]) == [
        "https://example.com/maps/pages-1.xml",
        "https://example.com/maps/pages-2.xml",
    ]


def test_index_needs_an_absolute_base_url():
    sitemap = Sitemap(max_urls=1)
    sitemap.extend(site_urls(2))
    with pytest.raises(FeedError, match="base URL must be absolute"):
        sitemap.render_files("/")


def test_render_refuses_to_drop_urls():
    sitemap = Sitemap(max_urls=2)
    sitemap.extend(site_urls(3))
    with pytest.raises(FeedError, match="does not fit in one file"):
        sitemap.render()


def test_splitting_by_size():
    one = len(render_sitemap(site_urls(1)).encode("utf-8"))
    ten = len(render_sitemap(site_urls(10)).encode("utf-8"))
    limit = one + (ten - one) // 3
    sitemap = Sitemap(max_bytes=limit)
    sitemap.extend(site_urls(10))
    files = sitemap.render_files("https://example.com/")
    parts = [xml for name, xml in files.items() if name != "sitemap.xml"]
    assert len(parts) >= 3
    assert all(len(xml.encode("utf-8")) <= limit for xml in parts)
    assert [loc for xml in parts for loc in locs(xml)] == site_urls(10)
    assert len(locs(files["sitemap.xml"])) == len(parts)


def test_size_is_measured_in_bytes_not_characters():
    urls = [f"https://example.com/日本語のページ/{n}/" for n in range(4)]
    as_text = len(render_sitemap(urls))
    sitemap = Sitemap(max_bytes=as_text)
    for url in urls:
        sitemap.add(url, alternates={"ja": url})
    # IRIs are percent-encoded, so each URL takes far more bytes than letters
    assert len(sitemap.split()) > 1


def test_one_entry_larger_than_the_size_limit_is_an_error():
    sitemap = Sitemap(max_bytes=200)
    sitemap.add("https://example.com/" + "long-path/" * 30)
    with pytest.raises(FeedError, match="alone exceeds the 200 byte limit"):
        sitemap.render_files("https://example.com/")


@pytest.mark.parametrize(
    "kwargs", [{"max_urls": 0}, {"max_bytes": 0}, {"max_urls": -5}]
)
def test_limits_must_be_positive(kwargs):
    with pytest.raises(FeedError):
        Sitemap(**kwargs)


def test_sitemap_index_accepts_several_shapes():
    xml = render_sitemap_index(
        [
            "https://example.com/sitemap-1.xml",
            ("https://example.com/sitemap-2.xml", date(2024, 5, 1)),
            SitemapUrl("https://example.com/sitemap-3.xml", datetime(2024, 5, 2, 8, 0)),
        ]
    )
    root = parse(xml)
    assert root.tag == SM + "sitemapindex"
    rows = [(e.findtext(SM + "loc"), e.findtext(SM + "lastmod")) for e in root]
    assert rows == [
        ("https://example.com/sitemap-1.xml", None),
        ("https://example.com/sitemap-2.xml", "2024-05-01"),
        ("https://example.com/sitemap-3.xml", "2024-05-02T08:00:00Z"),
    ]


def test_sitemap_index_needs_absolute_locations():
    with pytest.raises(FeedError, match="sitemap location"):
        render_sitemap_index(["/sitemap-1.xml"])


def test_stylesheet_and_compact_output():
    xml = render_sitemap(site_urls(2), pretty=False, stylesheet="/sitemap.xsl")
    assert xml.splitlines()[1].startswith(
        '<?xml-stylesheet type="text/xsl" href="/sitemap.xsl"?>'
    )
    assert xml.count("\n") == 2
    assert locs(xml) == site_urls(2)
    assert "\n  <url>\n    <loc>" in render_sitemap(site_urls(2))
