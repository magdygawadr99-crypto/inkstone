from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Iterator
from urllib.parse import urljoin

from .dates import aware, rfc3339
from .errors import FeedError
from .urls import is_absolute, to_uri
from .xmlwriter import XmlWriter

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"

# Limits from sitemaps.org, per file and before compression.
MAX_URLS = 50_000
MAX_BYTES = 50 * 1024 * 1024
MAX_LOC_LENGTH = 2048

CHANGEFREQS = ("always", "hourly", "daily", "weekly", "monthly", "yearly", "never")

_HREFLANG = re.compile(r"(?:x-default|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*)\Z")


@dataclass
class SitemapUrl:
    loc: str
    lastmod: date | datetime | None = None
    changefreq: str | None = None
    priority: float | None = None
    # hreflang -> URL of that translation; list the page itself too
    alternates: dict[str, str] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)


def _check_loc(url: str, what: str) -> None:
    if not isinstance(url, str) or not is_absolute(url):
        raise FeedError(f"{what} must be an absolute http(s) URL, got {url!r}")
    if len(to_uri(url)) > MAX_LOC_LENGTH:
        raise FeedError(f"{what} is over {MAX_LOC_LENGTH} characters: {url[:60]}...")


def validate_url(url: SitemapUrl) -> None:
    """Raise FeedError if the entry would make an invalid sitemap."""
    _check_loc(url.loc, "sitemap URL")
    if url.changefreq is not None and url.changefreq not in CHANGEFREQS:
        raise FeedError(
            f"changefreq of {url.loc} is {url.changefreq!r}, "
            f"expected one of {', '.join(CHANGEFREQS)}"
        )
    if url.priority is not None:
        priority = url.priority
        if isinstance(priority, bool) or not isinstance(priority, (int, float)):
            raise FeedError(f"priority of {url.loc} is not a number: {priority!r}")
        if not 0.0 <= priority <= 1.0:
            raise FeedError(f"priority of {url.loc} is not within 0..1: {priority}")
    for hreflang, href in url.alternates.items():
        if not _HREFLANG.match(hreflang):
            raise FeedError(f"{hreflang!r} is not a valid hreflang (on {url.loc})")
        _check_loc(href, f"hreflang alternate of {url.loc}")
    for image in url.images:
        _check_loc(image, f"image of {url.loc}")


