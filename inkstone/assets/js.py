from __future__ import annotations

import re
from typing import NamedTuple

from .errors import AssetError, line_at


class Token(NamedTuple):
    # type is one of: ws nl comment hashbang string template regex number
    # name punct. Keywords and #private names are "name".
    type: str
    value: str
    pos: int
    # What a closing bracket closes, where the lexer can tell:
    #   ")" "head"   the head of an if/for/switch..., a statement must follow
    #   ")" "while"  same, unless this is the tail of a do-while
    #   "}" "block"  the body of one of those, or of else/try/finally
    #   "}" "arrow"  the body of an arrow function
    role: str = ""


_LINE_TERMINATORS = "\n\r\u2028\u2029"
_NUMBER_RE = re.compile(
    r"0[xX][0-9a-fA-F_]+n?|0[oO][0-7_]+n?|0[bB][01_]+n?"
    r"|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d[\d_]*)?n?"
)
_NAME_RE = re.compile(r"(?:[\w$\u200c\u200d]|\\u[0-9a-fA-F]{4}|\\u\{[0-9a-fA-F]+\})+")
_PUNCT_RE = re.compile(
    r">>>=|\.\.\.|===|!==|\*\*=|<<=|>>=|>>>|&&=|\|\|=|\?\?="
    r"|=>|==|!=|<=|>=|&&|\|\||\?\?|\?\.(?!\d)|\+\+|--"
    r"|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<|>>|\*\*"
    r"|[{}()\[\];,<>+\-*/%&|^!~?:=.@]"
)

# keywords that leave us expecting an operand, so a following / is a regex
_REGEX_AFTER = frozenset(
    "return typeof instanceof in new delete void throw case do else yield await "
    "default extends".split()
)
# a parenthesised head follows these, and then the rest of the statement
_CONTROL_KEYWORDS = frozenset(["if", "for", "with", "switch", "catch"])
_BLOCK_KEYWORDS = frozenset(["else", "do", "try", "finally", "catch"])
_CLOSERS = {"(": ")", "[": "]", "{": "}"}


class _Frame:
    __slots__ = ("kind", "block", "role", "ternaries")

    def __init__(self, kind: str):
        self.kind = kind
        self.block = False
        self.role = ""
        self.ternaries = 0


