from __future__ import annotations

import json
from datetime import date

import pytest

from inkstone.feeds import (
    Author,
    Enclosure,
    FeedEntry,
    FeedError,
    FeedMeta,
    render_json_feed,
)


def load(meta, entries, **options) -> dict:
    return json.loads(render_json_feed(meta, entries, **options))


def test_top_level(meta, entries):
    feed = load(meta, entries)
    assert list(feed) == [
        "version",
        "title",
        "home_page_url",
        "feed_url",
        "description",
        "icon",
        "language",
        "authors",
        "items",
    ]
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["title"] == "Ink & Stone"
    assert feed["home_page_url"] == "https://example.com/"
    assert feed["feed_url"] == "https://example.com/feed.xml"
    assert feed["description"] == "Notes on <making> things"
    assert feed["icon"] == "https://example.com/icon.png"
    assert feed["language"] == "en"
    assert feed["authors"] == [
        {"name": "Ada Lovelace", "url": "https://example.com/ada/"}
    ]


def test_bare_feed_has_only_the_required_members():
    meta = FeedMeta("Bare", "https://example.com/", language=None)
    assert load(meta, []) == {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Bare",
        "home_page_url": "https://example.com/",
        "items": [],
    }


def test_items_are_newest_first(meta, entries):
    assert [item["title"] for item in load(meta, entries)["items"]] == [
        "Episode 1",
        "Second & better",
        "First post",
    ]
    assert len(load(meta, entries, limit=2)["items"]) == 2


def test_full_item(meta, entries):
    second = load(meta, entries)["items"][1]
    assert second == {
        "id": "tag:example.com,2024:second",
        "url": "https://example.com/posts/second/",
        "title": "Second & better",
        "content_html": (
            "<p>Fish &amp; chips "
            '<img src="https://example.com/posts/second/chips.jpg" alt=""></p>'
        ),
        "summary": "AT&T <3",
        "image": "https://example.com/posts/second/cover.jpg",
        "date_published": "2024-02-20T08:00:00+02:00",
        "date_modified": "2024-02-21T09:15:00Z",
        "authors": [{"name": "Grace Hopper", "url": "https://example.com/grace/"}],
        "tags": ["food"],
    }


def test_item_id_follows_the_url(meta, entries):
    first = load(meta, entries)["items"][2]
    assert first["id"] == first["url"] == "https://example.com/posts/first/"
    assert "date_modified" not in first and "authors" not in first


def test_item_without_html_gets_content_text(meta, entries):
    podcast = load(meta, entries)["items"][0]
    assert "content_html" not in podcast
    assert podcast["content_text"] == ""
    entry = FeedEntry("n1", "", "", date(2024, 1, 1), summary="Just a note.")
    [note] = load(meta, [entry])["items"]
    assert note == {
        "id": "n1",
        "summary": "Just a note.",
        "date_published": "2024-01-01T00:00:00Z",
        "content_text": "Just a note.",
    }


def test_attachments(meta, entries):
    podcast = load(meta, entries)["items"][0]
    assert podcast["attachments"] == [
        {
            "url": "https://example.com/audio/ep1.mp3",
            "mime_type": "audio/mpeg",
            "size_in_bytes": 123456,
        }
    ]
    entry = FeedEntry(
        "/p/", "P", "/p/", date(2024, 1, 1), enclosure=Enclosure("/a.ogg")
    )
    [item] = load(meta, [entry])["items"]
    assert item["attachments"] == [
        {"url": "https://example.com/a.ogg", "mime_type": "audio/ogg"}
    ]


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        (Author("Ada"), {"name": "Ada"}),
        (
            Author("Ada", "ada@example.com"),
            {"name": "Ada", "url": "mailto:ada@example.com"},
        ),
        (
            Author("Ada", None, "https://a.example/"),
            {"name": "Ada", "url": "https://a.example/"},
        ),
        (
            Author("Ada", "ada@example.com", "https://a.example/"),
            {"name": "Ada", "url": "https://a.example/"},
        ),
    ],
)
def test_authors(meta, author, expected):
    meta.authors = [author]
    assert load(meta, [])["authors"] == [expected]


def test_text_is_written_as_readable_utf8(meta):
    meta.title = "Crème brûlée 日本語 \U0001f600"
    text = render_json_feed(meta, [])
    assert "Crème brûlée 日本語 \U0001f600" in text
    assert text.endswith("}\n")


def test_awkward_content_round_trips(meta):
    html = '<p>"quotes" \\ backslash </script> ]]> &amp; \x01\u2028 tab\t</p>'
    entry = FeedEntry(
        "/p/", 'A "quoted" title', "/p/", date(2024, 1, 1), content_html=html
    )
    [item] = load(meta, [entry])["items"]
    assert item["content_html"] == html
    assert item["title"] == 'A "quoted" title'


def test_indentation(meta, entries):
    pretty = render_json_feed(meta, entries)
    compact = render_json_feed(meta, entries, indent=None)
    assert pretty.startswith('{\n  "version"')
    assert compact.count("\n") == 1
    assert json.loads(pretty) == json.loads(compact)


def test_invalid_feeds_are_refused(meta, entries):
    meta.link = "not a url"
    with pytest.raises(FeedError):
        render_json_feed(meta, entries)
