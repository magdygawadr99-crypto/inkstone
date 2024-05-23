from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping

from .errors import YamlError
from .resolver import resolve

# A plain scalar may not start with one of these. '-', '?' and ':' are only
# a problem when followed by a space, see _plain_ok.
_INDICATORS = frozenset("-?:,[]{}#&*!|>'\"%@`")

# YAML 1.1 parsers read these as booleans. We load them as strings, but
# quoting them on the way out keeps the file meaning the same thing to
# other tools. (1.1 also lists y/n, which nobody seems to implement.)
_YAML11_WORDS = frozenset({"yes", "no", "on", "off"})

# line breaks other than "\n", the BOM and lone surrogates
_EXOTIC = "\x85\u2028\u2029\ufeff\ud800-\udfff"
# characters that can never appear raw in a plain or single-quoted scalar
_SPECIAL = re.compile(f"[\x00-\x1f\x7f{_EXOTIC}]")
# same, minus tab and newline which are fine inside a block scalar
_BLOCK_UNSAFE = re.compile(f"[\x00-\x08\x0b-\x1f\x7f{_EXOTIC}]")
_ESCAPABLE = re.compile(f'["\\\\\x00-\x1f\x7f{_EXOTIC}]')
_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\0": "\\0",
    "\t": "\\t",
    "\n": "\\n",
    "\r": "\\r",
    "\x1b": "\\e",
    "\x85": "\\N",
    "\u2028": "\\L",
    "\u2029": "\\P",
}

_SEQUENCES = (list, tuple, set, frozenset)


def dumps(obj, *, indent: int = 2, sort_keys: bool = False) -> str:
    """Serialise ``obj`` as a YAML document that ``loads`` reads back.

    ``indent`` is how far nested collections move in under their key; list
    items always sit two columns after their dash.
    """
    if indent < 1:
        raise ValueError("indent must be at least 1")
    return _Dumper(indent, sort_keys).dump(obj)


class _Dumper:
    def __init__(self, step: int, sort_keys: bool):
        self.step = step
        self.sort_keys = sort_keys
        self.lines: list[str] = []
        # ids of the containers currently being written, to catch cycles
        self._open: set[int] = set()

    def dump(self, obj) -> str:
        if _is_block(obj):
            self._collection(obj, 0, None)
        else:
            self._leaf("", obj, 0, self.step)
        return "\n".join(self.lines) + "\n"

    def _collection(self, obj, col: int, lead: str | None) -> None:
        """Write a non-empty mapping or sequence at column ``col``.

        ``lead`` replaces the indentation of the first line; that is how
        "- key: value" and "- - item" end up on one line.
        """
        if id(obj) in self._open:
            raise YamlError("cannot dump a structure that contains itself")
        self._open.add(id(obj))
        try:
            if isinstance(obj, Mapping):
                self._mapping(obj, col, lead)
            else:
                self._sequence(obj, col, lead)
        finally:
            self._open.discard(id(obj))

    def _mapping(self, mapping: Mapping, col: int, lead: str | None) -> None:
        pad = " " * col
        items = mapping.items()
        if self.sort_keys:
            items = _ordered(items, key=lambda item: item[0])
        for key, value in items:
            head = (pad if lead is None else lead) + self._key(key) + ":"
            lead = None
            if _is_block(value):
                self.lines.append(head)
                self._collection(value, col + self.step, None)
            else:
                self._leaf(head, value, col, col + self.step)

    def _sequence(self, items, col: int, lead: str | None) -> None:
        pad = " " * col
        if isinstance(items, (set, frozenset)):
            items = _ordered(items)
        for item in items:
            head = (pad if lead is None else lead) + "-"
            lead = None
            if _is_block(item):
                self._collection(item, col + 2, head + " ")
            else:
                self._leaf(head, item, col, col + 2)

    def _leaf(self, head: str, value, col: int, content_col: int) -> None:
        """Write a scalar (or empty collection) after ``head``.

        ``col`` is the column of the enclosing collection and ``content_col``
        where the lines of a block scalar would go.
        """
        sep = " " if head else ""
        if isinstance(value, str) and "\n" in value:
            block = _block_scalar(value, content_col - col)
            if block is not None:
                header, body = block
                pad = " " * content_col
                self.lines.append(head + sep + header)
                self.lines.extend(pad + line if line else "" for line in body)
                return
        self.lines.append(head + sep + _inline(value))

    def _key(self, key) -> str:
        if isinstance(key, str):
            return key if _plain_ok(key) else _quote(key)
        if isinstance(key, Mapping) or isinstance(key, _SEQUENCES):
            raise YamlError("mapping keys must be scalars")
        return _inline(key)


