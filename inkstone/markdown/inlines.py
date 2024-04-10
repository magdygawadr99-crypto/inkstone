from __future__ import annotations

import re
from typing import Callable

from .entities import decode_entity
from .nodes import (
    Code,
    Document,
    Emphasis,
    HtmlInline,
    Image,
    LineBreak,
    Link,
    Node,
    Reference,
    SoftBreak,
    Strong,
    Text,
)
from .utils import (
    ENTITY,
    ESCAPABLE,
    is_punctuation,
    normalize_label,
    normalize_uri,
    unescape_string,
)

_TAG_NAME = r"[A-Za-z][A-Za-z0-9-]*"
_ATTRIBUTE_NAME = r"[a-zA-Z_:][a-zA-Z0-9:._-]*"
_ATTRIBUTE_VALUE = r"""(?:[^"'=<>`\x00-\x20]+|'[^']*'|"[^"]*")"""
_ATTRIBUTE = r"(?:\s+" + _ATTRIBUTE_NAME + r"(?:\s*=\s*" + _ATTRIBUTE_VALUE + ")?)"
OPEN_TAG = "<" + _TAG_NAME + _ATTRIBUTE + r"*\s*/?>"
CLOSE_TAG = "</" + _TAG_NAME + r"\s*>"

_HTML_TAG = re.compile(
    "|".join(
        [
            OPEN_TAG,
            CLOSE_TAG,
            r"<!-->|<!--->|<!--[\s\S]*?-->",
            r"<\?[\s\S]*?\?>",
            r"<![A-Za-z]+[^>]*>",
            r"<!\[CDATA\[[\s\S]*?\]\]>",
        ]
    )
)

_ESCAPABLE = re.compile(ESCAPABLE)
_ENTITY = re.compile(ENTITY)
_TICKS = re.compile(r"`+")
_EMAIL_AUTOLINK = re.compile(
    r"<([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*)>"
)
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9.+-]{1,31}:[^<>\x00-\x20]*)>")
_LINK_LABEL = re.compile(r"\[(?:[^\\\[\]]|\\.){0,1000}\]", re.S)
_LINK_DEST_BRACES = re.compile(r"<(?:[^<>\n\\\x00]|\\.)*>")
# A backslash may sit in front of anything in a title; only the matching
# closing quote (or a paren, for the third form) has to be escaped.
_LINK_TITLE = re.compile(
    r'"(?:\\[\s\S]|[^\\"\x00])*"'
    r"|'(?:\\[\s\S]|[^\\'\x00])*'"
    r"|\((?:\\[\s\S]|[^\\()\x00])*\)"
)
_SPNL = re.compile(r"[ \t]*(?:\n[ \t]*)?")
_REST_OF_LINE = re.compile(r"[ \t]*(?:\n|$)")
_ELLIPSIS = re.compile(r"\.\.\.")
_DASHES = re.compile(r"--+")

_BASE_SPECIALS = "\n`[]\\!<&*_"
_WHITESPACE = " \t\n\x0b\x0c\r"
# Parentheses in a link destination may nest, but only so far: without a
# limit "[a](b" repeated a few thousand times takes quadratic time.
_MAX_PAREN_DEPTH = 32

InlineHook = Callable[["InlineParser"], bool]
TextScanner = Callable[["InlineParser", "re.Match[str]"], bool]


class _Delimiter:
    """An entry on the stack of emphasis-like delimiter runs."""

    __slots__ = (
        "char",
        "count",
        "orig_count",
        "node",
        "prev",
        "next",
        "can_open",
        "can_close",
    )

    def __init__(
        self, char: str, count: int, node: Text, can_open: bool, can_close: bool
    ) -> None:
        self.char = char
        self.count = count
        self.orig_count = count
        self.node = node
        self.prev: _Delimiter | None = None
        self.next: _Delimiter | None = None
        self.can_open = can_open
        self.can_close = can_close


