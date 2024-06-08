from __future__ import annotations

import copy
import locale
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import pytest

from inkstone.feeds import Author, Enclosure, FeedEntry, FeedError, FeedMeta
from inkstone.feeds.dates import aware, rfc822, rfc3339
from inkstone.feeds.models import entry_iri, feed_updated, prepare

UTC = timezone.utc
CEST = timezone(timedelta(hours=2))
EST = timezone(timedelta(hours=-5))
INDIA = timezone(timedelta(hours=5, minutes=30))


def entry(ident: str, published, **fields) -> FeedEntry:
    return FeedEntry(
        id=ident, title=ident, url=f"/{ident}/", published=published, **fields
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2024, 1, 15, 10, 30, 5), "Mon, 15 Jan 2024 10:30:05 +0000"),
        (
            datetime(2024, 1, 15, 10, 30, 5, tzinfo=UTC),
            "Mon, 15 Jan 2024 10:30:05 +0000",
        ),
        (datetime(2024, 7, 4, 23, 59, tzinfo=CEST), "Thu, 04 Jul 2024 23:59:00 +0200"),
        (datetime(2024, 12, 25, 6, 0, tzinfo=EST), "Wed, 25 Dec 2024 06:00:00 -0500"),
        (datetime(2024, 2, 29, 12, 0, tzinfo=INDIA), "Thu, 29 Feb 2024 12:00:00 +0530"),
        (datetime(2024, 1, 15, 10, 30, 5, 999999), "Mon, 15 Jan 2024 10:30:05 +0000"),
        (date(2024, 3, 1), "Fri, 01 Mar 2024 00:00:00 +0000"),
        (datetime(1999, 12, 31, 23, 59, 59), "Fri, 31 Dec 1999 23:59:59 +0000"),
    ],
)
def test_rfc822(value, expected):
    assert rfc822(value) == expected
    assert parsedate_to_datetime(expected) == aware(value).replace(microsecond=0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2024, 1, 15, 10, 30, 5), "2024-01-15T10:30:05Z"),
        (datetime(2024, 1, 15, 10, 30, 5, tzinfo=UTC), "2024-01-15T10:30:05Z"),
        (datetime(2024, 7, 4, 23, 59, tzinfo=CEST), "2024-07-04T23:59:00+02:00"),
        (datetime(2024, 12, 25, 6, 0, tzinfo=EST), "2024-12-25T06:00:00-05:00"),
        (datetime(2024, 2, 29, 12, 0, tzinfo=INDIA), "2024-02-29T12:00:00+05:30"),
        (datetime(2024, 1, 15, 10, 30, 5, 999999), "2024-01-15T10:30:05Z"),
        (date(2024, 3, 1), "2024-03-01T00:00:00Z"),
    ],
)
def test_rfc3339(value, expected):
    assert rfc3339(value) == expected
    parsed = datetime.fromisoformat(expected.replace("Z", "+00:00"))
    assert parsed == aware(value).replace(microsecond=0)


