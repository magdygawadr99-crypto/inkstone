from __future__ import annotations

import re
from typing import Callable

from .inlines import CLOSE_TAG, OPEN_TAG, InlineParser
from .nodes import (
    Block,
    BlockQuote,
    CodeBlock,
    Document,
    Heading,
    HtmlBlock,
    List,
    ListItem,
    Paragraph,
    ThematicBreak,
)
from .utils import parse_attrs, unescape_string

CODE_INDENT = 4

# What a BlockRule.continue_() can answer for the current line.
CONTINUE = 0  # the block goes on
STOP = 1  # the block does not go on with this line
CONSUMED = 2  # the block ate the whole line (a closing code fence)

# What a block start function can answer.
NO_MATCH = 0
CONTAINER = 1  # opened a block that can hold other blocks
LEAF = 2  # opened a block that cannot

_ATX_MARKER = re.compile(r"#{1,6}(?:[ \t]+|$)")
_ATX_ONLY_CLOSER = re.compile(r"^[ \t]*#+[ \t]*$")
_ATX_CLOSER = re.compile(r"[ \t]+#+[ \t]*$")
_SETEXT_LINE = re.compile(r"(?:=+|-+)[ \t]*$")
_FENCE_OPEN = re.compile(r"`{3,}(?!.*`)|~{3,}")
_FENCE_CLOSE = re.compile(r"(?:`{3,}|~{3,})(?=[ \t]*$)")
_THEMATIC_BREAK = re.compile(r"(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$")
_BULLET_MARKER = re.compile(r"[*+-]")
_ORDERED_MARKER = re.compile(r"(\d{1,9})([.)])")
_INFO_ATTRS = re.compile(r"\{([^{}]*)\}\s*$")

_HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup"
    "|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame"
    "|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem"
    "|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td"
    "|tfoot|th|thead|title|tr|track|ul"
)
# The seven kinds of HTML block from the CommonMark spec, in order. Kinds 1-5
# run until their closing pattern shows up, 6 and 7 until a blank line.
_HTML_OPEN = [
    re.compile(r"<(?:script|pre|textarea|style)(?:\s|>|$)", re.I),
    re.compile(r"<!--"),
    re.compile(r"<\?"),
    re.compile(r"<![A-Za-z]"),
    re.compile(r"<!\[CDATA\["),
    re.compile(r"</?(?:" + _HTML_BLOCK_TAGS + r")(?:\s|/?>|$)", re.I),
    re.compile("(?:" + OPEN_TAG + "|" + CLOSE_TAG + r")\s*$"),
]
_HTML_CLOSE = [
    re.compile(r"</(?:script|pre|textarea|style)>", re.I),
    re.compile(r"-->"),
    re.compile(r"\?>"),
    re.compile(r">"),
    re.compile(r"\]\]>"),
]

BlockStart = Callable[["BlockParser", Block], int]


class BlockRule:
    """How an open block of one type deals with the lines that follow it."""

    accepts_lines = False
    # Takes text lines, yet other blocks may still start on them (paragraphs,
    # table bodies).
    interruptible = False

    def continue_(self, parser: BlockParser, block) -> int:
        return CONTINUE

    def finalize(self, parser: BlockParser, block) -> None:
        pass

    def can_contain(self, child: Block) -> bool:
        return False

    def line_added(self, parser: BlockParser, block) -> None:
        pass


class ContainerRule(BlockRule):
    def can_contain(self, child: Block) -> bool:
        return not isinstance(child, ListItem)


class LeafRule(BlockRule):
    """Single-line blocks: nothing ever continues them."""

    def continue_(self, parser: BlockParser, block) -> int:
        return STOP


class _BlockQuoteRule(ContainerRule):
    def continue_(self, parser: BlockParser, block: BlockQuote) -> int:
        if parser.indented or parser.next_char() != ">":
            return STOP
        parser.advance_next_nonspace()
        parser.advance_offset(1)
        if parser.char_at_offset() in (" ", "\t"):
            parser.advance_offset(1, columns=True)
        return CONTINUE


