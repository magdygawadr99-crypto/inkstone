from __future__ import annotations

import difflib
import json

from .. import tomlw
from ..config import default_config
from ..errors import ConfigError

_MISSING = object()


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "config",
        parents=[shared],
        help="show the configuration",
        description=(
            "Print the configuration the site ends up with: defaults, the "
            "config file, INKSTONE_* variables. With KEY, only that value."
        ),
    )
    parser.add_argument(
        "key", nargs="?", metavar="KEY", help="a setting, dotted: build.minify"
    )
    parser.add_argument(
        "--json", action="store_true", help="print JSON instead of TOML"
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="show the built-in defaults instead of this site's values",
    )
    parser.set_defaults(run=run)


def dotted_keys(tree: dict, prefix: str = "") -> list[str]:
    keys = []
    for name, value in tree.items():
        keys.append(prefix + name)
        if isinstance(value, dict):
            keys += dotted_keys(value, f"{prefix}{name}.")
    return keys


def pick(tree: dict, key: str):
    """The value at a dotted key; ConfigError with a suggestion if absent."""
    value = tree
    for part in key.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            # menus.main.0.url
            value = value[int(part)]
        else:
            value = _MISSING
            break
    if value is _MISSING:
        message = f"no setting called {key!r}"
        close = difflib.get_close_matches(key, dotted_keys(tree), n=1)
        if close:
            message += f", did you mean {close[0]!r}?"
        raise ConfigError(message)
    return value


def as_json(value) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def as_toml(value) -> str:
    """A whole tree as a TOML document; a single value the way a shell wants it."""
    if isinstance(value, dict):
        return tomlw.dumps(value).rstrip("\n")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            # an array of tables has no inline spelling worth reading
            return as_json(value)
        return json.dumps(value, ensure_ascii=False, default=str)
    return "" if value is None else str(value)


def run(app, args) -> int:
    tree = default_config() if args.defaults else app.config().to_dict()
    value = pick(tree, args.key) if args.key else tree
    app.out(as_json(value) if args.json else as_toml(value))
    return 0
