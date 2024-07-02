from __future__ import annotations

from ..errors import InkstoneError


class HighlightError(InkstoneError):
    """Unknown language or style, or a broken lexer/style definition."""
