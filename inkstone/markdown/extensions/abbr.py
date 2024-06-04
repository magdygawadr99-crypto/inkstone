from __future__ import annotations

import re

from ..blocks import LEAF, NO_MATCH, BlockParser
from ..nodes import Abbreviation, Block, Document, Node, Text
from . import Extension, replace_in_text

_DEFINITION = re.compile(r"\*\[([^\]]+)\]:[ \t]*(.*)$")


def _definition_start(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != "*":
        return NO_MATCH
    m = _DEFINITION.match(parser.current_line, parser.next_nonspace)
    if m is None or not m.group(1).strip():
        return NO_MATCH
    parser.doc.abbreviations[m.group(1).strip()] = m.group(2).strip()
    parser.close_unmatched_blocks()
    if parser.rules[type(container)].accepts_lines:
        # The definition leaves nothing behind in the tree, so a paragraph
        # it interrupts has to be closed by hand or it would get the (by
        # now empty) rest of the line.
        parser.finalize(container, parser.line_number - 1)
    parser.advance_to_end()
    return LEAF


class AbbrExtension(Extension):
    """``*[HTML]: Hyper Text Markup Language`` and ``<abbr>`` for every HTML."""

    name = "abbr"

    def setup_blocks(self, parser: BlockParser) -> None:
        parser.add_start("abbr_def", _definition_start)

    def after_inlines(self, doc: Document) -> None:
        abbreviations = doc.abbreviations
        if not abbreviations:
            return
        # longest first, so "HTML5" is not read as "HTML" followed by a 5
        words = sorted(abbreviations, key=len, reverse=True)
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(word) for word in words) + r")(?!\w)"
        )

        def make(m: re.Match) -> Node:
            node = Abbreviation(abbreviations[m.group()])
            node.append(Text(m.group()))
            return node

        replace_in_text(doc, pattern, make, skip=())
