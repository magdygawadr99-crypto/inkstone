"""Splitting source files into metadata and body.

Three flavours are understood, told apart by how the file starts:

    ---            +++            {                ;;;
    yaml           toml             "json": 1      "json": 1
    ---            +++            }                ;;;
"""

from __future__ import annotations

import datetime as dt
import json
import re

from . import tomlw, yamlite
from .errors import ContentError

_FENCES = {"---": "yaml", "+++": "toml", ";;;": "json"}

# A bare "{" only counts as JSON front matter if a key or the closing brace
# follows; otherwise template files starting with "{{ ... }}" or "{% ... %}"
# would be mistaken for it.
_JSON_OPENING = re.compile(r'\{\s*["}]')


def split(text: str) -> tuple[str | None, str, str | None]:
    """Separate front matter from the body without parsing it.

    Returns ``(raw_meta, body, fmt)`` where fmt is "yaml", "toml", "json" or
    None. Without front matter raw_meta is None and body is the whole text.
    """
    raw, body, fmt, _ = _split(text, None)
    return raw, body, fmt


def parse(text: str, *, path=None) -> tuple[dict, str]:
    """Split ``text`` and parse its metadata into a dict.

    Line numbers in errors count from the top of the file, not from the
    start of the metadata block.
    """
    raw, body, fmt, first_line = _split(text, path)
    if fmt is None or not raw.strip():
        return {}, body
    try:
        if fmt == "yaml":
            meta = yamlite.loads(raw)
        elif fmt == "toml":
            meta = tomlw.loads(raw)
        else:
            meta = _load_json(raw)
    except yamlite.YamlError as exc:
        problem = exc.problem
        if exc.column is not None:
            problem += f" (column {exc.column})"
        line = first_line + (exc.line or 1) - 1
        raise _error(f"invalid YAML front matter: {problem}", line, path) from None
    except tomlw.TomlError as exc:
        line = first_line + (exc.line or 1) - 1
        raise _error(f"invalid TOML front matter: {exc.message}", line, path) from None
    except json.JSONDecodeError as exc:
        line = first_line + exc.lineno - 1
        raise _error(f"invalid JSON front matter: {exc.msg}", line, path) from None
    if meta is None:
        return {}, body
    if not isinstance(meta, dict):
        kind = "list" if isinstance(meta, list) else type(meta).__name__
        raise _error(
            f"front matter must be a set of key: value pairs, not a {kind}",
            first_line,
            path,
        )
    return meta, body


def dumps(meta: dict, body: str, fmt: str = "yaml") -> str:
    """Put a file back together; the inverse of :func:`parse`."""
    # XXX a multi-line TOML string with a line that reads exactly "+++"
    # would end the block early when read back. Never seen in practice.
    if fmt == "yaml":
        block = yamlite.dumps(meta) if meta else ""
        return f"---\n{block}---\n{body}"
    if fmt == "toml":
        return f"+++\n{tomlw.dumps(meta)}+++\n{body}"
    if fmt == "json":
        block = json.dumps(meta, indent=2, ensure_ascii=False, default=_json_default)
        return f"{block}\n{body}"
    raise ValueError(f"unknown front matter format: {fmt!r}")


def _error(message: str, line: int | None, path) -> ContentError:
    if path is None and line is not None:
        # str() of our errors only shows the line next to a path
        message = f"{message} (line {line})"
    return ContentError(message, path=path, line=line)


def _split(text: str, path) -> tuple[str | None, str, str | None, int]:
    """Like split(), plus the 1-based line on which the metadata starts."""
    if text.startswith("\ufeff"):
        text = text[1:]
    end = text.find("\n")
    first = text if end == -1 else text[:end]
    fence = first.rstrip(" \t")
    if fence in _FENCES:
        return _split_fenced(text, fence, path)
    if _JSON_OPENING.match(text):
        return _split_braces(text, path)
    return None, text, None, 1


def _split_fenced(text: str, fence: str, path):
    fmt = _FENCES[fence]
    # pandoc and Jekyll also accept "..." to close a YAML block
    closers = (fence, "...") if fmt == "yaml" else (fence,)
    start = pos = text.find("\n") + 1
    while 0 < pos < len(text):
        end = text.find("\n", pos)
        following = len(text) if end == -1 else end + 1
        if text[pos:following].rstrip(" \t\n") in closers:
            return text[start:pos], text[following:], fmt, 2
        pos = following
    raise _error(
        f"front matter is never closed (expected another '{fence}' line)", 1, path
    )


def _split_braces(text: str, path):
    depth = 0
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        raise _error("JSON front matter is never closed (missing '}')", 1, path)
    end = index + 1
    # whatever is left of the closing line belongs to the body, unless it is
    # just the line break
    newline = text.find("\n", end)
    rest_of_line = text[end:] if newline == -1 else text[end : newline + 1]
    if not rest_of_line.strip():
        end += len(rest_of_line)
    return text[:end].rstrip("\r\n"), text[end:], "json", 1


def _load_json(raw: str):
    # Hexo-style blocks between ;;; fences leave out the outer braces.
    # Wrapping on the same line keeps the reported line numbers right.
    if not raw.lstrip().startswith("{"):
        raw = "{" + raw + "}"
    return json.loads(raw)


def _json_default(value):
    # JSON has no date type; these come back as strings when re-read
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    raise TypeError(f"cannot store {type(value).__name__} in JSON front matter")
