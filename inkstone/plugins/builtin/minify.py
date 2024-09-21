"""Minify each HTML page as it is written.

``build.minify`` does this too, and CSS and JS on top. The plugin is for
small HTML next to untouched assets, so when the build option is on it
steps aside rather than doing the work twice.
"""

from __future__ import annotations

from ...assets import AssetError, minify_html
from ...utils import log
from ..base import Plugin
from ._common import lookup, setting


class Minify(Plugin):
    name = "minify"
    # after everybody else is done with the document
    priority = 900

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.options = {
            "remove_comments": setting(self, "remove_comments", True),
            "collapse_whitespace": setting(self, "collapse_whitespace", True),
            "remove_attribute_quotes": setting(self, "remove_attribute_quotes", False),
            "minify_css": setting(self, "inline_css", True),
            "minify_js": setting(self, "inline_js", True),
        }

    def page_output(self, page, html):
        if lookup(lookup(self.config, "build"), "minify"):
            return html
        path = getattr(page, "output_path", "") or ""
        if not path.endswith((".html", ".htm")):
            return html
        try:
            return minify_html(html, path=path, **self.options)
        except AssetError as exc:
            # broken markup is not ours to fix; ship the page as it is
            log.warning("minify: %s left alone: %s", path, exc.message)
            return html
