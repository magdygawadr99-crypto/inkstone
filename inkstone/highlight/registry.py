from __future__ import annotations

import fnmatch
import posixpath
import re

from .errors import HighlightError
from .lexer import Lexer, TextLexer

_by_name: dict[str, type[Lexer]] = {}
_classes: list[type[Lexer]] = []
_instances: dict[type[Lexer], Lexer] = {}
_loaded = False

# Below this a content-based guess is more likely wrong than right.
_GUESS_THRESHOLD = 0.3


def register(cls: type[Lexer]) -> type[Lexer]:
    """Class decorator: make a lexer findable by its name and aliases."""
    if not cls.name:
        raise HighlightError(f"{cls.__name__} has no name")
    for key in (cls.name, *cls.aliases):
        key = key.lower()
        other = _by_name.get(key)
        if other is not None and other is not cls:
            raise HighlightError(
                f"language name {key!r} is used by both "
                f"{other.__name__} and {cls.__name__}"
            )
        _by_name[key] = cls
    if cls not in _classes:
        _classes.append(cls)
    return cls


register(TextLexer)


def _load() -> None:
    # Importing the package registers everything. Deferred until first use
    # because the lexer modules import this one.
    global _loaded
    if not _loaded:
        from . import lexers  # noqa: F401

        _loaded = True


def _instance(cls: type[Lexer]) -> Lexer:
    # Lexers keep no per-run state, so one shared instance each is enough.
    lexer = _instances.get(cls)
    if lexer is None:
        lexer = _instances[cls] = cls()
    return lexer


def _find(name: str) -> type[Lexer] | None:
    _load()
    return _by_name.get(name.strip().lower())


def get_lexer(name: str) -> Lexer:
    cls = _find(name) if isinstance(name, str) else None
    if cls is None:
        raise HighlightError(f"no lexer for language {name!r}")
    return _instance(cls)


def find_lexer(name: str | None) -> Lexer:
    """Like get_lexer, but unknown or missing names give the plain text lexer."""
    cls = _find(name) if isinstance(name, str) else None
    return _instance(cls or TextLexer)


def list_languages() -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """``(name, aliases, extensions)`` for every language, sorted by name."""
    _load()
    return sorted((cls.name, cls.aliases, cls.extensions) for cls in _classes)


def language_for_filename(filename: str) -> str | None:
    _load()
    base = posixpath.basename(str(filename).replace("\\", "/"))
    lowered = base.lower()
    # exact names first: "CMakeLists.txt" style clashes should beat ".txt"
    for cls in _classes:
        for pattern in cls.filenames:
            if fnmatch.fnmatchcase(base, pattern):
                return cls.name
    best: tuple[int, str] | None = None
    for cls in _classes:
        for ext in cls.extensions:
            # longest extension wins, so ".d.ts" can beat ".ts" if both exist
            if lowered.endswith(ext) and (best is None or len(ext) > best[0]):
                best = (len(ext), cls.name)
    return best[1] if best else None


_SHEBANG = re.compile(r"#!\s*(\S+)(.*)")
_MODELINES = (
    re.compile(r"-\*-.*?\bmode:\s*([\w+-]+).*?-\*-"),
    re.compile(r"\b(?:vim?|ex):\s*(?:set\s+)?.*?\b(?:ft|filetype)=([\w+-]+)"),
)


def _language_for_shebang(code: str) -> str | None:
    first_line = code.split("\n", 1)[0]
    match = _SHEBANG.match(first_line)
    if match is None:
        return None
    interpreter = posixpath.basename(match.group(1))
    if interpreter == "env":
        # "/usr/bin/env -S python3 -u", "/usr/bin/env FOO=1 node"
        args = [a for a in match.group(2).split() if "=" not in a]
        args = [a for a in args if not a.startswith("-")]
        if not args:
            return None
        interpreter = posixpath.basename(args[0])
    for cls in _classes:
        for pattern in cls.shebangs:
            if re.fullmatch(pattern, interpreter):
                return cls.name
    return None


def _language_for_modeline(code: str) -> str | None:
    lines = code.split("\n")
    # editors only look at the edges of the file, and so do we
    for line in lines[:3] + lines[-3:]:
        for pattern in _MODELINES:
            match = pattern.search(line)
            if match:
                cls = _by_name.get(match.group(1).lower())
                if cls is not None:
                    return cls.name
    return None


def guess_language(code: str, filename: str | None = None) -> str | None:
    """Best guess at the language of ``code``, or None.

    The filename is trusted first, then a ``#!`` line, then an editor
    modeline, and only then each lexer's own opinion of the text.
    """
    _load()
    if filename:
        name = language_for_filename(filename)
        if name is not None:
            return name
    if not code or not code.strip():
        return None
    name = _language_for_shebang(code) or _language_for_modeline(code)
    if name is not None:
        return name
    best_score = 0.0
    best = None
    for cls in _classes:
        score = cls.analyse(code)
        if score > best_score:
            best_score, best = score, cls.name
    return best if best_score >= _GUESS_THRESHOLD else None
