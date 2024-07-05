"""Site configuration: defaults, the config file, environment and CLI overrides."""

from __future__ import annotations

import copy
import datetime as dt
import difflib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit

from . import tomlw, yamlite
from .errors import ConfigError, ContentError
from .utils import log
from .utils.collections import AttrDict, deep_merge, get_path, set_path
from .utils.dates import parse_tz
from .utils.fs import read_text
from .utils.glob import GlobSet

CONFIG_NAMES = ("inkstone.toml", "inkstone.yaml", "inkstone.yml", "inkstone.json")
ENV_PREFIX = "INKSTONE_"
PERMALINK_TOKENS = ("year", "month", "day", "slug", "title", "section", "filename")

_DEFAULTS: dict[str, Any] = {
    "title": "My Site",
    "base_url": "http://localhost:8000/",
    "description": "",
    "language": "en",
    "timezone": "UTC",
    "theme": "default",
    "content_dir": "content",
    "output_dir": "public",
    "static_dir": "static",
    "data_dir": "data",
    "templates_dir": "templates",
    "themes_dir": "themes",
    "plugins_dir": "plugins",
    "cache_dir": ".inkstone-cache",
    "ignore": ["*.swp", "*~", ".DS_Store"],
    "plugins": [],
    "author": {"name": "", "email": "", "url": ""},
    "build": {
        "drafts": False,
        "future": False,
        "incremental": True,
        "minify": False,
        "fingerprint": False,
        "pretty_urls": True,
        "jobs": 0,
    },
    "markdown": {
        "extensions": [],
        "smart": True,
        "heading_ids": True,
        "highlight": True,
        "highlight_style": "dusk",
        "hard_wraps": False,
    },
    "permalinks": {"posts": "/:year/:month/:slug/"},
    "taxonomies": {"tags": "tag", "categories": "category"},
    "pagination": {"per_page": 10, "path": "page"},
    "feeds": {
        "rss": True,
        "atom": True,
        "json": False,
        "limit": 20,
        "sections": ["posts"],
        "full_content": True,
    },
    "search": {
        "enabled": True,
        "fields": {"title": 3.0, "tags": 2.0, "body": 1.0},
    },
    "sitemap": {"enabled": True, "changefreq": "weekly"},
    "robots": {"enabled": True, "disallow": []},
    "server": {"host": "127.0.0.1", "port": 8000, "livereload": True, "open": False},
    "menus": {},
    "params": {},
    "plugin": {},
}

# Tables where any key goes; their contents are checked separately or not at all.
_OPEN_TABLES = frozenset(
    {"author", "permalinks", "taxonomies", "search.fields", "menus", "params", "plugin"}
)
# Tables that replace their default instead of being merged into it: defining
# [taxonomies] with only "tags" means there are no categories.
_REPLACED_TABLES = ("permalinks", "taxonomies", "search.fields")
_DIR_KEYS = (
    "content_dir",
    "output_dir",
    "static_dir",
    "data_dir",
    "templates_dir",
    "themes_dir",
    "plugins_dir",
    "cache_dir",
)
_CHANGEFREQS = ("always", "hourly", "daily", "weekly", "monthly", "yearly", "never")
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})
_TOKEN = re.compile(r":([A-Za-z_]+)")
_MISSING = object()


def default_config() -> dict:
    """The full default tree, as a fresh dict that is safe to modify."""
    return copy.deepcopy(_DEFAULTS)


