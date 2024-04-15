from __future__ import annotations

import difflib
import re
from typing import Callable, Iterable

from ..blocks import BlockParser
from ..errors import MarkdownError
from ..inlines import InlineParser
from ..nodes import Document, Link, Node, Text, walk


class Extension:
    """Something that teaches the parser new syntax.

    An extension can hook into the block parser, into the inline parser, or
    rewrite the tree between and after the two phases. All four methods are
    optional. The nodes it produces are ordinary Node subclasses; rendering
    them is the renderers' business.
    """

    name = ""

    def setup_blocks(self, parser: BlockParser) -> None:
        pass

    def setup_inlines(self, parser: InlineParser) -> None:
        pass

    def before_inlines(self, doc: Document) -> None:
        """Called with the block structure in place and inline text still raw."""

    def after_inlines(self, doc: Document) -> None:
        """Called with the finished tree."""


_REGISTRY: dict[str, type[Extension]] = {}

# What you get with Markdown(extensions=None). The remaining ones change the
# meaning of characters people use in ordinary prose, so they are opt-in.
DEFAULT_EXTENSIONS = (
    "tables",
    "strikethrough",
    "tasklists",
    "autolink",
)


def register(cls: type[Extension]) -> type[Extension]:
    _REGISTRY[cls.name] = cls
    return cls


def available() -> list[str]:
    return list(_REGISTRY)


def load(names: Iterable[str | Extension] | None) -> list[Extension]:
    """Instantiate extensions by name.

    The result is in registration order rather than the order asked for, as
    some of them care who gets to look at a line first. Extension classes
    or ready-made instances may be mixed in; they go last.
    """
    if names is None:
        names = DEFAULT_EXTENSIONS
    elif isinstance(names, str):
        # extensions="tables" is an easy mistake to make
        names = [names]
    wanted: set[str] = set()
    custom: list[Extension] = []
    for item in names:
        if isinstance(item, Extension):
            custom.append(item)
        elif isinstance(item, type) and issubclass(item, Extension):
            custom.append(item())
        elif isinstance(item, str) and item in _REGISTRY:
            wanted.add(item)
        else:
            raise MarkdownError(_unknown(item))
    return [cls() for name, cls in _REGISTRY.items() if name in wanted] + custom


def _unknown(item: object) -> str:
    message = f"unknown markdown extension {item!r}"
    if isinstance(item, str):
        close = difflib.get_close_matches(item, _REGISTRY, n=1)
        if close:
            message += f" (did you mean {close[0]!r}?)"
    return message


def replace_in_text(
    root: Node,
    pattern: re.Pattern[str],
    make: Callable[[re.Match[str]], Node | None],
    skip: tuple[type, ...] = (Link,),
) -> None:
    """Replace every match of pattern in the text below root with a node.

    make(match) builds the replacement, or returns None to leave that match
    alone. Text inside nodes of the skip classes is not touched.
    """
    for node in list(walk(root)):
        if type(node) is not Text or node.parent is None:
            continue
        if any(isinstance(ancestor, skip) for ancestor in node.ancestors()):
            continue
        pieces: list[Node] = []
        text = node.literal
        last = 0
        for m in pattern.finditer(text):
            replacement = make(m)
            if replacement is None:
                continue
            if m.start() > last:
                pieces.append(Text(text[last : m.start()]))
            pieces.append(replacement)
            last = m.end()
        if not pieces:
            continue
        if last < len(text):
            pieces.append(Text(text[last:]))
        node.replace_with(*pieces)


# The modules below import Extension from here, hence the late imports.
from .autolink import AutolinkExtension  # noqa: E402
from .marks import (  # noqa: E402
    MarkExtension,
    StrikethroughExtension,
    SubscriptExtension,
    SuperscriptExtension,
)
from .tables import TablesExtension  # noqa: E402
from .tasklists import TaskListsExtension  # noqa: E402

# Order matters in one place: "sub" has to come after "strikethrough" to
# claim the single tilde.
for _cls in (
    TablesExtension,
    StrikethroughExtension,
    TaskListsExtension,
    AutolinkExtension,
    MarkExtension,
    SubscriptExtension,
    SuperscriptExtension,
):
    register(_cls)
