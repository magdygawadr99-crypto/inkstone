from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

import pytest

from inkstone.feeds import Author, Enclosure, FeedEntry, FeedError, FeedMeta, render_rss

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}
RFC822 = re.compile(
    r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} "
    r"\d{2}:\d{2}:\d{2} [+-]\d{4}"
)


def channel(xml: str) -> ET.Element:
    root = ET.fromstring(xml.encode("utf-8"))
    assert root.tag == "rss" and root.get("version") == "2.0"
    assert [child.tag for child in root] == ["channel"]
    return root[0]


def items(xml: str) -> list[ET.Element]:
    return channel(xml).findall("item")


def one_item(meta, **fields) -> ET.Element:
    fields.setdefault("published", date(2024, 1, 1))
    entry = FeedEntry(id="/p/", title="Post", url="/p/", **fields)
    [item] = items(render_rss(meta, [entry]))
    return item


def test_channel_metadata(meta, entries):
    ch = channel(render_rss(meta, entries))
    assert ch.findtext("title") == "Ink & Stone"
    assert ch.findtext("link") == "https://example.com/"
    assert ch.findtext("description") == "Notes on <making> things"
    assert ch.findtext("language") == "en"
    assert ch.findtext("copyright") == "© 2024 Ada"
    assert ch.findtext("managingEditor") == "ada@example.com (Ada Lovelace)"
    assert ch.findtext("generator") == "inkstone"
    assert ch.findtext("lastBuildDate") == "Sun, 10 Mar 2024 12:00:00 +0000"


def test_channel_links_back_to_the_feed_itself(meta, entries):
    link = channel(render_rss(meta, entries)).find("atom:link", NS)
    assert link.attrib == {
        "href": "https://example.com/feed.xml",
        "rel": "self",
        "type": "application/rss+xml",
    }


def test_channel_image_comes_from_the_icon(meta, entries):
    image = channel(render_rss(meta, entries)).find("image")
    assert image.findtext("url") == "https://example.com/icon.png"
    assert image.findtext("title") == "Ink & Stone"
    assert image.findtext("link") == "https://example.com/"


def test_optional_channel_elements_are_left_out():
    meta = FeedMeta("Bare", "https://example.com/", language=None, generator=None)
    ch = channel(render_rss(meta, []))
    assert [child.tag for child in ch] == ["title", "link", "description"]
    assert ch.findtext("description") == ""


def test_last_build_date_falls_back_to_the_newest_entry(meta, entries):
    meta.updated = None
    ch = channel(render_rss(meta, entries))
    assert ch.findtext("lastBuildDate") == "Fri, 01 Mar 2024 00:00:00 +0000"


def test_managing_editor_needs_an_email(meta, entries):
    meta.authors = [Author("No Mail"), Author("Has Mail", "has@example.com")]
    ch = channel(render_rss(meta, entries))
    assert ch.findtext("managingEditor") == "has@example.com (Has Mail)"
    meta.authors = [Author("No Mail")]
    assert channel(render_rss(meta, entries)).find("managingEditor") is None


def test_items_are_newest_first(meta, entries):
    titles = [item.findtext("title") for item in items(render_rss(meta, entries))]
    assert titles == ["Episode 1", "Second & better", "First post"]


def test_limit(meta, entries):
    titles = [
        item.findtext("title") for item in items(render_rss(meta, entries, limit=2))
    ]
    assert titles == ["Episode 1", "Second & better"]
    assert items(render_rss(meta, entries, limit=0)) == []


def test_item_basics(meta, entries):
    first = items(render_rss(meta, entries))[2]
    assert first.findtext("title") == "First post"
    assert first.findtext("link") == "https://example.com/posts/first/"
    assert first.findtext("pubDate") == "Mon, 15 Jan 2024 10:30:00 +0000"
    assert [c.text for c in first.findall("category")] == ["meta", "hello"]
    assert first.findtext("description") == "Where it all begins."