class Config:
    """The merged configuration of one site.

    Reads like nested dicts with attribute access: ``cfg.title``,
    ``cfg["title"]``, ``cfg.build.minify``, ``cfg.get("build.minify")``.
    """

    def __init__(
        self,
        data: Mapping[str, Any] | None = None,
        *,
        root: str | os.PathLike = ".",
        path: str | os.PathLike | None = None,
        overrides: Mapping[str, Any] | None = None,
    ):
        tree = default_config() if data is None else data
        object.__setattr__(self, "_data", AttrDict(tree))
        object.__setattr__(self, "root", Path(root).resolve())
        object.__setattr__(self, "path", Path(path).resolve() if path else None)
        # kept so a reload (the dev server, after the file changed) can apply
        # the same command line options again
        object.__setattr__(self, "overrides", dict(overrides or {}))
        object.__setattr__(self, "warnings", [])
        object.__setattr__(self, "explicit_path", False)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            # also keeps copy/pickle from recursing before _data exists
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"no config key {name!r}") from None

    def __setattr__(self, name: str, value) -> None:
        if name in self.__dict__ or name in type(self).__dict__:
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def __getitem__(self, key: str):
        return self._data[key]

    def __setitem__(self, key: str, value) -> None:
        self._data[key] = value

    def __contains__(self, key) -> bool:
        return key in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        where = self.path or self.root
        return f"<Config {str(where)!r}>"

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def get(self, key: str, default=None):
        """Look up a (possibly dotted) key: ``cfg.get("build.minify")``."""
        return get_path(self._data, key, default)

    def set(self, key: str, value) -> None:
        set_path(self._data, key, AttrDict._wrap(value))

    def to_dict(self) -> dict:
        return self._data.to_dict()

    def _dir(self, key: str) -> Path:
        # joining with an absolute path gives that path back, which is what we want
        return (self.root / str(self._data[key])).resolve()

    @property
    def content_path(self) -> Path:
        return self._dir("content_dir")

    @property
    def output_path(self) -> Path:
        return self._dir("output_dir")

    @property
    def static_path(self) -> Path:
        return self._dir("static_dir")

    @property
    def data_path(self) -> Path:
        return self._dir("data_dir")

    @property
    def templates_path(self) -> Path:
        return self._dir("templates_dir")

    @property
    def themes_path(self) -> Path:
        return self._dir("themes_dir")

    @property
    def cache_path(self) -> Path:
        return self._dir("cache_dir")

    @property
    def plugins_path(self) -> Path:
        return self._dir("plugins_dir")

    @property
    def base_path(self) -> str:
        """Path part of base_url with slashes on both ends: "/" or "/blog/"."""
        path = urlsplit(self._data["base_url"]).path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path if path.endswith("/") else path + "/"

    @property
    def tzinfo(self) -> dt.tzinfo:
        return _timezone(self._data["timezone"])

    def reload(self) -> Config:
        """Read the configuration again, with the overrides it was made with."""
        path = self.path if self.explicit_path else None
        return load_config(self.root, path=path, overrides=self.overrides)


def find_config_file(root) -> Path | None:
    root = Path(root)
    found = [root / name for name in CONFIG_NAMES if (root / name).is_file()]
    if len(found) > 1:
        others = ", ".join(path.name for path in found[1:])
        log.warning("using %s, ignoring %s", found[0].name, others)
    return found[0] if found else None


def find_site_root(start=None) -> Path | None:
    """Walk up from ``start`` (default: the cwd) to the directory with a config file."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in (here, *here.parents):
        if any((candidate / name).is_file() for name in CONFIG_NAMES):
            return candidate
    return None


def load_config(
    root, *, path=None, overrides: Mapping[str, Any] | None = None
) -> Config:
    """Load the configuration of the site at ``root``.

    Layers, later ones winning: built-in defaults, the theme's ``[params]``,
    the config file, ``INKSTONE_*`` environment variables, ``overrides``
    (a flat dict with dotted keys, what the command line options turn into).
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ConfigError(f"site directory does not exist: {root}")
    explicit = path is not None
    if explicit:
        path = Path(path)
        if not path.is_absolute() and not path.is_file() and (root / path).is_file():
            path = root / path
        if not path.is_file():
            raise ConfigError("config file not found", path=path)
        path = path.resolve()
    else:
        path = find_config_file(root)

    user = _read_file(path) if path is not None else {}
    warnings = _unknown_keys(user, _DEFAULTS, "")
    _check_types(user, _DEFAULTS, "", path)

    # None stands for "option not given", which is how argparse reports it
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    tree = _merge(default_config(), user)
    env = _env_overrides(os.environ)
    for key, value in env.items():
        _apply_override(tree, key, value, origin=f"environment variable {value.source}")
    for key, value in overrides.items():
        _apply_override(tree, key, value, origin="command line")

    _validate(tree, path)
    tree["base_url"] = _normalise_base_url(tree["base_url"])

    config = Config(tree, root=root, path=path, overrides=overrides)
    config.explicit_path = explicit
    _check_directories(config)
    _apply_theme_params(config, user, env, overrides)
    for message in warnings:
        log.warning("%s: %s", path.name if path else "config", message)
    config.warnings.extend(warnings)
    return config