class _Lexer:
    """Tokenizer with just enough parser state to tell `/` from a regex.

    XXX the brace tracking treats the body of a function *expression* as a
    block, so `x = function(){} / 2` is misread as starting a regex. Nobody
    writes that, but it is wrong.
    """

    def __init__(self, src: str, path=None):
        self.src = src
        self.path = path
        self.tokens: list[Token] = []
        self.frames = [_Frame("")]
        self.prev: Token | None = None
        self.prev_is_property = False
        self.before_prev: Token | None = None
        self.regex_ok = True
        self.label_colon = False

    def fail(self, message: str, pos: int):
        raise AssetError(message, path=self.path, line=line_at(self.src, pos))

    def scan(self, pos: int = 0, nested: bool = False) -> int:
        """Tokenize from `pos`. In nested mode stop after the `}` that closes
        a template substitution and return the offset just past it, or -1 if
        there is no such brace."""
        src = self.src
        end = len(src)
        while pos < end:
            ch = src[pos]
            role = ""
            if ch in _LINE_TERMINATORS:
                stop = pos + (2 if src.startswith("\r\n", pos) else 1)
                kind = "nl"
            elif ch in " \t\v\f\xa0\ufeff" or ch.isspace():
                stop = pos + 1
                while stop < end and src[stop] not in _LINE_TERMINATORS and (
                    src[stop] in " \t\v\f\xa0\ufeff" or src[stop].isspace()
                ):
                    stop += 1
                kind = "ws"
            elif ch == "/":
                kind, stop = self.slash(pos)
            elif ch in "\"'":
                stop = self.string_end(pos)
                kind = "string"
            elif ch == "`":
                stop = self.template_end(pos)
                kind = "template"
            elif ch.isdigit() or (ch == "." and src[pos + 1 : pos + 2].isdigit()):
                stop = _NUMBER_RE.match(src, pos).end()
                kind = "number"
            elif ch == "#":
                if pos == 0 and src.startswith("#!"):
                    stop = self.line_end(pos)
                    kind = "hashbang"
                else:
                    match = _NAME_RE.match(src, pos + 1)
                    if match is None:
                        self.fail("unexpected '#'", pos)
                    stop = match.end()
                    kind = "name"
            elif ch == "$" or ch == "_" or ch == "\\" or ch.isalpha():
                match = _NAME_RE.match(src, pos)
                if match is None:
                    self.fail("unexpected '\\'", pos)
                stop = match.end()
                kind = "name"
            else:
                match = _PUNCT_RE.match(src, pos)
                if match is None:
                    self.fail(f"unexpected character {ch!r}", pos)
                stop = match.end()
                kind = "punct"
                if ch == "}" and nested and len(self.frames) == 1:
                    return stop
                role = self.punctuator(match.group())
            tok = Token(kind, src[pos:stop], pos, role)
            self.tokens.append(tok)
            if kind not in ("ws", "nl", "comment", "hashbang"):
                self.note(tok)
            pos = stop
        # in nested mode running out of input means the template never closed;
        # the caller knows where it started
        return -1 if nested else pos

    def line_end(self, pos: int) -> int:
        src = self.src
        while pos < len(src) and src[pos] not in _LINE_TERMINATORS:
            pos += 1
        return pos

    def slash(self, pos: int) -> tuple[str, int]:
        src = self.src
        if src.startswith("//", pos):
            return "comment", self.line_end(pos)
        if src.startswith("/*", pos):
            stop = src.find("*/", pos + 2)
            if stop < 0:
                self.fail("unterminated comment", pos)
            return "comment", stop + 2
        if not self.regex_ok:
            self.punctuator("/")
            return "punct", pos + (2 if src.startswith("/=", pos) else 1)
        i = pos + 1
        in_class = False
        while i < len(src):
            ch = src[i]
            if ch == "\\":
                i += 2
                continue
            if ch in _LINE_TERMINATORS:
                break
            if ch == "[":
                in_class = True
            elif ch == "]":
                in_class = False
            elif ch == "/" and not in_class:
                flags = _NAME_RE.match(src, i + 1)
                return "regex", flags.end() if flags else i + 1
            i += 1
        self.fail("unterminated regular expression", pos)

    def string_end(self, pos: int) -> int:
        src = self.src
        quote = src[pos]
        i = pos + 1
        while i < len(src):
            ch = src[i]
            if ch == quote:
                return i + 1
            if ch == "\\":
                i += 3 if src.startswith("\r\n", i + 1) else 2
                continue
            if ch in "\n\r":
                break
            i += 1
        self.fail("unterminated string", pos)

    def template_end(self, pos: int) -> int:
        src = self.src
        i = pos + 1
        while i < len(src):
            ch = src[i]
            if ch == "`":
                return i + 1
            if ch == "\\":
                i += 2
            elif ch == "$" and src.startswith("{", i + 1):
                # the substitution is ordinary code and can hold anything,
                # more templates included; lex it properly to find its end
                inner = _Lexer(src, self.path)
                i = inner.scan(i + 2, nested=True)
                if i < 0:
                    break
            else:
                i += 1
        self.fail("unterminated template literal", pos)

    def punctuator(self, value: str) -> str:
        """Update bracket bookkeeping; returns the role of a closing bracket."""
        if value in ("(", "[", "{"):
            frame = _Frame(value)
            if value == "(":
                frame.role = self.paren_role()
            elif value == "{":
                frame.block = self.opens_block()
                frame.role = self.brace_role(frame.block)
            self.frames.append(frame)
            self.regex_ok = True
        elif value in (")", "]", "}"):
            frame = self.frames.pop() if len(self.frames) > 1 else _Frame("")
            if _CLOSERS.get(frame.kind) != value:
                # unbalanced input; no point guessing
                frame = _Frame("")
            if value == ")":
                self.regex_ok = frame.role != ""
            else:
                self.regex_ok = value == "}" and frame.block
            return frame.role
        elif value in ("++", "--"):
            # prefix or postfix, either way what may follow does not change
            pass
        else:
            top = self.frames[-1]
            if value == "?":
                top.ternaries += 1
            elif value == ":":
                if top.ternaries:
                    top.ternaries -= 1
                    self.label_colon = False
                else:
                    self.label_colon = top.kind == "" or top.block
            self.regex_ok = True
        return ""

    def brace_role(self, block: bool) -> str:
        prev = self.prev
        if prev is None or not block:
            return ""
        if prev.value == "=>":
            return "arrow"
        if prev.role in ("head", "while"):
            return "block"
        keyword = prev.type == "name" and not self.prev_is_property
        return "block" if keyword and prev.value in _BLOCK_KEYWORDS else ""

    def paren_role(self) -> str:
        prev = self.prev
        if prev is None or prev.type != "name" or self.prev_is_property:
            return ""
        if prev.value == "while":
            return "while"
        if prev.value in _CONTROL_KEYWORDS:
            return "head"
        before = self.before_prev
        if prev.value == "await" and before is not None and before.value == "for":
            return "head"
        return ""

    def opens_block(self) -> bool:
        prev = self.prev
        if prev is None or not self.regex_ok:
            return True
        if prev.type == "punct":
            if prev.value in (";", "{", "}", ")", "=>"):
                return True
            return prev.value == ":" and self.label_colon
        if prev.type == "name":
            return prev.value in _BLOCK_KEYWORDS and not self.prev_is_property
        return True

    def note(self, tok: Token) -> None:
        prev = self.prev
        if tok.type == "name":
            is_property = prev is not None and prev.value in (".", "?.")
            self.regex_ok = not is_property and tok.value in _REGEX_AFTER
            self.prev_is_property = is_property
        elif tok.type != "punct":
            self.regex_ok = False
        self.before_prev = prev
        self.prev = tok


