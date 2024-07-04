from __future__ import annotations

from inkstone.highlight import get_lexer
from inkstone.highlight.token import Text, TokenType


def lex(lang: str, code: str) -> list[tuple[TokenType, str]]:
    return list(get_lexer(lang).tokenize(code))


def visible(lang: str, code: str) -> list[tuple[TokenType, str]]:
    """Tokens without whitespace, touching tokens of one type joined up.

    Lexers are free to emit a string as three tokens or one; joining makes
    the assertions independent of that.
    """
    merged: list[tuple[TokenType, str]] = []
    touching = False
    for ttype, value in lex(lang, code):
        if ttype in Text and not value.strip():
            touching = False
            continue
        if touching and merged[-1][0] is ttype:
            merged[-1] = (ttype, merged[-1][1] + value)
        else:
            merged.append((ttype, value))
        touching = True
    return merged


def type_of(lang: str, code: str, text: str) -> TokenType:
    """Type of the first token (as joined by ``visible``) that reads ``text``."""
    tokens = visible(lang, code)
    for ttype, value in tokens:
        if value == text:
            return ttype
    raise AssertionError(f"no token {text!r} in {tokens!r}")


def types_of(lang: str, code: str, text: str) -> list[TokenType]:
    return [ttype for ttype, value in visible(lang, code) if value == text]
