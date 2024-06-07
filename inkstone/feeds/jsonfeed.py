from __future__ import annotations

import json
from typing import Any, Iterable

from .dates import rfc3339
from .models import Author, FeedEntry, FeedMeta, prepare

VERSION = "https://jsonfeed.org/version/1.1"


def _compact(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value not in (None, "", [])}


def _author(author: Author) -> dict[str, Any]:
    # JSON Feed has no email field; the spec suggests a mailto: URL instead
    url = author.url or (f"mailto:{author.email}" if author.email else None)
    return _compact({"name": author.name, "url": url})


def _item(entry: FeedEntry) -> dict[str, Any]:
    item = _compact(
        {
            "id": entry.id,
            "url": entry.url,
            "title": entry.title,
            "content_html": entry.content_html,
            "summary": entry.summary,
            "image": entry.image,
            "date_published": rfc3339(entry.published),
            "date_modified": rfc3339(entry.updated) if entry.updated else None,
            "authors": [_author(author) for author in entry.authors],
            "tags": list(entry.tags),
        }
    )
    if not entry.content_html:
        # one of content_html and content_text has to be there
        item["content_text"] = entry.summary or ""
    if entry.enclosure:
        attachment = {
            "url": entry.enclosure.url,
            "mime_type": entry.enclosure.mime_type,
            "size_in_bytes": entry.enclosure.length or None,
        }
        item["attachments"] = [_compact(attachment)]
    return item


def render_json_feed(
    meta: FeedMeta,
    entries: Iterable[FeedEntry],
    *,
    limit: int | None = None,
    indent: int | None = 2,
) -> str:
    """Render a JSON Feed 1.1 document."""
    meta, entries = prepare(meta, entries, limit)
    feed = _compact(
        {
            "version": VERSION,
            "title": meta.title,
            "home_page_url": meta.link,
            "feed_url": meta.feed_url,
            "description": meta.description,
            "icon": meta.icon,
            "language": meta.language,
            "authors": [_author(author) for author in meta.authors],
        }
    )
    feed["items"] = [_item(entry) for entry in entries]
    return json.dumps(feed, ensure_ascii=False, indent=indent) + "\n"