def test_date_names_do_not_follow_the_locale():
    saved = locale.setlocale(locale.LC_TIME)
    try:
        for name in ("de_DE.UTF-8", "German_Germany", "fr_FR.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
                break
            except locale.Error:
                continue
        assert rfc822(date(2024, 3, 1)) == "Fri, 01 Mar 2024 00:00:00 +0000"
    finally:
        locale.setlocale(locale.LC_TIME, saved)


def test_naive_datetimes_are_utc():
    assert aware(datetime(2024, 1, 1, 12, 0)) == datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


def test_aware_datetimes_keep_their_zone():
    stamp = datetime(2024, 1, 1, 12, 0, tzinfo=CEST)
    assert aware(stamp) is stamp


@pytest.mark.parametrize("value", [None, "2024-01-01", 1704067200, 3.5])
def test_other_types_are_not_dates(value):
    with pytest.raises(FeedError, match="expected a date"):
        aware(value)


def test_entries_are_sorted_newest_first(meta):
    entries = [
        entry("jan", datetime(2024, 1, 1)),
        entry("mar", date(2024, 3, 1)),
        entry("feb", datetime(2024, 2, 1, tzinfo=CEST)),
    ]
    _, prepared = prepare(meta, entries)
    assert [e.title for e in prepared] == ["mar", "feb", "jan"]


def test_sorting_compares_instants_not_wall_clock_times(meta):
    entries = [
        # 23:00 in New York is already the next morning in UTC
        entry("early-utc", datetime(2024, 1, 2, 1, 0, tzinfo=UTC)),
        entry("late-new-york", datetime(2024, 1, 1, 23, 0, tzinfo=EST)),
        entry("naive", datetime(2024, 1, 2, 3, 0)),
    ]
    _, prepared = prepare(meta, entries)
    assert [e.title for e in prepared] == ["late-new-york", "naive", "early-utc"]


def test_entries_with_the_same_date_keep_their_order(meta):
    day = date(2024, 5, 5)
    entries = [entry(name, day) for name in ("one", "two", "three", "four")]
    _, prepared = prepare(meta, entries)
    assert [e.title for e in prepared] == ["one", "two", "three", "four"]


@pytest.mark.parametrize(
    ("limit", "count"), [(None, 5), (10, 5), (5, 5), (2, 2), (0, 0)]
)
def test_limit_keeps_the_newest(meta, limit, count):
    entries = [entry(f"post-{n}", date(2024, 1, n + 1)) for n in range(5)]
    _, prepared = prepare(meta, entries, limit)
    assert [e.title for e in prepared] == [
        "post-4",
        "post-3",
        "post-2",
        "post-1",
        "post-0",
    ][:count]


def test_entries_can_be_any_iterable(meta):
    entries = (entry(f"post-{n}", date(2024, 1, n + 1)) for n in range(3))
    _, prepared = prepare(meta, entries)
    assert len(prepared) == 3


def test_urls_are_made_absolute(meta):
    item = entry(
        "post",
        date(2024, 1, 1),
        content_html='<img src="pic.png"> <a href="/about/">about</a>',
        image="cover.jpg",
        enclosure=Enclosure("/audio/a.mp3", 10),
    )
    meta.feed_url = "/feeds/all.xml"
    prepared_meta, [prepared] = prepare(meta, [item])
    assert prepared_meta.feed_url == "https://example.com/feeds/all.xml"
    assert prepared_meta.icon == "https://example.com/icon.png"
    assert prepared.url == "https://example.com/post/"
    assert prepared.image == "https://example.com/post/cover.jpg"
    assert prepared.enclosure.url == "https://example.com/audio/a.mp3"
    assert prepared.content_html == (
        '<img src="https://example.com/post/pic.png"> '
        '<a href="https://example.com/about/">about</a>'
    )


def test_prepare_leaves_its_input_alone(meta, entries):
    meta_before, entries_before = copy.deepcopy(meta), copy.deepcopy(entries)
    prepare(meta, entries, limit=2)
    assert meta == meta_before
    assert entries == entries_before


@pytest.mark.parametrize(
    ("ident", "url", "expected"),
    [
        ("/posts/a/", "/posts/a/", "https://example.com/posts/a/"),
        ("", "/posts/a/", "https://example.com/posts/a/"),
        (None, "/posts/a/", "https://example.com/posts/a/"),
        ("urn:uuid:1234", "/posts/a/", "urn:uuid:1234"),
        ("post-17", "/posts/a/", "post-17"),
        ("only-an-id", "", "only-an-id"),
    ],
)
def test_entry_id_follows_the_url_unless_it_is_its_own_thing(
    meta, ident, url, expected
):
    item = FeedEntry(id=ident, title="T", url=url, published=date(2024, 1, 1))
    _, [prepared] = prepare(meta, [item])
    assert prepared.id == expected


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"title": ""}, "needs a title"),
        ({"link": ""}, "absolute"),
        ({"link": "/blog/"}, "absolute"),
        ({"link": "example.com"}, "absolute"),
        ({"link": "ftp://example.com/"}, "absolute"),
    ],
)
def test_feed_needs_a_title_and_an_absolute_link(meta, changes, message):
    for name, value in changes.items():
        setattr(meta, name, value)
    with pytest.raises(FeedError, match=message):
        prepare(meta, [])


