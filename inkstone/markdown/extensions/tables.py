from __future__ import annotations

import re

from ..blocks import CONTINUE, LEAF, NO_MATCH, STOP, BlockParser, BlockRule
from ..nodes import Block, Paragraph, Table, TableCell, TableRow
from . import Extension

_DELIMITER_CELL = re.compile(r"[ \t]*(:?)-+(:?)[ \t]*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)(?:\\\\)*\|")


def split_row(line: str) -> list[str]:
    """Split a table row into the text of its cells.

    A pipe can be put inside a cell by escaping it, also within a code span;
    that is the one place Markdown lets a backslash work inside backticks.
    """
    line = line.strip(" \t")
    if line.startswith("|"):
        line = line[1:]
    cells = []
    start = 0
    for m in _UNESCAPED_PIPE.finditer(line):
        cells.append(line[start : m.end() - 1])
        start = m.end()
    if start < len(line) or not cells:
        cells.append(line[start:])
    return [cell.strip(" \t").replace("\\|", "|") for cell in cells]


def parse_delimiter_row(line: str) -> list[str | None] | None:
    """Column alignments from a ``|:--|--:|`` line, or None if it isn't one."""
    # Without a pipe this would also swallow setext underlines and "---".
    if "|" not in line:
        return None
    alignments: list[str | None] = []
    for cell in split_row(line):
        m = _DELIMITER_CELL.match(cell)
        if m is None:
            return None
        left, right = m.groups()
        if left and right:
            alignments.append("center")
        elif left:
            alignments.append("left")
        elif right:
            alignments.append("right")
        else:
            alignments.append(None)
    return alignments


class _TableRule(BlockRule):
    accepts_lines = True
    # body rows are plain text lines, but a quote or a list can still start
    interruptible = True

    def continue_(self, parser: BlockParser, block: Table) -> int:
        return STOP if parser.blank else CONTINUE

    def finalize(self, parser: BlockParser, block: Table) -> None:
        header, _, *body = block._lines
        block._lines = []
        self._add_row(block, header, block.line, header=True)
        for offset, line in enumerate(body):
            self._add_row(block, line, block.line + 2 + offset, header=False)

    def _add_row(self, table: Table, line: str, number: int, header: bool) -> None:
        row = TableRow(header=header)
        row.line = row.end_line = number
        row._open = False
        table.append(row)
        cells = split_row(line)
        # short rows are padded and long ones cut off, like GitHub does
        for column, align in enumerate(table.alignments):
            cell = TableCell(align=align, header=header)
            cell.line = cell.end_line = number
            cell._open = False
            cell.raw = cells[column] if column < len(cells) else ""
            row.append(cell)


def _table_start(parser: BlockParser, container: Block) -> int:
    """A delimiter row turns the paragraph line above it into a table header."""
    if parser.indented or not isinstance(container, Paragraph):
        return NO_MATCH
    if parser.next_char() not in ("|", ":", "-"):
        return NO_MATCH
    alignments = parse_delimiter_row(parser.rest_of_line())
    if alignments is None:
        return NO_MATCH
    header = container._lines[-1]
    if len(split_row(header)) != len(alignments):
        return NO_MATCH

    parser.close_unmatched_blocks()
    table = Table(alignments)
    table.line = parser.line_number - 1
    table._lines.append(header)
    del container._lines[-1]
    if container._lines:
        # earlier lines stay behind as a paragraph of their own
        parser.finalize(container, parser.line_number - 2)
        if container.parent is not None:
            container.insert_after(table)
        else:
            parser.tip.append(table)
    else:
        container.replace_with(table)
    parser.tip = table
    parser.advance_next_nonspace()
    return LEAF


class TablesExtension(Extension):
    """GFM pipe tables."""

    name = "tables"

    def setup_blocks(self, parser: BlockParser) -> None:
        parser.add_rule(Table, _TableRule())
        parser.add_start("table", _table_start, before="thematic_break")