def _read_file(path: Path) -> dict:
    try:
        text = read_text(path)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ConfigError(f"cannot read config file: {reason}", path=path) from None
    except ContentError as exc:
        raise ConfigError(exc.message, path=path, line=exc.line) from None
    suffix = path.suffix.lower()
    try:
        if suffix == ".toml":
            data = tomlw.loads(text)
        elif suffix in (".yaml", ".yml"):
            data = yamlite.loads(text)
        elif suffix == ".json":
            data = json.loads(text)
        else:
            raise ConfigError(
                f"unsupported config format {suffix or path.name!r} "
                "(use .toml, .yaml or .json)",
                path=path,
            )
    except tomlw.TomlError as exc:
        raise ConfigError(
            f"invalid TOML: {exc.message}", path=path, line=exc.line
        ) from None
    except yamlite.YamlError as exc:
        raise ConfigError(
            f"invalid YAML: {exc.problem}", path=path, line=exc.line
        ) from None
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"invalid JSON: {exc.msg}", path=path, line=exc.lineno
        ) from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(
            f"the config file has to be a table of settings, not a "
            f"{_type_name(data)}",
            path=path,
        )
    return data


def _merge(defaults: dict, user: Mapping) -> dict:
    merged = deep_merge(defaults, user)
    for key in _REPLACED_TABLES:
        value = get_path(user, key, _MISSING)
        if isinstance(value, Mapping):
            set_path(merged, key, copy.deepcopy(dict(value)))
    return merged


def _type_name(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, Mapping):
        return "table"
    return type(value).__name__


def _expected(default) -> str:
    if isinstance(default, bool):
        return "true or false"
    if isinstance(default, int):
        return "an integer"
    if isinstance(default, float):
        return "a number"
    if isinstance(default, str):
        return "a string"
    if isinstance(default, list):
        return "a list of strings"
    return "a table"


def _type_ok(value, default) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        return isinstance(value, list)
    if isinstance(default, dict):
        return isinstance(value, Mapping)
    return True


def _check_types(user: Mapping, defaults: Mapping, prefix: str, path) -> None:
    for key, value in user.items():
        if key not in defaults:
            continue
        dotted = f"{prefix}{key}"
        default = defaults[key]
        if not _type_ok(value, default):
            raise ConfigError(
                f"{dotted} must be {_expected(default)}, got {value!r} "
                f"({_type_name(value)})",
                path=path,
            )
        if isinstance(default, list):
            for index, item in enumerate(value):
                if not isinstance(item, str):
                    raise ConfigError(
                        f"{dotted}[{index}] must be a string, got {item!r} "
                        f"({_type_name(item)})",
                        path=path,
                    )
        elif isinstance(default, dict) and dotted not in _OPEN_TABLES:
            _check_types(value, default, dotted + ".", path)
        elif dotted == "author":
            for name in default:
                if name in value and not isinstance(value[name], str):
                    raise ConfigError(
                        f"author.{name} must be a string, got {value[name]!r}",
                        path=path,
                    )


def _unknown_keys(user: Mapping, defaults: Mapping, prefix: str) -> list[str]:
    """Warnings for keys we have never heard of, with a guess at what was meant."""
    messages = []
    for key, value in user.items():
        dotted = f"{prefix}{key}"
        if key not in defaults:
            message = f"unknown setting {dotted!r}"
            close = difflib.get_close_matches(str(key), list(defaults), n=1, cutoff=0.6)
            if close:
                message += f", did you mean {prefix + close[0]!r}?"
            elif not prefix:
                message += " (free-form values for themes belong under [params])"
            messages.append(message)
        elif isinstance(defaults[key], dict) and isinstance(value, Mapping):
            if dotted not in _OPEN_TABLES:
                messages.extend(_unknown_keys(value, defaults[key], dotted + "."))
    return messages


class _EnvValue(str):
    """A value from the environment that remembers which variable it came from."""

    source = ""


def _env_overrides(environ: Mapping[str, str]) -> dict[str, _EnvValue]:
    found: dict[str, _EnvValue] = {}
    for name in sorted(environ):
        if not name.startswith(ENV_PREFIX):
            continue
        parts = [part.lower() for part in name[len(ENV_PREFIX) :].split("__")]
        # other INKSTONE_* variables exist (the CLI reads a few); only the ones
        # that name a real setting are ours
        if not all(parts) or parts[0] not in _DEFAULTS:
            continue
        value = _EnvValue(environ[name])
        value.source = name
        found[".".join(parts)] = value
    return found


