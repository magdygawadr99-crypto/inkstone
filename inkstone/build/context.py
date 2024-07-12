"""What templates get to see: the per-page context, global functions, filters."""

from __future__ import annotations

import datetime as dt
import threading
from typing import Any

from .. import __version__
from ..content import summary as summaries
from ..tmpl import Markup, Undefined
from ..tmpl.filters import FILTERS as BUILTIN_FILTERS
from ..utils import dates, paths
from ..utils import text as textutil

GLOBAL_NAMES = (
    "url_for",
    "absolute_url",
    "asset",
    "asset_integrity",
    "get_page",
    "get_section",
    "get_data",
    "highlight_css",
)
FILTER_NAMES = (
    "markdown",
    "date",
    "slugify",
    "absolute_url",
    "relative_url",
    "strip_html",
    "truncate_html",
    "reading_time",
    "humanize_bytes",
)


def _blank(value) -> bool:
    return value is None or isinstance(value, Undefined) or value == ""


def _as_path(value) -> str:
    """Accept a URL string or anything that has one (pages, sections, terms)."""
    if _blank(value):
        return ""
    if isinstance(value, str):
        return str(value)
    url = getattr(value, "url", None)
    return str(url) if isinstance(url, str) else str(value)


class AssetTracker:
    """Remembers which assets the page being rendered asked for.

    A page that was skipped as unchanged still has the old asset URLs baked
    in; when fingerprinting gives a stylesheet a new name, the pages that
    link it have to be rendered again. The record made here is how the
    cache finds them.
    """

    def __init__(self):
        self._local = threading.local()

    def start(self) -> None:
        self._local.seen = {}

    def note(self, kind: str, path: str, answer: str) -> None:
        seen = getattr(self._local, "seen", None)
        if seen is not None:
            seen[f"{kind}:{path}"] = answer

    def finish(self) -> dict[str, str]:
        seen = getattr(self._local, "seen", None) or {}
        self._local.seen = None
        return dict(seen)


class TemplateHelpers:
    """The functions and filters added to the template environment.

    They are bound to the builder rather than to one build, so the same
    objects stay registered while `inkstone serve` rebuilds again and again.
    """

    def __init__(self, builder):
        self.builder = builder
        self.tracker = AssetTracker()
        self._warned: set[str] = set()

    @property
    def config(self):
        return self.builder.config

    def url_for(self, path="/") -> str:
        """Site-relative URL: ``/about/`` -> ``/blog/about/`` under a sub-path."""
        target = _as_path(path)
        if not target:
            return self.config.base_path
        if paths.is_external(target) or target.startswith(("#", "?")):
            return target
        return paths.url_join(self.config.base_path, target)

    def absolute_url(self, path="/") -> str:
        """The same with scheme and host, for feeds and Open Graph tags."""
        target = _as_path(path)
        if target and (paths.is_external(target) or target.startswith("#")):
            return target
        return paths.url_join(self.config.base_url, target or "/")

    def asset(self, path) -> str:
        """URL of a static file, with its fingerprint when there is one."""
        logical = _as_path(path).lstrip("/")
        if not logical or paths.is_external(logical):
            return _as_path(path)
        output = self.builder.asset_output(logical)
        if output is None:
            self._warn_missing(logical)
            output = logical
        url = self.url_for("/" + output)
        self.tracker.note("asset", logical, url)
        return url

    def asset_integrity(self, path) -> str:
        """``sha384-...`` for an ``integrity`` attribute ("" for unknown files)."""
        logical = _as_path(path).lstrip("/")
        value = self.builder.asset_integrity(logical) or ""
        if not value:
            self._warn_missing(logical)
        self.tracker.note("integrity", logical, value)
        return value

    def reset(self) -> None:
        """Start of a build: warn about missing assets afresh."""
        self._warned.clear()

    def _warn_missing(self, logical: str) -> None:
        # outside a build (a plugin rendering a template in setup, say) there
        # is no manifest to be missing from
        if logical in self._warned or not self.builder.assets_built:
            return
        self._warned.add(logical)
        self.builder.warn(
            f"asset({logical!r}): no such file in static/ or the theme's static/"
        )

    def get_page(self, path):
        site = self.builder.site
        return site.get_page(_as_path(path)) if site is not None else None

    def get_section(self, name):
        site = self.builder.site
        return site.get_section(_as_path(name)) if site is not None else None

    def get_data(self, dotted, default=None):
        site = self.builder.site
        if site is None or _blank(dotted):
            return default
        return site.get_data(str(dotted), default)

    def highlight_css(self, style=None) -> Markup:
        from .generators import highlight_css

        name = None if _blank(style) else str(style)
        # Markup, or the quotes in the CSS would be escaped inside <style>
        return Markup(highlight_css(self.config, style=name))

    def markdown_filter(self, value) -> Markup:
        if _blank(value):
            return Markup("")
        return self.builder.render_markdown(str(value))

    def date_filter(self, value, fmt: str = "%Y-%m-%d") -> str:
        """Named formats ("long", "iso", "rfc3339"...) or a strftime pattern."""
        if _blank(value):
            return ""
        if "%" in fmt:
            # the engine's own filter knows about "now", timestamps and %-d
            return BUILTIN_FILTERS["date"](value, fmt)
        if value == "now":
            value = dt.datetime.now(self.config.tzinfo)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            value = dt.datetime.fromtimestamp(value, self.config.tzinfo)
        return dates.format_date(value, fmt)

    def relative_url_filter(self, value) -> str:
        return self.url_for(value)

    def install(self, env) -> None:
        env.globals.update(
            url_for=self.url_for,
            absolute_url=self.absolute_url,
            asset=self.asset,
            asset_integrity=self.asset_integrity,
            get_page=self.get_page,
            get_section=self.get_section,
            get_data=self.get_data,
            highlight_css=self.highlight_css,
            inkstone={"version": __version__},
        )
        env.filters.update(
            markdown=self.markdown_filter,
            date=self.date_filter,
            slugify=slugify_filter,
            absolute_url=self.absolute_url,
            relative_url=self.relative_url_filter,
            strip_html=strip_html_filter,
            truncate_html=truncate_html_filter,
            reading_time=reading_time_filter,
            humanize_bytes=humanize_bytes_filter,
        )


def slugify_filter(value, sep: str = "-") -> str:
    return "" if _blank(value) else textutil.slugify(str(value), sep=sep)


def strip_html_filter(value) -> str:
    return "" if _blank(value) else textutil.strip_html(str(value))


def truncate_html_filter(value, length: int = 300, suffix: str = "…") -> Markup:
    if _blank(value):
        return Markup("")
    return Markup(summaries.truncate_html(str(value), int(length), suffix))


def reading_time_filter(value, wpm: int = 220) -> int:
    """Minutes to read some text or HTML; at least 1 unless there is nothing."""
    if _blank(value):
        return 0
    text = str(value)
    if "<" in text:
        text = textutil.strip_html(text)
    return textutil.reading_time(text, wpm=int(wpm))


def humanize_bytes_filter(value) -> str:
    if _blank(value):
        return ""
    return textutil.humanize_bytes(int(value))


def page_context(builder, page) -> dict[str, Any]:
    """The variables a page's template is rendered with."""
    site = builder.site
    context: dict[str, Any] = {
        "site": site,
        "config": builder.config,
        "page": page,
        "now": site.build_time,
        "inkstone": {"version": __version__},
    }
    if page.section is not None:
        context["section"] = page.section
    # generated pages bring their own: paginator, pages, taxonomy, term, and
    # whatever a plugin passed to Page.virtual()
    context.update(page.extra_context)
    return context
