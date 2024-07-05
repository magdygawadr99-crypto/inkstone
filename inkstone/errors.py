from __future__ import annotations


class InkstoneError(Exception):
    """Base class for everything we raise on purpose.

    The CLI catches this and prints the message without a traceback, so
    messages should make sense on their own.
    """

    def __init__(self, message: str = "", *, path=None, line: int | None = None):
        super().__init__(message)
        self.message = message
        self.path = path
        self.line = line

    def __str__(self) -> str:
        where = ""
        if self.path is not None:
            where = str(self.path)
            if self.line is not None:
                where += f":{self.line}"
            where += ": "
        return where + self.message


class ConfigError(InkstoneError):
    pass


class ContentError(InkstoneError):
    """Something wrong with a source file (bad front matter, bad date...)."""


class BuildError(InkstoneError):
    pass
