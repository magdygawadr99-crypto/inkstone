from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .dates import rfc3339
from .models import Author, FeedEntry, FeedMeta, entry_iri, feed_updated, prepare
from .rss import ATOM_NS, MEDIA_NS
from .xmlwriter import XmlWriter

ATOM_TYPE = "application/atom+xml"


def _write_person(w: XmlWriter, tag: str, person: Author) -> None:
    with w.start(tag):
        w.element("name", person.name)
        if person.email:
            w.element("email", person.email)
        if person.url:
            w.element("uri", person.url)


def _write_entry(w: XmlWriter, meta: FeedMeta, entry: FeedEntry) -> None:
    with w.start("entry"):
        w.element("title", entry.title)
        w.element("id", entry_iri(entry.id, meta.link))
        if entry.url:
            link = {"rel": "alternate", "type": "text/html", "href": entry.url}
            w.element("link", attrs=link)
        w.element("published", rfc3339(entry.published))
        w.element("updated", rfc3339(entry.updated or entry.published))
        for author in entry.authors:
            _write_person(w, "author", author)
        for tag in entry.tags:
            w.element("category", attrs={"term": tag})
        if entry.summary:
            w.element("summary", entry.summary)
        if entry.content_html:
            # type="html" means escaped markup as text, not child elements
            w.element("content", entry.content_html, {"type": "html"})
        if entry.enclosure:
            link = {
                "rel": "enclosure",
                "type": entry.enclosure.mime_type,
                "length": entry.enclosure.length or None,
                "href": entry.enclosure.url,
            }
            w.element("link", attrs=link)
        if entry.image:
            w.element("media:thumbnail", attrs={"url": entry.image})


def render_atom(
    meta: FeedMeta,
    entries: Iterable[FeedEntry],
    *,
    limit: int | None = None,
    pretty: bool = True,
    stylesheet: str | None = None,
) -> str:
    """Render an Atom 1.0 (RFC 4287) document."""
    meta, entries = prepare(meta, entries, limit)
    namespaces = {"": ATOM_NS}
    if any(entry.image for entry in entries):
        namespaces["media"] = MEDIA_NS

    # Atom wants an author on the feed unless every single entry has one.
    authors = meta.authors
    if not authors and not (entries and all(entry.authors for entry in entries)):
        authors = [Author(meta.title)]

    # <updated> is mandatory. An empty feed without a date of its own gets
    # the build time, which is the one place output is not reproducible.
    updated = feed_updated(meta, entries) or datetime.now(timezone.utc)

    w = XmlWriter(pretty=pretty)
    if stylesheet:
        w.stylesheet(stylesheet)
    with w.start("feed", {"xml:lang": meta.language or None}, namespaces=namespaces):
        w.element("title", meta.title)
        if meta.description:
            w.element("subtitle", meta.description)
        # Several feeds can share a site (one per tag), so the feed's own
        # address makes the better identifier when we have it.
        w.element("id", meta.feed_url or meta.link)
        link = {"rel": "alternate", "type": "text/html", "href": meta.link}
        w.element("link", attrs=link)
        if meta.feed_url:
            link = {"rel": "self", "type": ATOM_TYPE, "href": meta.feed_url}
            w.element("link", attrs=link)
        w.element("updated", rfc3339(updated))
        for author in authors:
            _write_person(w, "author", author)
        if meta.copyright:
            w.element("rights", meta.copyright)
        if meta.icon:
            w.element("icon", meta.icon)
        if meta.generator:
            w.element("generator", meta.generator)
        for entry in entries:
            _write_entry(w, meta, entry)
    return w.getvalue()
