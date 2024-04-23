from __future__ import annotations

import re
from typing import Any, NamedTuple

from .errors import TemplateSyntaxError

DATA = "data"
VARIABLE_BEGIN = "variable_begin"
VARIABLE_END = "variable_end"
BLOCK_BEGIN = "block_begin"
BLOCK_END = "block_end"
NAME = "name"
STRING = "string"
INTEGER = "integer"
FLOAT = "float"
OP = "op"
EOF = "eof"

# two-character operators come first so "**" isn't read as "*" twice
OPERATORS = "** // == != <= >= + - * / % ~ < > = . , : | ( ) [ ] { }".split()
_CLOSING = {"(": ")", "[": "]", "{": "}"}

_tag_start_re = re.compile(r"\{[{%#]")
_whitespace_re = re.compile(r"\s+")
_name_re = re.compile(r"[^\W\d]\w*")
# the lookbehind keeps `rows.0.1` from being read as rows . 0.1
_float_re = re.compile(
    r"(?<!\.)[0-9]+(?:_[0-9]+)*"
    r"(?:\.[0-9]+(?:_[0-9]+)*(?:[eE][+-]?[0-9]+)?|[eE][+-]?[0-9]+)"
)
_integer_re = re.compile(
    r"0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*"
    r"|0[oO][0-7]+(?:_[0-7]+)*"
    r"|0[bB][01]+(?:_[01]+)*"
    r"|[0-9]+(?:_[0-9]+)*"
)
_string_re = re.compile(r"'(?:[^'\\]|\\.)*'" r'|"(?:[^"\\]|\\.)*"', re.S)
_operator_re = re.compile("|".join(re.escape(op) for op in OPERATORS))
_raw_begin_re = re.compile(r"\{%([-+]?)\s*raw\s*([-+]?)%\}")
_raw_end_re = re.compile(r"\{%([-+]?)\s*endraw\s*([-+]?)%\}")
_escape_re = re.compile(
    r"\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.)", re.S
)

_SIMPLE_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "\\": "\\",
    "'": "'",
    '"': '"',
    "\n": "",
}

# people coming from other languages type these a lot
_CHAR_HINTS = {"&": "use 'and'", "!": "use 'not'", "?": "use 'a if cond else b'"}

_DESCRIPTIONS = {
    DATA: "template data",
    VARIABLE_BEGIN: "'{{'",
    VARIABLE_END: "'}}'",
    BLOCK_BEGIN: "'{%'",
    BLOCK_END: "'%}'",
    NAME: "a name",
    STRING: "a string",
    INTEGER: "a number",
    FLOAT: "a number",
    EOF: "end of template",
}


class Token(NamedTuple):
    type: str
    value: Any
    lineno: int

    def test(self, type: str, value: Any = None) -> bool:
        return self.type == type and (value is None or self.value == value)


def describe(token: Token) -> str:
    """How a token is spelled out in error messages."""
    if token.type in (NAME, OP):
        return repr(token.value)
    if token.type == STRING:
        return f"string {token.value!r}"
    if token.type in (INTEGER, FLOAT):
        return f"number {token.value!r}"
    return _DESCRIPTIONS[token.type]


def _unescape(text: str) -> str:
    if "\\" not in text:
        return text

    def replace(match: re.Match) -> str:
        esc = match.group(1)
        if len(esc) > 1:
            code = int(esc[1:], 16)
            # \UFFFFFFFF and friends are not characters, leave them alone
            return chr(code) if code <= 0x10FFFF else match.group()
        return _SIMPLE_ESCAPES.get(esc, "\\" + esc)

    return _escape_re.sub(replace, text)


def _parse_int(text: str) -> int:
    text = text.replace("_", "")
    if text[:2].lower() in ("0x", "0o", "0b"):
        return int(text, 0)
    return int(text)


