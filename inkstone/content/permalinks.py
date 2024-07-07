from __future__ import annotations

import posixpath
import re
from typing import Iterable, Mapping

from ..errors import ConfigError, ContentError
from ..utils.text import slugify

TOKENS = ("year", "month", "day", "slug", "title", "section", "filename")
DATE_TOKENS = frozenset({"year", "month", "day"})

_TOKEN = re.compile(r":([A-Za-z_]+)")
_SLASHES = re.compile(r"/{2,}")


class MissingDate(ContentError):
    """A permalink pattern asks for a date the page does not have."""


def url_segment(name: str) -> str:
    """One path segment from a directory or file name."""
    return slugify(name) or slugify(name, allow_unicode=True) or name


def section_url(name: str) -> str:
    if not name:
        return "/"
    return "/" + "/".join(url_segment(part) for part in name.split("/")) + "/"


def pattern_for(section_name: str | None, permalinks: Mapping[str, str]) -> str | None:
    """The pattern for a section; nested sections inherit from their parents."""
    name = section_name or ""
    while name:
        if name in permalinks:
            return permalinks[name]
        name = name.rpartition("/")[0]
    return None


def pattern_tokens(pattern: str) -> list[str]:
    return _TOKEN.findall(pattern)


def expand(pattern: str, page, section_name: str = "") -> str:
    """Fill a pattern such as ``/:year/:month/:slug/`` in for one page."""
    date = page.date

    def value(match: re.Match) -> str:
        token = match.group(1)
        if token in DATE_TOKENS:
            if date is None:
                raise MissingDate(
                    f"the permalink pattern {pattern!r} needs a date, "
                    "but this page has none",
                    path=page.source_path,
                )
            if token == "year":
                return f"{date.year:04d}"
            return f"{date.month:02d}" if token == "month" else f"{date.day:02d}"
        if token == "slug":
            return page.slug
        if token == "title":
            return slugify(page.title) or page.slug
        if token == "section":
            return section_url(section_name).strip("/")
        if token == "filename":
            return page.filename
        raise ConfigError(
            f"unknown token ':{token}' in permalink pattern {pattern!r} "
            f"(known: {' '.join(':' + name for name in TOKENS)})"
        )

    return normalise(_TOKEN.sub(value, pattern))


def normalise(url: str) -> str:
    """Leading slash, no doubled slashes, trailing slash unless it names a file."""
    url = _SLASHES.sub("/", "/" + url.strip())
    if url.endswith("/"):
        return url
    if posixpath.splitext(posixpath.basename(url))[1]:
        return url
    return url + "/"


def default_url(page, section_name: str = "") -> str:
    """Mirror the source path: ``docs/guide/setup.md`` -> ``/docs/guide/setup/``."""
    return normalise(section_url(section_name) + page.slug + "/")


def ugly(url: str) -> str:
    """``/about/`` -> ``/about.html``; URLs that already name a file stay."""
    if not url.endswith("/") or url == "/":
        return url
    return url.rstrip("/") + ".html"


def page_url(
    page,
    section_name: str = "",
    *,
    permalinks: Mapping[str, str] | None = None,
    pretty: bool = True,
) -> str:
    """Decide the URL of a regular page.

    Raises MissingDate when the section's pattern has date tokens and the
    page is undated; callers usually fall back to default_url() then.
    """
    pattern = pattern_for(section_name, permalinks or {})
    if pattern is None:
        url = default_url(page, section_name)
    else:
        url = expand(pattern, page, section_name)
    # a bundle keeps its directory in any case: its resources live in there
    # and relative links to them have to keep working
    if not pretty and not page.is_bundle:
        url = ugly(url)
    return url


def find_collisions(pages: Iterable) -> dict[str, list]:
    """Output paths that more than one page wants, with the pages involved."""
    by_path: dict[str, list] = {}
    for page in pages:
        # case-insensitive file systems would make these the same file
        by_path.setdefault(page.output_path.lower(), []).append(page)
    return {
        group[0].output_path: group for group in by_path.values() if len(group) > 1
    }


def describe_collision(output_path: str, pages: list) -> str:
    names = []
    for page in pages:
        names.append(page.source_path or f"a generated {page.kind} page ({page.url})")
    return f"{', '.join(names)} would all be written to {output_path}"


def check_collisions(pages: Iterable) -> None:
    collisions = find_collisions(pages)
    if not collisions:
        return
    output_path, group = sorted(collisions.items())[0]
    message = "duplicate URL: " + describe_collision(output_path, group)
    if len(collisions) > 1:
        message += f" (and {len(collisions) - 1} more like it)"
    first = next((page.source_path for page in group if page.source_path), None)
    raise ContentError(message, path=first)
