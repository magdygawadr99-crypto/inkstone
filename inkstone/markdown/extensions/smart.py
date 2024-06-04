from __future__ import annotations

from ..inlines import InlineParser
from . import Extension


class SmartExtension(Extension):
    """Typographic punctuation: curly quotes, dashes and ellipses.

    The work happens in the inline parser, since quotes are matched up with
    the same machinery as emphasis; this only switches it on. Same thing as
    ``Markdown(smart=True)``.
    """

    name = "smart"

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.smart = True
