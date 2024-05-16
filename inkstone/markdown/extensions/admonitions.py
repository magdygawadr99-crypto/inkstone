from __future__ import annotations

import re

from ..blocks import CONTAINER, CONTINUE, NO_MATCH, STOP, BlockParser, ContainerRule
from ..nodes import Admonition, Block
from . import Extension

_OPENER = re.compile(
    r"""(?P<marker>!!!|\?\?\?\+?)[ \t]+
        (?P<classes>[\w-]+(?:[ \t]+[\w-]+)*)
        (?:[ \t]+"(?P<title>.*)")?
        [ \t]*$""",
    re.X,
)

_INDENT = 4


class _AdmonitionRule(ContainerRule):
    def continue_(self, parser: BlockParser, block: Admonition) -> int:
        if parser.blank:
            parser.advance_next_nonspace()
        elif parser.indent >= _INDENT:
            parser.advance_offset(_INDENT, columns=True)
        else:
            return STOP
        return CONTINUE


def _admonition_start(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() not in ("!", "?"):
        return NO_MATCH
    m = _OPENER.match(parser.current_line, parser.next_nonspace)
    if m is None:
        return NO_MATCH
    kind, *extra = m.group("classes").split()
    title = m.group("title")
    if title is None:
        # no title given: "note" -> "Note", "see-also" -> "See also"
        title = kind.replace("-", " ").replace("_", " ").capitalize()

    parser.close_unmatched_blocks()
    # TODO the title is kept as plain text; `code` or *emphasis* in it would
    # be nice but needs a place in the tree for inline children.
    block = parser.add_child(Admonition(kind.lower(), title or None))
    block.classes = extra
    block.collapsible = m.group("marker").startswith("?")
    block.open = m.group("marker").endswith("+")
    parser.advance_to_end()
    return CONTAINER


class AdmonitionsExtension(Extension):
    """Call-out boxes: ``!!! note "Title"`` followed by an indented body.

    ``???`` makes a collapsed ``<details>`` block instead, ``???+`` one that
    starts out expanded.
    """

    name = "admonitions"

    def setup_blocks(self, parser: BlockParser) -> None:
        parser.add_rule(Admonition, _AdmonitionRule())
        parser.add_start("admonition", _admonition_start)
