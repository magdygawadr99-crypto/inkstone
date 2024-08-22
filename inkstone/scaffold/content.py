"""New posts and pages for an existing site."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .. import frontmatter
from ..errors import InkstoneError
from ..utils.dates import date_from_filename, parse_date
from ..utils.fs import atomic_write
from ..utils.paths import safe_join
from ..utils.text import slugify, titlecase

MARKDOWN_SUFFIXES = (".md", ".markdown")

_HAS_TIME = re.compile(r"\d:\d")


def _slug(text: str) -> str:
    return slugify(text) or slugify(text, allow_unicode=True)


def post_filename(title: str, date: dt.date, slug: str | None = None) -> str:
    """``2024-05-03-hello-world.md``: the date and slug a post is found by."""
    name = _slug(slug or title)
    if not name:
        raise InkstoneError(
            f"cannot make a file name out of {slug or title!r}; pass --slug"
        )
    return f"{date:%Y-%m-%d}-{name}.md"


def _inside(config, *parts: str) -> Path:
    try:
        return safe_join(config.content_path, *parts)
    except ValueError:
        where = "/".join(parts)
        raise InkstoneError(
            f"{where!r} is outside the content directory ({config.content_path})"
        ) from None


def _write(config, path: Path, meta: dict) -> Path:
    if path.exists():
        try:
            shown = path.relative_to(config.root).as_posix()
        except ValueError:
            shown = str(path)
        raise InkstoneError("already exists, not overwriting it", path=shown)
    # an empty line after the front matter, ready to type into
    atomic_write(path, frontmatter.dumps(meta, "\n"))
    return path


def new_post(
    config,
    title: str,
    *,
    section: str = "posts",
    date: str | dt.date | None = None,
    slug: str | None = None,
    tags=(),
    draft: bool = False,
) -> Path:
    """Create a post with its front matter filled in; returns the new file."""
    title = title.strip()
    if not title:
        raise InkstoneError("a post needs a title")
    stamp: dt.date
    if date is None:
        stamp = dt.datetime.now(getattr(config, "tzinfo", None)).date()
    elif isinstance(date, str):
        try:
            moment = parse_date(date)
        except ValueError as exc:
            raise InkstoneError(f"--date: {exc}") from None
        # keep the time of day only when one was asked for
        stamp = moment if _HAS_TIME.search(date) else moment.date()
    else:
        stamp = date
    day = stamp.date() if isinstance(stamp, dt.datetime) else stamp

    meta: dict = {"title": title, "date": stamp}
    if draft:
        meta["draft"] = True
    meta["tags"] = [tag.strip() for tag in tags if tag.strip()]
    section = section.replace("\\", "/").strip("/")
    path = _inside(config, section, post_filename(title, day, slug))
    return _write(config, path, meta)


def title_from_path(rel: str) -> str:
    """``projects/my-widget.md`` -> ``My Widget``."""
    path = Path(rel)
    name = path.stem
    if name in ("index", "_index") and path.parent.name:
        # bundles and section indexes are named by their directory
        name = path.parent.name
    name = date_from_filename(name)[1] or name
    words = re.sub(r"[-_]+", " ", name).strip()
    return titlecase(words) if words else name


def new_page(config, path: str, *, title: str | None = None) -> Path:
    """Create a page at ``path`` below the content directory.

    ``about`` and ``about.md`` are the same file; ``about/`` makes a page
    bundle (``about/index.md``).
    """
    rel = path.strip().replace("\\", "/").lstrip("/")
    content_dir = str(config.content_dir).replace("\\", "/").strip("/") + "/"
    if rel.startswith(content_dir):
        # tab completion from the site root gives "content/..."
        rel = rel[len(content_dir) :]
    if not rel:
        raise InkstoneError("new page needs a path, e.g. projects/widget.md")
    if rel.endswith("/"):
        rel += "index.md"
    elif not rel.lower().endswith(MARKDOWN_SUFFIXES):
        if "." in rel.rpartition("/")[2]:
            raise InkstoneError(f"{path!r}: pages are Markdown files (.md)")
        rel += ".md"
    target = _inside(config, rel)
    return _write(config, target, {"title": title or title_from_path(rel)})
