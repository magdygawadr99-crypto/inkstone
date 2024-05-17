from __future__ import annotations

import re
from collections import deque
from typing import NamedTuple

from .errors import YamlError

STREAM_START = "stream start"
STREAM_END = "stream end"
DOCUMENT_START = "document start"
DOCUMENT_END = "document end"
BLOCK_SEQUENCE_START = "block sequence start"
BLOCK_MAPPING_START = "block mapping start"
BLOCK_END = "block end"
FLOW_SEQUENCE_START = "["
FLOW_SEQUENCE_END = "]"
FLOW_MAPPING_START = "{"
FLOW_MAPPING_END = "}"
BLOCK_ENTRY = "-"
FLOW_ENTRY = ","
KEY = "key"
VALUE = ":"
ALIAS = "alias"
ANCHOR = "anchor"
TAG = "tag"
SCALAR = "scalar"

_BLANK = " \t"
_LINE_END = "\n\0"
_SPACE = " \t\n\0"
_FLOW_INDICATORS = ",[]{}"

_ESCAPES = {
    "0": "\0",
    "a": "\x07",
    "b": "\x08",
    "t": "\t",
    "\t": "\t",
    "n": "\n",
    "v": "\x0b",
    "f": "\x0c",
    "r": "\r",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\x85",
    "_": "\xa0",
    "L": "\u2028",
    "P": "\u2029",
}
_HEX_ESCAPES = {"x": 2, "u": 4, "U": 8}

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ANCHOR_NAME = re.compile(r"[\w.-]+")
_DOUBLE_QUOTED_RUN = re.compile(r'[^"\\ \t\n]+')
_SINGLE_QUOTED_RUN = re.compile(r"[^' \t\n]+")
_HEX_DIGITS = re.compile(r"[0-9a-fA-F]+\Z")


class Token:
    __slots__ = ("kind", "line", "column", "value", "style")

    def __init__(
        self,
        kind: str,
        line: int,
        column: int,
        value: str | None = None,
        style: str | None = None,
    ):
        self.kind = kind
        # 0-based, like the scanner's own counters; errors add one
        self.line = line
        self.column = column
        self.value = value
        # scalars only: None for plain, otherwise one of ' " | >
        self.style = style

    def __repr__(self) -> str:
        value = "" if self.value is None else f" {self.value!r}"
        return f"<{self.kind}{value} at {self.line + 1}:{self.column + 1}>"


class _SimpleKey(NamedTuple):
    token_number: int
    required: bool
    pos: int
    line: int
    column: int


