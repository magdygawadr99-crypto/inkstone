from __future__ import annotations

import importlib
import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..errors import InkstoneError, PluginError
from ..utils import log
from .base import Plugin, hook_names

BUILTIN_PACKAGE = "inkstone.plugins.builtin"
BUILTIN_NAMES = (
    "shortcodes",
    "toc",
    "reading_time",
    "related",
    "redirects",
    "archives",
    "external_links",
    "image_dims",
    "series",
    "minify",
    "drafts_banner",
    "footnote_previews",
    "git_dates",
)

_SIMPLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_DOTTED_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+\Z")
_LOCAL_MODULE_PREFIX = "_inkstone_site_plugins."


class PluginManager:
    """Loads the configured plugins and calls their hooks."""

    def __init__(self, config):
        self.config = config
        self.plugins: list[Plugin] = []
        self._order: dict[int, int] = {}
        self._by_hook: dict[str, list[Plugin]] = {}

    def __iter__(self) -> Iterator[Plugin]:
        return iter(self.plugins)

    def __len__(self) -> int:
        return len(self.plugins)

    def __contains__(self, name) -> bool:
        return self.get(name) is not None

    def __repr__(self) -> str:
        names = ", ".join(plugin.name for plugin in self.plugins)
        return f"<PluginManager [{names}]>"

    def load(self, names: Iterable[str] | None = None) -> list[Plugin]:
        """Import and instantiate plugins; replaces whatever was loaded before."""
        if names is None:
            names = _lookup(self.config, "plugins") or []
        if isinstance(names, str):
            names = [names]
        self.plugins = []
        self._order = {}
        self._by_hook = {}
        seen: set[str] = set()
        for name in names:
            if not isinstance(name, str) or not name.strip():
                raise PluginError(f"plugin names must be strings, got {name!r}")
            name = name.strip()
            if name in seen:
                log.once("plugin %r is listed twice, loading it once", name)
                continue
            seen.add(name)
            self.add(self._instantiate(name))
        return self.plugins

    def add(self, plugin: Plugin) -> Plugin:
        """Register an already constructed plugin (tests, programmatic use)."""
        if not isinstance(plugin, Plugin):
            raise PluginError(
                f"{plugin!r} is not a plugin: it has to subclass "
                "inkstone.plugins.Plugin"
            )
        self._order[id(plugin)] = len(self._order)
        self.plugins.append(plugin)
        # stable by config order within the same priority
        self.plugins.sort(key=lambda p: (_priority(p), self._order[id(p)]))
        self._by_hook = {}
        return plugin

    def get(self, name: str) -> Plugin | None:
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None

    def implementers(self, hook: str) -> list[Plugin]:
        """The plugins that actually override ``hook``, in calling order."""
        try:
            return self._by_hook[hook]
        except KeyError:
            pass
        if hook not in hook_names:
            raise PluginError(
                f"unknown plugin hook {hook!r} (known: {', '.join(hook_names)})"
            )
        base = getattr(Plugin, hook)
        found = [p for p in self.plugins if getattr(type(p), hook, base) is not base]
        self._by_hook[hook] = found
        return found

    def call(self, hook: str, *args) -> None:
        for plugin in self.implementers(hook):
            self._invoke(plugin, hook, args)

    def pipe(self, hook: str, value, *args):
        """Thread ``value`` through every implementation of ``hook``.

        The value is the hook's *last* argument, as in
        ``page_html(self, page, html)``: ``pipe("page_html", html, page)``.
        """
        for plugin in self.implementers(hook):
            result = self._invoke(plugin, hook, (*args, value))
            if result is None:
                # almost always a forgotten "return"; losing the page over it
                # would be a poor way to point that out
                log.once(
                    "plugin %r: %s() returned None, keeping the text as it was "
                    "(missing return?)",
                    plugin.name,
                    hook,
                )
                continue
            value = result
        return value

    def collect(self, hook: str, *args) -> list:
        out: list = []
        for plugin in self.implementers(hook):
            out.extend(self._invoke(plugin, hook, args, flatten=True))
        return out

    def _invoke(self, plugin: Plugin, hook: str, args: tuple, flatten: bool = False):
        try:
            result = getattr(plugin, hook)(*args)
            if flatten:
                # generators only raise once they are consumed, so do that
                # here where the error can still be pinned on the plugin
                if result is None:
                    return []
                return [result] if _is_single(result) else list(result)
            return result
        except InkstoneError as exc:
            if getattr(exc, "plugin", None) is None:
                exc.plugin = plugin.name
                exc.hook = hook
            raise
        except Exception as exc:
            error = PluginError(
                f"plugin {plugin.name!r} failed in {hook}(): "
                f"{type(exc).__name__}: {exc}",
                path=_source_of(args),
            )
            error.plugin = plugin.name
            error.hook = hook
            raise error from exc

    def _instantiate(self, name: str) -> Plugin:
        module, origin = self._import(name)
        target = _find_plugin(module, name, origin)
        if isinstance(target, Plugin):
            plugin = target
            if not plugin.name:
                plugin.name = name.rpartition(".")[2]
            return plugin
        plugin_name = target.name or name.rpartition(".")[2]
        settings = _lookup(_lookup(self.config, "plugin") or {}, plugin_name) or {}
        if not isinstance(settings, dict):
            raise PluginError(
                f"[plugin.{plugin_name}] has to be a table, got "
                f"{type(settings).__name__}"
            )
        settings = _plain(settings)
        try:
            plugin = target(self.config, settings)
        except InkstoneError:
            raise
        except Exception as exc:
            raise PluginError(
                f"plugin {plugin_name!r} could not be set up: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        if not plugin.name:
            plugin.name = plugin_name
        return plugin

    def _import(self, name: str) -> tuple[Any, str]:
        """Find the module for a configured name: built-in, site-local, dotted."""
        if _SIMPLE_NAME.match(name):
            builtin = f"{BUILTIN_PACKAGE}.{name}"
            if _module_exists(builtin):
                return _import_module(builtin, name), builtin
            local = self._local_path(name)
            if local is not None:
                return _import_file(local, name), str(local)
            if name in BUILTIN_NAMES:
                raise PluginError(
                    f"built-in plugin {name!r} is not available in this "
                    f"installation ({BUILTIN_PACKAGE}.{name} is missing)"
                )
        elif not _DOTTED_NAME.match(name):
            raise PluginError(
                f"{name!r} is not a valid plugin name (use a built-in name, a "
                "file in the plugins directory, or a dotted module path)"
            )
        if _module_exists(name):
            return _import_module(name, name), name
        places = [f"a built-in plugin ({', '.join(BUILTIN_NAMES)})"]
        directory = self._plugins_dir()
        if directory is not None and _SIMPLE_NAME.match(name):
            places.append(f"{directory / (name + '.py')}")
        places.append("an importable module")
        raise PluginError(f"plugin {name!r} not found; looked for " + ", ".join(places))

    def _plugins_dir(self) -> Path | None:
        path = _lookup(self.config, "plugins_path")
        if path is None:
            root = _lookup(self.config, "root")
            if root is None:
                return None
            path = Path(root) / (_lookup(self.config, "plugins_dir") or "plugins")
        return Path(path)

    def _local_path(self, name: str) -> Path | None:
        directory = self._plugins_dir()
        if directory is None:
            return None
        for candidate in (directory / f"{name}.py", directory / name / "__init__.py"):
            if candidate.is_file():
                return candidate
        return None


def _priority(plugin: Plugin) -> int:
    value = getattr(plugin, "priority", 100)
    return value if isinstance(value, (int, float)) else 100


def _lookup(obj, key: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    try:
        return getattr(obj, key)
    except AttributeError:
        pass
    getter = getattr(obj, "get", None)
    return getter(key) if callable(getter) else None


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _is_single(value) -> bool:
    """Did a collecting hook return one item instead of an iterable of them?"""
    if isinstance(value, (str, bytes, dict)):
        return True
    if isinstance(value, tuple) and len(value) == 2:
        # a lone ("robots.txt", "...") from extra_files rather than a list of them
        path, data = value
        return isinstance(path, str) and isinstance(data, (str, bytes))
    return not hasattr(value, "__iter__")


def _source_of(args: tuple):
    """The source file of the page a hook was called for, when it has one."""
    for arg in args[:1]:
        source = getattr(arg, "source_path", None)
        if isinstance(source, str) and source:
            return source
    return None


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        # a missing parent package, or a half-initialised module in sys.modules
        return False


def _import_module(module_name: str, plugin_name: str):
    try:
        return importlib.import_module(module_name)
    except InkstoneError:
        raise
    except Exception as exc:
        raise PluginError(
            f"plugin {plugin_name!r} could not be imported: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _import_file(path: Path, plugin_name: str):
    module_name = _LOCAL_MODULE_PREFIX + plugin_name
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginError(f"cannot load plugin {plugin_name!r}", path=path)
    module = importlib.util.module_from_spec(spec)
    # registered so dataclasses and pickling inside the plugin work, and
    # replaced on every load so an edited plugin is picked up by `serve`
    sys.modules[module_name] = module
    try:
        # Compiled here instead of through the loader: that would go by the
        # .pyc, which is only as fresh as the mtime of the source in whole
        # seconds, and leave a __pycache__ in the site's plugins directory.
        code = compile(path.read_bytes(), str(path), "exec")
        exec(code, module.__dict__)
    except InkstoneError:
        sys.modules.pop(module_name, None)
        raise
    except SyntaxError as exc:
        sys.modules.pop(module_name, None)
        raise PluginError(
            f"syntax error in plugin {plugin_name!r}: {exc.msg}",
            path=path,
            line=exc.lineno,
        ) from exc
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise PluginError(
            f"plugin {plugin_name!r} could not be imported: "
            f"{type(exc).__name__}: {exc}",
            path=path,
        ) from exc
    return module


def _find_plugin(module, name: str, origin: str):
    """The Plugin subclass (or ready instance) a module provides."""
    explicit = getattr(module, "plugin", None)
    if explicit is not None:
        if isinstance(explicit, Plugin):
            return explicit
        if inspect.isclass(explicit) and issubclass(explicit, Plugin):
            return explicit
        raise PluginError(
            f"plugin {name!r}: the module attribute 'plugin' in {origin} has to be "
            f"a Plugin subclass, not {type(explicit).__name__}"
        )
    classes = [
        obj
        for obj in vars(module).values()
        if inspect.isclass(obj)
        and issubclass(obj, Plugin)
        and obj is not Plugin
        and obj.__module__ == module.__name__
    ]
    # a shared base class in the same file does not count as a second plugin
    leaves = [
        cls for cls in classes if not any(cls in o.__mro__[1:] for o in classes)
    ]
    if len(leaves) == 1:
        return leaves[0]
    if not leaves:
        raise PluginError(
            f"plugin {name!r}: no Plugin subclass found in {origin} (define a "
            "class deriving from inkstone.plugins.Plugin)"
        )
    found = ", ".join(sorted(cls.__name__ for cls in leaves))
    raise PluginError(
        f"plugin {name!r}: {origin} defines several plugins ({found}); set a "
        "module attribute 'plugin = TheOne' to pick"
    )
