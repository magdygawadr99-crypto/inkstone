"""Themes, the template search path, and which template renders which page."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import tomlw
from ..errors import BuildError, ConfigError
from ..tmpl import (
    Environment,
    FileSystemLoader,
    Template,
    TemplateNotFound,
    select_autoescape,
)
from ..utils.fs import read_text
from ..utils.hashing import hash_text, stable_hash

BUILTIN_THEMES = Path(__file__).resolve().parent.parent / "themes"
THEME_FILE = "theme.toml"

_THEME_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class ThemeNotFound(ConfigError):
    pass


@dataclass
class Theme:
    name: str
    path: Path
    description: str = ""
    version: str = ""
    inherit: str | None = None
    params: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    builtin: bool = False

    @property
    def templates_path(self) -> Path:
        return self.path / "templates"

    @property
    def static_path(self) -> Path:
        return self.path / "static"


def available_themes(themes_dir=None) -> list[str]:
    """Names of the themes that can be used: the site's own and the built-in ones."""
    names: set[str] = set()
    for root in (themes_dir, BUILTIN_THEMES):
        if root is None or not Path(root).is_dir():
            continue
        for entry in Path(root).iterdir():
            if entry.is_dir() and not entry.name.startswith((".", "_")):
                names.add(entry.name)
    return sorted(names)


def find_theme(name: str, themes_dir=None) -> Theme:
    """Locate a theme: the site's themes directory wins over the built-in ones."""
    if not isinstance(name, str) or not _THEME_NAME.match(name):
        raise ConfigError(f"{name!r} is not a valid theme name")
    candidates = []
    if themes_dir is not None:
        candidates.append((Path(themes_dir) / name, False))
    candidates.append((BUILTIN_THEMES / name, True))
    for path, builtin in candidates:
        if path.is_dir():
            return _read_theme(name, path, builtin)
    known = available_themes(themes_dir)
    message = f"theme {name!r} not found"
    if themes_dir is not None:
        message += f" in {Path(themes_dir)} or among the built-in themes"
    if known:
        message += f" (available: {', '.join(known)})"
    raise ThemeNotFound(message)


def parse_simple_toml(text: str) -> dict:
    """Read the flat kind of TOML a theme.toml is, without tomllib.

    Python 3.10 has no TOML parser, and a theme that cannot say what it
    inherits from is no theme. This understands tables, comments and
    ``key = value`` with strings, numbers, booleans and one-line arrays;
    anything fancier raises TomlError.
    """
    data: dict = {}
    table = data
    for number, raw in enumerate(text.split("\n"), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]") and "=" not in line:
            table = data
            for part in line[1:-1].strip().split("."):
                table = table.setdefault(part.strip().strip("\"'"), {})
                if not isinstance(table, dict):
                    raise tomlw.TomlError("table name is already a value", line=number)
            continue
        key, equals, value = line.partition("=")
        key, value = key.strip().strip("\"'"), value.strip()
        if not equals or not key or not value:
            raise tomlw.TomlError("expected key = value", line=number)
        if len(value) >= 2 and value[0] == value[-1] == "'":
            table[key] = value[1:-1]
            continue
        try:
            # for these simple shapes TOML and JSON are spelled the same
            table[key] = json.loads(value)
        except json.JSONDecodeError:
            raise tomlw.TomlError(
                f"cannot read the value of {key!r} without Python 3.11", line=number
            ) from None
    return data


def _strip_comment(line: str) -> str:
    quote = ""
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _read_theme(name: str, path: Path, builtin: bool) -> Theme:
    meta_file = path / THEME_FILE
    if not meta_file.is_file():
        # a bare directory of templates works too, it just has no settings
        return Theme(name=name, path=path, builtin=builtin)
    try:
        text = read_text(meta_file)
        meta = tomlw.loads(text) if tomlw.tomllib else parse_simple_toml(text)
    except tomlw.TomlError as exc:
        raise ConfigError(
            f"invalid TOML: {exc.message}", path=meta_file, line=exc.line
        ) from None
    except OSError as exc:
        raise ConfigError(
            f"cannot read theme file: {exc.strerror or exc}", path=meta_file
        ) from None
    params = meta.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError("[params] has to be a table", path=meta_file)
    inherit = meta.get("inherit") or None
    if inherit is not None and not isinstance(inherit, str):
        raise ConfigError(
            f"inherit has to be the name of a theme, got {inherit!r}", path=meta_file
        )
    return Theme(
        name=name,
        path=path,
        description=str(meta.get("description", "")),
        version=str(meta.get("version", "")),
        inherit=inherit,
        params=params,
        meta=meta,
        builtin=builtin,
    )


