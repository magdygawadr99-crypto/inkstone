from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import pytest

from inkstone.feeds import (
    Author,
    Enclosure,
    FeedEntry,
    FeedError,
    FeedMeta,
    render_atom,
)

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})")


def feed(xml: str) -> ET.Element:
    root = ET.fromstring(xml.encode("utf-8"))
    assert root.tag == ATOM + "feed"
    return root


def entries_of(xml: str) -> list[ET.Element]:
    return feed(xml).findall(ATOM + "entry")


def text(element: ET.Element, name: str) -> str | None:
    return element.findtext(ATOM + name)


def links(element: ET.Element, rel: str) -> list[dict]:
    return [
        link.attrib for link in element.findall(ATOM + "link") if link.get("rel") == rel
    ]


def one_entry(meta, **fields) -> ET.Element:
    fields.setdefault("id", "/p/")
    fields.setdefault("published", date(2024, 1, 1))
    [entry] = entries_of(
        render_atom(meta, [FeedEntry(title="Post", url="/p/", **fields)])
    )
    return entry


def test_feed_metadata(meta, entries):
    root = feed(render_atom(meta, entries))
    assert root.get(XML_LANG) == "en"
    assert text(root, "title") == "Ink & Stone"
    assert text(root, "subtitle") == "Notes on <making> things"
    assert text(root, "id") == "https://example.com/feed.xml"
    assert text(root, "updated") == "2024-03-10T12:00:00Z"
    assert text(root, "rights") == "© 2024 Ada"
    assert text(root, "icon") == "https://example.com/icon.png"
    assert text(root, "generator") == "inkstone"


def test_feed_links(meta, entries):
    root = feed(render_atom(meta, entries))
    assert links(root, "alternate") == [
        {"rel": "alternate", "type": "text/html", "href": "https://example.com/"}
    ]
    assert links(root, "self") == [
        {
            "rel": "self",
            "type": "application/atom+xml",
            "href": "https://example.com/feed.xml",
        }
    ]


def test_feed_author_is_a_person_construct(meta, entries):
    [author] = feed(render_atom(meta, entries)).findall(ATOM + "author")
    assert [(child.tag[len(ATOM) :], child.text) for child in author] == [
        ("name", "Ada Lovelace"),
        ("email", "ada@example.com"),
        ("uri", "https://example.com/ada/"),
    ]


def test_bare_feed():
    meta = FeedMeta("Bare", "https://example.com/", language=None, generator=None)
    meta.updated = date(2024, 1, 1)
    root = feed(render_atom(meta, []))
    assert XML_LANG not in root.attrib
    assert [child.tag[len(ATOM) :] for child in root] == [
        "title",
        "id",
        "link",
        "updated",
        "author",
    ]
    assert text(root, "id") == "https://example.com/"
    assert links(root, "self") == []


def test_feed_without_any_author_is_credited_to_its_title(meta, entries):
    meta.authors = []
    root = feed(render_atom(meta, entries))
    [author] = root.findall(ATOM + "author")
    assert text(author, "name") == "Ink & Stone"


def test_feed_needs_no_author_when_every_entry_has_one(meta, entries):
    meta.authors = []
    for entry in entries:
        entry.authors = [Author("Someone")]
    assert feed(render_atom(meta, entries)).findall(ATOM + "author") == []


def test_updated_falls_back_to_the_newest_entry(meta, entries):
    meta.updated = None
    assert text(feed(render_atom(meta, entries)), "updated") == "2024-03-01T00:00:00Z"


def test_empty_feed_without_a_date_is_stamped_with_the_build_time(meta):
    meta.updated = None
    stamp = text(feed(render_atom(meta, [])), "updated")
    assert RFC3339.fullmatch(stamp)
    built = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    assert abs(datetime.now(timezone.utc) - built) < timedelta(minutes=1)


def test_entries_are_newest_first(meta, entries):
    titles = [text(entry, "title") for entry in entries_of(render_atom(meta, entries))]
    assert titles == ["Episode 1", "Second & better", "First post"]
    assert len(entries_of(render_atom(meta, entries, limit=1))) == 1


def test_entry_basics(meta, entries):
    first = entries_of(render_atom(meta, entries))[2]
    assert text(first, "title") == "First post"
    assert text(first, "id") == "https://example.com/posts/first/"
    assert links(first, "alternate") == [
        {
            "rel": "alternate",
            "type": "text/html",
            "href": "https://example.com/posts/first/",
        }
    ]
    assert text(first, "published") == "2024-01-15T10:30:00Z"
    assert text(first, "updated") == "2024-01-15T10:30:00Z"
    assert text(first, "summary") == "Where it all begins."
    categories = [c.get("term") for c in first.findall(ATOM + "category")]
    assert categories == ["meta", "hello"]


def test_dates_are_rfc3339(meta, entries):
    xml = render_atom(meta, entries)
    stamps = [
        e.text
        for e in feed(xml).iter()
        if e.tag in (ATOM + "published", ATOM + "updated")
    ]
    assert len(stamps) == 7
    assert all(RFC3339.fullmatch(stamp) for stamp in stamps)
    second = entries_of(xml)[1]
    assert text(second, "published") == "2024-02-20T08:00:00+02:00"
    assert text(second, "updated") == "2024-02-21T09:15:00Z"


