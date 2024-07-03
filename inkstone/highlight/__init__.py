"""Syntax highlighting for fenced code blocks.

    from inkstone.highlight import highlight
    html = highlight("print('hi')", "python")

Lexers live in ``lexers/``, one module per language family; each turns
source text into ``(Token, text)`` pairs that ``HtmlFormatter`` renders
with the short CSS classes a ``Style`` knows how to colour.
"""

from __future__ import annotations

from typing import Iterable

from .errors import HighlightError
from .formatter import HtmlFormatter
from .lexer import Lexer, RegexLexer
from .registry import (
    find_lexer,
    get_lexer,
    guess_language,
    language_for_filename,
    list_languages,
)
from .styles import Style, get_style, list_styles, register_style
from .token import Token

__all__ = [
    "HighlightError",
    "HtmlFormatter",
    "Lexer",
    "RegexLexer",
    "Style",
    "Token",
    "get_lexer",
    "get_style",
    "guess_language",
    "highlight",
    "list_languages",
    "list_styles",
    "register_style",
]


def highlight(
    code: str,
    lang: str | None = None,
    linenos: bool | str = False,
    hl_lines: str | Iterable[int] = (),
    css_class: str = "highlight",
    filename: str | None = None,
    line_start: int = 1,
    **options,
) -> str:
    """Highlight ``code`` and return an HTML block.

    ``lang`` is a language name or alias. An unknown or missing language is
    not an error: the code comes back escaped but uncoloured, since a typo
    on a code fence shouldn't break a build. If only ``filename`` is given
    its extension picks the language. Remaining keyword arguments go to
    ``HtmlFormatter``.
    """
    if lang is None and filename:
        lang = language_for_filename(filename)
    lexer = find_lexer(lang)
    formatter = HtmlFormatter(
        linenos=linenos,
        hl_lines=hl_lines,
        css_class=css_class,
        filename=filename,
        line_start=line_start,
        **options,
    )
    # Lexers key on "\n"; Windows line endings would only leave stray CRs
    # at the end of comments and strings.
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return formatter.format(lexer.tokenize(code))