def _coerce(text: str, default, key: str, origin: str):
    """Turn a string from the environment or the command line into a typed value."""
    stripped = text.strip()
    if isinstance(default, bool):
        lowered = stripped.lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        raise ConfigError(f"{key} must be true or false, got {text!r} ({origin})")
    if isinstance(default, int):
        try:
            return int(stripped)
        except ValueError:
            raise ConfigError(
                f"{key} must be an integer, got {text!r} ({origin})"
            ) from None
    if isinstance(default, float):
        try:
            return float(stripped)
        except ValueError:
            raise ConfigError(
                f"{key} must be a number, got {text!r} ({origin})"
            ) from None
    if isinstance(default, list):
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in stripped.split(",") if item.strip()]
    if isinstance(default, dict):
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            value = None
        if not isinstance(value, dict):
            raise ConfigError(f"{key} must be a JSON object, got {text!r} ({origin})")
        return value
    if default is _MISSING:
        return _guess_scalar(stripped)
    return text


def _guess_scalar(text: str):
    """For free-form keys (params.*, plugin.*) where no default tells the type."""
    lowered = text.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    for convert in (int, float):
        try:
            return convert(text)
        except ValueError:
            continue
    if text[:1] in "[{":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def _apply_override(tree: dict, key: str, value, *, origin: str) -> None:
    if not isinstance(key, str) or not key:
        raise ConfigError(f"override keys must be dotted strings, got {key!r}")
    top = key.split(".")[0]
    if top not in _DEFAULTS:
        message = f"unknown setting {key!r} ({origin})"
        close = difflib.get_close_matches(top, list(_DEFAULTS), n=1)
        if close:
            message += f", did you mean {close[0]!r}?"
        raise ConfigError(message)
    default = get_path(_DEFAULTS, key, _MISSING)
    if isinstance(value, str) and not isinstance(default, str):
        value = _coerce(value, default, key, origin)
    elif isinstance(value, str):
        value = str(value)
    if default is not _MISSING and not _type_ok(value, default):
        raise ConfigError(
            f"{key} must be {_expected(default)}, got {value!r} ({origin})"
        )
    parent = key.rpartition(".")[0]
    if parent and not isinstance(get_path(tree, parent, {}), dict):
        raise ConfigError(f"cannot set {key!r}: {parent!r} is not a table ({origin})")
    set_path(tree, key, copy.deepcopy(value))


def _timezone(name: str) -> dt.tzinfo:
    try:
        return parse_tz(name)
    except ValueError:
        pass
    try:
        import zoneinfo

        return zoneinfo.ZoneInfo(name)
    except Exception:
        # ZoneInfoNotFoundError, or a ValueError for names that look like paths
        raise ValueError(
            f"unknown time zone {name!r}: use a fixed offset such as \"+02:00\" or "
            "an IANA name (those need the tzdata package on Windows)"
        ) from None


def _normalise_base_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "/"
    return url if url.endswith("/") else url + "/"


def _validate(tree: dict, path) -> None:
    """Checks that need the whole merged tree rather than one value's type."""

    def fail(message: str):
        raise ConfigError(message, path=path)

    base_url = tree["base_url"].strip()
    parts = urlsplit(base_url)
    if base_url and not base_url.startswith("/"):
        if parts.scheme not in ("http", "https") or not parts.netloc:
            fail(
                f"base_url must be an http(s) URL or a path starting with '/', "
                f"got {base_url!r}"
            )
    if parts.query or parts.fragment:
        fail(f"base_url cannot have a query or fragment: {base_url!r}")

    try:
        _timezone(tree["timezone"])
    except ValueError as exc:
        fail(f"timezone: {exc}")

    for key in _DIR_KEYS:
        if not tree[key].strip():
            fail(f"{key} cannot be empty")
    if not tree["theme"].strip():
        fail("theme cannot be empty")

    try:
        GlobSet(tree["ignore"])
    except ValueError as exc:
        fail(f"ignore: {exc}")

    if tree["build"]["jobs"] < 0:
        fail(f"build.jobs cannot be negative, got {tree['build']['jobs']}")
    if tree["pagination"]["per_page"] < 1:
        fail(
            f"pagination.per_page must be at least 1, got "
            f"{tree['pagination']['per_page']}"
        )
    segment = tree["pagination"]["path"]
    if not segment or "/" in segment:
        fail(f"pagination.path must be a single URL segment, got {segment!r}")
    if tree["feeds"]["limit"] < 0:
        fail(f"feeds.limit cannot be negative, got {tree['feeds']['limit']}")
    if not 0 <= tree["server"]["port"] <= 65535:
        fail(f"server.port must be between 0 and 65535, got {tree['server']['port']}")
    if tree["sitemap"]["changefreq"] not in _CHANGEFREQS:
        fail(
            f"sitemap.changefreq must be one of {', '.join(_CHANGEFREQS)}; got "
            f"{tree['sitemap']['changefreq']!r}"
        )

    for name, pattern in tree["permalinks"].items():
        _validate_permalink(name, pattern, fail)
    for plural, singular in tree["taxonomies"].items():
        if not isinstance(singular, str) or not singular.strip():
            fail(
                f"taxonomies.{plural} must be the singular name as a string, "
                f"got {singular!r}"
            )
        if not plural.strip() or "/" in plural:
            fail(f"taxonomy name {plural!r} cannot be used as a URL segment")
    for field, weight in tree["search"]["fields"].items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            fail(f"search.fields.{field} must be a number, got {weight!r}")
        if weight < 0:
            fail(f"search.fields.{field} cannot be negative, got {weight!r}")
    for name, entries in tree["menus"].items():
        _validate_menu(f"menus.{name}", entries, fail)
    for name, settings in tree["plugin"].items():
        if not isinstance(settings, Mapping):
            fail(f"plugin.{name} must be a table, got {settings!r}")
    if tree["markdown"]["highlight"]:
        _validate_highlight_style(tree["markdown"]["highlight_style"], fail)


