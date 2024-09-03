from __future__ import annotations

from inkstone.errors import InkstoneError


class ServerError(InkstoneError):
    """The dev server can't start or carry on (port taken, bad address...)."""
