from __future__ import annotations

from inkstone.errors import InkstoneError


class MarkdownError(InkstoneError):
    """Bad parser configuration, or a document we refuse to handle."""