def _is_block(value) -> bool:
    """True for collections that need lines of their own (non-empty ones)."""
    return isinstance(value, (Mapping, *_SEQUENCES)) and len(value) > 0


def _ordered(values, key=lambda value: value) -> list:
    """Sort ``values`` (by ``key(value)``) without tripping over mixed types.

    The type name goes first so that ints, strings and None can share a
    mapping. Values that will not even compare with their own kind, like
    naive and aware datetimes, are ordered by their repr instead.
    """
    try:
        return sorted(values, key=lambda v: (type(key(v)).__name__, key(v)))
    except TypeError:
        return sorted(values, key=lambda v: (type(key(v)).__name__, repr(key(v))))


def _inline(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value if _plain_ok(value) else _quote(value)
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, dt.date):
        # covers datetime too; its isoformat is what the resolver expects
        return value.isoformat()
    if isinstance(value, Mapping):
        return "{}"
    if isinstance(value, _SEQUENCES):
        return "[]"
    raise YamlError(f"cannot represent {type(value).__name__} objects in YAML")


def _float(value: float) -> str:
    if math.isnan(value):
        return ".nan"
    if math.isinf(value):
        return ".inf" if value > 0 else "-.inf"
    return repr(float(value))


def _plain_ok(text: str) -> bool:
    """Can ``text`` be written without quotes and still load as this string?"""
    if not text or text != text.strip():
        return False
    first = text[0]
    if first in _INDICATORS:
        if first not in "-?:" or len(text) == 1 or text[1] in " \t":
            return False
    if text.startswith(("---", "...")) or text == "<<":
        return False
    if ": " in text or " #" in text or text.endswith(":"):
        return False
    if _SPECIAL.search(text) or text.lower() in _YAML11_WORDS:
        return False
    return isinstance(resolve(text), str)


def _quote(text: str) -> str:
    # single quotes read better when the only awkward characters are
    # backslashes or double quotes (Windows paths, regexes)
    if ('"' in text or "\\" in text) and "'" not in text and not _SPECIAL.search(text):
        return f"'{text}'"
    return '"' + _ESCAPABLE.sub(_escape, text) + '"'


def _escape(match: re.Match) -> str:
    char = match.group()
    short = _SHORT_ESCAPES.get(char)
    if short is not None:
        return short
    code = ord(char)
    if code <= 0xFF:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}"


def _block_scalar(text: str, offset: int) -> tuple[str, list[str]] | None:
    """Header and content lines for writing ``text`` as a '|' scalar.

    ``offset`` is how far the content sits to the right of the parent
    collection. Returns None when the text has to be quoted instead.
    """
    if _BLOCK_UNSAFE.search(text) or not text.strip("\n"):
        return None
    stripped = text.rstrip("\n")
    trailing = len(text) - len(stripped)
    lines = stripped.split("\n") + [""] * max(trailing - 1, 0)
    header = "|"
    first = next(line for line in lines if line)
    if first[0] == " ":
        # leading spaces would be mistaken for indentation unless we say
        # how wide the indentation is
        if offset > 9:
            return None
        header += str(offset)
    if trailing == 0:
        header += "-"
    elif trailing > 1:
        header += "+"
    return header, lines