@pytest.mark.parametrize(
    ("ident", "expected"),
    [
        ("/p/", "https://example.com/p/"),
        ("https://example.com/p/", "https://example.com/p/"),
        ("urn:uuid:1225c695-cfb8-4ebb-aaaa-80da344efa6a", None),
        ("tag:example.com,2024:post", None),
        ("post-17", "https://example.com/post-17"),
        ("2024/my first post", "https://example.com/2024/my%20first%20post"),
    ],
)
def test_entry_ids_are_absolute_iris(meta, ident, expected):
    assert text(one_entry(meta, id=ident), "id") == (expected or ident)


def test_entry_authors(meta, entries):
    podcast, second, first = entries_of(render_atom(meta, entries))
    [author] = second.findall(ATOM + "author")
    assert text(author, "name") == "Grace Hopper"
    assert text(author, "uri") == "https://example.com/grace/"
    assert author.find(ATOM + "email") is None
    # the feed-level author covers entries that have none of their own
    assert first.findall(ATOM + "author") == []


def test_content_is_escaped_html(meta, entries):
    xml = render_atom(meta, entries)
    first = entries_of(xml)[2]
    content = first.find(ATOM + "content")
    assert content.get("type") == "html"
    assert (
        content.text == '<p>Hello <a href="https://example.com/about/">world</a>.</p>'
    )
    assert len(content) == 0
    assert "&lt;p&gt;Hello &lt;a href=" in xml


def test_entities_in_content_are_escaped_once_more(meta, entries):
    xml = render_atom(meta, entries)
    second = entries_of(xml)[1]
    content = second.findtext(ATOM + "content")
    assert content.startswith("<p>Fish &amp; chips <img src=")
    assert 'src="https://example.com/posts/second/chips.jpg"' in content
    assert "Fish &amp;amp; chips" in xml


def test_summary_is_plain_text(meta, entries):
    xml = render_atom(meta, entries)
    second = entries_of(xml)[1]
    assert text(second, "summary") == "AT&T <3"
    assert second.find(ATOM + "summary").get("type") is None
    assert "<summary>AT&amp;T &lt;3</summary>" in xml


@pytest.mark.parametrize(
    "html",
    [
        "<p>a ]]> b</p>",
        "<![CDATA[ pretend ]]>",
        "<p>Fish &amp; chips &copy; &#8212;</p>",
        '<a href="https://example.com/?a=1&amp;b=2">q</a>',
        "<p>ünïcödé 日本語 \U0001f600</p>",
        "<pre>line one\r\nline two\ttabbed</pre>",
    ],
)
def test_awkward_content_survives(meta, html):
    assert one_entry(meta, content_html=html).findtext(ATOM + "content") == html


def test_control_characters_are_dropped(meta):
    entry = one_entry(
        meta, summary="Sum\x00mary\x1f", content_html="<p>Con\x0btent</p>"
    )
    assert text(entry, "summary") == "Summary"
    assert text(entry, "content") == "<p>Content</p>"


def test_awkward_titles_and_tags(meta):
    meta.title = 'Tom & Jerry\'s "<Blog>"'
    xml = render_atom(
        meta, [FeedEntry("/p/", "1 < 2 && 3 > 2", "/p/", date(2024, 1, 1))]
    )
    root = feed(xml)
    assert text(root, "title") == 'Tom & Jerry\'s "<Blog>"'
    assert text(root.find(ATOM + "entry"), "title") == "1 < 2 && 3 > 2"
    entry = one_entry(meta, tags=['R&D "labs"', "<b>"])
    assert [c.get("term") for c in entry.findall(ATOM + "category")] == [
        'R&D "labs"',
        "<b>",
    ]


def test_enclosure_is_a_link(meta, entries):
    podcast = entries_of(render_atom(meta, entries))[0]
    assert links(podcast, "enclosure") == [
        {
            "rel": "enclosure",
            "type": "audio/mpeg",
            "length": "123456",
            "href": "https://example.com/audio/ep1.mp3",
        }
    ]


def test_enclosure_of_unknown_length_has_no_length(meta):
    entry = one_entry(meta, enclosure=Enclosure("/a.mp3"))
    [link] = links(entry, "enclosure")
    assert "length" not in link


def test_image_becomes_a_media_thumbnail(meta, entries):
    xml = render_atom(meta, entries)
    second = entries_of(xml)[1]
    thumbnail = second.find(MEDIA + "thumbnail")
    assert thumbnail.get("url") == "https://example.com/posts/second/cover.jpg"
    assert "xmlns:media=" not in render_atom(meta, [entries[0]])


def test_entry_without_optional_parts(meta):
    entry = one_entry(meta)
    assert [child.tag[len(ATOM) :] for child in entry] == [
        "title",
        "id",
        "link",
        "published",
        "updated",
    ]


def test_stylesheet_and_compact_output(meta, entries):
    xml = render_atom(meta, entries, pretty=False, stylesheet="/atom.css")
    assert '<?xml-stylesheet type="text/css" href="/atom.css"?>' in xml
    assert xml.count("\n") == 2
    assert len(entries_of(xml)) == 3


def test_invalid_feeds_are_refused(meta, entries):
    meta.title = ""
    with pytest.raises(FeedError):
        render_atom(meta, entries)
