"""A small Jinja-flavoured template engine, used to render the themes."""

from __future__ import annotations

from .environment import Environment, Template, select_autoescape
from .errors import (
    TemplateError,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    UndefinedError,
)
from .loaders import BaseLoader, ChoiceLoader, DictLoader, FileSystemLoader
from .markup import Markup, escape
from .runtime import (
    Context,
    StrictUndefined,
    Undefined,
    pass_context,
    pass_environment,
)

__all__ = [
    "BaseLoader",
    "ChoiceLoader",
    "Context",
    "DictLoader",
    "Environment",
    "FileSystemLoader",
    "Markup",
    "StrictUndefined",
    "Template",
    "TemplateError",
    "TemplateNotFound",
    "TemplateRuntimeError",
    "TemplateSyntaxError",
    "Undefined",
    "UndefinedError",
    "escape",
    "pass_context",
    "pass_environment",
    "select_autoescape",
]
