"""Multi-part posts: ``series: Building inkstone`` in the front matter.

Every page of a series gets ``page.series`` with the series ``title``, its
``pages`` in order, and where this page sits (``index``, ``total``,
``prev``, ``next``). Parts are ordered by date, oldest first;
``series_order`` in the front matter overrides that.
"""

from __future__ import annotations

from ...content import Page
from ...utils.text import slugify
from ..base import Plugin
from . import _html
from ._common import date_key, front_matter, setting, template_exists, url_for


class Series:
    """One series: a name and its pages in reading order."""

    def __init__(self, name: str, slug: str, url: str):
        self.name = name
        self.slug = slug
        self.url = url
        self.pages: list = []

    def __repr__(self) -> str:
        return f"<Series {self.name!r} ({len(self.pages)} parts)>"

    @property
    def title(self) -> str:
        return self.name

    @property
    def parts(self) -> list:
        return self.pages

    @property
    def total(self) -> int:
        return len(self.pages)


class Part:
    """What ``page.series`` is: the series as seen from one of its pages."""

    def __init__(self, series: Series, position: int):
        # Plain attributes rather than a reference to the Series: the build
        # cache fingerprints pages by what it finds on them, and a part has
        # to be rendered again when the series gains another one.
        self.name = series.name
        self.title = series.name
        self.slug = series.slug
        self.url = series.url
        self.pages = series.pages
        self.total = len(series.pages)
        # 1-based
        self.index = position + 1

    def __repr__(self) -> str:
        return f"<Part {self.index}/{self.total} of {self.name!r}>"

    @property
    def parts(self) -> list:
        return self.pages

    @property
    def prev(self):
        return self.pages[self.index - 2] if self.index > 1 else None

    @property
    def next(self):
        return self.pages[self.index] if self.index < self.total else None

    @property
    def first(self) -> bool:
        return self.index == 1

    @property
    def last(self) -> bool:
        return self.index == self.total


def _order(page) -> tuple:
    order = front_matter(page, "series_order", 0)
    if isinstance(order, bool) or not isinstance(order, (int, float)):
        order = 0
    undated = page.date is None
    return (order, undated, date_key(page), page.title, page.url)


class SeriesPlugin(Plugin):
    name = "series"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        url = setting(self, "url", "/series/")
        self.url = "/" + url.strip("/") + "/" if url.strip("/") else "/"
        self.title = setting(self, "title", "Series")
        # write /series/ and /series/<name>/
        self.index = setting(self, "index", True)
        self.template = setting(self, "template", "series.html")
        self.all: list[Series] = []
        self._env = None

    def setup(self, builder) -> None:
        self._env = builder.env

    def content_loaded(self, site) -> None:
        found: dict[str, Series] = {}
        for page in sorted(site.pages, key=lambda page: page.url):
            page.series = None
            name = front_matter(page, "series")
            if isinstance(name, dict):
                name = name.get("name") or name.get("title")
            if not name or not str(name).strip():
                continue
            name = str(name).strip()
            # "Building Inkstone" and "building inkstone" are one series
            slug = slugify(name) or slugify(name, allow_unicode=True) or name
            series = found.get(slug)
            if series is None:
                series = found[slug] = Series(name, slug, f"{self.url}{slug}/")
            series.pages.append(page)
        for series in found.values():
            series.pages.sort(key=_order)
            for position, page in enumerate(series.pages):
                page.series = Part(series, position)
        self.all = sorted(found.values(), key=lambda series: series.name.lower())

    def generate_pages(self, site):
        if not self.index or not self.all:
            return
        template = self.template
        if not template_exists(self._env, template):
            template = "page.html"
        yield Page.virtual(
            self.url,
            title=self.title,
            template=template,
            content=self._overview(),
            all_series=self.all,
            series=None,
        )
        for series in self.all:
            yield Page.virtual(
                series.url,
                title=series.name,
                template=template,
                content=self._parts(series),
                all_series=self.all,
                series=series,
                pages=series.pages,
            )

    def _link(self, url: str, text: str) -> str:
        href = _html.escape(url_for(self.config, url))
        return f'<a href="{href}">{_html.escape(text)}</a>'

    def _parts(self, series: Series) -> str:
        items = "\n".join(
            f"<li>{self._link(page.url, page.title)}</li>" for page in series.pages
        )
        return f'<ol class="series__list">\n{items}\n</ol>'

    def _overview(self) -> str:
        out = ['<div class="series-index">']
        for series in self.all:
            parts = "1 part" if series.total == 1 else f"{series.total} parts"
            out.append(
                f'<h2 id="{_html.escape(series.slug)}">'
                f"{self._link(series.url, series.name)} <small>{parts}</small></h2>"
            )
            out.append(self._parts(series))
        out.append("</div>")
        return "\n".join(out)
