from __future__ import annotations

import datetime as dt
import posixpath

from ..utils.collections import AttrDict, get_path
from ..utils.paths import ensure_trailing_slash
from .menus import Menus, build_menus
from .page import LIST_KINDS, Page, Resource
from .pagination import Paginator, paginate
from .query import PageList
from .section import Section, sort_pages
from .taxonomy import Taxonomy, build_taxonomies


class Site:
    """Everything that was loaded: pages, sections, taxonomies, data, menus."""

    def __init__(self, config, *, build_time: dt.datetime | None = None):
        self.config = config
        self.build_time = build_time or dt.datetime.now(config.tzinfo)
        self.pages = PageList()
        self.all_pages: list[Page] = []
        self.sections: dict[str, Section] = {}
        self.home: Page | None = None
        self.taxonomies: dict[str, Taxonomy] = {}
        self.data = AttrDict()
        self.menus = Menus()
        # loose files from the content directory that are copied as they are
        self.resources: list[Resource] = []
        # source paths left out of this build, by reason ("draft", "future")
        self.skipped: dict[str, list[str]] = {"draft": [], "future": []}
        # non-fatal problems noticed while loading; validate_site() reports them
        self.problems: list = []
        self.warnings: list[str] = []
        self._by_url: dict[str, Page] = {}
        self._by_source: dict[str, Page] = {}

    def __repr__(self) -> str:
        return f"<Site {self.title!r}: {len(self.pages)} pages>"

    @property
    def title(self) -> str:
        return self.config.title

    @property
    def description(self) -> str:
        return self.config.description

    @property
    def base_url(self) -> str:
        return self.config.base_url

    @property
    def language(self) -> str:
        return self.config.language

    @property
    def author(self):
        return self.config.author

    @property
    def params(self):
        return self.config.params

    def add_page(self, page: Page) -> Page:
        """Register a page so that it gets written (and found by get_page)."""
        if page.site is self and page in self.all_pages:
            return page
        page.site = self
        self.all_pages.append(page)
        self._by_url.setdefault(page.url, page)
        if page.source_path:
            self._by_source[page.source_path] = page
        if page.kind == "page":
            self.pages.append(page)
        return page

    def remove_page(self, page: Page) -> None:
        if page in self.all_pages:
            self.all_pages.remove(page)
        if page in self.pages:
            self.pages.remove(page)
        if self._by_url.get(page.url) is page:
            del self._by_url[page.url]
        if page.source_path and self._by_source.get(page.source_path) is page:
            del self._by_source[page.source_path]
        if page.section is not None and page.kind == "page":
            page.section.remove(page)

    def get_page(self, path_or_url: str) -> Page | None:
        """Find a page by source path (``posts/hello.md``) or URL (``/about/``)."""
        if not path_or_url:
            return None
        key = str(path_or_url).replace("\\", "/")
        if key.startswith("/"):
            found = self._lookup_url(key)
            if found is not None:
                return found
            key = key.lstrip("/")
        while key.startswith("./"):
            key = key[2:]
        content_dir = str(self.config.content_dir).strip("/") + "/"
        candidates = [key]
        if key.startswith(content_dir):
            candidates.append(key[len(content_dir) :])
        for candidate in candidates:
            for name in (
                candidate,
                candidate + ".md",
                posixpath.join(candidate, "index.md"),
                posixpath.join(candidate, "_index.md"),
            ):
                if name in self._by_source:
                    return self._by_source[name]
        return self._lookup_url("/" + key)

    def _lookup_url(self, url: str) -> Page | None:
        url = url.partition("#")[0].partition("?")[0]
        for candidate in (url, ensure_trailing_slash(url), url.rstrip("/") or "/"):
            if candidate in self._by_url:
                return self._by_url[candidate]
        # plugins may have changed URLs after the page was registered
        for page in self.all_pages:
            if page.url in (url, ensure_trailing_slash(url)):
                return page
        return None

    def get_section(self, name: str) -> Section | None:
        if not name:
            return None
        return self.sections.get(str(name).strip("/"))

    def get_data(self, dotted: str, default=None):
        """``get_data("team.roles")``; missing levels give the default."""
        return get_path(self.data, dotted, default)

    def pages_by_date(self, newest_first: bool = True) -> PageList:
        """Regular pages that have a date, in date order."""
        return self.pages.dated().sort_by("date", reverse=newest_first)

    @property
    def top_sections(self) -> list[Section]:
        return [section for section in self.sections.values() if section.parent is None]

    def refresh(self) -> None:
        """Rebuild the derived structures after pages were added or changed.

        Called once after loading and again by the builder after plugins had
        their say: order of site.pages, section order with prev/next,
        taxonomies and menus.
        """
        self.pages = sort_pages(self.pages, "date")
        for section in self.sections.values():
            section.sort()
        self.taxonomies = build_taxonomies(self.config.taxonomies, self.pages)
        menu_pages = [
            page
            for page in self.all_pages
            if "menu" in page.meta and not getattr(page, "_list_generated", False)
        ]
        self.menus = build_menus(self.config.menus, menu_pages)
        self._by_url = {}
        for page in self.all_pages:
            self._by_url.setdefault(page.url, page)

    def list_items(self, page: Page) -> PageList:
        """What a list page lists (before pagination)."""
        if page.kind == "section" and page.section is not None:
            return page.section.pages
        if page.kind == "home":
            wanted = list(self.config.feeds.sections)
            pages = self.pages.dated() if not wanted else self.pages
            if wanted:
                pages = pages.filter(
                    lambda p: any(p.in_section(name) for name in wanted)
                )
            return sort_pages(pages, "date")
        if page.kind == "term":
            term = page.extra_context.get("term")
            return term.pages if term is not None else PageList()
        return PageList()

    def generate_list_pages(self) -> list[Page]:
        """Create taxonomy and term pages and split every list into pages.

        Page one of a section or of the home page is the page that already
        exists; later ones are copies at ``/posts/page/2/``. Safe to call
        again: pages from an earlier call are dropped first.
        """
        for page in [p for p in self.all_pages if getattr(p, "_list_generated", False)]:
            self.remove_page(page)
        created: list[Page] = []
        default_size = self.config.pagination.per_page
        path = self.config.pagination.path

        if self.home is not None:
            size = getattr(self.home, "paginate", None)
            created += self._paginate(
                self.home, default_size if size is None else size, path
            )
        for section in self.sections.values():
            if section.index is None:
                continue
            size = section.paginate if section.paginate is not None else default_size
            created += self._paginate(section.index, size, path)
        for taxonomy in self.taxonomies.values():
            listing = Page.virtual(
                taxonomy.url,
                title=taxonomy.name.replace("-", " ").replace("_", " ").title(),
                kind="taxonomy",
                taxonomy=taxonomy,
            )
            listing._list_generated = True
            self.add_page(listing)
            created.append(listing)
            for term in taxonomy:
                first = Page.virtual(
                    term.url, title=term.name, kind="term", taxonomy=taxonomy, term=term
                )
                first._list_generated = True
                self.add_page(first)
                created.append(first)
                created += self._paginate(first, default_size, path)
        return created

    def _paginate(self, first: Page, per_page: int | None, path: str) -> list[Page]:
        paginators = paginate(self.list_items(first), per_page, first.url, path)
        self._attach(first, paginators[0])
        extra = []
        for paginator in paginators[1:]:
            page = _clone_list_page(first, paginator.url)
            self._attach(page, paginator)
            page._list_generated = True
            self.add_page(page)
            extra.append(page)
        return extra

    @staticmethod
    def _attach(page: Page, paginator: Paginator) -> None:
        page.paginator = paginator
        page.extra_context["paginator"] = paginator
        page.extra_context["pages"] = paginator.items


def _clone_list_page(first: Page, url: str) -> Page:
    """Page two and later of a list: same title and text, another URL."""
    assert first.kind in LIST_KINDS
    page = Page(
        kind=first.kind,
        url=url,
        title=first.title,
        slug=first.slug,
        description=first.description,
        draft=first.draft,
        weight=first.weight,
        meta=first.meta,
        params=first.params,
        template=first.template,
    )
    page.section = first.section
    page.content = first.content
    page.summary = first.summary
    page.toc = first.toc
    page.toc_html = first.toc_html
    page.extra_context = dict(first.extra_context)
    # where the text came from, without claiming the source file as its own
    page.first_page = first
    page._rendered = True
    return page
