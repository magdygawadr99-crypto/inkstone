from __future__ import annotations

from inkstone.errors import InkstoneError


class TemplateError(InkstoneError):
    """Base class for template problems.

    `path` is the template's file name when it was loaded from disk and its
    plain name otherwise; `line` is the 1-based line in the template source.
    """


class TemplateSyntaxError(TemplateError):
    pass


class TemplateNotFound(TemplateError):
    def __init__(self, name, message: str | None = None, *, path=None, line=None):
        if message is None:
            message = f"template {name!r} not found"
        super().__init__(message, path=path, line=line)
        self.name = name


class TemplateRuntimeError(TemplateError):
    """Something went wrong while a template was being rendered."""


class UndefinedError(TemplateRuntimeError):
    pass
