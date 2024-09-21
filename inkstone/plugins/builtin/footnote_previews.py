"""The text of each footnote, attached to the number that refers to it.

Every footnote reference gets ``data-footnote-preview`` for scripts and a
``title`` so that hovering shows the note even without any. The default
theme's footnotes.js takes the title away again while its own pop-up shows.
"""

from __future__ import annotations

import re

from ..base import Plugin
from . import _html
from ._common import setting

_BACKREF = re.compile(r'<a\b[^>]*class="footnote-backref"[^>]*>.*?</a>', re.S)
_ELLIPSIS = "…"


def shorten(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[: limit - 1]
    # back to the end of a word, unless that throws away most of it
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + _ELLIPSIS


class FootnotePreviews(Plugin):
    name = "footnote_previews"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.max_length = setting(self, "max_length", 280, minimum=0)
        self.title = setting(self, "title", True)
        self.attribute = setting(self, "attribute", "data-footnote-preview")

    def notes(self, markup: str) -> dict[str, str]:
        """Footnote id -> its text, for the footnotes at the end of a page."""
        found = {}
        for item in _html.find_elements(markup, ("li",)):
            anchor = item.tag.get("id") or ""
            if not anchor.startswith("fn-"):
                continue
            body = _BACKREF.sub("", item.inner(markup))
            text = _html.text_content(body)
            if text:
                found[anchor] = shorten(text, self.max_length)
        return found

    def page_html(self, page, html):
        markup = str(html)
        if 'id="fn-' not in markup:
            return html
        notes = self.notes(markup)
        if not notes:
            return html

        def preview(tag: _html.Tag) -> None:
            href = tag.get("href") or ""
            if not href.startswith("#fn-") or "footnote-backref" in tag.classes:
                return
            text = notes.get(href[1:])
            if text is None:
                return
            tag.set(self.attribute, text)
            if self.title:
                tag.setdefault("title", text)

        return _html.rewrite(markup, preview, ("a",))
