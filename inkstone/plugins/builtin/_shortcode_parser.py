"""The shortcode syntax: finding the tags in Markdown and nesting them.

    {{< name positional "quoted" key="value" >}}    stands alone
    {{< name >}} ... {{< /name >}}                   wraps what is inside
    {{< name />}}                                    explicitly alone
    {{% name %}} ... {{% /name %}}                   inner text is Markdown
    {{</* name */>}}                                 printed as {{< name >}}

Tags inside fenced code, code spans and HTML comments are not shortcodes.
Whether a tag wraps something is decided by looking for its closing tag,
so shortcodes do not have to declare which kind they are.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...errors import ContentError

_INTERESTING = re.compile(
    r"(?P<fence>^[ \t>]*(?:(?P<backticks>`{3,})[^`\n]*|(?P<tildes>~{3,})[^\n]*)$)"
    r"|(?P<ticks>`+)"
    r"|(?P<comment><!--)"
    r"|(?P<escaped>\\\{\{[<%])"
    r"|(?P<tag>\{\{[<%])",
    re.M,
)
_WS = re.compile(r"\s*")
_NAME = re.compile(r"[A-Za-z_][\w-]*")
_KEY = re.compile(r"([A-Za-z_][\w.-]*)\s*=\s*")
_QUOTED = re.compile(
    r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`([^`]*)`',
    re.S,
)
# stops in front of the closing delimiter even without a space before it
_BARE = re.compile(r"(?:(?!/?[>%]\}\})[^\s\"'`])+")
_BACKSLASH = re.compile(r"\\(.)", re.S)
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "'": "'", "\\": "\\"}
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_TICK_RUN = re.compile(r"`+")


@dataclass
class Tag:
    """One ``{{< ... >}}`` as written, before pairing."""

    # open, close or self
    kind: str
    name: str
    args: list[str]
    kwargs: dict[str, str]
    # written with {{% %}}
    markdown: bool
    start: int
    end: int
    line: int


@dataclass
class Shortcode:
    name: str
    args: list[str]
    kwargs: dict[str, str]
    markdown: bool
    line: int
    # the text it was parsed from, closing tag included
    source: str
    # nodes between the tags; None for a shortcode that stands alone
    inner: list | None = None
    _tag: Tag | None = field(default=None, repr=False, compare=False)


def _fail(message: str, text: str, pos: int):
    raise ContentError(message, line=text.count("\n", 0, pos) + 1)


def _unescape(value: str) -> str:
    return _BACKSLASH.sub(lambda m: _ESCAPES.get(m.group(1), m.group()), value)


def _code_span_end(text: str, pos: int, width: int) -> int | None:
    """Where the code span opened by ``width`` backticks ends, if it does."""
    # a span cannot run past the end of its paragraph
    blank = _BLANK_LINE.search(text, pos)
    limit = blank.start() if blank else len(text)
    while True:
        run = _TICK_RUN.search(text, pos, limit)
        if run is None:
            return None
        if run.end() - run.start() == width:
            return run.end()
        pos = run.end()


def _fence_end(text: str, pos: int, marker: str) -> int:
    closing = re.compile(
        rf"^[ \t>]*{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$", re.M
    ).search(text, pos)
    # an unclosed fence runs to the end of the document
    return closing.end() if closing else len(text)


def _read_value(text: str, pos: int) -> tuple[str, int, bool] | None:
    """One argument value at ``pos``: ``(value, end, was_quoted)``."""
    quoted = _QUOTED.match(text, pos)
    if quoted is not None:
        double, single, raw = quoted.groups()
        if raw is not None:
            # backticks: nothing is an escape in there
            return raw, quoted.end(), True
        value = _unescape(double if double is not None else single)
        return value, quoted.end(), True
    bare = _BARE.match(text, pos)
    if bare is None:
        return None
    return bare.group(), bare.end(), False


def _read_tag(text: str, start: int) -> Tag | tuple[str, int]:
    """Parse the tag starting at ``start``.

    The escaped form comes back as ``(literal text, end)`` instead of a Tag.
    """
    delimiter = text[start + 2]
    closer = (">" if delimiter == "<" else "%") + "}}"
    other = ("%" if delimiter == "<" else ">") + "}}"
    opener = "{{" + delimiter

    def fail(message: str):
        raise ContentError(message, line=text.count("\n", 0, start) + 1)

    pos = _WS.match(text, start + 3).end()
    if text.startswith("/*", pos):
        end = text.find("*/", pos + 2)
        after = _WS.match(text, end + 2).end() if end != -1 else -1
        if end == -1 or not text.startswith(closer, after):
            fail(f"'{opener}/*' is never closed (expected '*/{closer}')")
        return opener + text[pos + 2 : end] + closer, after + 3

    closing = text.startswith("/", pos)
    if closing:
        pos = _WS.match(text, pos + 1).end()
    found = _NAME.match(text, pos)
    if found is None:
        fail(f"expected a shortcode name after '{opener}'")
    name = found.group()
    pos = found.end()
    unclosed = f"shortcode '{name}' is never closed (missing '{closer}')"

    args: list[str] = []
    kwargs: dict[str, str] = {}
    while True:
        pos = _WS.match(text, pos).end()
        if text.startswith(closer, pos):
            kind = "close" if closing else "open"
            end = pos + 3
            break
        if text.startswith("/" + closer, pos) and not closing:
            kind = "self"
            end = pos + 4
            break
        if pos >= len(text):
            fail(unclosed)
        if text.startswith(other, pos) or text.startswith("/" + other, pos):
            fail(f"shortcode '{name}' starts with '{opener}' but ends with '{other}'")
        if closing:
            fail(f"the closing tag of '{name}' takes no arguments")

        key = _KEY.match(text, pos)
        if key is not None:
            pos = key.end()
        read = _read_value(text, pos)
        if read is None:
            if text[pos : pos + 1] in ('"', "'", "`"):
                fail(f"unterminated quote in shortcode '{name}'")
            if key is not None:
                fail(f"shortcode '{name}': '{key.group(1)}=' has no value")
            fail(f"cannot read the arguments of shortcode '{name}'")
        value, pos, quoted = read
        if not quoted and value.startswith(("{{<", "{{%")):
            # ran into the next tag while looking for the end of this one
            fail(unclosed)
        if key is not None:
            kwargs[key.group(1)] = value
        else:
            args.append(value)

    line = text.count("\n", 0, start) + 1
    return Tag(kind, name, args, kwargs, delimiter == "%", start, end, line)


def scan(text: str) -> list[str | Tag]:
    """Split Markdown into literal text and shortcode tags."""
    out: list[str | Tag] = []
    literal_from = 0
    pos = 0
    while True:
        match = _INTERESTING.search(text, pos)
        if match is None:
            break
        if match.group("fence") is not None:
            marker = match.group("backticks") or match.group("tildes")
            pos = _fence_end(text, match.end(), marker)
        elif match.group("ticks") is not None:
            end = _code_span_end(text, match.end(), len(match.group("ticks")))
            pos = end if end is not None else match.end()
        elif match.group("comment") is not None:
            end = text.find("-->", match.end())
            pos = end + 3 if end != -1 else match.end()
        elif match.group("escaped") is not None:
            # "\{{<" stays as written; Markdown takes the backslash out
            pos = match.end()
        else:
            start = match.start("tag")
            if start > literal_from:
                out.append(text[literal_from:start])
            tag = _read_tag(text, start)
            if isinstance(tag, tuple):
                literal, pos = tag
                out.append(literal)
            else:
                out.append(tag)
                pos = tag.end
            literal_from = pos
    if literal_from < len(text):
        out.append(text[literal_from:])
    return out


def _delimiters(markdown: bool) -> str:
    return "{{% %}}" if markdown else "{{< >}}"


def parse(text: str) -> list[str | Shortcode]:
    """Parse Markdown into a list of text pieces and nested shortcodes.

    Raises ContentError with the line (in ``text``) for anything malformed.
    """
    root: list = []
    # nodes that are open and might still get a closing tag
    stack: list[Shortcode] = []

    def children() -> list:
        return stack[-1].inner if stack else root

    def stands_alone(node: Shortcode) -> None:
        # never closed: what looked like its content belongs to the parent
        collected, node.inner = node.inner, None
        node.source = text[node._tag.start : node._tag.end]
        children().extend(collected)

    for token in scan(text):
        if isinstance(token, str):
            children().append(token)
            continue
        if token.kind != "close":
            node = Shortcode(
                token.name,
                token.args,
                token.kwargs,
                token.markdown,
                token.line,
                text[token.start : token.end],
                _tag=token,
            )
            children().append(node)
            if token.kind == "open":
                node.inner = []
                stack.append(node)
            continue
        depth = len(stack) - 1
        while depth >= 0 and stack[depth].name != token.name:
            depth -= 1
        if depth < 0:
            _fail(
                f"closing tag for '{token.name}' without an opening one",
                text,
                token.start,
            )
        while len(stack) - 1 > depth:
            stands_alone(stack.pop())
        node = stack.pop()
        if node.markdown != token.markdown:
            _fail(
                f"shortcode '{node.name}' is opened with {_delimiters(node.markdown)} "
                f"on line {node.line} but closed with {_delimiters(token.markdown)}",
                text,
                token.start,
            )
        node.source = text[node._tag.start : token.end]
    while stack:
        stands_alone(stack.pop())
    return root
