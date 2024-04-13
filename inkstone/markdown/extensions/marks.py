from __future__ import annotations

from ..inlines import InlineParser
from ..nodes import Mark, Strikethrough, Subscript, Superscript
from . import Extension

# These all work the same way: a run of marker characters on each side, with
# the same flanking rules as emphasis deciding what may open and close.


class StrikethroughExtension(Extension):
    """``~~gone~~``, and like GitHub also ``~gone~``."""

    name = "strikethrough"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_mark("~", 1, Strikethrough)
        parser.add_mark("~", 2, Strikethrough)


class MarkExtension(Extension):
    """``==highlighted==``"""

    name = "mark"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_mark("=", 2, Mark)


class SubscriptExtension(Extension):
    """``H~2~O``. Takes the single tilde away from strikethrough."""

    name = "sub"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_mark("~", 1, Subscript)


class SuperscriptExtension(Extension):
    """``x^2^``"""

    name = "sup"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_mark("^", 1, Superscript)