def test_pub_dates_are_rfc822(meta, entries):
    dates = [item.findtext("pubDate") for item in items(render_rss(meta, entries))]
    assert all(RFC822.fullmatch(value) for value in dates)
    assert dates[1] == "Tue, 20 Feb 2024 08:00:00 +0200"
    assert parsedate_to_datetime(dates[1]) == datetime(
        2024, 2, 20, 6, 0, tzinfo=timezone.utc
    )


def test_guid_is_a_permalink_only_when_it_is_the_url(meta, entries):
    podcast, second, first = items(render_rss(meta, entries))
    assert first.findtext("guid") == "https://example.com/posts/first/"
    assert first.find("guid").get("isPermaLink") == "true"
    assert second.findtext("guid") == "tag:example.com,2024:second"
    assert second.find("guid").get("isPermaLink") == "false"
    assert podcast.find("guid").get("isPermaLink") == "true"


def test_creator_is_the_entry_author_or_else_the_feed_author(meta, entries):
    podcast, second, first = items(render_rss(meta, entries))
    assert [c.text for c in second.findall("dc:creator", NS)] == ["Grace Hopper"]
    assert [c.text for c in first.findall("dc:creator", NS)] == ["Ada Lovelace"]
    assert first.find("author") is None


def test_several_authors_give_several_creators(meta):
    item = one_item(meta, authors=[Author("One"), Author("Two")])
    assert [c.text for c in item.findall("dc:creator", NS)] == ["One", "Two"]


def test_summary_is_escaped_twice_because_description_is_html(meta, entries):
    xml = render_rss(meta, entries)
    second = items(xml)[1]
    # what a feed reader hands to its HTML renderer
    assert second.findtext("description") == "AT&amp;T &lt;3"
    assert "<description>AT&amp;amp;T &amp;lt;3</description>" in xml


def test_content_is_carried_in_cdata(meta, entries):
    xml = render_rss(meta, entries)
    first = items(xml)[2]
    expected = '<p>Hello <a href="https://example.com/about/">world</a>.</p>'
    assert first.findtext("content:encoded", namespaces=NS) == expected
    assert f"<content:encoded><![CDATA[{expected}]]></content:encoded>" in xml


def test_relative_urls_in_content_resolve_against_the_entry(meta, entries):
    second = items(render_rss(meta, entries))[1]
    content = second.findtext("content:encoded", namespaces=NS)
    assert 'src="https://example.com/posts/second/chips.jpg"' in content
    assert "Fish &amp; chips" in content


def test_items_without_content_or_summary_have_neither_element(meta, entries):
    podcast = items(render_rss(meta, entries))[0]
    assert podcast.find("description") is None
    assert podcast.find("content:encoded", NS) is None


@pytest.mark.parametrize(
    "html",
    [
        "<p>code: <code>if (a[b[0]]>1) {}</code></p>",
        "<pre>&lt;![CDATA[ x ]]&gt; and a literal ]]> too</pre>",
        "]]>]]>",
        "<p>Fish &amp; chips &copy; &#8212; &unknown;</p>",
        "<p>ünïcödé 日本語 \U0001f600</p>",
        "<p>trailing ]]</p>]]",
    ],
)
def test_awkward_content_survives(meta, html):
    item = one_item(meta, content_html=html)
    assert item.findtext("content:encoded", namespaces=NS) == html


def test_control_characters_are_dropped_everywhere(meta):
    meta.title = "Ti\x00tle"
    meta.description = "De\x1bscription"
    entry = FeedEntry(
        id="/p/",
        title="Po\x08st",
        url="/p/",
        published=date(2024, 1, 1),
        summary="Sum\x0bmary",
        content_html="<p>Con\x0ctent\x01</p>",
        tags=["ta\x02g"],
    )
    xml = render_rss(meta, [entry])
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", xml)
    ch = channel(xml)
    assert ch.findtext("title") == "Title"
    assert ch.findtext("description") == "Description"
    item = ch.find("item")
    assert item.findtext("title") == "Post"
    assert item.findtext("description") == "Summary"
    assert item.findtext("category") == "tag"
    assert item.findtext("content:encoded", namespaces=NS) == "<p>Content</p>"


