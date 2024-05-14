from __future__ import annotations

import re

from ..blocks import (
    CONTAINER,
    CONTINUE,
    NO_MATCH,
    STOP,
    BlockParser,
    BlockRule,
    ContainerRule,
    ends_with_blank_line,
)
from ..nodes import (
    Block,
    DefinitionDescription,
    DefinitionList,
    DefinitionTerm,
    Paragraph,
)
from . import Extension

_MARKER = re.compile(r":[ \t]+(?=\S)")


class _DefinitionListRule(BlockRule):
    def can_contain(self, child: Block) -> bool:
        return isinstance(child, (DefinitionTerm, DefinitionDescription))

    def finalize(self, parser: BlockParser, block: DefinitionList) -> None:
        # Every term starts out as a paragraph, so the list gets closed
        # before each new term and what was meant as one list arrives here
        # in pieces. Glue them back together.
        previous = block.previous
        if isinstance(previous, DefinitionList):
            for child in block.children:
                previous.append(child)
            previous.end_line = block.end_line
            block.children = []
            block.unlink()


class _DescriptionRule(ContainerRule):
    def continue_(self, parser: BlockParser, block: DefinitionDescription) -> int:
        if parser.blank:
            parser.advance_next_nonspace()
        elif parser.indent >= block._padding:
            parser.advance_offset(block._padding, columns=True)
        else:
            return STOP
        return CONTINUE

    def finalize(self, parser: BlockParser, block: DefinitionDescription) -> None:
        # same idea as loose list items
        if any(ends_with_blank_line(child) for child in block.children[:-1]):
            block.tight = False


def _terms_paragraph(container: Block) -> tuple[Paragraph | None, bool]:
    """The paragraph holding the terms for a definition starting here.

    The second value says whether it sits right above the definition, with
    no blank line in between.
    """
    if isinstance(container, Paragraph):
        return container, True
    last = container.children[-1] if container.children else None
    if isinstance(last, Paragraph) and not last._open:
        return last, False
    return None, False


def _definition_start(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != ":":
        return NO_MATCH
    if _MARKER.match(parser.current_line, parser.next_nonspace) is None:
        return NO_MATCH

    if isinstance(container, DefinitionList):
        # another definition for the same term(s)
        tight = not container.children[-1]._last_line_blank
        parser.close_unmatched_blocks()
    else:
        paragraph, tight = _terms_paragraph(container)
        if paragraph is None:
            return NO_MATCH
        if paragraph._open and not parser.consume_references(paragraph):
            return NO_MATCH
        parser.close_unmatched_blocks()
        parser.tip = _terms_to_list(paragraph)

    parser.advance_next_nonspace()
    parser.advance_offset(1, columns=True)
    padding = 1 + parser.skip_marker_spaces()
    description = parser.add_child(DefinitionDescription())
    description.tight = tight
    description._padding = padding
    return CONTAINER


def _terms_to_list(paragraph: Paragraph) -> DefinitionList:
    """Replace a paragraph with a definition list, one term per line."""
    lines = paragraph._lines if paragraph._open else paragraph.raw.split("\n")
    result = DefinitionList()
    result.line = paragraph.line
    for offset, line in enumerate(lines):
        term = DefinitionTerm()
        term.line = term.end_line = paragraph.line + offset
        term.raw = line.strip(" \t")
        term._open = False
        result.append(term)
    paragraph.replace_with(result)
    return result


class DefListsExtension(Extension):
    """Definition lists as in PHP Markdown Extra: a term, then ``: text``."""

    name = "deflists"

    def setup_blocks(self, parser: BlockParser) -> None:
        parser.add_rule(DefinitionList, _DefinitionListRule())
        parser.add_rule(DefinitionDescription, _DescriptionRule())
        parser.add_start("definition", _definition_start)
