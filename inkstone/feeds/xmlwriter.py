from __future__ import annotations

import re
from typing import Any, Mapping

from .errors import FeedError

# Everything outside the Char production of XML 1.0. There is no way to
# escape these, a parser rejects the document even for "&#1;".
_ILLEGAL = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")

_NAME = re.compile(r"[^\W\d][\w.\-]*(?::[^\W\d][\w.\-]*)?\Z")

_TEXT_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\r": "&#13;"}
_ATTR_ESCAPES = {**_TEXT_ESCAPES, '"': "&quot;", "\n": "&#10;", "\t": "&#9;"}
_TEXT_RE = re.compile("[&<>\r]")
_ATTR_RE = re.compile('[&<>\r"\n\t]')


def strip_illegal(text: str) -> str:
    """Drop characters that cannot appear in an XML 1.0 document at all."""
    return _ILLEGAL.sub("", text)


def escape_text(text: str) -> str:
    # ">" is only mandatory in "]]>", escaping it always is simpler. A bare
    # CR would be turned into LF by the parser, hence the reference.
    return _TEXT_RE.sub(lambda m: _TEXT_ESCAPES[m.group()], strip_illegal(text))


def escape_attr(text: str) -> str:
    # Literal tabs and newlines in an attribute are normalised to spaces on
    # parsing, so they have to go out as references too.
    return _ATTR_RE.sub(lambda m: _ATTR_ESCAPES[m.group()], strip_illegal(text))