class _ListRule(BlockRule):
    def can_contain(self, child: Block) -> bool:
        return isinstance(child, ListItem)

    def finalize(self, parser: BlockParser, block: List) -> None:
        # A list is loose if any of its items are separated by a blank line,
        # or if any item directly contains two blocks with one between them.
        items = block.children
        for i, item in enumerate(items):
            last_item = i == len(items) - 1
            if not last_item and ends_with_blank_line(item):
                block.tight = False
                return
            for j, child in enumerate(item.children):
                last_child = j == len(item.children) - 1
                if not (last_item and last_child) and ends_with_blank_line(child):
                    block.tight = False
                    return


class _ListItemRule(ContainerRule):
    def continue_(self, parser: BlockParser, block: ListItem) -> int:
        if parser.blank:
            if not block.children:
                # a blank line after an empty item ends it
                return STOP
            parser.advance_next_nonspace()
        elif parser.indent >= block._marker_offset + block._padding:
            parser.advance_offset(block._marker_offset + block._padding, columns=True)
        else:
            return STOP
        return CONTINUE


class _CodeBlockRule(BlockRule):
    accepts_lines = True

    def continue_(self, parser: BlockParser, block: CodeBlock) -> int:
        if not block.fenced:
            if parser.indent >= CODE_INDENT:
                parser.advance_offset(CODE_INDENT, columns=True)
            elif parser.blank:
                parser.advance_next_nonspace()
            else:
                return STOP
            return CONTINUE

        if parser.indent <= 3 and parser.next_char() == block._fence_char:
            m = _FENCE_CLOSE.match(parser.current_line, parser.next_nonspace)
            if m is not None and len(m.group()) >= block._fence_length:
                parser.finalize(block, parser.line_number)
                return CONSUMED
        # the content may be indented as far as the opening fence was
        skip = block._fence_offset
        while skip > 0 and parser.char_at_offset() in (" ", "\t"):
            parser.advance_offset(1, columns=True)
            skip -= 1
        return CONTINUE

    def finalize(self, parser: BlockParser, block: CodeBlock) -> None:
        lines = block._lines
        if block.fenced:
            # the first line is whatever followed the opening fence
            block.info = unescape_string(lines[0].strip()) if lines else ""
            block.lang, block.attrs = parse_info(block.info)
            block.literal = "".join(line + "\n" for line in lines[1:])
        else:
            while lines and not lines[-1].strip(" \t"):
                lines.pop()
                block.end_line -= 1
            block.literal = "".join(line + "\n" for line in lines)
        block._lines = []


class _HtmlBlockRule(BlockRule):
    accepts_lines = True

    def continue_(self, parser: BlockParser, block: HtmlBlock) -> int:
        if parser.blank and block._html_type >= 6:
            return STOP
        return CONTINUE

    def line_added(self, parser: BlockParser, block: HtmlBlock) -> None:
        if block._html_type > 5:
            return
        closer = _HTML_CLOSE[block._html_type - 1]
        if closer.search(parser.current_line, parser.offset):
            parser.finalize(block, parser.line_number)

    def finalize(self, parser: BlockParser, block: HtmlBlock) -> None:
        block.literal = "\n".join(block._lines)
        block._lines = []


class _ParagraphRule(BlockRule):
    accepts_lines = True
    interruptible = True

    def continue_(self, parser: BlockParser, block: Paragraph) -> int:
        return STOP if parser.blank else CONTINUE

    def finalize(self, parser: BlockParser, block: Paragraph) -> None:
        if not parser.consume_references(block):
            block.unlink()
            return
        block.raw = "\n".join(block._lines).strip(" \t\n")
        block._lines = []


def ends_with_blank_line(block: Block | None) -> bool:
    while block is not None:
        if block._last_line_blank:
            return True
        if not block._last_line_checked and isinstance(block, (List, ListItem)):
            block._last_line_checked = True
            block = block.children[-1] if block.children else None
        else:
            block._last_line_checked = True
            break
    return False


