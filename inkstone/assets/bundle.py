from __future__ import annotations

import fnmatch
import posixpath
import re
from dataclasses import dataclass, field
from typing import Iterable

from . import css as _css
from . import js as _js
from .errors import AssetError
from .manifest import normalise

_GLOB_CHARS = frozenset("*?[")
_KINDS = {".css": "css", ".js": "js", ".mjs": "js"}
_WS_RE = re.compile(r"\s+")


@dataclass
class Bundle:
    """Several source files concatenated into one output file.

    Inputs are paths relative to the source directories and may be glob
    patterns (`js/vendor/*.js`); matches of a pattern are taken in sorted
    order. `minify` overrides the pipeline setting for this bundle only.
    """

    output: str
    inputs: list[str] = field(default_factory=list)
    minify: bool | None = None

    def __post_init__(self):
        self.output = normalise(self.output)
        if isinstance(self.inputs, str):
            # Bundle("a.js", "b.js") would otherwise iterate the characters
            self.inputs = [self.inputs]
        self.inputs = [normalise(name) for name in self.inputs]
        if not self.inputs:
            raise AssetError("bundle has no inputs", path=self.output)

    @property
    def kind(self) -> str:
        return _KINDS.get(posixpath.splitext(self.output)[1].lower(), "")

    def expand(self, available: Iterable[str]) -> list[str]:
        """Resolve the inputs against the files that exist, globs and all."""
        available = sorted(available)
        known = set(available)
        out: list[str] = []
        for name in self.inputs:
            if _GLOB_CHARS.intersection(name):
                matches = [p for p in available if fnmatch.fnmatchcase(p, name)]
            else:
                matches = [name] if name in known else []
            if not matches:
                raise AssetError(
                    f"bundle input {name!r} does not match any file", path=self.output
                )
            # a file named twice (or caught by two patterns) is included once
            out.extend(m for m in matches if m not in out)
        return out

    def concat(self, parts: list[tuple[str, str]]) -> str:
        if self.kind == "css":
            return concat_css(parts)
        if self.kind == "js":
            return concat_js(parts)
        return "\n".join(text for _name, text in parts)


def _js_terminator(name: str, source: str) -> str:
    """What to append so the next file starts a fresh statement."""
    tokens = [t for t in _js.tokenize(source, name) if t.type not in ("ws", "nl")]
    if not tokens:
        return ""
    code = [t for t in tokens if t.type not in ("comment", "hashbang")]
    need = ";" if code and code[-1].value != ";" else ""
    if need and tokens[-1].value.startswith("//"):
        # a semicolon on the same line would be part of the comment
        return "\n;"
    return need


def concat_js(parts: Iterable[tuple[str, str]]) -> str:
    """Join scripts given as (name, source) pairs.

    Each file is closed off with a `;` unless it already ends with one, so
    that `(function(){...})()` at the top of the next file cannot be read as
    a call on whatever came before.

    XXX a "use strict" at the top of the first file ends up applying to the
    whole bundle. Wrapping each file in a function would fix that and break
    files that declare globals with var.
    """
    out: list[str] = []
    for name, source in parts:
        source = source.strip()
        if source:
            out.append(source + _js_terminator(name, source))
    return "\n".join(out) + ("\n" if out else "")


def concat_css(parts: Iterable[tuple[str, str]]) -> str:
    """Join stylesheets given as (name, source) pairs.

    @charset and @import are only honoured at the very top of a stylesheet,
    so they are lifted out of the individual files: the first @charset wins
    and the imports follow it in the order they were met.

    XXX an `@layer a, b;` statement that precedes an @import stays where it
    is, so the import now comes before it.
    """
    charset = ""
    imports: list[str] = []
    seen: set[str] = set()
    bodies: list[str] = []
    for name, source in parts:
        tokens = _css.tokenize(source, name)
        kept: list[str] = []
        last = 0
        for kind, start, stop in _css.leading_statements(tokens):
            if kind == "@layer":
                continue
            begin = tokens[start].pos
            end = tokens[stop].end if stop < len(tokens) else len(source)
            statement = source[begin:end].rstrip("; \t\r\n") + ";"
            if kind == "@charset":
                charset = charset or statement
            else:
                key = _WS_RE.sub(" ", statement)
                if key not in seen:
                    seen.add(key)
                    imports.append(statement)
            kept.append(source[last:begin])
            last = end
        kept.append(source[last:])
        body = "".join(kept).strip()
        if body:
            bodies.append(body)
    pieces = [charset] if charset else []
    pieces += imports + bodies
    return "\n".join(pieces) + ("\n" if pieces else "")
