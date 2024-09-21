"""A banner across the top of draft pages.

Drafts only exist in builds made with ``--drafts``, which is exactly when
it is easy to mistake one for the real thing (or to deploy it).
"""

from __future__ import annotations

import re

from ..base import Plugin
from . import _html
from ._common import setting

_BODY = re.compile(r"<body\b[^>]*>", re.I)

# Inline so the banner shows whatever the theme's stylesheet does or
# does not know about it.
_STYLE = (
    "position:sticky;top:0;z-index:1000;padding:.35em 1em;"
    "background:#b3261e;color:#fff;font:600 .875rem/1.4 system-ui,sans-serif;"
    "text-align:center"
)


class DraftsBanner(Plugin):
    name = "drafts_banner"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.text = setting(self, "text", "Draft: not published")
        self.css_class = setting(self, "class", "draft-banner")
        # set to "" when the site's own CSS styles the class
        self.style = setting(self, "style", _STYLE)

    def banner(self) -> str:
        attrs = f' class="{_html.escape(self.css_class)}" role="status"'
        if self.style:
            attrs += f' style="{_html.escape(self.style)}"'
        return f"<div{attrs}>{_html.escape(self.text)}</div>"

    def page_output(self, page, html):
        if not getattr(page, "draft", False):
            return html
        body = _BODY.search(html)
        if body is None:
            # not an HTML document (a feed, a redirect stub without a body)
            return html
        return html[: body.end()] + "\n" + self.banner() + html[body.end() :]
