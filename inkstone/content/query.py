from __future__ import annotations

import datetime as dt
import operator
from typing import Any, Callable, Iterable

from ..utils.collections import get_path
from ..utils.text import natural_sort_key, slugify

_MISSING = object()

_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "eq": operator.eq,
    "!=": operator.ne,
    "ne": operator.ne,
    "<": operator.lt,
    "lt": operator.lt,
    "<=": operator.le,
    "le": operator.le,
    ">": operator.gt,
    "gt": operator.gt,
    ">=": operator.ge,
    "ge": operator.ge,
    "in": lambda a, b: a in b,
    "not in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
    "startswith": lambda a, b: str(a).startswith(b),
    "endswith": lambda a, b: str(a).endswith(b),
}


def _lookup(item, key):
    if callable(key):
        return key(item)
    return get_path(item, key, None)


def _order_key(value):
    """Make values of mixed types sortable; None always goes last."""
    if value is None:
        return (2, 0)
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return (0, value.timestamp())
    if isinstance(value, dt.date):
        return (0, dt.datetime(value.year, value.month, value.day).timestamp())
    return (1, natural_sort_key(str(value)))


class PageList(list):
    """A list of pages with a few chainable query helpers.

        site.pages.where("section.name", "posts").sort_by("date").limit(5)

    Every helper returns a new PageList and leaves this one alone. It is a
    real list, so len(), indexing, slicing and the template filters all work.
    """

    def __getitem__(self, index):
        result = super().__getitem__(index)
        if isinstance(index, slice):
            return type(self)(result)
        return result

    def __add__(self, other):
        return type(self)(list(self) + list(other))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list.__repr__(self)})"

    def copy(self) -> PageList:
        return type(self)(self)

    def where(self, key=None, *args, **equals) -> PageList:
        """Keep the items where a (dotted) attribute matches.

        ``where("draft")`` tests truthiness, ``where("kind", "page")``
        equality, ``where("weight", ">", 3)`` uses an operator, and keyword
        arguments are shorthand for equality: ``where(draft=False)``.
        """
        items: Iterable = self
        if key is not None:
            if len(args) > 2:
                raise TypeError("where() takes a key, an optional operator and a value")
            if not args:
                items = [item for item in items if _lookup(item, key)]
            else:
                op_name, value = ("==", args[0]) if len(args) == 1 else args
                items = [item for item in items if _test(item, key, op_name, value)]
        for name, value in equals.items():
            items = [item for item in items if _lookup(item, name) == value]
        return type(self)(items)

    def exclude(self, key, *args) -> PageList:
        """The opposite of where(): drop the items that match."""
        dropped = {id(item) for item in self.where(key, *args)}
        return type(self)(item for item in self if id(item) not in dropped)

    def filter(self, predicate: Callable[[Any], bool]) -> PageList:
        return type(self)(item for item in self if predicate(item))

    def sort_by(self, key, reverse: bool = False) -> PageList:
        """Sort by a dotted attribute or a function; a leading "-" reverses.

        Items without a value go last whichever way the rest is sorted.
        """
        if isinstance(key, str) and key.startswith("-"):
            key, reverse = key[1:], not reverse
        have, lack = [], []
        for item in self:
            (lack if _lookup(item, key) is None else have).append(item)
        have.sort(key=lambda item: _order_key(_lookup(item, key)), reverse=reverse)
        return type(self)(have + lack)

    def reversed(self) -> PageList:
        return type(self)(self[::-1])

    def limit(self, count: int) -> PageList:
        return type(self)(self[: max(int(count), 0)])

    def offset(self, count: int) -> PageList:
        return type(self)(self[max(int(count), 0) :])

    def first(self, default=None):
        return self[0] if self else default

    def last(self, default=None):
        return self[-1] if self else default

    def unique(self) -> PageList:
        seen: set[int] = set()
        out = []
        for item in self:
            if id(item) not in seen:
                seen.add(id(item))
                out.append(item)
        return type(self)(out)

    def pluck(self, key) -> list:
        """The values of one attribute: ``pages.pluck("title")``."""
        return [_lookup(item, key) for item in self]

    def group_by(self, key) -> list[tuple[Any, PageList]]:
        """(value, pages) pairs in order of first appearance."""
        groups: dict[Any, PageList] = {}
        for item in self:
            value = _lookup(item, key)
            try:
                bucket = groups.setdefault(value, type(self)())
            except TypeError:
                # lists and dicts cannot be dict keys
                bucket = groups.setdefault(repr(value), type(self)())
            bucket.append(item)
        return list(groups.items())

    def group_by_year(self) -> list[tuple[int, PageList]]:
        """Dated pages grouped by year, newest year first."""
        return self._group_by_date(lambda date: date.year)

    def group_by_month(self) -> list[tuple[tuple[int, int], PageList]]:
        """Dated pages grouped by (year, month), newest first."""
        return self._group_by_date(lambda date: (date.year, date.month))

    def _group_by_date(self, bucket_of) -> list:
        groups: dict[Any, PageList] = {}
        for item in self.dated().sort_by("date", reverse=True):
            groups.setdefault(bucket_of(item.date), type(self)()).append(item)
        return sorted(groups.items(), key=lambda pair: pair[0], reverse=True)

    def dated(self) -> PageList:
        return type(self)(
            item for item in self if getattr(item, "date", None) is not None
        )

    def tagged(self, term: str, taxonomy: str = "tags") -> PageList:
        """Pages carrying a term; spelling and case are compared as slugs."""
        wanted = slugify(term) or term

        def has_term(item) -> bool:
            names = (getattr(item, "taxonomies", None) or {}).get(taxonomy, ())
            return any((slugify(name) or name) == wanted for name in names)

        return type(self)(item for item in self if has_term(item))

    def in_section(self, name: str, nested: bool = True) -> PageList:
        """Pages of a section; with ``nested`` also those of its subsections."""

        def belongs(item) -> bool:
            section = getattr(item, "section", None)
            while section is not None:
                if section.name == name:
                    return True
                if not nested:
                    return False
                section = section.parent
            return False

        return type(self)(item for item in self if belongs(item))

    def published(self) -> PageList:
        return type(self)(item for item in self if not getattr(item, "draft", False))

    def drafts(self) -> PageList:
        return type(self)(item for item in self if getattr(item, "draft", False))


def _test(item, key, op_name: str, value) -> bool:
    try:
        compare = _OPERATORS[op_name]
    except (KeyError, TypeError):
        known = ", ".join(sorted(_OPERATORS))
        raise ValueError(f"unknown operator {op_name!r} (known: {known})") from None
    actual = _lookup(item, key)
    try:
        return bool(compare(actual, value))
    except TypeError:
        # None < 3, a str against a date...: no match rather than a crash
        return False
