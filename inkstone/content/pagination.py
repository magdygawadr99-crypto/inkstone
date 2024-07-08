from __future__ import annotations

from typing import Iterator, Sequence

from ..utils.paths import ensure_trailing_slash, url_join
from .query import PageList


def page_url(base_url: str, number: int, path: str = "page") -> str:
    """URL of page ``number`` of a list: ``/posts/`` and ``/posts/page/2/``."""
    base = ensure_trailing_slash(base_url)
    if number <= 1:
        return base
    return url_join(base, path, str(number)) + "/"


class Paginator:
    """One page of a paginated list, and where its neighbours are."""

    def __init__(
        self,
        items: Sequence,
        *,
        page: int,
        pages: int,
        total: int,
        per_page: int,
        base_url: str,
        path: str = "page",
    ):
        self.items = PageList(items)
        self.page = page
        self.pages = pages
        self.total = total
        self.per_page = per_page
        self.base_url = ensure_trailing_slash(base_url)
        self.path = path

    def __repr__(self) -> str:
        return f"<Paginator {self.base_url} page {self.page}/{self.pages}>"

    def __iter__(self) -> Iterator:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def url_for_page(self, number: int) -> str:
        return page_url(self.base_url, number, self.path)

    @property
    def url(self) -> str:
        return self.url_for_page(self.page)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_url(self) -> str | None:
        return self.url_for_page(self.page - 1) if self.has_prev else None

    @property
    def next_url(self) -> str | None:
        return self.url_for_page(self.page + 1) if self.has_next else None

    @property
    def first_url(self) -> str:
        return self.url_for_page(1)

    @property
    def last_url(self) -> str:
        return self.url_for_page(self.pages)

    @property
    def page_urls(self) -> list[tuple[int, str]]:
        return [(n, self.url_for_page(n)) for n in range(1, self.pages + 1)]

    @property
    def start(self) -> int:
        """1-based position of this page's first item in the whole list (0 if empty)."""
        if not self.items:
            return 0
        return (self.page - 1) * self.per_page + 1

    @property
    def end(self) -> int:
        return self.start + len(self.items) - 1 if self.items else 0

    def window(self, around: int = 2) -> list[tuple[int | None, str | None]]:
        """Page links for long lists: 1 … 4 5 [6] 7 8 … 20.

        Gaps come back as ``(None, None)`` so a template can print an ellipsis.
        """
        keep = {1, self.pages}
        keep.update(range(self.page - around, self.page + around + 1))
        out: list[tuple[int | None, str | None]] = []
        previous = 0
        for number in sorted(n for n in keep if 1 <= n <= self.pages):
            if number - previous > 1:
                out.append((None, None))
            out.append((number, self.url_for_page(number)))
            previous = number
        return out


def paginate(
    items: Sequence, per_page: int | None, base_url: str, path: str = "page"
) -> list[Paginator]:
    """Split ``items`` into pages.

    There is always at least one page, so an empty section still gets its
    list page. ``per_page`` of None or 0 means everything on one page.
    """
    items = list(items)
    total = len(items)
    if not per_page or per_page < 0:
        size = max(total, 1)
    else:
        size = int(per_page)
    count = max(1, -(-total // size))
    return [
        Paginator(
            items[index * size : (index + 1) * size],
            page=index + 1,
            pages=count,
            total=total,
            per_page=size,
            base_url=base_url,
            path=path,
        )
        for index in range(count)
    ]
