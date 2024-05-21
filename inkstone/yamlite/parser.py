from __future__ import annotations

from typing import Iterator

from . import resolver
from .errors import YamlError
from .scanner import (
    ALIAS,
    ANCHOR,
    BLOCK_END,
    BLOCK_ENTRY,
    BLOCK_MAPPING_START,
    BLOCK_SEQUENCE_START,
    DOCUMENT_END,
    DOCUMENT_START,
    FLOW_ENTRY,
    FLOW_MAPPING_END,
    FLOW_MAPPING_START,
    FLOW_SEQUENCE_END,
    FLOW_SEQUENCE_START,
    KEY,
    SCALAR,
    STREAM_END,
    TAG,
    VALUE,
    Scanner,
    Token,
)

# punctuation tokens are named after themselves and need no entry here
_DESCRIPTIONS = {
    STREAM_END: "the end of the document",
    DOCUMENT_START: "a document separator ('---')",
    DOCUMENT_END: "a document end marker ('...')",
    BLOCK_END: "the end of the block",
    BLOCK_ENTRY: "a sequence entry ('- ')",
    KEY: "a mapping key",
    ALIAS: "an alias",
    ANCHOR: "an anchor",
    TAG: "a tag",
}

_VERBATIM_PREFIX = "!<tag:yaml.org,2002:"
_SCALAR_TAGS = {
    "int": resolver.to_int,
    "float": resolver.to_float,
    "bool": resolver.to_bool,
    "null": resolver.to_null,
    "timestamp": resolver.to_timestamp,
}
_COLLECTION_TAGS = {"seq": list, "map": dict}


def _error(problem: str, tok: Token) -> YamlError:
    return YamlError(problem, line=tok.line + 1, column=tok.column + 1)


def _describe(tok: Token) -> str:
    if tok.kind == SCALAR:
        text = tok.value if len(tok.value) <= 24 else tok.value[:21] + "..."
        return f'the scalar "{text}"'
    return _DESCRIPTIONS.get(tok.kind) or f"'{tok.kind}'"


class _Pairs:
    """Collects the entries of one mapping, minding duplicates and merges."""

    def __init__(self):
        self.data: dict = {}
        self.first_seen: dict = {}
        self.merges: list[dict] = []

    def add(self, key, value, tok: Token, merge: bool = False) -> None:
        if merge:
            sources = value if isinstance(value, list) else [value]
            if not all(isinstance(source, dict) for source in sources):
                raise _error(
                    "a merge key ('<<') needs a mapping or a list of mappings", tok
                )
            self.merges.extend(sources)
            return
        if key in self.first_seen:
            shown = f'"{key}"' if isinstance(key, str) else str(key)
            raise _error(
                f"duplicate key {shown} (first used on line {self.first_seen[key]})",
                tok,
            )
        self.first_seen[key] = tok.line + 1
        self.data[key] = value

    def result(self) -> dict:
        if not self.merges:
            return self.data
        # explicit keys beat merged ones, and earlier merge sources beat later
        merged: dict = {}
        for source in self.merges:
            for key, value in source.items():
                merged.setdefault(key, value)
        merged.update(self.data)
        return merged