class _Bracket:
    """A "[" or "![" that might still turn out to open a link or image."""

    __slots__ = (
        "node",
        "prev",
        "prev_delimiter",
        "index",
        "image",
        "active",
        "bracket_after",
    )

    def __init__(self, node: Text, index: int, image: bool) -> None:
        self.node = node
        self.prev: _Bracket | None = None
        self.prev_delimiter: _Delimiter | None = None
        # where the "[" sits in the subject
        self.index = index
        self.image = image
        self.active = True
        self.bracket_after = False


def _smart_dashes(m: re.Match) -> str:
    # Runs of hyphens become em dashes where possible, with en dashes making
    # up the remainder, so that "-----" is not left with a stray hyphen.
    n = len(m.group())
    if n % 3 == 0:
        em, en = n // 3, 0
    elif n % 2 == 0:
        em, en = 0, n // 2
    elif n % 3 == 2:
        em, en = (n - 2) // 3, 1
    else:
        em, en = (n - 4) // 3, 2
    return "\u2014" * em + "\u2013" * en


class InlineParser:
    """Turns the text of a paragraph, heading or table cell into inline nodes.

    Works on one string at a time and keeps the nodes in a flat list while
    parsing; emphasis and links are built by folding slices of that list
    into a new parent once both ends are known.
    """

    def __init__(self, smart: bool = False) -> None:
        self.doc: Document | None = None
        self.refmap: dict[str, Reference] = {}
        self._smart = smart
        self._hooks: dict[str, list[InlineHook]] = {}
        self._scanners: list[tuple[re.Pattern[str], TextScanner]] = []
        self._marks: dict[str, dict[int, type[Node]]] = {}
        # built on first use, and again whenever the set of special
        # characters may have changed
        self._text_re: re.Pattern[str] | None = None
        self._handlers: dict[str, Callable[[], bool]] = {}
        self._reset("")

    @property
    def smart(self) -> bool:
        return self._smart

    @smart.setter
    def smart(self, value: bool) -> None:
        self._smart = value
        self._text_re = None

    def add_hook(self, char: str, hook: InlineHook) -> None:
        """Call hook(parser) when the parser sits on char, before the built-ins.

        The hook returns True if it consumed something.
        """
        self._hooks.setdefault(char, []).append(hook)
        self._text_re = None

    def add_scanner(self, pattern: re.Pattern[str], scanner: TextScanner) -> None:
        """Look for pattern inside runs of ordinary text.

        scanner(parser, match) is called with the parser positioned at the
        start of the match and may consume beyond the end of the run.
        """
        self._scanners.append((pattern, scanner))

    def add_mark(self, char: str, length: int, node_class: type[Node]) -> None:
        """Wrap text between two runs of `length` chars in a node_class node."""
        self._marks.setdefault(char, {})[length] = node_class
        self._text_re = None

    def parse(self, text: str, doc: Document | None = None) -> list[Node]:
        """Parse text and return the resulting nodes, not attached to anything."""
        if self._text_re is None:
            self._compile()
        self._reset(text)
        self.doc = doc
        self.refmap = doc.references if doc is not None else {}
        while self.pos < len(self.subject):
            self._parse_inline()
        self._process_emphasis(None)
        nodes = _tidy(self.nodes)
        self._reset("")
        return nodes

    def _reset(self, text: str) -> None:
        self.subject = text
        self.pos = 0
        self.nodes: list[Node] = []
        self._delimiters: _Delimiter | None = None
        self._brackets: _Bracket | None = None

    def _compile(self) -> None:
        self._handlers = {
            "\n": self._parse_newline,
            "\\": self._parse_backslash,
            "`": self._parse_backticks,
            "*": self._parse_delimiters,
            "_": self._parse_delimiters,
            "[": self._parse_open_bracket,
            "!": self._parse_bang,
            "]": self._parse_close_bracket,
            "<": self._parse_angle,
            "&": self._parse_entity,
        }
        for char in self._marks:
            self._handlers[char] = self._parse_delimiters
        specials = set(_BASE_SPECIALS) | set(self._marks) | set(self._hooks)
        if self.smart:
            self._handlers["'"] = self._parse_delimiters
            self._handlers['"'] = self._parse_delimiters
            specials.update("'\"")
        chars = "".join(sorted(specials))
        self._text_re = re.compile("[^" + re.escape(chars) + "]+")

    def add(self, node: Node) -> Node:
        self.nodes.append(node)
        return node

    def add_text(self, text: str) -> None:
        if self.smart:
            text = _DASHES.sub(_smart_dashes, _ELLIPSIS.sub("\u2026", text))
        self.nodes.append(Text(text))

    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.subject[index] if index < len(self.subject) else ""

    def _parse_inline(self) -> None:
        char = self.subject[self.pos]
        for hook in self._hooks.get(char, ()):
            if hook(self):
                return
        handler = self._handlers.get(char)
        matched = self._parse_text() if handler is None else handler()
        if not matched:
            self.pos += 1
            self.nodes.append(Text(char))

    def _parse_text(self) -> bool:
        m = self._text_re.match(self.subject, self.pos)
        if m is None:
            return False
        end = m.end()
        hit = scanner = None
        for pattern, candidate in self._scanners:
            found = pattern.search(self.subject, self.pos, end)
            if found is not None and (hit is None or found.start() < hit.start()):
                hit, scanner = found, candidate
        if hit is None:
            self.add_text(self.subject[self.pos : end])
            self.pos = end
            return True
        if hit.start() > self.pos:
            self.add_text(self.subject[self.pos : hit.start()])
        self.pos = hit.start()
        if not scanner(self, hit):
            # false alarm; step over one char so the same spot isn't found again
            self.nodes.append(Text(self.subject[self.pos]))
            self.pos += 1
        return True

    def _parse_newline(self) -> bool:
        self.pos += 1
        last = self.nodes[-1] if self.nodes else None
        if isinstance(last, Text) and last.literal.endswith(" "):
            hard = last.literal.endswith("  ")
            last.literal = last.literal.rstrip(" ")
            self.nodes.append(LineBreak() if hard else SoftBreak())
        else:
            self.nodes.append(SoftBreak())
        while self.peek() == " ":
            self.pos += 1
        return True

    def _parse_backslash(self) -> bool:
        self.pos += 1
        char = self.peek()
        if char == "\n":
            self.pos += 1
            self.nodes.append(LineBreak())
            while self.peek() == " ":
                self.pos += 1
        elif char and _ESCAPABLE.match(char):
            self.pos += 1
            self.nodes.append(Text(char))
        else:
            self.nodes.append(Text("\\"))
        return True

    def _parse_backticks(self) -> bool:
        ticks = _TICKS.match(self.subject, self.pos).group()
        self.pos += len(ticks)
        after_open = self.pos
        pos = after_open
        while True:
            m = _TICKS.search(self.subject, pos)
            if m is None:
                break
            pos = m.end()
            if m.group() != ticks:
                continue
            content = self.subject[after_open : m.start()].replace("\n", " ")
            if content.strip(" ") and content[0] == " " and content[-1] == " ":
                content = content[1:-1]
            self.nodes.append(Code(content))
            self.pos = pos
            return True
        # no closing run of the same length: the backticks are just text
        self.nodes.append(Text(ticks))
        return True

    def _parse_angle(self) -> bool:
        m = _EMAIL_AUTOLINK.match(self.subject, self.pos)
        if m is not None:
            link = Link(normalize_uri("mailto:" + m.group(1)))
            link.children = [Text(m.group(1))]
            self.nodes.append(link)
            self.pos = m.end()
            return True
        m = _AUTOLINK.match(self.subject, self.pos)
        if m is not None:
            link = Link(normalize_uri(m.group(1)))
            link.children = [Text(m.group(1))]
            self.nodes.append(link)
            self.pos = m.end()
            return True
        m = _HTML_TAG.match(self.subject, self.pos)
        if m is not None:
            self.nodes.append(HtmlInline(m.group()))
            self.pos = m.end()
            return True
        return False

    def _parse_entity(self) -> bool:
        m = _ENTITY.match(self.subject, self.pos)
        if m is None:
            return False
        decoded = decode_entity(m.group())
        if decoded is None:
            return False
        self.nodes.append(Text(decoded))
        self.pos = m.end()
        return True

    def _scan_delimiters(self, char: str) -> tuple[int, bool, bool]:
        subject = self.subject
        start = self.pos
        end = start + 1
        if char not in "'\"":
            while end < len(subject) and subject[end] == char:
                end += 1

        before = subject[start - 1] if start > 0 else "\n"
        after = subject[end] if end < len(subject) else "\n"
        after_space = after.isspace()
        after_punct = is_punctuation(after)
        before_space = before.isspace()
        before_punct = is_punctuation(before)

        left_flanking = not after_space and (
            not after_punct or before_space or before_punct
        )
        right_flanking = not before_space and (
            not before_punct or after_space or after_punct
        )
        if char == "_":
            can_open = left_flanking and (not right_flanking or before_punct)
            can_close = right_flanking and (not left_flanking or after_punct)
        elif char in "'\"":
            can_open = left_flanking and not right_flanking
            can_close = right_flanking
        else:
            can_open = left_flanking
            can_close = right_flanking
        return end - start, can_open, can_close

    def _parse_delimiters(self) -> bool:
        char = self.subject[self.pos]
        count, can_open, can_close = self._scan_delimiters(char)
        start = self.pos
        self.pos += count
        if char == "'":
            literal = "\u2019"
        elif char == '"':
            literal = "\u201c"
        else:
            literal = self.subject[start : self.pos]
        node = Text(literal)
        self.nodes.append(node)

        if not (can_open or can_close):
            return True
        if char in self._marks and count not in self._marks[char]:
            return True
        delim = _Delimiter(char, count, node, can_open, can_close)
        delim.prev = self._delimiters
        if delim.prev is not None:
            delim.prev.next = delim
        self._delimiters = delim
        return True

    def _remove_delimiter(self, delim: _Delimiter) -> None:
        if delim.prev is not None:
            delim.prev.next = delim.next
        if delim.next is None:
            self._delimiters = delim.prev
        else:
            delim.next.prev = delim.prev

    def _index(self, node: Node) -> int:
        nodes = self.nodes
        for i in range(len(nodes) - 1, -1, -1):
            if nodes[i] is node:
                return i
        raise ValueError("delimiter node is not in the output list")

    def _process_emphasis(self, stack_bottom: _Delimiter | None) -> None:
        openers_bottom: dict[tuple, _Delimiter | None] = {}

        closer = self._delimiters
        while closer is not None and closer.prev is not stack_bottom:
            closer = closer.prev

        while closer is not None:
            if not closer.can_close:
                closer = closer.next
                continue
            char = closer.char
            emphasis = char in "*_"
            if emphasis:
                key: tuple = (char, closer.can_open, closer.orig_count % 3)
            else:
                key = (char, closer.orig_count)
            bottom = openers_bottom.get(key, stack_bottom)

            opener = closer.prev
            found = False
            while opener is not None and opener not in (stack_bottom, bottom):
                if opener.char == char and opener.can_open:
                    if emphasis:
                        # "rule of three": a run that can both open and close
                        # doesn't pair up if the lengths add up to a multiple
                        # of 3, unless both are multiples of 3 themselves
                        odd = (
                            (closer.can_open or opener.can_close)
                            and closer.orig_count % 3 != 0
                            and (opener.orig_count + closer.orig_count) % 3 == 0
                        )
                        found = not odd
                    elif char in self._marks:
                        found = opener.orig_count == closer.orig_count
                    else:
                        found = True
                    if found:
                        break
                opener = opener.prev

            old_closer = closer
            if char == "'":
                closer.node.literal = "\u2019"
                if found:
                    opener.node.literal = "\u2018"
                closer = closer.next
            elif char == '"':
                closer.node.literal = "\u201d"
                if found:
                    opener.node.literal = "\u201c"
                closer = closer.next
            elif not found:
                closer = closer.next
            elif emphasis:
                closer = self._wrap_emphasis(opener, closer)
            else:
                closer = self._wrap_mark(opener, closer)

            if not found:
                # nothing below this point can match a closer like this one
                openers_bottom[key] = old_closer.prev
                if not old_closer.can_open:
                    self._remove_delimiter(old_closer)

        while self._delimiters is not None and self._delimiters is not stack_bottom:
            self._remove_delimiter(self._delimiters)

    def _wrap_emphasis(
        self, opener: _Delimiter, closer: _Delimiter
    ) -> _Delimiter | None:
        use = 2 if closer.count >= 2 and opener.count >= 2 else 1
        opener.count -= use
        closer.count -= use
        opener.node.literal = opener.node.literal[:-use]
        closer.node.literal = closer.node.literal[:-use]

        nodes = self.nodes
        end = self._index(closer.node)
        start = self._index(opener.node)
        wrapper: Node = Strong() if use == 2 else Emphasis()
        wrapper.children = nodes[start + 1 : end]
        nodes[start + 1 : end] = [wrapper]

        # anything on the stack between the two is now inside the wrapper
        if opener.next is not closer:
            opener.next = closer
            closer.prev = opener

        following: _Delimiter | None = closer
        if closer.count == 0:
            del nodes[start + 2]
            following = closer.next
            self._remove_delimiter(closer)
        if opener.count == 0:
            del nodes[start]
            self._remove_delimiter(opener)
        return following

    def _wrap_mark(self, opener: _Delimiter, closer: _Delimiter) -> _Delimiter | None:
        nodes = self.nodes
        end = self._index(closer.node)
        start = self._index(opener.node)
        wrapper = self._marks[closer.char][closer.orig_count]()
        wrapper.children = nodes[start + 1 : end]
        nodes[start : end + 1] = [wrapper]
        if opener.next is not closer:
            opener.next = closer
            closer.prev = opener
        following = closer.next
        self._remove_delimiter(closer)
        self._remove_delimiter(opener)
        return following

    def _parse_open_bracket(self) -> bool:
        start = self.pos
        self.pos += 1
        node = Text("[")
        self.nodes.append(node)
        self._add_bracket(node, start, False)
        return True

    def _parse_bang(self) -> bool:
        start = self.pos
        self.pos += 1
        if self.peek() == "[":
            self.pos += 1
            node = Text("![")
            self.nodes.append(node)
            self._add_bracket(node, start + 1, True)
        else:
            self.nodes.append(Text("!"))
        return True

    def _add_bracket(self, node: Text, index: int, image: bool) -> None:
        bracket = _Bracket(node, index, image)
        if self._brackets is not None:
            self._brackets.bracket_after = True
        bracket.prev = self._brackets
        bracket.prev_delimiter = self._delimiters
        self._brackets = bracket

    def _parse_close_bracket(self) -> bool:
        self.pos += 1
        start = self.pos
        opener = self._brackets
        if opener is None:
            self.nodes.append(Text("]"))
            return True
        if not opener.active:
            self.nodes.append(Text("]"))
            self._brackets = opener.prev
            return True

        target = self._inline_link_target()
        if target is None:
            target = self._reference_target(opener, start)
        if target is None:
            self._brackets = opener.prev
            self.pos = start
            self.nodes.append(Text("]"))
            return True

        dest, title = target
        node: Node = Image(dest, title) if opener.image else Link(dest, title)
        self._process_emphasis(opener.prev_delimiter)
        index = self._index(opener.node)
        content = self.nodes[index + 1 :]
        del self.nodes[index:]
        if not opener.image:
            content = _unwrap_bare_links(content)
        node.children = content
        self.nodes.append(node)
        self._brackets = opener.prev

        if not opener.image:
            # no links inside links: earlier "[" can no longer open one
            bracket = self._brackets
            while bracket is not None:
                if not bracket.image:
                    bracket.active = False
                bracket = bracket.prev
        return True

    def _inline_link_target(self) -> tuple[str, str] | None:
        """Parse ``(dest "title")`` right after a closing bracket."""
        if self.peek() != "(":
            return None
        saved = self.pos
        self.pos += 1
        self._skip_spnl()
        dest = self._parse_link_destination()
        if dest is not None:
            title = ""
            before_title = self.pos
            self._skip_spnl()
            # a title needs whitespace between it and the destination
            if self.pos > before_title:
                title = self._parse_link_title() or ""
            self._skip_spnl()
            if self.peek() == ")":
                self.pos += 1
                return dest, title
        self.pos = saved
        return None

    def _reference_target(self, opener: _Bracket, start: int) -> tuple[str, str] | None:
        """Resolve ``[text][label]``, ``[text][]`` or plain ``[text]``."""
        saved = self.pos
        label = None
        length = self._match_link_label()
        if length > 2:
            label = self.subject[saved + 1 : saved + length - 1]
        elif not opener.bracket_after:
            # collapsed or shortcut reference: the link text is the label,
            # which cannot work if the text itself contains brackets
            label = self.subject[opener.index + 1 : start - 1]
        if length == 0:
            self.pos = saved
        if label is None:
            return None
        ref = self.refmap.get(normalize_label(label))
        if ref is None:
            return None
        return ref.dest, ref.title

    def _match_link_label(self) -> int:
        m = _LINK_LABEL.match(self.subject, self.pos)
        if m is None or len(m.group()) > 1001:
            return 0
        self.pos = m.end()
        return len(m.group())

    def _skip_spnl(self) -> None:
        self.pos = _SPNL.match(self.subject, self.pos).end()

    def _parse_link_destination(self) -> str | None:
        subject = self.subject
        m = _LINK_DEST_BRACES.match(subject, self.pos)
        if m is not None:
            self.pos = m.end()
            return normalize_uri(unescape_string(m.group()[1:-1]))
        if self.peek() == "<":
            return None
        start = self.pos
        pos = start
        depth = 0
        while pos < len(subject):
            char = subject[pos]
            if char == "\\" and _ESCAPABLE.match(subject, pos + 1):
                pos += 2
            elif char == "(":
                depth += 1
                if depth > _MAX_PAREN_DEPTH:
                    return None
                pos += 1
            elif char == ")":
                if depth < 1:
                    break
                depth -= 1
                pos += 1
            elif char in _WHITESPACE or char < " ":
                break
            else:
                pos += 1
        if pos == start and (pos >= len(subject) or subject[pos] != ")"):
            return None
        if depth != 0:
            return None
        self.pos = pos
        return normalize_uri(unescape_string(subject[start:pos]))

    def _parse_link_title(self) -> str | None:
        m = _LINK_TITLE.match(self.subject, self.pos)
        if m is None:
            return None
        self.pos = m.end()
        return unescape_string(m.group()[1:-1])

    def parse_reference(self, text: str, refmap: dict[str, Reference]) -> int:
        """Try to read a link reference definition off the start of text.

        Returns the number of characters consumed (0 if there is no
        definition) and records the reference unless the label is taken.
        """
        self._reset(text)
        length = self._match_link_label()
        if length == 0:
            return 0
        label = text[1 : length - 1]
        if self.peek() != ":":
            return 0
        self.pos += 1
        self._skip_spnl()

        dest = self._parse_link_destination()
        if dest is None:
            return 0

        before_title = self.pos
        self._skip_spnl()
        title = None
        if self.pos != before_title:
            title = self._parse_link_title()
        if title is None:
            self.pos = before_title

        m = _REST_OF_LINE.match(text, self.pos)
        if m is None and title is not None:
            # junk after the title: maybe it's still a valid definition
            # without one, with the "title" belonging to the next paragraph
            title = None
            self.pos = before_title
            m = _REST_OF_LINE.match(text, self.pos)
        if m is None:
            return 0
        consumed = m.end()

        key = normalize_label(label)
        if not key:
            return 0
        if key not in refmap:
            refmap[key] = Reference(label, dest, title or "")
        self._reset("")
        return consumed


def _unwrap_bare_links(nodes: list[Node]) -> list[Node]:
    """Flatten links the autolink extension made inside what is now link text."""
    result: list[Node] = []
    for node in nodes:
        if isinstance(node, Link) and node.bare:
            result.extend(node.children)
        else:
            if node.children:
                node.children = _unwrap_bare_links(node.children)
            result.append(node)
    return result


def _tidy(nodes: list[Node]) -> list[Node]:
    """Merge neighbouring text nodes and drop the empty ones."""
    result: list[Node] = []
    for node in nodes:
        if isinstance(node, Text):
            if not node.literal:
                continue
            if result and type(result[-1]) is Text:
                result[-1].literal += node.literal
                continue
        elif node.children:
            node.set_children(_tidy(node.children))
        result.append(node)
    return result
