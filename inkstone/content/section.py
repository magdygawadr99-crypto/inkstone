from __future__ import annotations

from typing import Iterator

from ..utils.text import natural_sort_key
from .page import Page, Resource
from .query import PageList

SORT_ORDERS = ("date", "weight", "title")


def _date_key(page: Page) -> float:
    return page.date.timestamp() if page.date is not None else 0.0


def sort_pages(pages, order: str = "date") -> PageList:
    """Order pages the way a section asks for.

    ``date`` is newest first with undated pages at the end, ``weight`` is
    lowest first (then newest), ``title`` is alphabetical. Ties always end
    with the URL so the order does not depend on the file system.
    """
    if order == "weight":

        def key(page):
            return (
                page.weight,
                page.date is None,
                -_date_key(page),
                natural_sort_key(page.title),
                page.url,
            )

    elif order == "title":

        def key(page):
            return (natural_sort_key(page.title), page.url)

    elif order == "date":

        def key(page):
            return (
                page.date is None,
                -_date_key(page),
                natural_sort_key(page.title),
                page.url,
            )

    else:
        raise ValueError(f"unknown sort order {order!r}")
    return PageList(sorted(pages, key=key))


class Section:
    """A directory of pages: ``posts``, or ``docs/guide`` when nested."""

    def __init__(self, name: str, *, url: str | None = None, index: Page | None = None):
        self.name = name
        self.url = url if url is not None else f"/{name}/"
        self.index = index
        self.pages = PageList()
        self.subsections: list[Section] = []
        self.parent: Section | None = None
        self.sort_by = "date"
        self.paginate: int | None = None
        # loose non-Markdown files in the directory, copied next to the list page
        self.resources: list[Resource] = []

    def __repr__(self) -> str:
        return f"<Section {self.name!r} ({len(self.pages)} pages)>"

    def __iter__(self) -> Iterator[Page]:
        return iter(self.pages)

    def __len__(self) -> int:
        return len(self.pages)

    def __bool__(self) -> bool:
        # an empty section is still there
        return True

    @property
    def title(self) -> str:
        return self.index.title if self.index is not None else self.basename

    @property
    def description(self) -> str:
        return self.index.description if self.index is not None else ""

    @property
    def meta(self) -> dict:
        return self.index.meta if self.index is not None else {}

    @property
    def params(self) -> dict:
        return self.index.params if self.index is not None else {}

    @property
    def basename(self) -> str:
        return self.name.rpartition("/")[2]

    @property
    def depth(self) -> int:
        return self.name.count("/") + 1

    @property
    def ancestors(self) -> list[Section]:
        """Parent sections, outermost first."""
        chain = []
        section = self.parent
        while section is not None:
            chain.append(section)
            section = section.parent
        return chain[::-1]

    @property
    def all_pages(self) -> PageList:
        """Pages of this section and of everything nested below it."""
        pages = list(self.pages)
        for child in self.subsections:
            pages.extend(child.all_pages)
        return sort_pages(pages, self.sort_by)

    def sort(self) -> None:
        """Re-sort the pages and relink prev/next; call after changing them."""
        self.pages = sort_pages(self.pages, self.sort_by)
        self.subsections.sort(
            key=lambda sub: (sub.index.weight if sub.index else 0, sub.name)
        )
        last = len(self.pages) - 1
        for position, page in enumerate(self.pages):
            page.prev = self.pages[position - 1] if position > 0 else None
            page.next = self.pages[position + 1] if position < last else None

    def add(self, page: Page) -> None:
        page.section = self
        self.pages.append(page)

    def remove(self, page: Page) -> None:
        if page in self.pages:
            self.pages.remove(page)
