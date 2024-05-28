"""TOML output, plus a thin wrapper around tomllib for reading.

The standard library can read TOML (from 3.11 on) but not write it, and
front matter needs both directions.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping

from .errors import InkstoneError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+\Z")
_POSITION = re.compile(r"\s*\(at (?:line (\d+), column \d+|end of document)\)\Z")
_CONTROL = re.compile("[\x00-\x1f\x7f]")
_BASIC_UNSAFE = re.compile('[\x00-\x1f\x7f"\\\\]')
_MULTILINE_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f\\\\]")
_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}

# arrays longer than this get one item per line
_WRAP_AT = 80


class TomlError(InkstoneError):
    pass


def loads(text: str) -> dict:
    """Parse a TOML document, turning syntax errors into TomlError."""
    if tomllib is None:
        raise TomlError("reading TOML needs Python 3.11 or newer")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        message = str(exc)
        line = None
        # the position is only available as part of the message before 3.14
        match = _POSITION.search(message)
        if match:
            message = message[: match.start()]
            line = int(match.group(1)) if match.group(1) else text.count("\n") + 1
        raise TomlError(message, line=line) from None


def dumps(data: dict) -> str:
    """Serialise a dict as a TOML document.

    TOML has no null, so keys whose value is None are left out. None inside
    an array is an error because dropping it would shift the other items.
    """
    if not isinstance(data, Mapping):
        raise TomlError("the top level of a TOML document must be a table")
    lines: list[str] = []
    _write_table(lines, data, ())
    return "\n".join(lines) + "\n" if lines else ""


def _write_table(lines: list[str], table: Mapping, path: tuple[str, ...]) -> None:
    # Plain values have to come before any [section] header, otherwise they
    # would end up belonging to that section.
    tables = []
    arrays = []
    for key, value in table.items():
        if value is None:
            continue
        if _is_table(value):
            tables.append((key, value))
        elif _is_table_array(value):
            arrays.append((key, value))
        else:
            lines.append(_pair(key, value))
    for key, value in tables:
        sub = path + (key,)
        if _needs_header(value):
            _start_section(lines, f"[{_dotted(sub)}]")
        _write_table(lines, value, sub)
    for key, items in arrays:
        sub = path + (key,)
        for item in items:
            _start_section(lines, f"[[{_dotted(sub)}]]")
            _write_table(lines, item, sub)


def _is_table(value) -> bool:
    return isinstance(value, Mapping) and len(value) > 0


def _is_table_array(value) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return all(isinstance(item, Mapping) for item in value)


def _needs_header(table: Mapping) -> bool:
    """False for tables that only hold sub-tables; [a.b] then implies [a]."""
    nested = False
    for value in table.values():
        if value is None:
            continue
        if _is_table(value) or _is_table_array(value):
            nested = True
        else:
            return True
    return not nested


def _start_section(lines: list[str], header: str) -> None:
    if lines:
        lines.append("")
    lines.append(header)


def _dotted(path: tuple[str, ...]) -> str:
    return ".".join(_key(part) for part in path)


def _key(key) -> str:
    if not isinstance(key, str):
        raise TomlError(f"TOML keys must be strings, got {key!r}")
    return key if _BARE_KEY.match(key) else _basic_string(key)


def _pair(key, value) -> str:
    left = f"{_key(key)} = "
    if isinstance(value, str) and "\n" in value:
        return left + _multiline_string(value)
    text = _inline(value)
    if isinstance(value, (list, tuple)) and len(left) + len(text) > _WRAP_AT:
        items = "".join(f"    {_inline(item)},\n" for item in value)
        return f"{left}[\n{items}]"
    return left + text


def _inline(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        return _float(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, dt.time):
        if value.tzinfo is not None:
            raise TomlError("a TOML time cannot carry a UTC offset")
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Mapping):
        pairs = [
            f"{_key(key)} = {_inline(item)}"
            for key, item in value.items()
            if item is not None
        ]
        return "{ " + ", ".join(pairs) + " }" if pairs else "{}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_inline(item) for item in value) + "]"
    if value is None:
        raise TomlError("TOML has no null, so None cannot be stored in an array")
    raise TomlError(f"cannot represent {type(value).__name__} objects in TOML")


def _float(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return repr(float(value))


def _string(text: str) -> str:
    # literal strings keep Windows paths and regexes readable
    if "\\" in text and "'" not in text and not _CONTROL.search(text):
        return f"'{text}'"
    return _basic_string(text)


def _basic_string(text: str) -> str:
    return '"' + _BASIC_UNSAFE.sub(_escape, text) + '"'


def _multiline_string(text: str) -> str:
    body = _MULTILINE_UNSAFE.sub(_escape, text)
    # Lone quotes are fine inside """...""", but runs of them or one right
    # before the closing delimiter are not; escaping all of them is simplest.
    if '""' in body or body.endswith('"'):
        body = body.replace('"', '\\"')
    # the newline right after the opening quotes is not part of the string
    return f'"""\n{body}"""'


def _escape(match: re.Match) -> str:
    char = match.group()
    return _ESCAPES.get(char) or f"\\u{ord(char):04x}"