def parse_info(info: str) -> tuple[str | None, dict]:
    """Split a fence info string into the language and any {...} attributes.

    Both ``python {linenos}`` and the pandoc-ish ``{.python linenos}`` work.
    """
    attrs: dict = {}
    m = _INFO_ATTRS.search(info)
    if m is not None:
        parsed = parse_attrs(m.group(1))
        if parsed is not None:
            attrs = parsed
            info = info[: m.start()]
    words = info.split()
    if words:
        return words[0], attrs
    if "class" in attrs:
        lang, _, rest = attrs["class"].partition(" ")
        if rest:
            attrs["class"] = rest
        else:
            del attrs["class"]
        return lang, attrs
    return None, attrs


def _block_quote(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != ">":
        return NO_MATCH
    parser.advance_next_nonspace()
    parser.advance_offset(1)
    if parser.char_at_offset() in (" ", "\t"):
        parser.advance_offset(1, columns=True)
    parser.close_unmatched_blocks()
    parser.add_child(BlockQuote())
    return CONTAINER


def _atx_heading(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != "#":
        return NO_MATCH
    m = _ATX_MARKER.match(parser.current_line, parser.next_nonspace)
    if m is None:
        return NO_MATCH
    parser.advance_next_nonspace()
    parser.advance_offset(len(m.group()))
    parser.close_unmatched_blocks()
    heading = parser.add_child(Heading(level=len(m.group().strip())))
    text = parser.current_line[parser.offset :]
    text = _ATX_CLOSER.sub("", _ATX_ONLY_CLOSER.sub("", text))
    heading.raw = text.strip(" \t")
    parser.advance_to_end()
    return LEAF


def _fenced_code(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() not in ("`", "~"):
        return NO_MATCH
    m = _FENCE_OPEN.match(parser.current_line, parser.next_nonspace)
    if m is None:
        return NO_MATCH
    parser.close_unmatched_blocks()
    block = parser.add_child(CodeBlock())
    block.fenced = True
    block._fence_length = len(m.group())
    block._fence_char = m.group()[0]
    block._fence_offset = parser.indent
    parser.advance_next_nonspace()
    parser.advance_offset(block._fence_length)
    return LEAF


def _html_block(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != "<":
        return NO_MATCH
    for html_type, opener in enumerate(_HTML_OPEN, 1):
        if not opener.match(parser.current_line, parser.next_nonspace):
            continue
        if html_type == 7 and (
            isinstance(container, Paragraph) or parser.is_lazy_continuation()
        ):
            # a lone inline tag cannot interrupt a paragraph
            continue
        parser.close_unmatched_blocks()
        # the offset stays where it is: indentation is part of the HTML
        block = parser.add_child(HtmlBlock())
        block._html_type = html_type
        return LEAF
    return NO_MATCH


def _setext_heading(parser: BlockParser, container: Block) -> int:
    if parser.indented or not isinstance(container, Paragraph):
        return NO_MATCH
    m = _SETEXT_LINE.match(parser.current_line, parser.next_nonspace)
    if m is None:
        return NO_MATCH
    parser.close_unmatched_blocks()
    if not parser.consume_references(container):
        # the "paragraph" was nothing but link definitions
        return NO_MATCH
    heading = Heading(level=1 if m.group()[0] == "=" else 2)
    heading.setext = True
    heading.line = container.line
    heading.raw = "\n".join(container._lines).strip(" \t\n")
    container.replace_with(heading)
    parser.tip = heading
    parser.advance_to_end()
    return LEAF


def _thematic_break(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() not in ("*", "-", "_"):
        return NO_MATCH
    if not _THEMATIC_BREAK.match(parser.current_line, parser.next_nonspace):
        return NO_MATCH
    parser.close_unmatched_blocks()
    parser.add_child(ThematicBreak())
    parser.advance_to_end()
    return LEAF


def _list_item(parser: BlockParser, container: Block) -> int:
    if parser.indented:
        return NO_MATCH
    line = parser.current_line
    in_paragraph = isinstance(container, Paragraph)

    ordered = False
    start = None
    m = _BULLET_MARKER.match(line, parser.next_nonspace)
    if m is None:
        m = _ORDERED_MARKER.match(line, parser.next_nonspace)
        if m is None:
            return NO_MATCH
        ordered = True
        start = int(m.group(1))
        # only a list starting at 1 may interrupt a paragraph; otherwise a
        # wrapped line that happens to begin with "1986." would start one
        if in_paragraph and start != 1:
            return NO_MATCH
    marker = m.group()
    after = line[m.end() : m.end() + 1]
    if after not in ("", " ", "\t"):
        return NO_MATCH
    if in_paragraph and not line[m.end() :].strip(" \t"):
        # an empty item cannot interrupt a paragraph either
        return NO_MATCH

    marker_offset = parser.indent
    parser.advance_next_nonspace()
    parser.advance_offset(len(marker), columns=True)
    padding = len(marker) + parser.skip_marker_spaces()

    parser.close_unmatched_blocks()
    delimiter = m.group(2) if ordered else marker
    tip = parser.tip
    if not (
        isinstance(tip, List)
        and tip.ordered == ordered
        and tip.delimiter == delimiter
    ):
        new_list = parser.add_child(List(ordered=ordered, start=start))
        new_list.delimiter = delimiter
        if not ordered:
            new_list.bullet = marker
    item = parser.add_child(ListItem())
    item._marker_offset = marker_offset
    item._padding = padding
    return CONTAINER


def _indented_code(parser: BlockParser, container: Block) -> int:
    if not parser.indented or parser.blank:
        return NO_MATCH
    tip = parser.tip
    if isinstance(tip, Paragraph):
        return NO_MATCH
    if tip is container and parser.rules[type(tip)].interruptible:
        return NO_MATCH
    parser.advance_offset(CODE_INDENT, columns=True)
    parser.close_unmatched_blocks()
    parser.add_child(CodeBlock())
    return LEAF


class BlockParser:
    """First phase: split the source into blocks, without looking inside them.

    This follows the strategy from the CommonMark spec's appendix. Lines are
    consumed one at a time; for each we see how many of the currently open
    blocks it continues, then whether it starts new ones, and whatever is
    left over is text for the innermost open block.
    """

    def __init__(self) -> None:
        self.rules: dict[type, BlockRule] = {
            Document: ContainerRule(),
            BlockQuote: _BlockQuoteRule(),
            List: _ListRule(),
            ListItem: _ListItemRule(),
            Heading: LeafRule(),
            ThematicBreak: LeafRule(),
            CodeBlock: _CodeBlockRule(),
            HtmlBlock: _HtmlBlockRule(),
            Paragraph: _ParagraphRule(),
        }
        self.starts: list[tuple[str, BlockStart]] = [
            ("block_quote", _block_quote),
            ("atx_heading", _atx_heading),
            ("fenced_code", _fenced_code),
            ("html_block", _html_block),
            ("setext_heading", _setext_heading),
            ("thematic_break", _thematic_break),
            ("list_item", _list_item),
            ("indented_code", _indented_code),
        ]
        # Stops pathological input (thousands of nested quotes) from blowing
        # the stack in the renderers, which recurse.
        self.max_nesting = 100
        self._refs = InlineParser()
        self._reset()

    def add_rule(self, node_class: type, rule: BlockRule) -> None:
        self.rules[node_class] = rule

    def add_start(
        self, name: str, start: BlockStart, before: str = "list_item"
    ) -> None:
        """Register a block start, to be tried just ahead of an existing one."""
        names = [existing for existing, _ in self.starts]
        self.starts.insert(names.index(before), (name, start))

    def _reset(self) -> None:
        self.doc = Document()
        self.doc.line = 1
        self.tip: Block | None = self.doc
        self.old_tip: Block = self.doc
        self.last_matched_container: Block = self.doc
        self.current_line = ""
        self.line_number = 0
        self.offset = 0
        self.column = 0
        self.next_nonspace = 0
        self.next_nonspace_column = 0
        self.indent = 0
        self.indented = False
        self.blank = False
        self.partially_consumed_tab = False
        self.all_closed = True

    def parse(self, text: str) -> Document:
        self._reset()
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\0", "\ufffd")
        if text.startswith("\ufeff"):
            text = text[1:]
        lines = text.split("\n")
        if text.endswith("\n"):
            lines.pop()
        for line in lines:
            self._incorporate_line(line)
        while self.tip is not None:
            self.finalize(self.tip, max(self.line_number, 1))
        doc = self.doc
        self.doc = Document()
        return doc

    def next_char(self) -> str:
        """First non-blank character of what is left of the line ("" if none)."""
        return self.current_line[self.next_nonspace : self.next_nonspace + 1]

    def char_at_offset(self) -> str:
        return self.current_line[self.offset : self.offset + 1] or "\0"

    def rest_of_line(self) -> str:
        return self.current_line[self.next_nonspace :]

    def find_next_nonspace(self) -> None:
        line = self.current_line
        i = self.offset
        cols = self.column
        while i < len(line):
            char = line[i]
            if char == " ":
                cols += 1
            elif char == "\t":
                cols += 4 - cols % 4
            else:
                break
            i += 1
        self.blank = i >= len(line)
        self.next_nonspace = i
        self.next_nonspace_column = cols
        self.indent = cols - self.column
        self.indented = self.indent >= CODE_INDENT

    def advance_next_nonspace(self) -> None:
        self.offset = self.next_nonspace
        self.column = self.next_nonspace_column
        self.partially_consumed_tab = False

    def advance_offset(self, count: int, columns: bool = False) -> None:
        """Move forward by count characters, or by count columns.

        Counting columns matters when there are tabs: one tab can stand for
        the indentation of a list item plus part of an indented code block.
        """
        line = self.current_line
        while count > 0 and self.offset < len(line):
            if line[self.offset] == "\t":
                to_tab = 4 - self.column % 4
                if columns:
                    self.partially_consumed_tab = to_tab > count
                    step = min(count, to_tab)
                    self.column += step
                    if not self.partially_consumed_tab:
                        self.offset += 1
                    count -= step
                else:
                    self.partially_consumed_tab = False
                    self.column += to_tab
                    self.offset += 1
                    count -= 1
            else:
                self.partially_consumed_tab = False
                self.offset += 1
                self.column += 1
                count -= 1

    def advance_to_end(self) -> None:
        self.advance_offset(len(self.current_line) - self.offset)

    def skip_marker_spaces(self) -> int:
        """Skip the whitespace after a list-like marker; return its width.

        One to four columns count as padding. With five or more (or nothing
        but whitespace) only one does, and the rest belongs to the content,
        where it will usually make an indented code block.
        """
        line = self.current_line
        start_column = self.column
        start_offset = self.offset
        while True:
            self.advance_offset(1, columns=True)
            width = self.column - start_column
            if width >= 5 or self.char_at_offset() not in (" ", "\t"):
                break
        blank_item = self.offset >= len(line)
        if 1 <= width < 5 and not blank_item:
            return width
        self.column = start_column
        self.offset = start_offset
        self.partially_consumed_tab = False
        if self.char_at_offset() in (" ", "\t"):
            self.advance_offset(1, columns=True)
        return 1

    def is_lazy_continuation(self) -> bool:
        """Would this line, failing all else, extend an unclosed paragraph?"""
        if self.all_closed or self.blank:
            return False
        return isinstance(self.tip, Paragraph)

    def add_child(self, block: Block) -> Block:
        """Open block inside the current tip, closing what cannot hold it."""
        while not self.rules[type(self.tip)].can_contain(block):
            self.finalize(self.tip, self.line_number - 1)
        block.line = self.line_number
        self.tip.append(block)
        self.tip = block
        return block

    def add_line(self) -> None:
        text = self.current_line[self.offset :]
        if self.partially_consumed_tab:
            # the tab was only partly used up as indentation, the rest of its
            # width is content
            text = " " * (4 - self.column % 4) + self.current_line[self.offset + 1 :]
        self.tip._lines.append(text)

    def finalize(self, block: Block, line_number: int) -> None:
        above = block.parent
        block._open = False
        block.end_line = line_number
        if block.children and block.children[-1].end_line is not None:
            # a container ends with its last child, not with the blank lines
            # that may have come after it
            block.end_line = block.children[-1].end_line
        self.rules[type(block)].finalize(self, block)
        self.tip = above

    def close_unmatched_blocks(self) -> None:
        if self.all_closed:
            return
        while self.old_tip is not self.last_matched_container:
            parent = self.old_tip.parent
            self.finalize(self.old_tip, self.line_number - 1)
            self.old_tip = parent
        self.all_closed = True

    def consume_references(self, paragraph: Paragraph) -> bool:
        """Peel link reference definitions off the front of a paragraph.

        Returns False if nothing else is left of it.
        """
        lines = paragraph._lines
        if not lines or not lines[0].startswith("["):
            return any(line.strip(" \t") for line in lines)
        text = "\n".join(lines)
        changed = False
        while text.startswith("["):
            consumed = self._refs.parse_reference(text, self.doc.references)
            if not consumed:
                break
            text = text[consumed:]
            changed = True
        if changed:
            paragraph._lines = text.split("\n") if text else []
        return bool(text.strip(" \t\n"))

    def _incorporate_line(self, line: str) -> None:
        container: Block = self.doc
        self.old_tip = self.tip
        self.offset = 0
        self.column = 0
        self.blank = False
        self.partially_consumed_tab = False
        self.line_number += 1
        self.current_line = line
        depth = 0

        # Walk down the open blocks and see how far this line continues them.
        while container.children and container.children[-1]._open:
            child = container.children[-1]
            self.find_next_nonspace()
            result = self.rules[type(child)].continue_(self, child)
            if result == CONSUMED:
                return
            if result == STOP:
                break
            container = child
            depth += 1

        self.all_closed = container is self.old_tip
        self.last_matched_container = container

        # See whether the rest of the line opens new blocks inside the last
        # one that matched.
        rule = self.rules[type(container)]
        matched_leaf = rule.accepts_lines and not rule.interruptible
        while not matched_leaf:
            self.find_next_nonspace()
            if depth >= self.max_nesting:
                self.advance_next_nonspace()
                break
            result = NO_MATCH
            for _, start in self.starts:
                result = start(self, container)
                if result != NO_MATCH:
                    break
            if result == NO_MATCH:
                self.advance_next_nonspace()
                break
            container = self.tip
            depth += 1
            matched_leaf = result == LEAF

        # What remains is text.
        if self.is_lazy_continuation():
            self.add_line()
            return

        self.close_unmatched_blocks()
        if self.blank and container.children:
            container.children[-1]._last_line_blank = True

        # Blank lines decide whether lists are tight. A "blank" line inside a
        # quote still has its ">" so it doesn't count, nor do blank lines in
        # fenced code, nor the line that opened a still empty container (a list
        # marker with nothing after it).
        last_line_blank = self.blank and not (
            isinstance(container, BlockQuote)
            or (isinstance(container, CodeBlock) and container.fenced)
            or (not container.children and container.line == self.line_number)
        )
        ancestor: Block | None = container
        while ancestor is not None:
            ancestor._last_line_blank = last_line_blank
            ancestor = ancestor.parent

        rule = self.rules[type(container)]
        if rule.accepts_lines:
            self.add_line()
            rule.line_added(self, container)
        elif self.offset < len(line) and not self.blank:
            self.add_child(Paragraph())
            self.advance_next_nonspace()
            self.add_line()