def _attr_value(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


class _Element:
    __slots__ = ("tag", "prefixes", "has_children", "has_text")

    def __init__(self, tag: str, prefixes: frozenset[str]):
        self.tag = tag
        self.prefixes = prefixes
        self.has_children = False
        self.has_text = False


class _Scope:
    """Returned by start() so that it can be used in a with statement."""

    def __init__(self, writer: XmlWriter, tag: str):
        self._writer = writer
        self._tag = tag

    def __enter__(self) -> XmlWriter:
        return self._writer

    def __exit__(self, exc_type, exc, tb) -> None:
        # don't pile a "wrong end tag" error on top of whatever went wrong
        if exc_type is None:
            self._writer.end(self._tag)


class XmlWriter:
    """Small streaming XML writer.

    Elements are written as they are opened and closed; the writer keeps just
    enough state to refuse output that would not be well-formed (stray end
    tags, a second root, undeclared namespace prefixes).

        w = XmlWriter(pretty=True)
        with w.start("feed", namespaces={"": ATOM}):
            w.element("title", "Hello & goodbye")
        xml = w.getvalue()
    """

    def __init__(
        self,
        *,
        pretty: bool = False,
        indent: str = "  ",
        declaration: bool = True,
    ):
        self._pretty = pretty
        self._indent = indent
        self._parts: list[str] = []
        self._stack: list[_Element] = []
        self._pending = False
        self._root_done = False
        if declaration:
            self._parts.append('<?xml version="1.0" encoding="utf-8"?>')
            if not pretty:
                self._parts.append("\n")

    @property
    def depth(self) -> int:
        return len(self._stack)

    def _close_start_tag(self) -> None:
        if self._pending:
            self._parts.append(">")
            self._pending = False

    def _newline(self) -> None:
        # Indenting next to character data would change the text, so mixed
        # content is left exactly as written.
        if not self._pretty or not self._parts:
            return
        if self._stack and self._stack[-1].has_text:
            return
        self._parts.append("\n" + self._indent * len(self._stack))

    def _before_node(self) -> None:
        self._close_start_tag()
        self._newline()
        if self._stack:
            self._stack[-1].has_children = True

    def _check_name(self, name: str, what: str) -> str:
        if not isinstance(name, str) or not _NAME.match(name):
            raise FeedError(f"{name!r} is not a valid XML {what} name")
        return name

    def _check_prefix(self, name: str, declared: frozenset[str]) -> None:
        prefix, colon, _ = name.partition(":")
        if colon and prefix not in declared:
            raise FeedError(f"namespace prefix {prefix!r} of <{name}> is not declared")

    def start(
        self,
        tag: str,
        attrs: Mapping[str, Any] | None = None,
        *,
        namespaces: Mapping[str, str] | None = None,
    ) -> _Scope:
        """Open an element. `namespaces` maps prefix to URI ("" is the default).

        Attributes whose value is None are left out.
        """
        self._check_name(tag, "element")
        if not self._stack and self._root_done:
            raise FeedError(f"<{tag}> would be a second root element")

        attributes: dict[str, str] = {}
        declared = self._stack[-1].prefixes if self._stack else frozenset(["xml"])
        for prefix, uri in (namespaces or {}).items():
            name = f"xmlns:{prefix}" if prefix else "xmlns"
            self._check_name(name, "namespace")
            attributes[name] = uri
        for name, value in (attrs or {}).items():
            if value is None:
                continue
            self._check_name(name, "attribute")
            if name in attributes:
                raise FeedError(f"attribute {name!r} given twice on <{tag}>")
            attributes[name] = _attr_value(value)
        declared |= {name[6:] for name in attributes if name.startswith("xmlns:")}

        self._check_prefix(tag, declared)
        for name in attributes:
            if not name.startswith("xmlns"):
                self._check_prefix(name, declared)

        self._before_node()
        self._parts.append(f"<{tag}")
        for name, value in attributes.items():
            self._parts.append(f' {name}="{escape_attr(value)}"')
        self._stack.append(_Element(tag, declared))
        self._pending = True
        return _Scope(self, tag)

    def end(self, tag: str | None = None) -> None:
        """Close the current element; pass the tag to have it checked."""
        if not self._stack:
            raise FeedError(f"end tag </{tag or ''}> without an open element")
        element = self._stack[-1]
        if tag is not None and tag != element.tag:
            raise FeedError(f"end tag </{tag}> does not match <{element.tag}>")
        self._stack.pop()
        if self._pending:
            self._parts.append("/>")
            self._pending = False
        else:
            if self._pretty and element.has_children and not element.has_text:
                self._parts.append("\n" + self._indent * len(self._stack))
            self._parts.append(f"</{element.tag}>")
        if not self._stack:
            self._root_done = True

    def element(
        self,
        tag: str,
        text: Any = None,
        attrs: Mapping[str, Any] | None = None,
        *,
        namespaces: Mapping[str, str] | None = None,
    ) -> None:
        """Write <tag attrs>text</tag>, or <tag attrs/> without text."""
        self.start(tag, attrs, namespaces=namespaces)
        if text is not None:
            self.text(text)
        self.end()

    def text(self, text: Any) -> None:
        if text is None or text == "":
            return
        text = str(text)
        if not self._stack:
            raise FeedError("text outside of the root element")
        self._close_start_tag()
        self._stack[-1].has_text = True
        self._parts.append(escape_text(text))

    def cdata(self, text: str) -> None:
        """Write text as a CDATA section, splitting it around any "]]>"."""
        if not self._stack:
            raise FeedError("CDATA outside of the root element")
        self._close_start_tag()
        self._stack[-1].has_text = True
        text = strip_illegal(str(text)).replace("]]>", "]]]]><![CDATA[>")
        self._parts.append(f"<![CDATA[{text}]]>")

    def comment(self, text: str) -> None:
        # "--" may not appear inside a comment and it may not end in "-";
        # there is no escape for either, so space them out.
        text = strip_illegal(str(text))
        while "--" in text:
            text = text.replace("--", "- -")
        if text.endswith("-"):
            text += " "
        self._before_node()
        self._parts.append(f"<!--{text}-->")

    def pi(self, target: str, data: str = "") -> None:
        """Processing instruction, e.g. pi("xml-stylesheet", 'href="feed.xsl"')."""
        self._check_name(target, "processing instruction")
        if target.lower() == "xml" or ":" in target:
            raise FeedError(f"{target!r} is not allowed as a processing instruction")
        data = strip_illegal(str(data))
        if "?>" in data:
            raise FeedError('a processing instruction cannot contain "?>"')
        self._before_node()
        self._parts.append(f"<?{target} {data}?>" if data else f"<?{target}?>")

    def stylesheet(self, href: str) -> None:
        """Point browsers at an XSLT or CSS file to render the document with."""
        kind = "text/css" if href.lower().endswith(".css") else "text/xsl"
        self.pi("xml-stylesheet", f'type="{kind}" href="{escape_attr(href)}"')

    def getvalue(self) -> str:
        if self._stack:
            raise FeedError(f"<{self._stack[-1].tag}> was never closed")
        if not self._root_done:
            raise FeedError("XML document has no root element")
        return "".join(self._parts) + "\n"
