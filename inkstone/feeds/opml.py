from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from .dates import rfc822
from .errors import FeedError
from .models import Author, FeedMeta
from .urls import absolutize, is_absolute
from .xmlwriter import XmlWriter


@dataclass
class OpmlFeed:
    title: str
    xml_url: str
    html_url: str | None = None
    description: str | None = None
    # feeds with the same category end up under one folder outline
    category: str | None = None
    type: str = "rss"


def _coerce(feed: OpmlFeed | FeedMeta) -> OpmlFeed:
    if isinstance(feed, OpmlFeed):
        return feed
    if not feed.feed_url:
        raise FeedError(f"feed {feed.title!r} has no feed_url to list in OPML")
    return OpmlFeed(
        title=feed.title,
        xml_url=absolutize(feed.feed_url, feed.link),
        html_url=feed.link,
        description=feed.description or None,
    )


def _write_feed(w: XmlWriter, feed: OpmlFeed) -> None:
    if not is_absolute(feed.xml_url):
        raise FeedError(f"OPML feed URL must be absolute, got {feed.xml_url!r}")
    attrs = {
        "type": feed.type,
        # readers disagree on which of the two they show, so give both
        "text": feed.title,
        "title": feed.title,
        "xmlUrl": feed.xml_url,
        "htmlUrl": feed.html_url,
        "description": feed.description,
    }
    w.element("outline", attrs=attrs)


def render_opml(
    feeds: Iterable[OpmlFeed | FeedMeta],
    *,
    title: str = "Feeds",
    owner: Author | None = None,
    created: date | datetime | None = None,
    pretty: bool = True,
) -> str:
    """Export a list of feeds as OPML 2.0, the format readers import."""
    plain: list[OpmlFeed] = []
    folders: dict[str, list[OpmlFeed]] = {}
    for feed in map(_coerce, feeds):
        if feed.category:
            folders.setdefault(feed.category, []).append(feed)
        else:
            plain.append(feed)

    w = XmlWriter(pretty=pretty)
    with w.start("opml", {"version": "2.0"}):
        with w.start("head"):
            w.element("title", title)
            if created is not None:
                w.element("dateCreated", rfc822(created))
            if owner:
                w.element("ownerName", owner.name)
                if owner.email:
                    w.element("ownerEmail", owner.email)
                if owner.url:
                    w.element("ownerId", owner.url)
        with w.start("body"):
            for feed in plain:
                _write_feed(w, feed)
            for category, members in folders.items():
                with w.start("outline", {"text": category, "title": category}):
                    for feed in members:
                        _write_feed(w, feed)
    return w.getvalue()
