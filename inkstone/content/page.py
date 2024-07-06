from __future__ import annotations

import datetime as dt
import posixpath
from pathlib import Path
from typing import Any

from ..tmpl import Markup
from ..utils import paths
from ..utils import text as textutil

KINDS = ("page", "section", "home", "taxonomy", "term", "404", "virtual")
# kinds that list other pages and therefore get a paginator
LIST_KINDS = ("section", "home", "term")

_IMAGE_EXTENSIONS = frozenset(
    ".png .jpg .jpeg .gif .webp .avif .svg .bmp .ico".split()
)


class Resource:
    """A file that lives next to a page bundle's index.md."""

    def __init__(
        self,
        name: str,
        url: str,
        source_path: str,
        *,
        output_path: str | None = None,
        path: Path | None = None,
    ):
        self.name = name
        self.url = url
        self.source_path = source_path
        self.output_path = output_path or url.lstrip("/")
        # absolute location on disk; None for resources made up by plugins
        self.path = path

    @property
    def ext(self) -> str:
        return posixpath.splitext(self.name)[1].lower()

    @property
    def is_image(self) -> bool:
        return self.ext in _IMAGE_EXTENSIONS

    def __str__(self) -> str:
        return self.url

    def __repr__(self) -> str:
        return f"Resource({self.name!r}, {self.url!r}, {self.source_path!r})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Resource):
            return NotImplemented
        return (self.name, self.url, self.source_path) == (
            other.name,
            other.url,
            other.source_path,
        )

    def __hash__(self) -> int:
        return hash((self.name, self.url, self.source_path))


def output_path_for(url: str) -> str:
    """Where the document behind a site URL is written, relative to the output dir.

    ``/a/`` -> ``a/index.html``, ``/a.html`` and ``/feed.xml`` stay files, and
    ``/a`` (no slash, no extension) is treated like ``/a/`` because a file
    called ``a`` would be served as a download.
    """
    path = paths.url_to_path(url)
    if not posixpath.splitext(posixpath.basename(path))[1]:
        path = posixpath.join(path, "index.html")
    return path


