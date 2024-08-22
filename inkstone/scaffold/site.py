"""Copying the starter site out of the package.

The files live in ``skeleton/`` as they will be written, give or take:

- ``{{name}}`` in a file or in its name is replaced (title, author, theme,
  date, year); ``{{name|json}}`` writes the value as a quoted string, which
  is valid in TOML, YAML and JSON alike
- a name starting with ``dot-`` gets a real dot instead, because packaging
  tools have a habit of leaving dotfiles behind
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from .. import tomlw
from ..config import CONFIG_NAMES
from ..errors import ConfigError, InkstoneError
from ..utils.fs import atomic_write

SKELETON = Path(__file__).resolve().parent / "skeleton"
THEMES = Path(__file__).resolve().parent.parent / "themes"
CONFIG_FORMATS = ("toml", "yaml")

_VARIABLE = re.compile(r"\{\{\s*([a-z_]+)\s*(?:\|\s*(json)\s*)?\}\}")


def render(text: str, variables: dict) -> str:
    """Fill in ``{{name}}`` and ``{{name|json}}``; unknown names are left alone."""

    def fill(match: re.Match) -> str:
        name, as_json = match.groups()
        if name not in variables:
            return match.group()
        value = variables[name]
        if as_json:
            return json.dumps(str(value), ensure_ascii=False)
        return str(value)

    return _VARIABLE.sub(fill, text)


def default_config_format() -> str:
    # TOML can only be read from Python 3.11 on; a site that cannot load its
    # own config would be a poor start
    return "toml" if tomlw.tomllib is not None else "yaml"


def skeleton_files(config_format: str = "toml") -> list[tuple[str, Path]]:
    """``(path inside the new site, source file)`` for everything to write."""
    files = []
    for source in sorted(SKELETON.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(SKELETON)
        if rel.parent == Path(".") and rel.stem == "inkstone":
            if rel.suffix != "." + config_format:
                continue
        parts = [
            "." + part[len("dot-") :] if part.startswith("dot-") else part
            for part in rel.parts
        ]
        files.append(("/".join(parts), source))
    return files


def builtin_themes() -> list[str]:
    if not THEMES.is_dir():
        return []
    return sorted(
        entry.name
        for entry in THEMES.iterdir()
        if entry.is_dir() and not entry.name.startswith((".", "_"))
    )


def git_user_name() -> str:
    """The name git signs commits with, for the author field; "" if unknown."""
    try:
        done = subprocess.run(
            ["git", "config", "--get", "user.name"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def create_site(
    path,
    *,
    title: str = "My Site",
    theme: str = "default",
    author: str | None = None,
    force: bool = False,
    config_format: str | None = None,
    today: dt.date | None = None,
) -> list[Path]:
    """Write the starter site into ``path`` and return the files created.

    A directory that already has something in it is refused unless ``force``
    is set, and even then existing files are never overwritten.
    """
    target = Path(path)
    if target.exists() and not target.is_dir():
        raise InkstoneError(f"{target} exists and is not a directory")
    if target.is_dir() and any(target.iterdir()) and not force:
        raise InkstoneError(
            f"{target} is not empty (use --force to add the missing files anyway)"
        )
    known = builtin_themes()
    if theme not in known and not (target / "themes" / theme).is_dir():
        raise ConfigError(
            f"no theme called {theme!r} (available: {', '.join(known) or 'none'})"
        )
    if config_format is None:
        config_format = default_config_format()
    if config_format not in CONFIG_FORMATS:
        raise ValueError(f"unknown config format: {config_format!r}")
    if today is None:
        # The new site's timezone is UTC until somebody changes it. Going by
        # the local date instead would, east of Greenwich in the small hours,
        # date the first post tomorrow and keep it out of the first build.
        today = dt.datetime.now(dt.timezone.utc).date()
    variables = {
        "title": title,
        "theme": theme,
        "author": git_user_name() if author is None else author,
        "date": today.isoformat(),
        "year": today.year,
    }

    # with --force this may be a site already; a second config file next to
    # the one it has would only get in the way
    configured = any((target / name).is_file() for name in CONFIG_NAMES)
    created = []
    for rel, source in skeleton_files(config_format):
        destination = target / render(rel, variables)
        if destination.exists() or (configured and rel in CONFIG_NAMES):
            continue
        text = source.read_text(encoding="utf-8")
        atomic_write(destination, render(text, variables))
        created.append(destination)
    return created