class Lexer:
    """Splits template source into tokens.

    Whitespace control (`{%-`, `-%}`, trim_blocks, lstrip_blocks) and raw
    blocks are dealt with here, so the parser only ever sees clean data.
    """

    def __init__(
        self,
        source: str,
        path: str | None = None,
        *,
        trim_blocks: bool = False,
        lstrip_blocks: bool = False,
        keep_trailing_newline: bool = False,
    ):
        source = source.replace("\r\n", "\n").replace("\r", "\n")
        if not keep_trailing_newline and source.endswith("\n"):
            source = source[:-1]
        self.source = source
        self.path = path
        self.trim_blocks = trim_blocks
        self.lstrip_blocks = lstrip_blocks
        self.pos = 0
        self.lineno = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        src = self.source
        while True:
            match = _tag_start_re.search(src, self.pos)
            if match is None:
                rest = src[self.pos :]
                self._data(rest, rest)
                break
            start = match.start()
            kind = src[start + 1]
            sign = src[start + 2 : start + 3]
            # "{{+" is a unary plus, only block and comment tags take a "+"
            if sign not in ("-", "+") or (kind == "{" and sign == "+"):
                sign = ""
            before = src[self.pos : start]
            self._data(before, self._strip_before(before, sign, kind != "{"))
            self.pos = start
            if kind == "#":
                self._comment(sign)
            elif kind == "{":
                self._tag(VARIABLE_BEGIN, sign)
            else:
                raw = _raw_begin_re.match(src, start)
                if raw is not None:
                    self._raw(raw)
                else:
                    self._tag(BLOCK_BEGIN, sign)
        self.tokens.append(Token(EOF, None, self.lineno))
        return self.tokens

    def _fail(self, message: str, lineno: int | None = None):
        if lineno is None:
            lineno = self.lineno
        raise TemplateSyntaxError(message, path=self.path, line=lineno)

    def _data(self, original: str, text: str) -> None:
        # `original` is what the source says, `text` what is left of it after
        # whitespace control
        if text:
            last = self.tokens[-1] if self.tokens else None
            if last is not None and last.type == DATA:
                self.tokens[-1] = Token(DATA, last.value + text, last.lineno)
            else:
                self.tokens.append(Token(DATA, text, self.lineno))
        self.lineno += original.count("\n")

    def _strip_before(self, text: str, sign: str, is_block: bool) -> str:
        if sign == "-":
            return text.rstrip()
        if self.lstrip_blocks and is_block and sign != "+":
            line_start = text.rfind("\n") + 1
            at_line_start = self.pos == 0 or self.source[self.pos - 1] == "\n"
            if (line_start > 0 or at_line_start) and not text[line_start:].strip():
                return text[:line_start]
        return text

    def _skip_after(self, sign: str, is_block: bool) -> None:
        src = self.source
        if sign == "-":
            match = _whitespace_re.match(src, self.pos)
            if match is not None:
                self.lineno += match.group().count("\n")
                self.pos = match.end()
        elif is_block and self.trim_blocks and sign != "+":
            if src.startswith("\n", self.pos):
                self.pos += 1
                self.lineno += 1

    def _comment(self, sign: str) -> None:
        src = self.source
        body = self.pos + 2 + len(sign)
        end = src.find("#}", body)
        if end == -1:
            self._fail("unclosed comment, expected '#}'")
        end_sign = src[end - 1] if end > body and src[end - 1] in "-+" else ""
        self.lineno += src.count("\n", self.pos, end)
        self.pos = end + 2
        self._skip_after(end_sign, True)

    def _raw(self, begin: re.Match) -> None:
        src = self.source
        end = _raw_end_re.search(src, begin.end())
        if end is None:
            self._fail("unclosed raw block, expected '{% endraw %}'")
        self.lineno += begin.group().count("\n")
        self.pos = begin.end()
        self._skip_after(begin.group(2), True)
        content = src[self.pos : end.start()]
        self._data(content, self._strip_before(content, end.group(1), True))
        self.lineno += end.group().count("\n")
        self.pos = end.end()
        self._skip_after(end.group(2), True)

    def _tag(self, begin: str, sign: str) -> None:
        src = self.source
        is_block = begin == BLOCK_BEGIN
        opener, closer = ("{%", "%}") if is_block else ("{{", "}}")
        opened_at = self.lineno
        self.tokens.append(Token(begin, opener, self.lineno))
        self.pos += 2 + len(sign)
        brackets: list[str] = []
        while True:
            match = _whitespace_re.match(src, self.pos)
            if match is not None:
                self.lineno += match.group().count("\n")
                self.pos = match.end()
            if self.pos >= len(src):
                self._fail(f"unclosed {opener!r}, expected {closer!r}", opened_at)
            # inside brackets "}}" closes two dicts, not the tag
            if not brackets:
                end_sign = ""
                if src.startswith(closer, self.pos + 1):
                    if src[self.pos] in ("-+" if is_block else "-"):
                        end_sign = src[self.pos]
                if end_sign or src.startswith(closer, self.pos):
                    end = BLOCK_END if is_block else VARIABLE_END
                    self.tokens.append(Token(end, closer, self.lineno))
                    self.pos += len(end_sign) + 2
                    self._skip_after(end_sign, is_block)
                    return
            self._token(brackets)

    def _token(self, brackets: list[str]) -> None:
        src = self.source
        char = src[self.pos]
        if char in "'\"":
            match = _string_re.match(src, self.pos)
            if match is None:
                self._fail("unterminated string literal")
            token = Token(STRING, _unescape(match.group()[1:-1]), self.lineno)
        elif char in "0123456789":
            match = _float_re.match(src, self.pos)
            if match is not None:
                value = float(match.group().replace("_", ""))
                token = Token(FLOAT, value, self.lineno)
            else:
                match = _integer_re.match(src, self.pos)
                token = Token(INTEGER, _parse_int(match.group()), self.lineno)
        else:
            match = _name_re.match(src, self.pos)
            if match is not None:
                token = Token(NAME, match.group(), self.lineno)
            else:
                match = _operator_re.match(src, self.pos)
                if match is None:
                    hint = _CHAR_HINTS.get(char)
                    extra = f" ({hint})" if hint else ""
                    self._fail(f"unexpected character {char!r}{extra}")
                op = match.group()
                if op in _CLOSING:
                    brackets.append(_CLOSING[op])
                elif op in ")]}":
                    if not brackets:
                        self._fail(f"unexpected {op!r}")
                    expected = brackets.pop()
                    if op != expected:
                        self._fail(f"unexpected {op!r}, expected {expected!r}")
                token = Token(OP, op, self.lineno)
        self.tokens.append(token)
        self.lineno += match.group().count("\n")
        self.pos = match.end()


