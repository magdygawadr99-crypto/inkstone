from __future__ import annotations

import posixpath
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Iterable
from urllib.parse import quote, urlsplit

from .dates import aware
from .errors import FeedError
from .urls import absolutize, absolutize_html, has_scheme, is_absolute

# What people actually attach to posts. The mimetypes module knows more, but
# its answers change with the Python version and, through the registry or
# /etc/mime.types, with the machine; a feed should not.
_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".zip": "application/zip",
}


@dataclass
class Author:
    name: str
    email: str | None = None
    url: str | None = None


@dataclass
class Enclosure:
    """A media file attached to an entry (podcast audio and the like)."""

    url: str
    length: int = 0
    # guessed from the file extension when left out
    type: str | None = None

    @property
    def mime_type(self) -> str:
        if self.type:
            return self.type
        extension = posixpath.splitext(urlsplit(self.url).path)[1].lower()
        return _MEDIA_TYPES.get(extension, "application/octet-stream")


@dataclass
class FeedMeta:
    title: str
    link: str
    feed_url: str | None = None
    description: str = ""
    language: str | None = "en"
    authors: list[Author] = field(default_factory=list)
    updated: date | datetime | None = None
    icon: str | None = None
    copyright: str | None = None
    generator: str | None = "inkstone"


@dataclass
class FeedEntry:
    id: str
    title: str
    url: str
    published: date | datetime
    updated: date | datetime | None = None
    # plain text; markup belongs in content_html
    summary: str | None = None
    content_html: str | None = None
    authors: list[Author] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    enclosure: Enclosure | None = None
    image: str | None = None


def prepare(
    meta: FeedMeta, entries: Iterable[FeedEntry], limit: int | None = None
) -> tuple[FeedMeta, list[FeedEntry]]:
    """Validate and normalise what the renderers are given.

    Returns copies with every URL made absolute against the site link,
    entries sorted newest first and cut to `limit`. The originals are left
    alone since the same objects are usually rendered into several formats.
    """
    if not meta.title:
        raise FeedError("a feed needs a title")
    if not meta.link or not is_absolute(meta.link):
        raise FeedError(f"feed link must be an absolute http(s) URL, got {meta.link!r}")
    meta = replace(
        meta,
        feed_url=absolutize(meta.feed_url, meta.link) if meta.feed_url else None,
        icon=absolutize(meta.icon, meta.link) if meta.icon else None,
    )

    prepared = []
    for entry in entries:
        if entry.published is None:
            name = entry.id or entry.url or entry.title
            raise FeedError(f"feed entry {name!r} has no publication date")
        url = absolutize(entry.url, meta.link) if entry.url else ""
        # An id that is just the (possibly relative) URL follows the URL, so
        # RSS can mark the guid as a permalink.
        ident = url if not entry.id or entry.id == entry.url else entry.id
        if not ident:
            raise FeedError(f"feed entry {entry.title!r} has neither an id nor a url")
        base = url or meta.link
        enclosure = entry.enclosure
        if enclosure is not None:
            enclosure = replace(enclosure, url=absolutize(enclosure.url, base))
        content = entry.content_html
        prepared.append(
            replace(
                entry,
                id=ident,
                url=url,
                content_html=absolutize_html(content, base) if content else None,
                image=absolutize(entry.image, base) if entry.image else None,
                enclosure=enclosure,
            )
        )

    # sort() is stable, also with reverse=True: entries published at the same
    # moment keep the order they were given in
    prepared.sort(key=lambda entry: aware(entry.published), reverse=True)
    if limit is not None:
        prepared = prepared[: max(limit, 0)]
    return meta, prepared


def feed_updated(meta: FeedMeta, entries: list[FeedEntry]) -> datetime | None:
    """When the feed last changed: stated explicitly, or its newest entry."""
    if meta.updated is not None:
        return aware(meta.updated)
    stamps = [aware(entry.updated or entry.published) for entry in entries]
    return max(stamps, default=None)


def entry_iri(ident: str, base: str) -> str:
    """An entry id in the shape Atom insists on, i.e. an absolute IRI."""
    if has_scheme(ident):
        return ident
    return absolutize(quote(ident, safe="/%:@!$&'()*+,;=~#?"), base)