class Scanner:
    """Turns YAML text into tokens.

    The design is the classic libyaml one. Block structure comes from an
    indentation stack that emits start/end tokens, and because a mapping key
    is only recognisable once its ':' turns up, every token that could begin
    a key is remembered so KEY can be inserted in front of it after the fact.
    """

    def __init__(self, text: str):
        if text.startswith("\ufeff"):
            text = text[1:]
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        bad = _CONTROL_CHARS.search(text)
        if bad:
            line = text.count("\n", 0, bad.start())
            column = bad.start() - (text.rfind("\n", 0, bad.start()) + 1)
            raise YamlError(
                f"control character {bad.group()!r} is not allowed",
                line=line + 1,
                column=column + 1,
            )
        self.text = text
        self.length = len(text)
        self.pos = 0
        self.line = 0
        self.column = 0
        self.queue: deque[Token] = deque([Token(STREAM_START, 0, 0)])
        self.taken = 0
        self.done = False
        self.flow_level = 0
        self.indent = -1
        self.indents: list[int] = []
        self.allow_simple_key = True
        self.simple_keys: dict[int, _SimpleKey] = {}
        # where a JSON-style key ("a":1) just ended, if it did
        self._adjacent_value = -1

    def peek(self) -> Token:
        while self._need_more():
            self._fetch()
        return self.queue[0]

    def next(self) -> Token:
        tok = self.peek()
        # the end token stays put so callers can keep peeking at it
        if tok.kind != STREAM_END:
            self.queue.popleft()
            self.taken += 1
        return tok

    def check(self, *kinds: str) -> bool:
        return self.peek().kind in kinds

    def _need_more(self) -> bool:
        if self.done:
            return False
        if not self.queue:
            return True
        # The head of the queue cannot be handed out while it might still
        # get a KEY inserted in front of it.
        self._expire_simple_keys()
        pending = [key.token_number for key in self.simple_keys.values()]
        return bool(pending) and min(pending) == self.taken

    def _fetch(self) -> None:
        self._skip_to_token()
        self._expire_simple_keys()
        self._unwind(self.column)
        ch = self._peek()
        if ch == "\0":
            return self._fetch_stream_end()
        if self.column == 0:
            if ch == "%":
                self._fail("directives (lines starting with '%') are not supported")
            if self._at_document_marker():
                kind = DOCUMENT_START if ch == "-" else DOCUMENT_END
                return self._fetch_document_marker(kind)
        if ch in "[{":
            return self._fetch_flow_start(ch)
        if ch in "]}":
            return self._fetch_flow_end(ch)
        if ch == ",":
            return self._fetch_flow_entry()
        follows = self._peek(1)
        if ch == "-" and follows in _SPACE:
            return self._fetch_block_entry()
        if ch == "?" and follows in _SPACE:
            self._fail("complex keys ('? key') are not supported")
        if ch == ":" and self._at_value_indicator():
            return self._fetch_value()
        if ch == "*":
            return self._fetch_name(ALIAS)
        if ch == "&":
            return self._fetch_name(ANCHOR)
        if ch == "!":
            return self._fetch_tag()
        if ch in "|>":
            if self.flow_level:
                self._fail("block scalars are not allowed inside flow collections")
            return self._fetch_block_scalar(ch)
        if ch in "'\"":
            return self._fetch_quoted(ch)
        if ch in "%@`":
            self._fail(f"a plain value cannot start with {ch!r}; put it in quotes")
        return self._fetch_plain()

    def _peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.text[index] if index < self.length else "\0"

    def _forward(self, count: int = 1) -> None:
        end = min(self.pos + count, self.length)
        chunk = self.text[self.pos : end]
        breaks = chunk.count("\n")
        if breaks:
            self.line += breaks
            self.column = len(chunk) - chunk.rfind("\n") - 1
        else:
            self.column += len(chunk)
        self.pos = end

    def _fail(self, problem: str, line: int | None = None, column: int | None = None):
        if line is None:
            line, column = self.line, self.column
        raise YamlError(problem, line=line + 1, column=column + 1)

    def _emit(self, kind: str, width: int = 0) -> None:
        self.queue.append(Token(kind, self.line, self.column))
        self._forward(width)

    def _at_document_marker(self) -> bool:
        if self.column != 0:
            return False
        if not self.text.startswith(("---", "..."), self.pos):
            return False
        return self._peek(3) in _SPACE

    def _at_value_indicator(self) -> bool:
        follows = self._peek(1)
        if follows in _SPACE:
            return True
        if not self.flow_level:
            return False
        return follows in _FLOW_INDICATORS or self.pos == self._adjacent_value

    def _skip_to_token(self) -> None:
        while True:
            while self._peek() == " ":
                self._forward()
            if self._peek() == "\t":
                self._skip_tabs()
            if self._peek() == "#":
                while self._peek() not in _LINE_END:
                    self._forward()
            if self._peek() != "\n":
                return
            self._forward()
            if not self.flow_level:
                self.allow_simple_key = True

    def _skip_tabs(self) -> None:
        # Tabs are fine as separators but YAML forbids them as indentation,
        # so it matters whether anything else came before on this line.
        line_start = self.text.rfind("\n", 0, self.pos) + 1
        before = self.text[line_start : self.pos]
        indenting = not self.flow_level and not before.strip(" ")
        line, column = self.line, self.column
        while self._peek() in _BLANK:
            self._forward()
        if indenting and self._peek() not in "#\n\0":
            self._fail("tabs cannot be used for indentation", line, column)

    def _unwind(self, column: int) -> None:
        if self.flow_level:
            return
        while self.indent > column:
            self.indent = self.indents.pop()
            self.queue.append(Token(BLOCK_END, self.line, self.column))

    def _add_indent(self, column: int) -> bool:
        if self.indent < column:
            self.indents.append(self.indent)
            self.indent = column
            return True
        return False

    def _save_simple_key(self) -> None:
        # At the indentation of the current block mapping a key is the only
        # thing that can legally appear, hence "required".
        required = not self.flow_level and self.indent == self.column
        if self.allow_simple_key:
            self._remove_simple_key()
            number = self.taken + len(self.queue)
            self.simple_keys[self.flow_level] = _SimpleKey(
                number, required, self.pos, self.line, self.column
            )

    def _remove_simple_key(self) -> None:
        key = self.simple_keys.pop(self.flow_level, None)
        if key is not None and key.required:
            self._fail("missing ':' after mapping key", key.line, key.column)

    def _expire_simple_keys(self) -> None:
        # a simple key lives on one line, and the spec caps it at 1024 chars
        for level, key in list(self.simple_keys.items()):
            if key.line != self.line or self.pos - key.pos > 1024:
                del self.simple_keys[level]
                if key.required:
                    self._fail("missing ':' after mapping key", key.line, key.column)

    def _fetch_stream_end(self) -> None:
        self._unwind(-1)
        self._remove_simple_key()
        self.simple_keys.clear()
        self.allow_simple_key = False
        self._emit(STREAM_END)
        self.done = True

    def _fetch_document_marker(self, kind: str) -> None:
        if self.flow_level:
            marker = self.text[self.pos : self.pos + 3]
            self._fail(f"found '{marker}' inside an unclosed flow collection")
        self._unwind(-1)
        self._remove_simple_key()
        self.allow_simple_key = False
        self._emit(kind, 3)

    def _fetch_flow_start(self, kind: str) -> None:
        self._save_simple_key()
        self.flow_level += 1
        self.allow_simple_key = True
        self._emit(kind, 1)

    def _fetch_flow_end(self, kind: str) -> None:
        if not self.flow_level:
            self._fail(f"unexpected '{kind}' outside of a flow collection")
        self._remove_simple_key()
        self.flow_level -= 1
        self.allow_simple_key = False
        self._emit(kind, 1)
        self._adjacent_value = self.pos

    def _fetch_flow_entry(self) -> None:
        if not self.flow_level:
            self._fail("unexpected ',' outside of a flow collection")
        self.allow_simple_key = True
        self._remove_simple_key()
        self._emit(FLOW_ENTRY, 1)

    def _fetch_block_entry(self) -> None:
        if self.flow_level:
            self._fail("'- ' entries are not allowed inside flow collections")
        if not self.allow_simple_key:
            self._fail("sequence entries are not allowed here")
        if self._add_indent(self.column):
            self.queue.append(Token(BLOCK_SEQUENCE_START, self.line, self.column))
        self.allow_simple_key = True
        self._remove_simple_key()
        self._emit(BLOCK_ENTRY, 1)

    def _fetch_value(self) -> None:
        key = self.simple_keys.pop(self.flow_level, None)
        if key is not None:
            index = key.token_number - self.taken
            self.queue.insert(index, Token(KEY, key.line, key.column))
            if not self.flow_level and self._add_indent(key.column):
                start = Token(BLOCK_MAPPING_START, key.line, key.column)
                self.queue.insert(index, start)
            self.allow_simple_key = False
        else:
            # A ':' with nothing usable in front of it. The parser reports
            # the missing key; here we only reject the hopeless positions.
            if not self.flow_level:
                if not self.allow_simple_key:
                    self._fail(
                        "mapping values are not allowed here "
                        "(a value containing ': ' needs quotes)"
                    )
                if self._add_indent(self.column):
                    start = Token(BLOCK_MAPPING_START, self.line, self.column)
                    self.queue.append(start)
            self.allow_simple_key = not self.flow_level
        self._emit(VALUE, 1)

    def _fetch_name(self, kind: str) -> None:
        self._save_simple_key()
        self.allow_simple_key = False
        line, column = self.line, self.column
        indicator = self._peek()
        self._forward()
        match = _ANCHOR_NAME.match(self.text, self.pos)
        if match is None:
            self._fail(f"expected a name right after '{indicator}'", line, column)
        self._forward(len(match.group()))
        if self._peek() not in " \t\n\0,[]{}:":
            self._fail(
                f"unexpected character {self._peek()!r} in {kind} name "
                f"(quote the value if '{indicator}' is meant literally)"
            )
        self.queue.append(Token(kind, line, column, match.group()))

    def _fetch_tag(self) -> None:
        self._save_simple_key()
        self.allow_simple_key = False
        line, column = self.line, self.column
        start = self.pos
        if self._peek(1) == "<":
            while self._peek() not in ">\n\0":
                self._forward()
            if self._peek() != ">":
                self._fail("unclosed '!<' in tag", line, column)
            self._forward()
        else:
            self._forward()
            while self._peek() not in _SPACE:
                if self.flow_level and self._peek() in _FLOW_INDICATORS:
                    break
                self._forward()
        self.queue.append(Token(TAG, line, column, self.text[start : self.pos]))

    def _fetch_block_scalar(self, style: str) -> None:
        self.allow_simple_key = True
        self._remove_simple_key()
        self.queue.append(self._scan_block_scalar(style))

    def _fetch_quoted(self, quote: str) -> None:
        self._save_simple_key()
        self.allow_simple_key = False
        self.queue.append(self._scan_quoted(quote))
        self._adjacent_value = self.pos

    def _fetch_plain(self) -> None:
        self._save_simple_key()
        self.allow_simple_key = False
        self.queue.append(self._scan_plain())

    def _scan_plain(self) -> Token:
        line, column = self.line, self.column
        indent = self.indent + 1
        chunks: list[str] = []
        gap = ""
        while True:
            if self._peek() == "#":
                break
            length = 0
            while True:
                ch = self._peek(length)
                if ch in _SPACE:
                    break
                if ch == ":":
                    follows = self._peek(length + 1)
                    if follows in _SPACE:
                        break
                    if self.flow_level and follows in _FLOW_INDICATORS:
                        break
                elif self.flow_level and ch in _FLOW_INDICATORS:
                    break
                length += 1
            if length == 0:
                break
            self.allow_simple_key = False
            chunks.append(gap)
            chunks.append(self.text[self.pos : self.pos + length])
            self._forward(length)
            gap = self._scan_plain_gap()
            if not gap or (not self.flow_level and self.column < indent):
                break
        return Token(SCALAR, line, column, "".join(chunks))

    def _scan_plain_gap(self) -> str:
        """Skip the whitespace after a piece of a plain scalar.

        Returns what the gap folds to if the scalar carries on: the blanks
        themselves within a line, one space for a single line break, n-1
        newlines for n breaks. Empty means the scalar definitely ends here.
        """
        start = self.pos
        while self._peek() in _BLANK:
            self._forward()
        blanks = self.text[start : self.pos]
        if self._peek() != "\n":
            return blanks
        self._forward()
        self.allow_simple_key = True
        breaks = 0
        while True:
            if self._at_document_marker():
                return ""
            while self._peek() == " ":
                self._forward()
            if self._peek() != "\n":
                break
            self._forward()
            breaks += 1
        return "\n" * breaks if breaks else " "

    def _scan_quoted(self, quote: str) -> Token:
        line, column = self.line, self.column
        double = quote == '"'
        run = _DOUBLE_QUOTED_RUN if double else _SINGLE_QUOTED_RUN
        self._forward()
        chunks: list[str] = []
        while True:
            match = run.match(self.text, self.pos)
            if match:
                chunks.append(match.group())
                self._forward(len(match.group()))
            ch = self._peek()
            if ch == "\0":
                self._fail("unclosed quoted string", line, column)
            if ch == quote:
                if not double and self._peek(1) == "'":
                    chunks.append("'")
                    self._forward(2)
                    continue
                self._forward()
                break
            if ch == "\\":
                chunks.append(self._scan_escape(line, column))
            else:
                chunks.append(self._scan_quoted_gap(line, column))
        return Token(SCALAR, line, column, "".join(chunks), quote)

    def _scan_escape(self, start_line: int, start_column: int) -> str:
        line, column = self.line, self.column
        self._forward()
        ch = self._peek()
        if ch in _ESCAPES:
            self._forward()
            return _ESCAPES[ch]
        if ch in _HEX_ESCAPES:
            size = _HEX_ESCAPES[ch]
            code = self._hex(self.pos + 1, size)
            if code is None:
                self._fail(
                    f"expected {size} hexadecimal digits after '\\{ch}'", line, column
                )
            self._forward(size + 1)
            # JSON spells astral characters as a surrogate pair of \u escapes
            if 0xD800 <= code <= 0xDBFF and self.text.startswith("\\u", self.pos):
                low = self._hex(self.pos + 2, 4)
                if low is not None and 0xDC00 <= low <= 0xDFFF:
                    self._forward(6)
                    code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
            if code > 0x10FFFF:
                self._fail(f"'\\{ch}' escape is not a valid code point", line, column)
            return chr(code)
        if ch == "\n":
            # an escaped line break joins the lines without adding a space
            self._forward()
            return self._scan_quoted_breaks(start_line, start_column)
        shown = "end of input" if ch == "\0" else f"'\\{ch}'"
        self._fail(f"unknown escape sequence {shown}", line, column)

    def _hex(self, start: int, size: int) -> int | None:
        digits = self.text[start : start + size]
        if len(digits) != size or not _HEX_DIGITS.match(digits):
            return None
        return int(digits, 16)

    def _scan_quoted_gap(self, start_line: int, start_column: int) -> str:
        start = self.pos
        while self._peek() in _BLANK:
            self._forward()
        blanks = self.text[start : self.pos]
        if self._peek() != "\n":
            return blanks
        self._forward()
        return self._scan_quoted_breaks(start_line, start_column) or " "

    def _scan_quoted_breaks(self, start_line: int, start_column: int) -> str:
        """After a line break inside quotes: eat indentation and blank lines."""
        count = 0
        while True:
            if self._at_document_marker():
                self._fail("unclosed quoted string", start_line, start_column)
            while self._peek() in _BLANK:
                self._forward()
            if self._peek() != "\n":
                return "\n" * count
            self._forward()
            count += 1

    def _scan_block_scalar(self, style: str) -> Token:
        line, column = self.line, self.column
        self._forward()
        chomp, increment = self._scan_block_header()
        # With an explicit indicator the content indent is fixed up front,
        # otherwise the first non-blank line decides.
        indent = max(self.indent, 0) + increment if increment else None
        minimum = self.indent + 1
        lines: list[str] = []
        while self._peek() != "\0":
            width = 0
            while self._peek(width) == " ":
                width += 1
            if self._peek(width) in _LINE_END:
                # spaces beyond the content indent count as text even on an
                # otherwise blank line
                extra = width - indent if indent is not None else 0
                lines.append(" " * max(extra, 0))
                self._forward(width + 1)
                continue
            if indent is None:
                if width < minimum:
                    break
                indent = width
            elif width < indent:
                break
            if indent == 0 and self._at_document_marker():
                break
            self._forward(indent)
            end = self.text.find("\n", self.pos)
            if end == -1:
                end = self.length
            lines.append(self.text[self.pos : end])
            self._forward(end - self.pos + 1)

        trailing = 0
        while lines and not lines[-1]:
            lines.pop()
            trailing += 1
        body = "\n".join(lines) if style == "|" else _fold(lines)
        if chomp == "+":
            body += "\n" * (trailing + 1 if lines else trailing)
        elif chomp != "-" and lines:
            body += "\n"
        return Token(SCALAR, line, column, body, style)

    def _scan_block_header(self) -> tuple[str, int]:
        chomp = ""
        increment = 0
        for _ in range(2):
            ch = self._peek()
            if ch in "+-" and not chomp:
                chomp = ch
            elif ch in "0123456789" and not increment:
                if ch == "0":
                    self._fail("block scalar indentation must be between 1 and 9")
                increment = int(ch)
            else:
                break
            self._forward()
        while self._peek() in _BLANK:
            self._forward()
        if self._peek() == "#":
            while self._peek() not in _LINE_END:
                self._forward()
        if self._peek() not in _LINE_END:
            self._fail(
                "unexpected text after block scalar indicator "
                "(the content starts on the next line)"
            )
        self._forward()
        return chomp, increment


def _fold(lines: list[str]) -> str:
    """Join the lines of a '>' scalar: single breaks become spaces."""
    parts: list[str] = []
    previous = None
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            continue
        if previous is None:
            parts.append("\n" * blank)
        elif previous[0] in _BLANK or line[0] in _BLANK:
            # "more indented" lines keep their line breaks
            parts.append("\n" * (blank + 1))
        else:
            parts.append("\n" * blank if blank else " ")
        parts.append(line)
        previous = line
        blank = 0
    return "".join(parts)


def tokenize(text: str) -> list[Token]:
    """All tokens of ``text``; mostly useful for tests and debugging."""
    scanner = Scanner(text)
    tokens = []
    while True:
        tok = scanner.next()
        tokens.append(tok)
        if tok.kind == STREAM_END:
            return tokens