def tokenize(source: str, path: str | None = None, **options) -> list[Token]:
    return Lexer(source, path, **options).tokenize()


class TokenStream:
    """A cursor over the token list, with the helpers the parser wants."""

    def __init__(self, tokens: list[Token], path: str | None = None):
        self._tokens = tokens
        self._index = 0
        self.path = path

    @property
    def current(self) -> Token:
        return self._tokens[self._index]

    def look(self, offset: int = 1) -> Token:
        index = min(self._index + offset, len(self._tokens) - 1)
        return self._tokens[index]

    def next(self) -> Token:
        token = self._tokens[self._index]
        if token.type != EOF:
            self._index += 1
        return token

    def skip(self, count: int = 1) -> None:
        for _ in range(count):
            self.next()

    def at_name(self, *values: str) -> bool:
        token = self.current
        return token.type == NAME and token.value in values

    def at_op(self, *values: str) -> bool:
        token = self.current
        return token.type == OP and token.value in values

    def skip_name(self, value: str) -> bool:
        if self.at_name(value):
            self.next()
            return True
        return False

    def skip_op(self, value: str) -> bool:
        if self.at_op(value):
            self.next()
            return True
        return False

    def expect(self, type: str, value: Any = None) -> Token:
        token = self.current
        if not token.test(type, value):
            wanted = repr(value) if value is not None else _DESCRIPTIONS[type]
            raise TemplateSyntaxError(
                f"expected {wanted}, got {describe(token)}",
                path=self.path,
                line=token.lineno,
            )
        return self.next()

    def expect_op(self, value: str) -> Token:
        return self.expect(OP, value)

    def expect_name(self, value: str | None = None) -> Token:
        return self.expect(NAME, value)