def _validate_permalink(name: str, pattern, fail) -> None:
    key = f"permalinks.{name}"
    if not isinstance(pattern, str):
        fail(f"{key} must be a string, got {pattern!r}")
    if not pattern.startswith("/"):
        fail(f"{key} must start with '/', got {pattern!r}")
    for token in _TOKEN.findall(pattern):
        if token not in PERMALINK_TOKENS:
            message = f"{key}: unknown token ':{token}'"
            close = difflib.get_close_matches(token, PERMALINK_TOKENS, n=1)
            if close:
                message += f", did you mean ':{close[0]}'?"
            else:
                known = " ".join(":" + name for name in PERMALINK_TOKENS)
                message += f" (known: {known})"
            fail(message)


def _validate_menu(key: str, entries, fail) -> None:
    if not isinstance(entries, list):
        fail(f"{key} must be a list of entries ([[{key}]] tables), got {entries!r}")
    for index, entry in enumerate(entries):
        where = f"{key}[{index}]"
        if not isinstance(entry, Mapping):
            fail(f"{where} must be a table with name and url, got {entry!r}")
        for field in ("name", "url"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                fail(f"{where} needs a {field!r} (a non-empty string)")
        weight = entry.get("weight", 0)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            fail(f"{where}.weight must be a number, got {weight!r}")
        if "children" in entry:
            _validate_menu(f"{where}.children", entry["children"], fail)


def _validate_highlight_style(style: str, fail) -> None:
    try:
        from .highlight import list_styles
    except Exception:
        # the highlighter is optional as far as the config is concerned
        return
    known = list(list_styles())
    if style not in known:
        message = f"markdown.highlight_style: unknown style {style!r}"
        close = difflib.get_close_matches(style, known, n=1)
        if close:
            message += f", did you mean {close[0]!r}?"
        else:
            message += f" (available: {', '.join(sorted(known))})"
        fail(message)


def _check_directories(config: Config) -> None:
    """Refuse layouts where cleaning the output would eat the sources."""
    output = config.output_path
    for key, other in (
        ("the site root", config.root),
        ("content_dir", config.content_path),
        ("static_dir", config.static_path),
        ("templates_dir", config.templates_path),
        ("data_dir", config.data_path),
    ):
        if output == other or output in other.parents:
            raise ConfigError(
                f"output_dir ({output}) cannot be {key} or a directory above it: "
                "a clean build would delete the sources",
                path=config.path,
            )
    cache = config.cache_path
    if cache == config.root or cache in config.root.parents:
        raise ConfigError(
            f"cache_dir ({cache}) cannot be the site root or above it",
            path=config.path,
        )


def _apply_theme_params(
    config: Config, user: Mapping, env: Mapping, cli: Mapping
) -> None:
    """Put the theme chain's [params] defaults underneath the site's own."""
    # imported late: the build package imports this module
    from .build.templates import ThemeNotFound, theme_chain

    try:
        themes = theme_chain(config)
    except ThemeNotFound:
        # a missing theme is the builder's problem; `inkstone config` and
        # friends should still be able to show what is configured
        return
    params: dict = {}
    for theme in reversed(themes):
        params = deep_merge(params, theme.params)
    if not params:
        return
    site = user.get("params")
    if isinstance(site, Mapping):
        params = deep_merge(params, site)
    config._data["params"] = params
    # these were applied to the tree before the theme was known; again on top
    for source, origin in ((env, "environment"), (cli, "command line")):
        for key, value in source.items():
            if key == "params" or key.startswith("params."):
                _apply_override(config._data, key, value, origin=origin)
