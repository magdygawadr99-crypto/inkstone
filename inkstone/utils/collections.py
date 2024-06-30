from __future__ import annotations

from collections.abc import Hashable, Mapping, MutableSet
from typing import Any, Callable, Iterable, Iterator

_MISSING = object()


def chunked(iterable: Iterable, size: int) -> Iterator[list]:
    """Yield successive lists of ``size`` items; the last may be shorter."""
    if size < 1:
        raise ValueError("chunk size must be at least 1")
    chunk: list = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def unique(iterable: Iterable, key: Callable | None = None) -> list:
    """Drop duplicates, keeping the first occurrence and the order."""
    seen: set = set()
    seen_unhashable: list = []
    out = []
    for item in iterable:
        marker = item if key is None else key(item)
        if isinstance(marker, Hashable):
            if marker in seen:
                continue
            seen.add(marker)
        else:
            # lists and dicts cannot go in a set; fall back to a slow scan
            if marker in seen_unhashable:
                continue
            seen_unhashable.append(marker)
        out.append(item)
    return out


def group_by(iterable: Iterable, key: Callable | str) -> dict[Any, list]:
    """Group items into a dict of lists, in order of first appearance.

    ``key`` is a function, or a dotted path looked up with get_path().
    """
    if isinstance(key, str):
        path = key

        def key(item):
            return get_path(item, path)

    groups: dict[Any, list] = {}
    for item in iterable:
        groups.setdefault(key(item), []).append(item)
    return groups


def deep_merge(base: Mapping, override: Mapping, *, lists: str = "replace") -> dict:
    """Merge two nested dicts into a new one; ``override`` wins.

    Dicts are merged key by key, everything else is replaced. ``lists`` can
    be "replace" (default), "append" or "unique" to control what happens
    when both sides hold a list. Neither input is modified.
    """
    if lists not in ("replace", "append", "unique"):
        raise ValueError(f"unknown list strategy: {lists!r}")
    merged = {key: _copy(value) for key, value in base.items()}
    for key, value in override.items():
        current = merged.get(key)
        both_lists = isinstance(current, list) and isinstance(value, list)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value, lists=lists)
        elif both_lists and lists != "replace":
            combined = current + _copy(value)
            merged[key] = unique(combined) if lists == "unique" else combined
        else:
            merged[key] = _copy(value)
    return merged


def _copy(value):
    """Copy the containers, share the leaves."""
    if isinstance(value, Mapping):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy(item) for item in value]
    return value


def _step(container, part: str):
    if isinstance(container, Mapping):
        return container.get(part, _MISSING)
    if isinstance(container, (list, tuple)):
        try:
            return container[int(part)]
        except (ValueError, IndexError):
            return _MISSING
    return getattr(container, part, _MISSING)


def get_path(obj, path: str, default=None, *, sep: str = "."):
    """Look up ``"a.b.0.c"`` in nested dicts, lists and objects.

    Returns ``default`` as soon as a step is missing.
    """
    current = obj
    for part in path.split(sep):
        current = _step(current, part)
        if current is _MISSING:
            return default
    return current


def set_path(obj, path: str, value, *, sep: str = ".") -> None:
    """Set ``"a.b.c"`` in nested dicts, creating the ones in between.

    Existing lists can be indexed along the way, but are not grown.
    """
    parts = path.split(sep)
    current = obj
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
            continue
        child = current.get(part)
        if not isinstance(child, (dict, list)):
            child = current[part] = {}
        current = child
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value


def flatten(iterable: Iterable, *, depth: int | None = None) -> list:
    """Flatten nested lists and tuples; ``depth`` limits how far down."""
    out = []
    for item in iterable:
        if isinstance(item, (list, tuple)) and (depth is None or depth > 0):
            out.extend(flatten(item, depth=None if depth is None else depth - 1))
        else:
            out.append(item)
    return out


class AttrDict(dict):
    """A dict whose keys can also be read and written as attributes.

    Nested dicts (also inside lists) are wrapped on the way in, so
    ``site.author.name`` works at any depth. Keys that clash with dict
    methods ("items", "keys", ...) are only reachable with ``[]``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.update(*args, **kwargs)

    @classmethod
    def _wrap(cls, value):
        if isinstance(value, dict) and not isinstance(value, AttrDict):
            return cls(value)
        if isinstance(value, list):
            return [cls._wrap(item) for item in value]
        return value

    def __setitem__(self, key, value) -> None:
        super().__setitem__(key, self._wrap(value))

    def update(self, *args, **kwargs) -> None:
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name) from None

    def copy(self) -> AttrDict:
        return type(self)(self)

    def to_dict(self) -> dict:
        """Plain dicts all the way down again."""
        return _unwrap(self)


def _unwrap(value):
    if isinstance(value, dict):
        return {key: _unwrap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unwrap(item) for item in value]
    return value


class OrderedSet(MutableSet):
    """A set that remembers insertion order."""

    def __init__(self, items: Iterable = ()):
        self._items: dict = dict.fromkeys(items)

    def __contains__(self, item) -> bool:
        return item in self._items

    def __iter__(self) -> Iterator:
        return iter(self._items)

    def __reversed__(self) -> Iterator:
        return reversed(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int):
        # O(n), but handy for "first"/"last" and nobody indexes these in a loop
        return list(self._items)[index]

    def add(self, item) -> None:
        self._items[item] = None

    def discard(self, item) -> None:
        self._items.pop(item, None)

    def update(self, items: Iterable) -> None:
        for item in items:
            self._items[item] = None

    def __and__(self, other):
        # the inherited version walks ``other``, which loses our ordering
        if not isinstance(other, Iterable):
            return NotImplemented
        keep = set(other)
        return type(self)(item for item in self if item in keep)

    def __eq__(self, other) -> bool:
        # order matters between two OrderedSets, not against a plain set
        if isinstance(other, OrderedSet):
            return list(self._items) == list(other._items)
        return super().__eq__(other)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._items)!r})"
