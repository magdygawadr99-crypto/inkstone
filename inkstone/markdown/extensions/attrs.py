from __future__ import annotations

import re

from ..nodes import Document, Heading
from ..utils import parse_attrs
from . import Extension

_TRAILING_BLOCK = re.compile(r"[ \t]*(?<!\\)\{([^{}\n]*)\}[ \t]*$")


def split_attrs(text: str) -> tuple[str, dict]:
    """Split ``Title {#id .cls}`` into the title and its attributes.

    The braces are only taken for an attribute list if they hold at least
    one id, class or key=value pair. A heading like ``Using {braces}`` is
    left alone.
    """
    m = _TRAILING_BLOCK.search(text)
    if m is None:
        return text, {}
    attrs = parse_attrs(m.group(1))
    if not attrs or all(value is True for value in attrs.values()):
        return text, {}
    return text[: m.start()], attrs


class AttrsExtension(Extension):
    """Attribute lists on headings: ``## Title {#custom-id .cls}``."""

    name = "attrs"

    def before_inlines(self, doc: Document) -> None:
        for heading in doc.find_all(Heading):
            if heading.raw and heading.raw.endswith("}"):
                heading.raw, heading.attrs = split_attrs(heading.raw)