def test_ampersands_and_angle_brackets_in_plain_fields(meta):
    item = one_item(meta, tags=["R&D", "<meta>"], authors=[Author("Tom & Jerry <Inc>")])
    assert [c.text for c in item.findall("category")] == ["R&D", "<meta>"]
    assert item.findtext("dc:creator", namespaces=NS) == "Tom & Jerry <Inc>"


def test_enclosure(meta, entries):
    podcast = items(render_rss(meta, entries))[0]
    assert podcast.find("enclosure").attrib == {
        "url": "https://example.com/audio/ep1.mp3",
        "length": "123456",
        "type": "audio/mpeg",
    }


def test_enclosure_with_explicit_type_and_unknown_length(meta):
    item = one_item(
        meta, enclosure=Enclosure("https://cdn.example.net/a.bin", type="x/y")
    )
    assert item.find("enclosure").attrib == {
        "url": "https://cdn.example.net/a.bin",
        "length": "0",
        "type": "x/y",
    }


def test_image_becomes_a_media_thumbnail(meta, entries):
    second = items(render_rss(meta, entries))[1]
    thumbnail = second.find("media:thumbnail", NS)
    assert thumbnail.get("url") == "https://example.com/posts/second/cover.jpg"


def test_media_namespace_is_only_declared_when_needed(meta, entries):
    assert "xmlns:media=" in render_rss(meta, entries)
    assert "xmlns:media=" not in render_rss(meta, [entries[0]])


def test_updated_entries_carry_an_atom_timestamp(meta, entries):
    podcast, second, first = items(render_rss(meta, entries))
    assert second.findtext("atom:updated", namespaces=NS) == "2024-02-21T09:15:00Z"
    assert first.find("atom:updated", NS) is None


def test_item_without_title_or_link(meta):
    entry = FeedEntry(
        id="note-1", title="", url="", published=date(2024, 1, 1), summary="Hi"
    )
    [item] = items(render_rss(meta, [entry]))
    assert [child.tag for child in item][:3] == [
        "guid",
        "pubDate",
        "{%s}creator" % NS["dc"],
    ]
    assert item.find("guid").get("isPermaLink") == "false"


def test_relative_feed_url_is_resolved(meta, entries):
    meta.feed_url = "rss.xml"
    link = channel(render_rss(meta, entries)).find("atom:link", NS)
    assert link.get("href") == "https://example.com/rss.xml"


def test_no_self_link_without_a_feed_url(meta, entries):
    meta.feed_url = None
    assert channel(render_rss(meta, entries)).find("atom:link", NS) is None


def test_stylesheet(meta, entries):
    xml = render_rss(meta, entries, stylesheet="/feed.xsl")
    assert xml.splitlines()[1] == '<?xml-stylesheet type="text/xsl" href="/feed.xsl"?>'
    assert len(items(xml)) == 3


def test_compact_and_pretty_output_hold_the_same_feed(meta, entries):
    pretty = render_rss(meta, entries)
    compact = render_rss(meta, entries, pretty=False)
    assert len(compact) < len(pretty) and compact.count("\n") == 2

    def flatten(xml):
        return [(e.tag, e.attrib, (e.text or "").strip()) for e in channel(xml).iter()]

    assert flatten(compact) == flatten(pretty)


def test_output_starts_with_an_xml_declaration(meta, entries):
    assert render_rss(meta, entries).startswith(
        '<?xml version="1.0" encoding="utf-8"?>\n<rss '
    )


def test_invalid_feeds_are_refused(meta, entries):
    meta.link = "/relative/"
    with pytest.raises(FeedError):
        render_rss(meta, entries)
