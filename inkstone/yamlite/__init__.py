"""A reader and writer for the subset of YAML that inkstone needs.

Covers what shows up in front matter and data files: block and flow
collections, all the scalar styles, anchors, merge keys and multiple
documents. Complex keys, custom tags and directives are rejected with an
error instead of being guessed at.
"""

from __future__ import annotations

from .dumper import dumps
from .errors import YamlError
from .parser import Parser

__all__ = ["YamlError", "dumps", "load_all", "loads"]


def loads(text: str | bytes) -> object:
    """Parse the first document in ``text``; None if there is none."""
    for document in _documents(text):
        return document
    return None


def load_all(text: str | bytes) -> list[object]:
    """Parse every document of a ``---`` separated stream."""
    return list(_documents(text))


def _documents(text):
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise YamlError(f"input is not valid UTF-8: {exc.reason}") from None
    try:
        yield from Parser(text).documents()
    except RecursionError:
        raise YamlError("document is nested too deeply") from None