def _format_lastmod(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return rfc3339(value)
    return value.isoformat()


def _format_priority(value: float) -> str:
    # "0.8" and "1.0" rather than "0.80" or "1"
    text = f"{value:.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _coerce(url: SitemapUrl | str) -> SitemapUrl:
    return SitemapUrl(url) if isinstance(url, str) else url


def render_sitemap(
    urls: Iterable[SitemapUrl | str],
    *,
    pretty: bool = True,
    stylesheet: str | None = None,
) -> str:
    """Render one <urlset> file. No splitting here, see Sitemap for that."""
    urls = [_coerce(url) for url in urls]
    namespaces = {"": SITEMAP_NS}
    if any(url.alternates for url in urls):
        namespaces["xhtml"] = XHTML_NS
    if any(url.images for url in urls):
        namespaces["image"] = IMAGE_NS

    w = XmlWriter(pretty=pretty)
    if stylesheet:
        w.stylesheet(stylesheet)
    with w.start("urlset", namespaces=namespaces):
        for url in urls:
            validate_url(url)
            with w.start("url"):
                w.element("loc", to_uri(url.loc))
                if url.lastmod is not None:
                    w.element("lastmod", _format_lastmod(url.lastmod))
                if url.changefreq:
                    w.element("changefreq", url.changefreq)
                if url.priority is not None:
                    w.element("priority", _format_priority(url.priority))
                for hreflang, href in url.alternates.items():
                    link = {
                        "rel": "alternate",
                        "hreflang": hreflang,
                        "href": to_uri(href),
                    }
                    w.element("xhtml:link", attrs=link)
                for image in url.images:
                    with w.start("image:image"):
                        w.element("image:loc", to_uri(image))
    return w.getvalue()


def render_sitemap_index(
    sitemaps: Iterable[SitemapUrl | str | tuple],
    *,
    pretty: bool = True,
    stylesheet: str | None = None,
) -> str:
    """Render a <sitemapindex> pointing at other sitemap files.

    Items are URLs, (url, lastmod) pairs or SitemapUrl objects.
    """
    w = XmlWriter(pretty=pretty)
    if stylesheet:
        w.stylesheet(stylesheet)
    with w.start("sitemapindex", namespaces={"": SITEMAP_NS}):
        for item in sitemaps:
            if isinstance(item, tuple):
                item = SitemapUrl(*item)
            item = _coerce(item)
            _check_loc(item.loc, "sitemap location")
            with w.start("sitemap"):
                w.element("loc", to_uri(item.loc))
                if item.lastmod is not None:
                    w.element("lastmod", _format_lastmod(item.lastmod))
    return w.getvalue()


class Sitemap:
    """Collects the URLs of a site and writes them out as sitemap files."""

    def __init__(
        self,
        *,
        max_urls: int = MAX_URLS,
        max_bytes: int = MAX_BYTES,
        pretty: bool = True,
    ):
        if max_urls < 1 or max_bytes < 1:
            raise FeedError("sitemap limits must be positive")
        self.max_urls = max_urls
        self.max_bytes = max_bytes
        self.pretty = pretty
        self._urls: dict[str, SitemapUrl] = {}

    def __len__(self) -> int:
        return len(self._urls)

    def __iter__(self) -> Iterator[SitemapUrl]:
        return iter(self._urls.values())

    def __contains__(self, loc: object) -> bool:
        return loc in self._urls

    def add(self, url: SitemapUrl | str, **fields) -> SitemapUrl:
        """Add a URL, either a SitemapUrl or a loc plus its fields.

        Adding the same loc again replaces the earlier entry.
        """
        if isinstance(url, str):
            url = SitemapUrl(url, **fields)
        elif fields:
            raise FeedError("pass either a SitemapUrl or a URL with fields, not both")
        validate_url(url)
        self._urls[url.loc] = url
        return url

    def extend(self, urls: Iterable[SitemapUrl | str]) -> None:
        for url in urls:
            self.add(url)

    def _fit(self, urls: list[SitemapUrl]) -> list[tuple[list[SitemapUrl], str]]:
        xml = render_sitemap(urls, pretty=self.pretty)
        if len(xml.encode("utf-8")) <= self.max_bytes:
            return [(urls, xml)]
        if len(urls) == 1:
            raise FeedError(
                f"sitemap entry for {urls[0].loc} alone exceeds "
                f"the {self.max_bytes} byte limit"
            )
        # Halving does not pack files as full as they could be. Running into
        # the byte limit before the URL limit takes absurdly long URLs, so
        # a few bytes of slack in that case are fine.
        middle = len(urls) // 2
        return self._fit(urls[:middle]) + self._fit(urls[middle:])

    def split(self) -> list[tuple[list[SitemapUrl], str]]:
        """Chunks that respect both limits, each with its rendered XML."""
        urls = list(self._urls.values())
        chunks = []
        for start in range(0, len(urls), self.max_urls):
            chunks += self._fit(urls[start : start + self.max_urls])
        return chunks or [([], render_sitemap([], pretty=self.pretty))]

    def render(self) -> str:
        """The whole sitemap as one document; an error if it needs splitting."""
        chunks = self.split()
        if len(chunks) > 1:
            raise FeedError(
                f"sitemap with {len(self)} URLs does not fit in one file, "
                "use render_files()"
            )
        return chunks[0][1]

    def render_files(self, base_url: str, name: str = "sitemap") -> dict[str, str]:
        """Everything that has to be written, as {filename: xml}.

        One sitemap.xml when it fits. Otherwise sitemap-1.xml, sitemap-2.xml
        and so on, with sitemap.xml as the index tying them together.
        `base_url` is where the files will be served from; the index needs
        absolute addresses.
        """
        chunks = self.split()
        if len(chunks) == 1:
            return {f"{name}.xml": chunks[0][1]}
        if not is_absolute(base_url):
            raise FeedError(f"sitemap base URL must be absolute, got {base_url!r}")
        base_url = base_url.rstrip("/") + "/"
        files = {}
        entries = []
        for number, (urls, xml) in enumerate(chunks, 1):
            filename = f"{name}-{number}.xml"
            files[filename] = xml
            stamps = [url.lastmod for url in urls if url.lastmod is not None]
            newest = max(stamps, key=aware, default=None)
            entries.append(SitemapUrl(urljoin(base_url, filename), newest))
        index = render_sitemap_index(entries, pretty=self.pretty)
        return {f"{name}.xml": index, **files}
