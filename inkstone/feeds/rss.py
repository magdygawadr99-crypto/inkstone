from __future__ import annotations

import html
from typing import Iterable

from .dates import rfc822, rfc3339
from .models import FeedEntry, FeedMeta, feed_updated, prepare
from .xmlwriter import XmlWriter

ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
DC_NS = "http://purl.org/dc/elements/1.1/"
MEDIA_NS = "http://search.yahoo.com/mrss/"


def _write_item(w: XmlWriter, meta: FeedMeta, entry: FeedEntry) -> None:
    with w.start("item"):
        if entry.title:
            w.element("title", entry.title)
        if entry.url:
            w.element("link", entry.url)
        w.element("guid", entry.id, {"isPermaLink": entry.id == entry.url})
        w.element("pubDate", rfc822(entry.published))
        # RSS's own <author> has to be an email address, which nobody wants
        # to publish per post. dc:creator takes a plain name.
        for author in entry.authors or meta.authors:
            w.element("dc:creator", author.name)
        for tag in entry.tags:
            w.element("category", tag)
        if entry.summary:
            # <description> is read as HTML, the summary is plain text
            w.element("description", html.escape(entry.summary, quote=False))
        if entry.content_html:
            with w.start("content:encoded"):
                w.cdata(entry.content_html)
        if entry.enclosure:
            attrs = {
                "url": entry.enclosure.url,
                "length": entry.enclosure.length,
                "type": entry.enclosure.mime_type,
            }
            w.element("enclosure", attrs=attrs)
        if entry.image:
            w.element("media:thumbnail", attrs={"url": entry.image})
        if entry.updated:
            w.element("atom:updated", rfc3339(entry.updated))


def render_rss(
    meta: FeedMeta,
    entries: Iterable[FeedEntry],
    *,
    limit: int | None = None,
    pretty: bool = True,
    stylesheet: str | None = None,
) -> str:
    """Render an RSS 2.0 document."""
    meta, entries = prepare(meta, entries, limit)
    namespaces = {"atom": ATOM_NS, "content": CONTENT_NS, "dc": DC_NS}
    if any(entry.image for entry in entries):
        namespaces["media"] = MEDIA_NS

    w = XmlWriter(pretty=pretty)
    if stylesheet:
        w.stylesheet(stylesheet)
    with w.start("rss", {"version": "2.0"}, namespaces=namespaces), w.start("channel"):
        w.element("title", meta.title)
        w.element("link", meta.link)
        # required by the spec, even when there is nothing to say
        w.element("description", meta.description)
        if meta.language:
            w.element("language", meta.language)
        if meta.copyright:
            w.element("copyright", meta.copyright)
        editor = next((author for author in meta.authors if author.email), None)
        if editor:
            w.element("managingEditor", f"{editor.email} ({editor.name})")
        updated = feed_updated(meta, entries)
        if updated:
            w.element("lastBuildDate", rfc822(updated))
        if meta.generator:
            w.element("generator", meta.generator)
        if meta.feed_url:
            link = {"href": meta.feed_url, "rel": "self", "type": "application/rss+xml"}
            w.element("atom:link", attrs=link)
        if meta.icon:
            with w.start("image"):
                w.element("url", meta.icon)
                w.element("title", meta.title)
                w.element("link", meta.link)
        for entry in entries:
            _write_item(w, meta, entry)
    return w.getvalue()
