"""``rel`` (and optionally ``target`` and a class) on links that leave the site."""

from __future__ import annotations

from urllib.parse import urlsplit

from ..base import Plugin
from . import _html
from ._common import lookup, setting


def _host(url: str) -> str:
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    # example.com and www.example.com are the same site to a reader
    return host[4:] if host.startswith("www.") else host


class ExternalLinks(Plugin):
    name = "external_links"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.rel = setting(self, "rel", "noopener noreferrer").split()
        self.target_blank = setting(self, "target_blank", False)
        self.css_class = setting(self, "class", "").split()
        # content: links in the text of pages. page: also the ones the
        # theme writes (menus, footer).
        self.scope = setting(self, "scope", "content", choices=("content", "page"))
        self.internal = {_host(lookup(config, "base_url") or "")}
        for host in setting(self, "internal", []):
            self.internal.add(_host(host if "//" in host else "//" + host))
        self.internal.discard("")
        if self.target_blank and "noopener" not in self.rel:
            # a new tab without it can reach back into this one
            self.rel.append("noopener")

    def is_external(self, href: str) -> bool:
        href = href.strip()
        try:
            parts = urlsplit(href)
        except ValueError:
            return False
        if parts.scheme not in ("", "http", "https") or not parts.netloc:
            # relative links, and mailto:, tel:, javascript: and friends
            return False
        return _host(href) not in self.internal

    def _mark(self, tag: _html.Tag) -> None:
        href = tag.get("href")
        if not href or not self.is_external(href):
            return
        rel = tag.tokens("rel")
        missing = [token for token in self.rel if token not in rel]
        if missing:
            tag.set("rel", " ".join(rel + missing))
        if self.target_blank:
            tag.setdefault("target", "_blank")
        if self.css_class:
            tag.add_class(*self.css_class)

    def rewrite(self, markup: str) -> str:
        if "<a" not in markup:
            return markup
        return _html.rewrite(markup, self._mark, ("a",))

    def page_html(self, page, html):
        if self.scope != "content":
            return html
        return self.rewrite(str(html))

    def page_output(self, page, html):
        if self.scope != "page":
            return html
        path = getattr(page, "output_path", "") or ""
        if not path.endswith((".html", ".htm")):
            return html
        return self.rewrite(html)