def tokenize(source: str, path=None) -> list[Token]:
    """Split JavaScript source into tokens (whitespace and comments included)."""
    lexer = _Lexer(source, path)
    lexer.scan()
    return lexer.tokens


_RESTRICTED = frozenset(["return", "break", "continue", "throw", "yield"])
_ENDERS = frozenset([")", "]", "}", ",", ";", ":"])
# punctuators that can only begin something, never carry an expression on
_STARTERS = frozenset(["{", "!", "~", "++", "--", "@", "..."])
_LICENCE_RE = re.compile(r"@(?:license|preserve|cc_on)\b")


def _keep_comment(text: str) -> bool:
    return text.startswith("/*!") or (
        text.startswith("/*") and _LICENCE_RE.search(text) is not None
    )


def _can_end_statement(tok: Token) -> bool:
    if tok.type != "punct":
        return True
    if tok.value == ")":
        return tok.role != "head"
    if tok.value == "}":
        return tok.role != "block"
    return tok.value in ("]", "++", "--")


def _needs_newline(prev: Token, is_property: bool, tok: Token) -> bool:
    """Could dropping the line break between these two change the parse?

    Leaving a break in is always safe, so this only says no when it is sure:
    either the statement cannot have ended at `prev`, or `tok` is something
    the parser would have glued on regardless of the break.
    """
    closing = tok.type == "punct" and tok.value in _ENDERS
    keyword = prev.type == "name" and not is_property
    if keyword and prev.value in _RESTRICTED:
        return not closing
    if closing or not _can_end_statement(prev):
        return False
    if prev.role == "arrow" or (prev.type == "punct" and prev.value in ("++", "--")):
        # Nothing attaches to `() => {}` or `a++`. A ( or [ on the next line
        # would continue most expressions, but here it starts a new one.
        return tok.value not in (".", "?.")
    if tok.type == "name":
        return tok.value not in ("in", "instanceof")
    if tok.type == "template":
        return False
    if tok.type != "punct":
        return True
    if tok.value == "{":
        # Allman-style `else` newline `{`
        return not (keyword and prev.value in _BLOCK_KEYWORDS)
    if tok.value in _STARTERS:
        return True
    if tok.value in ("[", "*"):
        # in a class body, `x` newline `[y]() {}` is a field and then a method
        return prev.type != "punct" or prev.value == "]"
    return False


