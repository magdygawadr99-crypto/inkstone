from __future__ import annotations

import html
import re

from .nodes import Block, List, Node, NodeVisitor

_TAG = re.compile(r"<[^>]*>")
_SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|\Z)", re.S | re.I)
_SPACES = re.compile(r"[ \t]+")


class PlainTextRenderer(NodeVisitor):
    """Render a tree as plain text, with all the markup gone.

    Meant for summaries, the search index, alt attributes, feed
    descriptions: places where only the words matter. Blocks end up
    separated by blank lines and soft line breaks become spaces.
    """

    def __init__(
        self,
        *,
        code_blocks: bool = True,
        images: bool = True,
        footnotes: bool = False,
        raw_html: bool = False,
        separator: str = "\n\n",
    ) -> None:
        self.code_blocks = code_blocks
        # whether an image contributes its alt text
        self.images = images
        self.footnotes = footnotes
        # keep the text between the tags of raw HTML (the tags always go)
        self.raw_html = raw_html
        self.separator = separator
        # what goes between things that are closer together than blocks: list
        # items, table rows. With a one-line separator the output is one line.
        self._line = "\n" if "\n" in separator else separator

    def render(self, node: Node) -> str:
        text = self.visit(node)
        return text.strip() if node.is_block else text

    def generic_visit(self, node: Node) -> str:
        if isinstance(node, Block) and any(child.is_block for child in node.children):
            return self._blocks(node)
        return self._inlines(node)

    def _inlines(self, node: Node) -> str:
        return "".join(self.visit(child) for child in node.children)

    def _blocks(self, node: Node, separator: str | None = None) -> str:
        if separator is None:
            separator = self.separator
        parts = (self.visit(child) for child in node.children)
        return separator.join(part for part in parts if part)

    def visit_text(self, node) -> str:
        return node.literal

    def visit_code(self, node) -> str:
        return node.literal

    def visit_soft_break(self, node) -> str:
        return " "

    def visit_line_break(self, node) -> str:
        return self._line

    def visit_image(self, node) -> str:
        return self._inlines(node) if self.images else ""

    def visit_html_inline(self, node) -> str:
        # tags carry no text of their own; what they wrap is separate nodes
        return ""

    def visit_footnote_ref(self, node) -> str:
        return ""

    def visit_footnote_backref(self, node) -> str:
        return ""

    def visit_paragraph(self, node) -> str:
        return _SPACES.sub(" ", self._inlines(node)).strip()

    visit_heading = visit_paragraph
    visit_table_cell = visit_paragraph
    visit_definition_term = visit_paragraph

    def visit_code_block(self, node) -> str:
        if not self.code_blocks:
            return ""
        return node.literal.rstrip("\n").replace("\n", self._line)

    def visit_html_block(self, node) -> str:
        if not self.raw_html:
            return ""
        visible = _SCRIPT_OR_STYLE.sub("", node.literal)
        return html.unescape(_TAG.sub("", visible)).strip()

    def visit_thematic_break(self, node) -> str:
        return ""

    def visit_toc_marker(self, node) -> str:
        return ""

    def visit_list(self, node: List) -> str:
        return self._blocks(node, self._line if node.tight else self.separator)

    def visit_list_item(self, node) -> str:
        return self._blocks(node, self._line)

    def visit_table(self, node) -> str:
        return self._blocks(node, self._line)

    def visit_table_row(self, node) -> str:
        return self._blocks(node, " | ")

    def visit_definition_list(self, node) -> str:
        return self._blocks(node, self._line)

    def visit_admonition(self, node) -> str:
        body = self._blocks(node)
        if node.title:
            return node.title + self.separator + body if body else node.title
        return body

    def visit_footnote_list(self, node) -> str:
        return self._blocks(node) if self.footnotes else ""

    def visit_footnote_def(self, node) -> str:
        return self._blocks(node) if self.footnotes else ""


def plain_text(node: Node, **options) -> str:
    """Shorthand for ``PlainTextRenderer(**options).render(node)``."""
    return PlainTextRenderer(**options).render(node)
