from __future__ import annotations

from inkstone.errors import InkstoneError


class AssetError(InkstoneError):
    """A static file we could not process (bad syntax, missing import...)."""


def line_at(text: str, pos: int) -> int:
    """1-based line number of offset `pos`, counting \\r\\n as one break."""
    head = text[:pos]
    return head.count("\n") + head.replace("\r\n", "").count("\r") + 1
