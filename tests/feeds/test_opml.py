from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest

from inkstone.feeds import Author, FeedError, FeedMeta, OpmlFeed, render_opml


def parse(xml: str) -> ET.Element:
    root = ET.fromstring(xml.encode("utf-8"))
    assert root.tag == "opml" and root.get("version") == "2.0"
    assert [child.tag for child in root] == ["head", "body"]
    return root


def test_feed_list():
    feeds = [
        OpmlFeed("First", "https://one.example/feed.xml", "https://one.example/"),
        OpmlFeed("Second", "https://two.example/atom.xml", description="Number two"),
    ]
    root = parse(render_opml(feeds, title="Reading list"))
    assert root.findtext("head/title") == "Reading list"
    first, second = root.findall("body/outline")
    assert first.attrib == {
        "type": "rss",
        "text": "First",
        "title": "First",
        "xmlUrl": "https://one.example/feed.xml",
        "htmlUrl": "https://one.example/",
    }
    assert second.attrib == {
        "type": "rss",
        "text": "Second",
        "title": "Second",
        "xmlUrl": "https://two.example/atom.xml",
        "description": "Number two",
    }


def test_feed_meta_can_be_exported_directly(meta):
    meta.feed_url = "/feed.xml"
    [outline] = parse(render_opml([meta])).findall("body/outline")
    assert outline.attrib == {
        "type": "rss",
        "text": "Ink & Stone",
        "title": "Ink & Stone",
        "xmlUrl": "https://example.com/feed.xml",
        "htmlUrl": "https://example.com/",
        "description": "Notes on <making> things",
    }


def test_categories_become_folders():
    feeds = [
        OpmlFeed("Loose", "https://a.example/feed"),
        OpmlFeed("Python one", "https://b.example/feed", category="Python"),
        OpmlFeed("Cooking", "https://c.example/feed", category="Food & drink"),
        OpmlFeed("Python two", "https://d.example/feed", category="Python"),
    ]
    body = parse(render_opml(feeds)).find("body")
    assert [outline.get("text") for outline in body] == [
        "Loose",
        "Python",
        "Food & drink",
    ]
    python = body[1]
    assert "xmlUrl" not in python.attrib
    assert [outline.get("text") for outline in python] == ["Python one", "Python two"]
    assert [outline.get("xmlUrl") for outline in body[2]] == ["https://c.example/feed"]


def test_head_details():
    xml = render_opml(
        [],
        owner=Author("Ada Lovelace", "ada@example.com", "https://example.com/ada/"),
        created=datetime(2024, 3, 10, 12, 0, tzinfo=timezone.utc),
    )
    head = parse(xml).find("head")
    assert [(child.tag, child.text) for child in head] == [
        ("title", "Feeds"),
        ("dateCreated", "Sun, 10 Mar 2024 12:00:00 +0000"),
        ("ownerName", "Ada Lovelace"),
        ("ownerEmail", "ada@example.com"),
        ("ownerId", "https://example.com/ada/"),
    ]


def test_owner_with_only_a_name():
    head = parse(render_opml([], owner=Author("Ada"))).find("head")
    assert [child.tag for child in head] == ["title", "ownerName"]


def test_awkward_titles_are_escaped():
    title = 'Tom & Jerry\'s "<feed>"\twith a tab'
    xml = render_opml([OpmlFeed(title, "https://a.example/feed?x=1&y=2")])
    [outline] = parse(xml).findall("body/outline")
    assert outline.get("title") == title
    assert outline.get("xmlUrl") == "https://a.example/feed?x=1&y=2"


def test_feed_meta_without_a_feed_url_cannot_be_listed():
    meta = FeedMeta("No feed", "https://example.com/")
    with pytest.raises(FeedError, match="'No feed' has no feed_url"):
        render_opml([meta])


def test_feed_urls_must_be_absolute():
    with pytest.raises(FeedError, match="must be absolute"):
        render_opml([OpmlFeed("Relative", "/feed.xml")])


def test_compact_output():
    feeds = [OpmlFeed("One", "https://one.example/feed")]
    assert render_opml(feeds, pretty=False).count("\n") == 2
    assert render_opml(feeds).count("\n") > 5