def test_entry_needs_a_publication_date(meta):
    with pytest.raises(FeedError, match="'/posts/a/' has no publication date"):
        prepare(meta, [FeedEntry("/posts/a/", "A", "/posts/a/", None)])


def test_entry_needs_an_id_or_a_url(meta):
    with pytest.raises(FeedError, match="'Orphan' has neither"):
        prepare(meta, [FeedEntry("", "Orphan", "", date(2024, 1, 1))])


def test_feed_updated_prefers_the_explicit_value(meta, entries):
    _, prepared = prepare(meta, entries)
    assert feed_updated(meta, prepared) == datetime(2024, 3, 10, 12, 0, tzinfo=UTC)


def test_feed_updated_falls_back_to_the_newest_entry(meta, entries):
    meta.updated = None
    _, prepared = prepare(meta, entries)
    # the podcast entry, published as a plain date
    assert feed_updated(meta, prepared) == datetime(2024, 3, 1, tzinfo=UTC)
    entries[0].updated = datetime(2024, 6, 1, 9, 0)
    assert feed_updated(meta, entries) == datetime(2024, 6, 1, 9, 0, tzinfo=UTC)


def test_feed_updated_is_unknown_for_an_empty_feed(meta):
    meta.updated = None
    assert feed_updated(meta, []) is None


@pytest.mark.parametrize(
    ("ident", "expected"),
    [
        ("https://example.com/posts/a/", "https://example.com/posts/a/"),
        ("urn:uuid:9e1f", "urn:uuid:9e1f"),
        ("tag:example.com,2024:a", "tag:example.com,2024:a"),
        ("/posts/a/", "https://example.com/posts/a/"),
        ("post-17", "https://example.com/post-17"),
        ("2024/my first post", "https://example.com/2024/my%20first%20post"),
        ("café", "https://example.com/caf%C3%A9"),
    ],
)
def test_entry_iri(ident, expected):
    assert entry_iri(ident, "https://example.com/") == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/audio/ep1.mp3", "audio/mpeg"),
        ("https://cdn.example.net/ep1.MP3?token=abc", "audio/mpeg"),
        ("/audio/ep1.m4a", "audio/mp4"),
        ("/audio/ep1.opus", "audio/ogg"),
        ("/video/clip.mp4", "video/mp4"),
        ("/files/paper.pdf", "application/pdf"),
        ("/img/cover.JPEG", "image/jpeg"),
        ("/files/mystery.xyz123", "application/octet-stream"),
        ("/files/no-extension", "application/octet-stream"),
    ],
)
def test_enclosure_type_is_guessed_from_the_extension(url, expected):
    assert Enclosure(url).mime_type == expected


def test_enclosure_type_can_be_given():
    assert Enclosure("/a.mp3", 10, "audio/x-custom").mime_type == "audio/x-custom"


def test_dataclass_defaults():
    meta = FeedMeta(title="T", link="https://example.com/")
    assert (meta.feed_url, meta.description, meta.language) == (None, "", "en")
    assert (meta.authors, meta.updated, meta.icon, meta.copyright) == (
        [],
        None,
        None,
        None,
    )
    assert meta.generator == "inkstone"
    item = FeedEntry(id="a", title="A", url="/a/", published=date(2024, 1, 1))
    assert (item.updated, item.summary, item.content_html) == (None, None, None)
    assert (item.authors, item.tags, item.enclosure, item.image) == ([], [], None, None)
    assert Author("Ada") == Author("Ada", None, None)
    assert FeedMeta("T", "https://a.example/").authors is not meta.authors
