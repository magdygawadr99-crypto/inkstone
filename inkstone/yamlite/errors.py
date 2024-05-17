from __future__ import annotations

from ..errors import InkstoneError


class YamlError(InkstoneError):
    """Raised for YAML we cannot read, refuse to read, or cannot write.

    ``line`` and ``column`` are 1-based. ``problem`` is the message without
    the position suffix, which is what callers want when they re-raise with
    a line number relative to some bigger file.
    """

    def __init__(
        self,
        problem: str,
        *,
        line: int | None = None,
        column: int | None = None,
        path=None,
    ):
        self.problem = problem
        self.column = column
        message = problem
        if line is not None:
            where = f"line {line}"
            if column is not None:
                where += f", column {column}"
            message = f"{problem} ({where})"
        super().__init__(message, path=path, line=line)
