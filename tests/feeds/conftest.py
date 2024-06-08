from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from inkstone.feeds import Author, Enclosure, FeedEntry, FeedMeta


@pytest.fixture
def meta():
    return FeedMeta(
        title="Ink & Stone",
        link="https://example.com/",
        feed_url="https://example.com/feed.xml",
        description="Notes on <making> things",
        language="en",
        authors=[Author("Ada Lovelace", "ada@example.com", "https://example.com/ada/")],
        updated=datetime(2024, 3, 10, 12, 0, tzinfo=timezone.utc),
        icon="/icon.png",
        copyright="© 2024 Ada",
    )


@pytest.fixture
def entries():
    return [
        FeedEntry(
            id="/posts/first/",
            title="First post",
            url="/posts/first/",
            published=datetime(2024, 1, 15, 10, 30),
            summary="Where it all begins.",
            content_html='<p>Hello <a href="/about/">world</a>.</p>',
            tags=["meta", "hello"],
        ),
        FeedEntry(
            id="tag:example.com,2024:second",
            title="Second & better",
            url="https://example.com/posts/second/",
            published=datetime(2024, 2, 20, 8, 0, tzinfo=timezone(timedelta(hours=2))),
            updated=datetime(2024, 2, 21, 9, 15, tzinfo=timezone.utc),
            summary="AT&T <3",
            content_html='<p>Fish &amp; chips <img src="chips.jpg" alt=""></p>',
            authors=[Author("Grace Hopper", url="https://example.com/grace/")],
            tags=["food"],
            image="cover.jpg",
        ),
        FeedEntry(
            id="/posts/podcast/",
            title="Episode 1",
            url="/posts/podcast/",
            published=date(2024, 3, 1),
            enclosure=Enclosure("/audio/ep1.mp3", 123456),
        ),
    ]