def _wordy(tok: Token) -> bool:
    return tok.type in ("name", "number")


def _needs_space(prev: Token, tok: Token) -> bool:
    # a regex counts as a word on its right edge: /x/ in y must not turn
    # into the flags "in"
    if (_wordy(prev) or prev.type == "regex") and _wordy(tok):
        return True
    if prev.type in ("string", "template") or tok.type in ("string", "template"):
        return False
    last = prev.value[-1]
    first = tok.value[0]
    if first == "." and prev.type == "number":
        # 1 .toString() needs the space, 1.5.toFixed() and 0x1f.toString() do not
        return prev.value.replace("_", "").isdigit()
    if last in "+-" and first == last:
        return True
    if last == "/" and first in "/*":
        return True
    # <!-- and --> are comments in scripts, believe it or not
    return (last == "<" and first == "!") or (last == "-" and first == ">")


def _after_semicolons(tokens: list[Token], i: int) -> Token | None:
    """The next token that will be emitted and is not another `;`."""
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "comment":
            if _keep_comment(tok.value):
                return tok
        elif tok.type not in ("ws", "nl") and tok.value != ";":
            return tok
        i += 1
    return None


def _redundant_semicolon(
    prev: Token | None, is_property: bool, nxt: Token | None
) -> bool:
    """Is a `;` between prev and a following `}` safe to drop?"""
    if nxt is None or nxt.type != "punct" or nxt.value != "}":
        return False
    if prev is None:
        return False
    if prev.type == "punct":
        # `if (x);` and `label:;` need their empty statement
        return not (prev.role in ("head", "while") or prev.value == ":")
    if prev.type == "name" and not is_property:
        return prev.value not in ("else", "do")
    return True


def minify_js(source: str, *, path=None) -> str:
    """Strip comments and whitespace without changing what the code means.

    Deliberately modest: identifiers are never renamed, and a line break is
    kept wherever semicolon insertion might depend on it.
    """
    if source.startswith("\ufeff"):
        source = source[1:]
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    tokens = tokenize(source, path)

    out: list[str] = []
    prev: Token | None = None
    prev_is_property = False
    newline = False
    after_comment = False
    for i, tok in enumerate(tokens):
        kind = tok.type
        if kind == "ws":
            continue
        if kind == "nl":
            newline = True
            continue
        if kind == "hashbang":
            out.append(tok.value + "\n")
            continue
        if kind == "comment":
            if not _keep_comment(tok.value):
                # a block comment spanning lines is a line break as far as
                # semicolon insertion goes
                if tok.value.startswith("/*") and "\n" in tok.value:
                    newline = True
                continue
            if out and newline:
                out.append("\n")
            out.append(tok.value)
            newline = False
            after_comment = True
            continue

        if kind == "punct" and tok.value == ";":
            nxt = _after_semicolons(tokens, i + 1)
            if _redundant_semicolon(prev, prev_is_property, nxt):
                continue
        if after_comment:
            if newline:
                out.append("\n")
        elif prev is not None:
            if newline and _needs_newline(prev, prev_is_property, tok):
                out.append("\n")
            elif _needs_space(prev, tok):
                out.append(" ")
        out.append(tok.value)
        prev_is_property = (
            kind == "name" and prev is not None and prev.value in (".", "?.")
        )
        prev = tok
        newline = False
        after_comment = False
    return "".join(out)
