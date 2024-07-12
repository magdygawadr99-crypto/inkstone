"""Incremental build state, kept as JSON files in the cache directory.

    build.json            keys of everything written, and the dependency graph
    renders/<hash>.json   rendered Markdown per source file, so an unchanged
                          page does not go through the parser again

Nothing in here is precious. A cache that is missing, from another version
or simply broken is treated as empty and the build starts from scratch.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .. import __version__
from ..markdown import TocEntry
from ..tmpl import Markup
from ..utils import log
from ..utils.fs import atomic_write, remove_tree
from ..utils.hashing import hash_text
from .depgraph import DepGraph

# bump when the layout of the files (or the meaning of the keys) changes
CACHE_VERSION = 4
STATE_FILE = "build.json"
RENDER_DIR = "renders"
_TAG = "$type"


class NotCacheable(TypeError):
    """A value that cannot be stored as JSON and read back unchanged."""


def encode(value: Any) -> Any:
    """Turn a value into JSON-safe data that decode() can restore."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Markup):
        return {_TAG: "markup", "value": str(value)}
    if isinstance(value, str):
        return value
    if isinstance(value, TocEntry):
        return {
            _TAG: "toc",
            "level": value.level,
            "id": value.id,
            "title": value.title,
            "children": [encode(child) for child in value.children],
        }
    if isinstance(value, dt.datetime):
        return {_TAG: "datetime", "value": value.isoformat()}
    if isinstance(value, dt.date):
        return {_TAG: "date", "value": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise NotCacheable("only dicts with string keys can be cached")
        items = {key: encode(item) for key, item in value.items()}
        # a real dict that happens to use our marker key gets wrapped
        return {_TAG: "dict", "value": items} if _TAG in value else items
    raise NotCacheable(f"cannot cache a {type(value).__name__}")


def decode(value: Any) -> Any:
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    tag = value.get(_TAG)
    if tag is None:
        return {key: decode(item) for key, item in value.items()}
    if tag == "markup":
        return Markup(value["value"])
    if tag == "toc":
        return TocEntry(
            value["level"],
            value["id"],
            value["title"],
            [decode(child) for child in value["children"]],
        )
    if tag == "datetime":
        return dt.datetime.fromisoformat(value["value"])
    if tag == "date":
        return dt.date.fromisoformat(value["value"])
    if tag == "dict":
        return {key: decode(item) for key, item in value["value"].items()}
    raise ValueError(f"unknown cached type {tag!r}")


class BuildCache:
    def __init__(self, directory):
        self.directory = Path(directory)
        # output path -> {"key": ..., "kind": ..., "assets": {...}}
        self.outputs: dict[str, dict] = {}
        self.graph = DepGraph()
        # what the previous build left on disk, for removing stale files
        self.previous_outputs: set[str] = set()
        # why we started empty, None when a usable cache was found
        self.reset_reason: str | None = "no cache yet"
        self._render_sources: set[str] = set()

    def __repr__(self) -> str:
        return f"<BuildCache {self.directory} ({len(self.outputs)} outputs)>"

    @property
    def state_path(self) -> Path:
        return self.directory / STATE_FILE

    @property
    def render_dir(self) -> Path:
        return self.directory / RENDER_DIR

    @classmethod
    def load(cls, directory) -> BuildCache:
        cache = cls(directory)
        try:
            raw = cache.state_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cache
        except (OSError, UnicodeDecodeError) as exc:
            cache.reset_reason = f"unreadable cache ({exc})"
            return cache
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            if data.get("version") != CACHE_VERSION:
                cache.reset_reason = "cache format changed"
                # the list of files is still worth having: they are ours to
                # clean up even if nothing else can be trusted
                cache.previous_outputs = _output_names(data.get("outputs"))
                return cache
            outputs = data["outputs"]
            if not isinstance(outputs, dict):
                raise ValueError("outputs is not a mapping")
            for path, entry in outputs.items():
                if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
                    raise ValueError(f"bad entry for {path!r}")
            graph = DepGraph.from_dict(data.get("deps", {}))
        except (ValueError, KeyError, TypeError) as exc:
            log.verbose("ignoring a damaged build cache: %s", exc)
            cache.reset_reason = "damaged cache"
            return cache
        cache.outputs = outputs
        cache.graph = graph
        cache.previous_outputs = set(outputs)
        cache.reset_reason = None
        if data.get("inkstone") != __version__:
            # keys contain the version too; this is only for the log message
            cache.reset_reason = "inkstone was upgraded"
            cache.outputs = {}
            cache.graph = DepGraph()
        return cache

    def save(self) -> None:
        data = {
            "version": CACHE_VERSION,
            "inkstone": __version__,
            "outputs": {path: self.outputs[path] for path in sorted(self.outputs)},
            "deps": self.graph.to_dict(),
        }
        text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True)
        atomic_write(self.state_path, text + "\n")
        self.previous_outputs = set(self.outputs)

    def clear(self) -> None:
        """Forget everything except which files we are responsible for."""
        self.outputs = {}
        self.graph = DepGraph()

    def destroy(self) -> None:
        remove_tree(self.directory)
        self.outputs = {}
        self.graph = DepGraph()
        self.previous_outputs = set()

    def key_of(self, output: str) -> str | None:
        entry = self.outputs.get(output)
        return entry["key"] if entry else None

    def entry(self, output: str) -> dict | None:
        return self.outputs.get(output)

    def is_fresh(self, output: str, key: str) -> bool:
        return self.key_of(output) == key

    def record(
        self,
        output: str,
        key: str,
        *,
        kind: str = "page",
        deps: Iterable[str] = (),
        assets: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {"key": key, "kind": kind}
        if assets:
            entry["assets"] = assets
        self.outputs[output] = entry
        self.graph.set(f"output:{output}", deps)

    def forget(self, output: str) -> None:
        self.outputs.pop(output, None)
        self.graph.discard(f"output:{output}")

    def retain(self, outputs: Iterable[str]) -> None:
        """Drop the records of everything that is not in ``outputs``."""
        keep = set(outputs)
        for path in [path for path in self.outputs if path not in keep]:
            self.forget(path)

    def _render_path(self, source: str) -> Path:
        return self.render_dir / f"{hash_text(source)}.json"

    def get_render(self, source: str, key: str) -> dict | None:
        """The stored render of a source file, if it was made from ``key``."""
        try:
            data = json.loads(self._render_path(source).read_text(encoding="utf-8"))
            if data["key"] != key or data["source"] != source:
                return None
            fields = decode(data["fields"])
            if not isinstance(fields, dict):
                return None
        except (OSError, ValueError, KeyError, TypeError):
            # missing, half-written or from some other format: render again
            return None
        self._render_sources.add(source)
        return fields

    def put_render(self, source: str, key: str, fields: dict) -> bool:
        """Store a render; False (and nothing stored) if it cannot be cached."""
        path = self._render_path(source)
        try:
            data = {"source": source, "key": key, "fields": encode(fields)}
            text = json.dumps(data, ensure_ascii=False)
        except (NotCacheable, TypeError, ValueError):
            with contextlib.suppress(OSError):
                path.unlink()
            return False
        atomic_write(path, text)
        self._render_sources.add(source)
        return True

    def prune_renders(self) -> int:
        """Delete stored renders of sources this build never asked about."""
        keep = {self._render_path(source).name for source in self._render_sources}
        removed = 0
        try:
            names = os.listdir(self.render_dir)
        except OSError:
            return 0
        for name in names:
            if name not in keep:
                with contextlib.suppress(OSError):
                    os.unlink(self.render_dir / name)
                    removed += 1
        self._render_sources = set()
        return removed


def _output_names(outputs) -> set[str]:
    if isinstance(outputs, dict):
        return {path for path in outputs if isinstance(path, str)}
    if isinstance(outputs, list):
        return {path for path in outputs if isinstance(path, str)}
    return set()