class Page:
    """One output document: a Markdown file or something generated.

    Deliberately a plain class without __slots__: plugins hang their own
    attributes on pages (page.related, page.series...) and templates read them.
    """

    def __init__(
        self,
        *,
        kind: str = "page",
        url: str = "/",
        title: str = "",
        slug: str = "",
        description: str = "",
        date: dt.datetime | None = None,
        updated: dt.datetime | None = None,
        draft: bool = False,
        weight: int = 0,
        source_path: str | None = None,
        file_path: Path | None = None,
        meta: dict | None = None,
        params: dict | None = None,
        taxonomies: dict[str, list[str]] | None = None,
        raw: str = "",
        template: str | None = None,
        aliases: list[str] | None = None,
        resources: list[Resource] | None = None,
        output_path: str | None = None,
        extra_context: dict | None = None,
    ):
        self.kind = kind
        self.url = url
        self.title = title
        self.slug = slug
        self.description = description
        self.date = date
        self.updated = updated
        self.draft = draft
        self.weight = weight
        self.source_path = source_path
        # absolute path of the source file, for plugins that need to stat it
        self.file_path = file_path
        self.meta = meta if meta is not None else {}
        self.params = params if params is not None else {}
        self.taxonomies = taxonomies if taxonomies is not None else {}
        self.raw = raw
        self.content = Markup("")
        self.summary = Markup("")
        # True when the summary is shorter than the content ("read more")
        self.truncated = False
        self.toc: list = []
        self.toc_html = Markup("")
        self.template = template
        self.layout: str | None = None
        self.section = None
        self.site = None
        self.prev: Page | None = None
        self.next: Page | None = None
        self.aliases = aliases if aliases is not None else []
        self.resources = resources if resources is not None else []
        self.extra_context = extra_context if extra_context is not None else {}
        self._output_path = output_path
        self._permalink: str | None = None
        self._word_count: int | None = None
        self._reading_time: int | None = None
        # set once the Markdown body went through the renderer
        self._rendered = False

    @classmethod
    def virtual(
        cls,
        url: str,
        *,
        title: str = "",
        template: str | None = None,
        content: str = "",
        kind: str = "virtual",
        **context: Any,
    ) -> Page:
        """A page without a source file (archives, redirects, list pages).

        Extra keyword arguments become template variables. With
        ``template=None`` the content is written to the output as it is.
        """
        if not url.startswith("/"):
            url = "/" + url
        page = cls(kind=kind, url=url, title=title, template=template)
        page.slug = posixpath.basename(url.rstrip("/"))
        page.content = Markup(content)
        page.extra_context = dict(context)
        page._rendered = True
        return page

    def __repr__(self) -> str:
        return f"<Page {self.kind} {self.url}>"

    @property
    def permalink(self) -> str:
        if self._permalink is not None:
            return self._permalink
        base = getattr(self.site, "base_url", "") or ""
        if not base:
            return self.url
        return paths.url_join(base, self.url)

    @permalink.setter
    def permalink(self, value: str | None) -> None:
        self._permalink = value

    @property
    def output_path(self) -> str:
        if self._output_path is not None:
            return self._output_path
        return output_path_for(self.url)

    @output_path.setter
    def output_path(self, value: str | None) -> None:
        if value is not None:
            value = str(value).replace("\\", "/").lstrip("/")
        self._output_path = value

    @property
    def tags(self) -> list[str]:
        return self.taxonomies.setdefault("tags", [])

    @tags.setter
    def tags(self, value) -> None:
        self.taxonomies["tags"] = list(value)

    @property
    def categories(self) -> list[str]:
        return self.taxonomies.setdefault("categories", [])

    @categories.setter
    def categories(self, value) -> None:
        self.taxonomies["categories"] = list(value)

    @property
    def word_count(self) -> int:
        if self._word_count is not None:
            return self._word_count
        return textutil.word_count(self._plain_text())

    @word_count.setter
    def word_count(self, value: int | None) -> None:
        self._word_count = value

    @property
    def reading_time(self) -> int:
        """Minutes, never less than one."""
        if self._reading_time is not None:
            return self._reading_time
        return max(1, textutil.reading_time(self._plain_text()))

    @reading_time.setter
    def reading_time(self, value: int | None) -> None:
        self._reading_time = value

    def _plain_text(self) -> str:
        if self.content:
            return textutil.strip_html(str(self.content))
        return self.raw

    @property
    def is_page(self) -> bool:
        return self.kind == "page"

    @property
    def is_section(self) -> bool:
        return self.kind == "section"

    @property
    def is_home(self) -> bool:
        return self.kind == "home"

    @property
    def is_list(self) -> bool:
        return self.kind in LIST_KINDS

    @property
    def is_generated(self) -> bool:
        """No source file behind it."""
        return self.source_path is None

    @property
    def filename(self) -> str:
        """File name of the source without extension ("" for generated pages)."""
        if not self.source_path:
            return ""
        stem = posixpath.splitext(posixpath.basename(self.source_path))[0]
        if stem in ("index", "_index"):
            # for bundles and section indexes the directory is the name
            return posixpath.basename(posixpath.dirname(self.source_path))
        return stem

    @property
    def is_bundle(self) -> bool:
        if not self.source_path:
            return False
        name = posixpath.basename(self.source_path).lower()
        return name in ("index.md", "index.markdown")

    def get_resource(self, name: str) -> Resource | None:
        for resource in self.resources:
            if resource.name == name:
                return resource
        return None

    def in_section(self, name: str) -> bool:
        """True for pages of ``name`` and of any section nested below it."""
        section = self.section
        while section is not None:
            if section.name == name:
                return True
            section = section.parent
        return False
