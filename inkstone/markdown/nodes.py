from __future__ import annotations

import re
from typing import Iterable, Iterator, NamedTuple


def _snake_case(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


class Reference(NamedTuple):
    """A link reference definition: ``[label]: dest "title"``."""

    label: str
    dest: str
    title: str


class Node:
    """Base class for everything in the tree.

    ``type`` is the snake_case class name ("block_quote", "soft_break"...)
    and is what visitors dispatch on.
    """

    type = "node"
    is_block = False
    line: int | None = None
    raw: str | None = None
    # attributes worth showing in repr() and dump()
    _fields: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "type" not in cls.__dict__:
            cls.type = _snake_case(cls.__name__)

    def __init__(self) -> None:
        self.parent: Node | None = None
        self.children: list[Node] = []

    def append(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    def set_children(self, children: Iterable[Node]) -> None:
        self.children = list(children)
        for child in self.children:
            child.parent = self

    def unlink(self) -> None:
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None

    def replace_with(self, *nodes: Node) -> None:
        """Swap this node for zero or more others, in place."""
        parent = self.parent
        if parent is None:
            raise ValueError("cannot replace a node that has no parent")
        index = parent.children.index(self)
        parent.children[index : index + 1] = nodes
        for node in nodes:
            node.parent = parent
        self.parent = None

    def insert_after(self, node: Node) -> None:
        parent = self.parent
        if parent is None:
            raise ValueError("cannot insert next to a node that has no parent")
        parent.children.insert(parent.children.index(self) + 1, node)
        node.parent = parent

    def insert_before(self, node: Node) -> None:
        parent = self.parent
        if parent is None:
            raise ValueError("cannot insert next to a node that has no parent")
        parent.children.insert(parent.children.index(self), node)
        node.parent = parent

    @property
    def previous(self) -> Node | None:
        return self._sibling(-1)

    @property
    def next(self) -> Node | None:
        return self._sibling(1)

    def _sibling(self, step: int) -> Node | None:
        if self.parent is None:
            return None
        siblings = self.parent.children
        index = siblings.index(self) + step
        if 0 <= index < len(siblings):
            return siblings[index]
        return None

    def ancestors(self) -> Iterator[Node]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def walk(self) -> Iterator[Node]:
        return walk(self)

    def find_all(self, *classes: type) -> Iterator[Node]:
        for node in walk(self):
            if isinstance(node, classes):
                yield node

    def __repr__(self) -> str:
        parts = [type(self).__name__]
        for name in self._fields:
            value = getattr(self, name, None)
            if value is not None and value != "" and value != {}:
                parts.append(f"{name}={value!r}")
        if self.line is not None:
            parts.append(f"line={self.line}")
        return "<" + " ".join(parts) + ">"


class Block(Node):
    is_block = True

    def __init__(self) -> None:
        super().__init__()
        self.line = None
        self.end_line: int | None = None
        # Bookkeeping for the block parser. Meaningless once parsing is done.
        self._open = True
        self._lines: list[str] = []
        self._last_line_blank = False
        self._last_line_checked = False


class Inline(Node):
    pass


class Document(Block):
    def __init__(self) -> None:
        super().__init__()
        self.references: dict[str, Reference] = {}
        self.footnotes: dict[str, FootnoteDef] = {}
        self.abbreviations: dict[str, str] = {}
        self.toc: list = []


class Paragraph(Block):
    pass


class Heading(Block):
    _fields = ("level", "id")

    def __init__(self, level: int = 1) -> None:
        super().__init__()
        self.level = level
        self.id: str | None = None
        self.attrs: dict = {}
        self.setext = False


class BlockQuote(Block):
    pass


class List(Block):
    _fields = ("ordered", "start", "tight")

    def __init__(self, ordered: bool = False, start: int | None = None) -> None:
        super().__init__()
        self.ordered = ordered
        self.start = start
        self.tight = True
        # "." or ")" for ordered lists, the bullet character otherwise
        self.delimiter: str | None = None
        self.bullet: str | None = None


class ListItem(Block):
    _fields = ("checked",)

    def __init__(self) -> None:
        super().__init__()
        # None for an ordinary item, True/False for a task list item
        self.checked: bool | None = None
        self._marker_offset = 0
        self._padding = 0


class CodeBlock(Block):
    _fields = ("lang", "info")

    def __init__(self, literal: str = "", info: str = "") -> None:
        super().__init__()
        self.literal = literal
        self.info = info
        self.lang: str | None = None
        self.attrs: dict = {}
        self.fenced = False
        self._fence_char = ""
        self._fence_length = 0
        self._fence_offset = 0


class ThematicBreak(Block):
    pass


class HtmlBlock(Block):
    def __init__(self, literal: str = "") -> None:
        super().__init__()
        self.literal = literal
        self._html_type = 0


class Table(Block):
    _fields = ("alignments",)

    def __init__(self, alignments: list[str | None] | None = None) -> None:
        super().__init__()
        # one of None, "left", "center", "right" per column
        self.alignments: list[str | None] = alignments or []


class TableRow(Block):
    _fields = ("header",)

    def __init__(self, header: bool = False) -> None:
        super().__init__()
        self.header = header


class TableCell(Block):
    _fields = ("align",)

    def __init__(self, align: str | None = None, header: bool = False) -> None:
        super().__init__()
        self.align = align
        self.header = header


class DefinitionList(Block):
    pass


class DefinitionTerm(Block):
    pass


class DefinitionDescription(Block):
    _fields = ("tight",)

    def __init__(self) -> None:
        super().__init__()
        self.tight = True
        self._padding = 0


class Admonition(Block):
    _fields = ("kind", "title")

    def __init__(self, kind: str = "note", title: str | None = None) -> None:
        super().__init__()
        self.kind = kind
        self.classes: list[str] = []
        self.title = title
        self.collapsible = False
        self.open = False


class FootnoteDef(Block):
    _fields = ("label", "number")

    def __init__(self, label: str = "") -> None:
        super().__init__()
        self.label = label
        # position in the rendered list; stays None if nothing refers to it
        self.number: int | None = None
        self.ref_ids: list[str] = []


class FootnoteList(Block):
    """The collected footnotes, appended to the end of the document."""


class TocMarker(Block):
    pass


class Text(Inline):
    _fields = ("literal",)

    def __init__(self, literal: str = "") -> None:
        super().__init__()
        self.literal = literal


class SoftBreak(Inline):
    pass


class LineBreak(Inline):
    pass


class Code(Inline):
    _fields = ("literal",)

    def __init__(self, literal: str = "") -> None:
        super().__init__()
        self.literal = literal


class Emphasis(Inline):
    pass


class Strong(Inline):
    pass


class Strikethrough(Inline):
    pass


class Mark(Inline):
    pass


class Subscript(Inline):
    pass


class Superscript(Inline):
    pass


class Link(Inline):
    _fields = ("dest", "title")

    def __init__(self, dest: str = "", title: str = "") -> None:
        super().__init__()
        self.dest = dest
        self.title = title
        # set on links the autolink extension made out of a bare URL
        self.bare = False


class Image(Inline):
    _fields = ("dest", "title")

    def __init__(self, dest: str = "", title: str = "") -> None:
        super().__init__()
        self.dest = dest
        self.title = title


class HtmlInline(Inline):
    _fields = ("literal",)

    def __init__(self, literal: str = "") -> None:
        super().__init__()
        self.literal = literal


class FootnoteRef(Inline):
    _fields = ("label", "number")

    def __init__(self, label: str = "") -> None:
        super().__init__()
        self.label = label
        self.number: int | None = None
        self.ref_id = ""


class FootnoteBackref(Inline):
    """The little return arrow(s) at the end of a footnote."""

    def __init__(self, ref_ids: list[str] | None = None) -> None:
        super().__init__()
        self.ref_ids: list[str] = ref_ids or []


class Abbreviation(Inline):
    _fields = ("title",)

    def __init__(self, title: str = "") -> None:
        super().__init__()
        self.title = title


def walk(node: Node) -> Iterator[Node]:
    """Yield node and all its descendants, depth first, in document order.

    A node's children are looked at only after it has been yielded, so the
    caller is free to replace them while iterating.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.children))


class NodeVisitor:
    """Dispatch on ``node.type``: a Heading goes to ``visit_heading`` etc.

    Node types without a method of their own end up in ``generic_visit``.
    """

    def visit(self, node: Node):
        method = getattr(self, "visit_" + node.type, None)
        if method is None:
            return self.generic_visit(node)
        return method(node)

    def generic_visit(self, node: Node):
        for child in node.children:
            self.visit(child)


def dump(node: Node, indent: int = 0) -> str:
    """An indented outline of the tree. Handy in tests and when debugging."""
    label = node.type
    for name in node._fields:
        value = getattr(node, name, None)
        if value is not None and value != "" and value != {}:
            label += f" {name}={value!r}"
    lines = ["  " * indent + label]
    for child in node.children:
        lines.append(dump(child, indent + 1))
    return "\n".join(lines)
