"""Redirect pages for ``aliases`` and for a table of old URLs in the config.

A static host cannot answer with a 301, so each old address gets a tiny
page that sends the browser on: a meta refresh (which search engines treat
as a move), a canonical link, and a line of script that keeps the #fragment.

    [plugin.redirects]
    netlify = true            # also write a _redirects file

    [plugin.redirects.map]
    "/feed/" = "/rss.xml"
    "/talks/" = "https://example.org/talks/"
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass

from ...content import Page
from ...utils import log, paths
from ..base import Plugin
from . import _html
from ._common import absolute_url, lookup, setting

_STATUSES = (301, 302, 307, 308)


@dataclass
class Redirect:
    source: str
    # a site URL starting with "/", or an absolute one for other hosts
    target: str
    title: str = ""


def normalise(url: str) -> str:
    """An old address as a site URL: leading slash, no query or fragment."""
    url = "/" + url.strip().partition("#")[0].partition("?")[0].lstrip("/")
    tidy = posixpath.normpath(url)
    return tidy + "/" if url.endswith("/") and tidy != "/" else tidy


def redirect_page(target: str, title: str = "", language: str = "en") -> str:
    """The HTML document that forwards to ``target``."""
    href = _html.escape(target)
    # "</" must not appear inside a script element
    script_target = json.dumps(target).replace("</", "<\\/")
    heading = _html.escape(title) if title else "This page has moved"
    return (
        "<!doctype html>\n"
        f'<html lang="{_html.escape(language)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{heading}</title>\n"
        f'<link rel="canonical" href="{href}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<meta http-equiv="refresh" content="0; url={href}">\n'
        "</head>\n"
        "<body>\n"
        f'<p>This page has moved to <a href="{href}">{href}</a>.</p>\n'
        f"<script>location.replace({script_target} + location.hash);</script>\n"
        "</body>\n"
        "</html>\n"
    )


class Redirects(Plugin):
    name = "redirects"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.map = setting(self, "map", {})
        self.html = setting(self, "html", True)
        self.netlify = setting(self, "netlify", False)
        self.status = setting(self, "status", 301, choices=_STATUSES)
        self._found: list[Redirect] | None = None

    def content_loaded(self, site) -> None:
        self._found = None

    def collect(self, site) -> list[Redirect]:
        """Every redirect of the site, conflicts dropped, sorted by old URL."""
        if self._found is not None:
            return self._found
        taken = {page.url for page in site.all_pages}
        for taxonomy in getattr(site, "taxonomies", {}).values():
            taken.add(taxonomy.url)
            taken.update(term.url for term in taxonomy.terms.values())
        found: dict[str, Redirect] = {}

        def add(source: str, target: str, title: str, origin: str) -> None:
            if source == target:
                return
            if source in taken:
                log.warning(
                    "redirects: %s wants %s, which is the URL of a page; skipped",
                    origin,
                    source,
                )
            elif source in found:
                if found[source].target != target:
                    log.warning(
                        "redirects: %s is redirected twice, keeping the one to %s",
                        source,
                        found[source].target,
                    )
            else:
                found[source] = Redirect(source, target, title)

        for page in sorted(site.all_pages, key=lambda page: page.url):
            origin = getattr(page, "source_path", None) or page.url
            for alias in getattr(page, "aliases", None) or ():
                add(normalise(alias), page.url, page.title, origin)
        for source, target in sorted(self.map.items()):
            target = self._target(site, str(target))
            add(normalise(str(source)), target, "", "the config")
        self._found = [found[source] for source in sorted(found)]
        return self._found

    def _target(self, site, target: str) -> str:
        if paths.is_external(target) or target.startswith("/"):
            return target
        # anything else is taken to be a content path: posts/new-home.md
        page = site.get_page(target)
        if page is not None:
            return page.url
        log.warning("redirects: no page found for %r, using it as a URL", target)
        return "/" + target

    def generate_pages(self, site):
        if not self.html:
            return
        language = lookup(self.config, "language") or "en"
        for redirect in self.collect(site):
            target = absolute_url(self.config, redirect.target)
            page = Page.virtual(
                redirect.source,
                title=redirect.title,
                content=redirect_page(target, redirect.title, language),
            )
            page.redirect_to = redirect.target
            yield page

    def extra_files(self, site):
        if not self.netlify:
            return
        redirects = self.collect(site)
        if not redirects:
            return
        width = max(len(redirect.source) for redirect in redirects)
        lines = [
            f"{redirect.source.ljust(width)}  {redirect.target}  {self.status}"
            for redirect in redirects
        ]
        yield "_redirects", "\n".join(lines) + "\n"
