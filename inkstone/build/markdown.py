"""The Markdown converter as the site configures it."""

from __future__ import annotations

import posixpath
import re
import threading
from typing import Callable, NamedTuple

from ..errors import BuildError, ConfigError
from ..markdown import Link, Markdown, MarkdownError, TocEntry, render_toc
from ..utils import log
from ..utils.paths import is_external

_MD_TARGET = re.compile(r"\.(?:md|markdown)\Z", re.I)
# cheap scan of raw Markdown for link targets ending in .md, for cache keys:
# "](other.md)", "](../a/b.md#part)", "[ref]: other.md"
_MD_LINK = re.compile(
    r"(?:\]\(\s*<?|^\s{0,3}\[[^\]]+\]:\s*<?)([^)\s>]+?\.(?:md|markdown))(?=[#?)\s>]|$)",
    re.I | re.M,
)


class Rendered(NamedTuple):
    html: str
    toc: list[TocEntry]
    toc_html: str


def split_target(dest: str) -> tuple[str, str]:
    """Separate a link target from its ?query and #fragment."""
    for index, char in enumerate(dest):
        if char in "?#":
            return dest[:index], dest[index:]
    return dest, ""


def markdown_link_targets(raw: str) -> list[str]:
    """Targets of links to other Markdown files, as written in the source."""
    return sorted({match.group(1) for match in _MD_LINK.finditer(raw)})


def resolve_source(target: str, from_source: str) -> str | None:
    """Content-relative path a ``.md`` link points at, None if it leaves the tree."""
    if target.startswith("/"):
        joined = target.lstrip("/")
    else:
        joined = posixpath.join(posixpath.dirname(from_source), target)
    path = posixpath.normpath(joined)
    if path.startswith("..") or path == ".":
        return None
    return path


def make_highlighter(config) -> Callable | None:
    """The callback the Markdown renderer uses for fenced code blocks."""
    if not config.markdown.highlight:
        return None
    from ..highlight import HighlightError, highlight

    def highlight_block(code: str, lang: str | None, attrs: dict | None = None):
        if not lang:
            # nothing to colour; the plain <pre><code> is the better markup
            return None
        attrs = attrs or {}
        options = {}
        linenos = str(attrs.get("linenos", "")).lower()
        if linenos and linenos not in ("false", "no", "off", "0"):
            options["linenos"] = "inline" if linenos == "inline" else True
        if attrs.get("hl_lines"):
            options["hl_lines"] = attrs["hl_lines"]
        if attrs.get("linenostart"):
            try:
                options["line_start"] = int(attrs["linenostart"])
            except (TypeError, ValueError):
                pass
        filename = attrs.get("filename") or attrs.get("title")
        if filename:
            options["filename"] = str(filename)
        try:
            return highlight(code, lang, **options)
        except HighlightError as exc:
            # a typo in hl_lines should not take the build down
            log.once("code block (%s): %s; not highlighted", lang, exc.message)
            return None

    return highlight_block


def make_markdown(config) -> Markdown:
    """A converter set up from the ``[markdown]`` table of the config."""
    settings = config.markdown
    extensions = list(settings.extensions) or None
    try:
        return Markdown(
            extensions=extensions,
            highlight=make_highlighter(config),
            heading_ids=bool(settings.heading_ids),
            smart=bool(settings.smart),
            hard_wraps=bool(settings.hard_wraps),
        )
    except MarkdownError as exc:
        raise ConfigError(
            f"markdown.extensions: {exc.message}", path=config.path
        ) from None


class MarkdownRenderer:
    """Renders pages and loose snippets with the site's Markdown settings.

    A Markdown object remembers the last document it parsed, so every thread
    gets its own.
    """

    def __init__(self, config, *, url_for: Callable[[str], str] | None = None):
        self.config = config
        self.url_for = url_for or (lambda url: url)
        self.site = None
        self._local = threading.local()
        # fail on bad extension names now rather than on the first page
        self._local.markdown = make_markdown(config)

    def converter(self) -> Markdown:
        markdown = getattr(self._local, "markdown", None)
        if markdown is None:
            markdown = self._local.markdown = make_markdown(self.config)
        return markdown

    def render(self, text: str, page=None) -> Rendered:
        """Convert Markdown; with a page, links to other ``.md`` files are fixed up."""
        markdown = self.converter()
        try:
            doc = markdown.parse(text)
            if page is not None and page.source_path and self.site is not None:
                self._rewrite_links(doc, page)
            html = markdown.render(doc)
        except MarkdownError as exc:
            source = page.source_path if page is not None else None
            raise BuildError(exc.message, path=source, line=exc.line) from None
        toc = list(markdown.toc)
        return Rendered(html, toc, render_toc(toc))

    def render_inline(self, text: str) -> str:
        return self.converter().convert_inline(text)

    def link_signature(self, page) -> list[tuple[str, str]]:
        """What the ``.md`` links of a page currently resolve to.

        Part of the page's cache key: when a linked page moves, the page
        linking to it has to be rendered again.
        """
        if self.site is None or not page.source_path:
            return []
        pairs = []
        for target in markdown_link_targets(page.raw):
            found = self._lookup(split_target(target)[0], page)
            pairs.append((target, found.url if found is not None else ""))
        return pairs

    def _lookup(self, target: str, page):
        source = resolve_source(target, page.source_path)
        if source is None:
            return None
        found = self.site.get_page(source)
        if found is not None and found.source_path == source:
            return found
        return None

    def _rewrite_links(self, doc, page) -> None:
        for link in doc.find_all(Link):
            dest = link.dest
            if not dest or dest.startswith("#") or is_external(dest):
                continue
            target, suffix = split_target(dest)
            if not _MD_TARGET.search(target):
                continue
            found = self._lookup(target, page)
            if found is None:
                log.once(
                    "%s: link to %s, which is not a page of this site",
                    page.source_path,
                    dest,
                )
                continue
            link.dest = self.url_for(found.url) + suffix
