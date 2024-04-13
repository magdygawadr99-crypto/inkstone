from __future__ import annotations

import re

from ..nodes import Document, ListItem, Paragraph
from . import Extension

_CHECKBOX = re.compile(r"\[([ xX])\][ \t]+(?=\S)")


class TaskListsExtension(Extension):
    """``- [ ] todo`` and ``- [x] done`` list items."""

    name = "tasklists"

    def before_inlines(self, doc: Document) -> None:
        for item in doc.find_all(ListItem):
            first = item.children[0] if item.children else None
            if not isinstance(first, Paragraph) or first.raw is None:
                continue
            m = _CHECKBOX.match(first.raw)
            if m is None:
                continue
            item.checked = m.group(1) != " "
            first.raw = first.raw[m.end() :]
