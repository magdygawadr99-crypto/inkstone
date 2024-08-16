"""Just enough HTML handling to edit rendered content.

Not a parser: tags and comments are picked out with a regex and everything
else is passed through untouched, so a rewrite never changes bytes it was
not asked to change. What it does know is which stretches are code.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Iterator

# Elements whose content is not ours to edit.
PROTECTED = frozenset({"pre", "code", "script", "style", "textarea"})
# Of those, the ones whose content is not markup at all.
_RAW_TEXT = frozenset({"script", "style", "textarea"})

_TAG = re.compile(
    r"<!--.*?-->"
    r"|<(?P<close>/)?(?P<name>[A-Za-z][A-Za-z0-9:-]*)"
    r"(?P<attrs>(?:[^>\"']|\"[^\"]*\"|'[^']*')*)>",
    re.S,
)
_ATTR = re.compile(
    r"""([^\s"'<>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?"""
)
_SELF_CLOSING = re.compile(r"""(?:\A|[\s"'])/\s*\Z""")
_SPACE = re.compile(r"\s+")


def escape(text: str) -> str:
    return html.escape(str(text), quote=True)


class Tag:
    """A start tag. Attribute values are read and written unescaped."""

    def __init__(self, name: str, source: str, raw_attrs: str = ""):
        self.name = name.lower()
        self.source = source
        # in <a href=/x/> the slash belongs to the value
        self.self_closing = _SELF_CLOSING.search(raw_attrs) is not None
        self.changed = False
        self._raw = raw_attrs
        self._attrs: list[list] | None = None

    def __repr__(self) -> str:
        return f"<Tag {str(self)!r}>"

    @property
    def attrs(self) -> list[list]:
        # [name, raw value or None] pairs in source order; parsed on first
        # use since most tags are only looked at by name
        if self._attrs is None:
            self._attrs = []
            for match in _ATTR.finditer(self._raw):
                name, double, single, bare = match.groups()
                value = next((v for v in (double, single, bare) if v is not None), None)
                self._attrs.append([name, value])
        return self._attrs

    def _find(self, name: str) -> list | None:
        name = name.lower()
        for attr in self.attrs:
            if attr[0].lower() == name:
                return attr
        return None

    def has(self, name: str) -> bool:
        return self._find(name) is not None

    def get(self, name: str, default: str | None = None) -> str | None:
        attr = self._find(name)
        if attr is None:
            return default
        return html.unescape(attr[1]) if attr[1] is not None else ""

    def set(self, name: str, value: str | None = "") -> None:
        """Set an attribute; ``None`` writes it without a value."""
        raw = None if value is None else escape(value)
        attr = self._find(name)
        if attr is None:
            self.attrs.append([name, raw])
        elif attr[1] == raw:
            return
        else:
            attr[1] = raw
        self.changed = True

    def setdefault(self, name: str, value: str | None = "") -> None:
        if not self.has(name):
            self.set(name, value)

    def remove(self, name: str) -> None:
        attr = self._find(name)
        if attr is not None:
            self.attrs.remove(attr)
            self.changed = True

    @property
    def classes(self) -> list[str]:
        return (self.get("class") or "").split()

    def add_class(self, *names: str) -> None:
        classes = self.classes
        missing = [name for name in names if name and name not in classes]
        if missing:
            self.set("class", " ".join(classes + missing))

    def tokens(self, name: str) -> list[str]:
        """A space separated attribute (rel, class) as a list."""
        return (self.get(name) or "").split()

    def __str__(self) -> str:
        if not self.changed:
            return self.source
        parts = [self.name]
        for name, value in self.attrs:
            parts.append(name if value is None else f'{name}="{value}"')
        return "<" + " ".join(parts) + (" />" if self.self_closing else ">")


@dataclass
class Token:
    # text, start, end or comment
    kind: str
    source: str
    pos: int
    name: str = ""
    tag: Tag | None = None
    # inside <pre>, <code>, <script>... (the element's own tags are not)
    protected: bool = False

    @property
    def end(self) -> int:
        return self.pos + len(self.source)


def tokenize(markup: str) -> Iterator[Token]:
    """Split markup into tags, comments and the text between them.

    The tokens cover the input exactly: joining their sources gives it back.
    """
    pos = 0
    depth = 0
    length = len(markup)
    while pos < length:
        match = _TAG.search(markup, pos)
        if match is None:
            break
        if match.start() > pos:
            yield Token("text", markup[pos : match.start()], pos, protected=depth > 0)
        pos = match.end()
        source = match.group()
        name = match.group("name")
        if name is None:
            yield Token("comment", source, match.start(), protected=depth > 0)
            continue
        name = name.lower()
        if match.group("close"):
            if name in PROTECTED and depth:
                depth -= 1
            yield Token("end", source, match.start(), name, protected=depth > 0)
            continue
        tag = Tag(name, source, match.group("attrs"))
        yield Token("start", source, match.start(), name, tag, protected=depth > 0)
        if name not in PROTECTED or tag.self_closing:
            continue
        depth += 1
        if name in _RAW_TEXT:
            # a "<" in a script is not a tag; skip to where the element ends
            closing = re.compile(rf"</{name}\s*>", re.I).search(markup, pos)
            stop = closing.start() if closing else length
            if stop > pos:
                yield Token("text", markup[pos:stop], pos, protected=True)
            pos = stop
    if pos < length:
        yield Token("text", markup[pos:], pos, protected=depth > 0)


def rewrite(
    markup: str,
    handler: Callable[[Tag], object],
    names: Iterable[str] | None = None,
) -> str:
    """Run ``handler`` over start tags outside code and put the result together.

    The handler edits the tag in place. Tags it leaves alone come out
    byte for byte as they went in.
    """
    wanted = None if names is None else frozenset(names)
    out = []
    for token in tokenize(markup):
        tag = token.tag
        skip = tag is None or token.protected
        if skip or (wanted is not None and tag.name not in wanted):
            out.append(token.source)
            continue
        handler(tag)
        out.append(str(tag))
    return "".join(out)


@dataclass
class Element:
    """A start tag with its matching end tag, as offsets into the markup."""

    tag: Tag
    start: int
    inner_start: int
    inner_end: int
    end: int

    def inner(self, markup: str) -> str:
        return markup[self.inner_start : self.inner_end]


def find_elements(markup: str, names: Iterable[str]) -> list[Element]:
    """Outermost elements with one of ``names``, in document order.

    Elements inside code are skipped, and so are ones that are never closed.
    """
    wanted = frozenset(names)
    found: list[Element] = []
    open_token: Token | None = None
    depth = 0
    for token in tokenize(markup):
        if token.protected or token.kind not in ("start", "end"):
            continue
        if open_token is None:
            if token.kind == "start" and token.name in wanted:
                if not token.tag.self_closing:
                    open_token = token
                    depth = 1
            continue
        if token.name != open_token.name:
            continue
        if token.kind == "start":
            if not token.tag.self_closing:
                depth += 1
            continue
        depth -= 1
        if depth == 0:
            opened, open_token = open_token, None
            found.append(
                Element(opened.tag, opened.pos, opened.end, token.pos, token.end)
            )
    return found


def text_content(markup: str) -> str:
    """The text of a fragment: tags dropped, entities decoded, spaces squeezed."""
    parts = [token.source for token in tokenize(markup) if token.kind == "text"]
    return _SPACE.sub(" ", html.unescape("".join(parts))).strip()
