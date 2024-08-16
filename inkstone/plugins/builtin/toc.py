"""Table of contents: page.toc and page.toc_html, cut to the wanted levels.

The Markdown parser already collects headings, all of them. This plugin
rebuilds the list from the rendered HTML instead, so that it also sees
headings that came out of shortcodes, and keeps only the configured range.
A ``[TOC]`` marker in the text gets the same trimmed list.
"""

from __future__ import annotations

import re

from ...errors import PluginError
from ...markdown import TocEntry, render_toc
from ...tmpl import Markup
from ..base import Plugin
from . import _html
from ._common import front_matter, setting

_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# what the Markdown renderer writes for a [TOC] marker
_MARKER_NAV = re.compile(r'<nav class="toc">\n.*?</nav>\n?', re.S)
_INSERT_CHOICES = ("", "top", "before-first-heading")


def build_tree(headings: list[tuple[int, str, str]]) -> list[TocEntry]:
    """Nest ``(level, id, title)`` rows by level.

    A heading goes under the closest earlier one with a lower level, so
    jumping from h2 straight to h4 still gives a sensible tree.
    """
    roots: list[TocEntry] = []
    stack: list[TocEntry] = []
    for level, anchor, title in headings:
        entry = TocEntry(level, anchor, title)
        while stack and stack[-1].level >= level:
            stack.pop()
        (stack[-1].children if stack else roots).append(entry)
        stack.append(entry)
    return roots


class Toc(Plugin):
    name = "toc"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.min_level = setting(self, "min_level", 2)
        self.max_level = setting(self, "max_level", 3)
        self._check_levels(self.min_level, self.max_level, "[plugin.toc]")
        # fewer headings than this and the page gets no table of contents
        self.min_items = setting(self, "min_items", 1, minimum=1)
        self.insert = setting(self, "insert", "", choices=_INSERT_CHOICES)
        self.anchors = setting(self, "anchors", False)
        self.anchor_text = setting(self, "anchor_text", "¶")
        self.anchor_class = setting(self, "anchor_class", "heading-anchor")
        self.anchor_position = setting(
            self, "anchor_position", "after", choices=("after", "before")
        )

    @staticmethod
    def _check_levels(low, high, where: str) -> None:
        for value in (low, high):
            if isinstance(value, bool) or not isinstance(value, int):
                raise PluginError(f"{where}: heading levels must be numbers")
        if not 1 <= low <= high <= 6:
            raise PluginError(
                f"{where}: min_level and max_level must satisfy "
                f"1 <= min <= max <= 6, got {low} and {high}"
            )

    def _levels(self, page) -> tuple[bool, int, int]:
        """(enabled, min_level, max_level) for one page.

        ``toc: false`` in the front matter switches the list off, a table
        such as ``toc: {max_level: 4}`` changes the range for that page.
        """
        wanted = front_matter(page, "toc")
        if wanted is False:
            return False, self.min_level, self.max_level
        if isinstance(wanted, dict):
            low = wanted.get("min_level", self.min_level)
            high = wanted.get("max_level", self.max_level)
            source = getattr(page, "source_path", None) or "front matter"
            self._check_levels(low, high, f"{source}: toc")
            return True, low, high
        return True, self.min_level, self.max_level

    def page_html(self, page, html):
        markup = str(html)
        enabled, low, high = self._levels(page)
        headings = _html.find_elements(markup, _HEADINGS)
        rows = []
        for heading in headings:
            level = int(heading.tag.name[1])
            anchor = heading.tag.get("id")
            if anchor and low <= level <= high:
                rows.append((level, anchor, _html.text_content(heading.inner(markup))))
        tree = build_tree(rows)
        nav = f'<nav class="toc">\n{render_toc(tree)}</nav>\n' if tree else ""
        listed = enabled and len(rows) >= self.min_items

        if page is not None:
            page.toc = tree if listed else []
            page.toc_html = Markup(render_toc(tree)) if listed else Markup("")

        if self.anchors:
            markup = self._add_anchors(markup, headings, low)
        if _MARKER_NAV.search(markup):
            # written by hand, so it stays even when the sidebar list is off
            markup = _MARKER_NAV.sub(lambda match: nav, markup)
        elif self.insert and listed:
            markup = self._insert(markup, nav, low, high)
        return markup

    def _insert(self, markup: str, nav: str, low: int, high: int) -> str:
        if self.insert == "before-first-heading":
            # looked up again: adding anchors has moved things
            for heading in _html.find_elements(markup, _HEADINGS):
                if low <= int(heading.tag.name[1]) <= high:
                    return markup[: heading.start] + nav + markup[heading.start :]
        return nav + markup

    def _anchor(self, target: str) -> str:
        return (
            f'<a class="{_html.escape(self.anchor_class)}" '
            f'href="#{_html.escape(target)}" aria-label="Link to this section">'
            f"{_html.escape(self.anchor_text)}</a>"
        )

    def _add_anchors(self, markup: str, headings, low: int) -> str:
        """Put a link to itself into every heading that has an id."""
        # back to front, so the offsets of earlier headings stay valid
        for heading in reversed(headings):
            target = heading.tag.get("id")
            if not target or int(heading.tag.name[1]) < low:
                continue
            if self.anchor_class in heading.inner(markup):
                continue
            link = self._anchor(target)
            if self.anchor_position == "before":
                at = heading.inner_start
                link += " "
            else:
                at = heading.inner_end
                link = " " + link
            markup = markup[:at] + link + markup[at:]
        return markup