def theme_chain(config) -> list[Theme]:
    """The configured theme followed by the themes it inherits from."""
    themes_dir = config.themes_path
    chain: list[Theme] = []
    name = config.theme
    while name:
        if any(theme.name == name for theme in chain):
            loop = " -> ".join([theme.name for theme in chain] + [name])
            raise ConfigError(f"themes inherit from each other in a circle: {loop}")
        try:
            theme = find_theme(name, themes_dir)
        except ThemeNotFound as exc:
            if chain:
                raise ThemeNotFound(
                    f"{exc.message} (inherited by theme {chain[-1].name!r})"
                ) from None
            raise
        chain.append(theme)
        name = theme.inherit
    return chain


def template_search_path(config, themes: list[Theme]) -> list[Path]:
    """Site templates first, then the theme, then its parents."""
    return [config.templates_path] + [theme.templates_path for theme in themes]


def static_search_path(config, themes: list[Theme]) -> list[Path]:
    """Static directories, lowest priority first, as the asset pipeline wants them."""
    return [theme.static_path for theme in reversed(themes)] + [config.static_path]


def make_environment(config, themes: list[Theme]) -> Environment:
    search = [str(path) for path in template_search_path(config, themes)]
    return Environment(
        loader=FileSystemLoader(search),
        # escape HTML and XML output, leave robots.txt-style templates alone
        autoescape=select_autoescape(),
        auto_reload=True,
    )


def template_candidates(page) -> list[str]:
    """Template names to try for a page, most specific first."""
    names: list[str] = []
    if page.template:
        names.append(page.template)
    kind = page.kind
    if kind == "page":
        names += _section_candidates(page.section, "page.html")
    elif kind == "section":
        names += _section_candidates(page.section, "section.html")
    elif kind == "home":
        names.append("index.html")
    elif kind in ("taxonomy", "term"):
        taxonomy = page.extra_context.get("taxonomy")
        if taxonomy is not None:
            names.append(f"{taxonomy.name}/{kind}.html")
        names.append(f"{kind}.html")
    elif kind == "404":
        names.append("404.html")
    # preserve order, drop repeats (template: page.html in front matter)
    return list(dict.fromkeys(names))


def _section_candidates(section, filename: str) -> list[str]:
    names = []
    while section is not None and section.name:
        names.append(f"{section.name}/{filename}")
        # pages of docs/guide fall back to docs/page.html before page.html
        section = section.parent
    names.append(filename)
    return names


def select_template(env: Environment, page) -> Template:
    names = template_candidates(page)
    if not names:
        raise BuildError(
            f"no template given for the {page.kind} page {page.url}",
            path=page.source_path,
        )
    try:
        return env.select_template(names)
    except TemplateNotFound:
        tried = ", ".join(names)
        raise BuildError(
            f"no template found for the {page.kind} page {page.url} (tried: {tried})",
            path=page.source_path,
        ) from None


class TemplateFingerprints:
    """Hashes of templates including everything they extend, include or import.

    Memoised for the length of one build; call reset() at the start of the next.
    """

    def __init__(self, env: Environment):
        self.env = env
        self._sources: dict[str, str] = {}
        self._full: dict[str, str] = {}
        self._deps: dict[str, list[str]] = {}

    def reset(self) -> None:
        """Forget everything; to be called at the start of a build.

        The environment notices edited templates by their mtime. Two saves
        within one tick of a coarse file system clock would get past that,
        and then pages would be re-rendered from the stale parse and cached
        as current. So templates whose text changed since the last build
        are looked for here, and the environment's cache goes if there are any.
        """
        previous = dict(self._sources)
        self._sources.clear()
        self._full.clear()
        self._deps.clear()
        if any(self.source_hash(name) != digest for name, digest in previous.items()):
            self.env.clear_cache()

    def source_hash(self, name: str) -> str:
        """Hash of one template's own source; "" when it does not exist."""
        try:
            return self._sources[name]
        except KeyError:
            pass
        digest = ""
        loader = self.env.loader
        if loader is not None:
            try:
                digest = hash_text(loader.get_source(name)[0])
            except TemplateNotFound:
                digest = ""
        self._sources[name] = digest
        return digest

    def dependencies(self, name: str) -> list[str]:
        """The template itself plus every template it pulls in, sorted."""
        try:
            return self._deps[name]
        except KeyError:
            pass
        try:
            found = self.env.get_template(name).all_dependencies()
        except TemplateNotFound:
            found = set()
        names = sorted(found | {name})
        self._deps[name] = names
        return names

    def fingerprint(self, name: str) -> str:
        try:
            return self._full[name]
        except KeyError:
            pass
        parts = {dep: self.source_hash(dep) for dep in self.dependencies(name)}
        digest = stable_hash(parts)
        self._full[name] = digest
        return digest
