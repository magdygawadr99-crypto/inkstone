"""Archive pages: everything with a date, by year and by month.

    /archive/            all years
    /archive/2024/       one year
    /archive/2024/05/    one month

A theme can provide ``archive.html``; it gets ``years``, ``year``, ``month``
and ``pages``. Without one the lists are rendered here and shown through the
theme's ordinary ``page.html``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...content import Page
from ..base import Plugin
from . import _html
from ._common import (
    MONTHS,
    date_key,
    in_sections,
    setting,
    template_exists,
    url_for,
)


@dataclass
class Month:
    year: int
    month: int
    url: str
    pages: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return MONTHS[self.month - 1]

    @property
    def count(self) -> int:
        return len(self.pages)


@dataclass
class Year:
    year: int
    url: str
    months: list[Month] = field(default_factory=list)

    @property
    def pages(self) -> list:
        return [page for month in self.months for page in month.pages]

    @property
    def count(self) -> int:
        return sum(month.count for month in self.months)


class Archives(Plugin):
    name = "archives"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        url = setting(self, "url", "/archive/")
        self.url = "/" + url.strip("/") + "/" if url.strip("/") else "/"
        self.title = setting(self, "title", "Archive")
        self.yearly = setting(self, "yearly", True)
        self.monthly = setting(self, "monthly", True)
        # empty: every dated page of the site
        self.sections = setting(self, "sections", [])
        self.template = setting(self, "template", "archive.html")
        self._env = None

    def setup(self, builder) -> None:
        self._env = builder.env

    def dated(self, site) -> list:
        """The pages that go into the archive, newest first."""
        pages = [page for page in site.pages if page.date is not None]
        if self.sections:
            pages = [page for page in pages if in_sections(page, self.sections)]
        pages.sort(key=lambda page: (-date_key(page), page.title, page.url))
        return pages

    def group(self, pages: list) -> list[Year]:
        """Pages (newest first) grouped into years and months, newest first."""
        years: list[Year] = []
        for page in pages:
            year, month = page.date.year, page.date.month
            if not years or years[-1].year != year:
                years.append(Year(year, f"{self.url}{year}/"))
            months = years[-1].months
            if not months or months[-1].month != month:
                months.append(Month(year, month, f"{self.url}{year}/{month:02d}/"))
            months[-1].pages.append(page)
        return years

    def generate_pages(self, site):
        pages = self.dated(site)
        years = self.group(pages)
        yield self._page(self.url, self.title, self._index_html(years), years, pages)
        for year in years:
            if self.yearly:
                yield self._page(
                    year.url,
                    f"{self.title}: {year.year}",
                    self._year_html(year, years),
                    years,
                    year.pages,
                    year=year,
                )
            if not self.monthly:
                continue
            for month in year.months:
                yield self._page(
                    month.url,
                    f"{self.title}: {month.name} {month.year}",
                    self._month_html(month, year),
                    years,
                    month.pages,
                    year=year,
                    month=month,
                )

    def _page(self, url, title, content, years, pages, year=None, month=None):
        template = self.template
        if not template_exists(self._env, template):
            template = "page.html"
        return Page.virtual(
            url,
            title=title,
            template=template,
            content=content,
            years=years,
            year=year,
            month=month,
            pages=pages,
        )

    def _link(self, url: str, text) -> str:
        href = _html.escape(url_for(self.config, url))
        return f'<a href="{href}">{_html.escape(text)}</a>'

    def _list(self, pages: list) -> str:
        items = []
        for page in pages:
            day = f"{MONTHS[page.date.month - 1][:3]} {page.date.day}"
            stamp = page.date.date().isoformat()
            items.append(
                f'<li><time datetime="{stamp}">{day}</time> '
                f"{self._link(page.url, page.title)}</li>"
            )
        return '<ul class="archive__list">\n' + "\n".join(items) + "\n</ul>"

    def _month_heading(self, month: Month, tag: str) -> str:
        name = self._link(month.url, month.name) if self.monthly else month.name
        return f'<{tag} id="m{month.year}-{month.month:02d}">{name}</{tag}>'

    def _index_html(self, years: list[Year]) -> str:
        if not years:
            return '<p class="archive__empty">Nothing here yet.</p>'
        out = ['<div class="archive">']
        for year in years:
            label = self._link(year.url, year.year) if self.yearly else str(year.year)
            out.append('<section class="archive__year">')
            out.append(f'<h2 id="y{year.year}">{label}</h2>')
            for month in year.months:
                out.append(self._month_heading(month, "h3"))
                out.append(self._list(month.pages))
            out.append("</section>")
        out.append("</div>")
        return "\n".join(out)

    def _year_html(self, year: Year, years: list[Year]) -> str:
        out = ['<div class="archive">']
        for month in year.months:
            out.append(self._month_heading(month, "h2"))
            out.append(self._list(month.pages))
        others = [self._link(self.url, "All years")]
        for other in years:
            if other is year:
                others.append(f"<strong>{other.year}</strong>")
            else:
                others.append(self._link(other.url, other.year))
        out.append('<p class="archive__years">' + " · ".join(others) + "</p>")
        out.append("</div>")
        return "\n".join(out)

    def _month_html(self, month: Month, year: Year) -> str:
        back = self._link(year.url, year.year) if self.yearly else ""
        up = self._link(self.url, self.title)
        trail = " · ".join(part for part in (up, back) if part)
        return "\n".join(
            [
                '<div class="archive">',
                self._list(month.pages),
                f'<p class="archive__years">{trail}</p>',
                "</div>",
            ]
        )