class Parser:
    """Builds Python values straight from the token stream."""

    def __init__(self, text: str):
        self.scanner = Scanner(text)
        self.anchors: dict[str, object] = {}

    def documents(self) -> Iterator[object]:
        sc = self.scanner
        sc.next()
        while True:
            while sc.check(DOCUMENT_END):
                sc.next()
            if sc.check(STREAM_END):
                return
            if sc.check(DOCUMENT_START):
                sc.next()
            # anchors do not carry over from one document to the next
            self.anchors = {}
            if sc.check(DOCUMENT_START, DOCUMENT_END, STREAM_END):
                yield None
                continue
            value = self._node()
            if not sc.check(DOCUMENT_START, DOCUMENT_END, STREAM_END):
                self._unexpected("the end of the document")
            yield value

    def _unexpected(self, expected: str):
        tok = self.scanner.peek()
        if tok.kind in (BLOCK_MAPPING_START, BLOCK_SEQUENCE_START):
            raise _error(
                "inconsistent indentation: this line does not line up with "
                "the entries above it",
                tok,
            )
        raise _error(f"expected {expected}, but found {_describe(tok)}", tok)

    def _node(self, *, indentless: bool = False):
        sc = self.scanner
        anchor = tag = None
        while sc.check(ANCHOR, TAG):
            tok = sc.next()
            if tok.kind == ANCHOR:
                if anchor is not None:
                    raise _error("a node cannot have two anchors", tok)
                anchor = tok
            else:
                if tag is not None:
                    raise _error("a node cannot have two tags", tok)
                tag = tok

        tok = sc.peek()
        if tok.kind == ALIAS:
            if anchor is not None or tag is not None:
                raise _error("an alias cannot take an anchor or a tag of its own", tok)
            sc.next()
            if tok.value not in self.anchors:
                raise _error(f'undefined alias "{tok.value}"', tok)
            return self.anchors[tok.value]

        if tok.kind == SCALAR:
            sc.next()
            value = self._scalar(tok, tag)
        elif tok.kind == BLOCK_SEQUENCE_START:
            value = self._block_sequence()
        elif tok.kind == BLOCK_MAPPING_START:
            value = self._block_mapping()
        elif tok.kind == FLOW_SEQUENCE_START:
            value = self._flow_sequence()
        elif tok.kind == FLOW_MAPPING_START:
            value = self._flow_mapping()
        elif tok.kind == BLOCK_ENTRY and indentless:
            value = self._indentless_sequence()
        else:
            # nothing here: "key:" with no value, "- " with no item, ...
            value = self._scalar(Token(SCALAR, tok.line, tok.column, ""), tag)

        if tag is not None and isinstance(value, (list, dict)):
            self._check_collection_tag(tag, value)
        # Registered only once the node is complete, so an anchor cannot be
        # referenced from inside itself. Nobody needs recursive front matter.
        if anchor is not None:
            self.anchors[anchor.value] = value
        return value

    def _tag_name(self, tag: Token) -> str:
        raw = tag.value
        if raw == "!":
            return "!"
        name = None
        if raw.startswith("!!"):
            name = raw[2:]
        elif raw.startswith(_VERBATIM_PREFIX) and raw.endswith(">"):
            name = raw[len(_VERBATIM_PREFIX) : -1]
        if name != "str" and name not in _SCALAR_TAGS and name not in _COLLECTION_TAGS:
            raise _error(
                f'unsupported tag "{raw}" (only the standard !!str, !!int, '
                "!!float, !!bool and !!null style tags are understood)",
                tag,
            )
        return name

    def _scalar(self, tok: Token, tag: Token | None):
        text = tok.value
        if tag is None:
            return resolver.resolve(text) if tok.style is None else text
        name = self._tag_name(tag)
        if name in ("str", "!"):
            return text
        if name in _COLLECTION_TAGS:
            raise _error(f"tag {tag.value} cannot be applied to a scalar", tag)
        try:
            return _SCALAR_TAGS[name](text)
        except ValueError:
            raise _error(f'cannot read "{text}" as !!{name}', tok) from None

    def _check_collection_tag(self, tag: Token, value) -> None:
        name = self._tag_name(tag)
        if name == "!":
            return
        expected = _COLLECTION_TAGS.get(name)
        if expected is None or not isinstance(value, expected):
            kind = "sequence" if isinstance(value, list) else "mapping"
            raise _error(f"tag {tag.value} cannot be applied to a {kind}", tag)

    def _key(self):
        """Parse a mapping key. Returns (key, is_merge_key)."""
        first = self.scanner.peek()
        merge = first.kind == SCALAR and first.style is None and first.value == "<<"
        key = self._node()
        if isinstance(key, (list, dict)):
            raise _error("only scalars can be used as mapping keys", first)
        return key, merge

    def _block_sequence(self) -> list:
        sc = self.scanner
        sc.next()
        items: list = []
        while sc.check(BLOCK_ENTRY):
            sc.next()
            items.append(self._node())
        if not sc.check(BLOCK_END):
            self._unexpected("a sequence entry ('- ')")
        sc.next()
        return items

    def _indentless_sequence(self) -> list:
        # a sequence at the same indentation as its parent key; it has no
        # start/end tokens of its own and simply stops at the next key
        sc = self.scanner
        items: list = []
        while sc.check(BLOCK_ENTRY):
            sc.next()
            items.append(self._node())
        return items

    def _block_mapping(self) -> dict:
        sc = self.scanner
        sc.next()
        pairs = _Pairs()
        while not sc.check(BLOCK_END):
            tok = sc.peek()
            if tok.kind == VALUE:
                raise _error("missing mapping key before ':'", tok)
            if tok.kind != KEY:
                self._unexpected("a mapping key")
            sc.next()
            key, merge = self._key()
            if not sc.check(VALUE):
                self._unexpected("':'")
            sc.next()
            pairs.add(key, self._node(indentless=True), tok, merge)
        sc.next()
        return pairs.result()

    def _flow_sequence(self) -> list:
        sc = self.scanner
        start = sc.next()
        items: list = []
        while not sc.check(FLOW_SEQUENCE_END):
            if sc.check(FLOW_ENTRY):
                raise _error("unexpected ',' (empty entry)", sc.peek())
            if sc.check(KEY):
                # [a: 1, b: 2] is a list of single-pair mappings
                pairs = _Pairs()
                self._flow_pair(pairs, FLOW_SEQUENCE_END)
                items.append(pairs.result())
            else:
                items.append(self._node())
            if sc.check(FLOW_ENTRY):
                sc.next()
            elif not sc.check(FLOW_SEQUENCE_END):
                self._flow_trouble(start, "sequence", "]")
        sc.next()
        return items

    def _flow_mapping(self) -> dict:
        sc = self.scanner
        start = sc.next()
        pairs = _Pairs()
        while not sc.check(FLOW_MAPPING_END):
            tok = sc.peek()
            if tok.kind == FLOW_ENTRY:
                raise _error("unexpected ',' (empty entry)", tok)
            if tok.kind == VALUE:
                raise _error("missing mapping key before ':'", tok)
            if tok.kind == KEY:
                self._flow_pair(pairs, FLOW_MAPPING_END)
            else:
                # {a, b}: keys with no value at all
                key, merge = self._key()
                pairs.add(key, None, tok, merge)
            if sc.check(FLOW_ENTRY):
                sc.next()
            elif not sc.check(FLOW_MAPPING_END):
                self._flow_trouble(start, "mapping", "}")
        sc.next()
        return pairs.result()

    def _flow_pair(self, pairs: _Pairs, closer: str) -> None:
        sc = self.scanner
        tok = sc.next()
        key, merge = self._key()
        value = None
        if sc.check(VALUE):
            sc.next()
            if not sc.check(FLOW_ENTRY, closer):
                value = self._node()
        pairs.add(key, value, tok, merge)

    def _flow_trouble(self, start: Token, kind: str, closer: str):
        if self.scanner.check(STREAM_END):
            raise _error(f"flow {kind} is never closed (missing '{closer}')", start)
        self._unexpected(f"',' or '{closer}'")
