from __future__ import annotations

import html
import re
import string
from collections.abc import Iterable
from typing import Any

_striptags_re = re.compile(r"<!--.*?-->|<[^>]*>", re.S)


def _escape_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&#34;")
        .replace("'", "&#39;")
    )


def escape(value: Any) -> Markup:
    """HTML-escape `value`, unless it is markup already."""
    if hasattr(value, "__html__"):
        return Markup(value.__html__())
    return Markup(_escape_text(str(value)))


class Markup(str):
    """A string that is safe to put into HTML as it is.

    Combining it with plain strings escapes those, so the result stays safe:
    Markup("<b>") + "<i>" gives Markup("<b>&lt;i&gt;").
    """

    __slots__ = ()

    def __new__(cls, value: Any = "") -> Markup:
        if hasattr(value, "__html__"):
            value = value.__html__()
        return super().__new__(cls, value)

    def __html__(self) -> Markup:
        return self

    def __repr__(self) -> str:
        return f"Markup({super().__repr__()})"

    def __add__(self, other):
        if isinstance(other, str) or hasattr(other, "__html__"):
            return self.__class__(super().__add__(escape(other)))
        return NotImplemented

    def __radd__(self, other):
        if isinstance(other, str) or hasattr(other, "__html__"):
            return escape(other).__add__(self)
        return NotImplemented

    def __mul__(self, count):
        if isinstance(count, int):
            return self.__class__(super().__mul__(count))
        return NotImplemented

    __rmul__ = __mul__

    def __mod__(self, arg):
        if isinstance(arg, tuple):
            arg = tuple(_EscapedArg(item) for item in arg)
        elif hasattr(type(arg), "__getitem__") and not isinstance(arg, str):
            arg = _EscapedArg(arg)
        else:
            arg = (_EscapedArg(arg),)
        return self.__class__(super().__mod__(arg))

    def join(self, items: Iterable[Any]) -> Markup:
        return self.__class__(super().join(escape(item) for item in items))

    def split(self, sep=None, maxsplit=-1) -> list[Markup]:
        return [self.__class__(part) for part in super().split(sep, maxsplit)]

    def rsplit(self, sep=None, maxsplit=-1) -> list[Markup]:
        return [self.__class__(part) for part in super().rsplit(sep, maxsplit)]

    def splitlines(self, keepends=False) -> list[Markup]:
        return [self.__class__(line) for line in super().splitlines(keepends)]

    def partition(self, sep):
        return tuple(self.__class__(part) for part in super().partition(escape(sep)))

    def rpartition(self, sep):
        return tuple(self.__class__(part) for part in super().rpartition(escape(sep)))

    def format(self, *args, **kwargs) -> Markup:
        return self.__class__(_EscapeFormatter().vformat(self, args, kwargs))

    def unescape(self) -> str:
        """The plain text, with entities turned back into characters."""
        return html.unescape(str(self))

    def striptags(self) -> str:
        """Plain text without tags and comments, whitespace collapsed."""
        text = _striptags_re.sub("", str(self))
        return " ".join(html.unescape(text).split())

    @classmethod
    def escape(cls, value: Any) -> Markup:
        rv = escape(value)
        if rv.__class__ is not cls:
            return cls(rv)
        return rv


def _escaping(name: str):
    """Wrap a str method so that it escapes its arguments and returns Markup."""
    method = getattr(str, name)

    def wrapper(self, *args, **kwargs):
        args = tuple(_escape_arg(arg) for arg in args)
        kwargs = {key: _escape_arg(value) for key, value in kwargs.items()}
        return self.__class__(method(self, *args, **kwargs))

    wrapper.__name__ = name
    wrapper.__doc__ = method.__doc__
    return wrapper


def _escape_arg(arg: Any) -> Any:
    if isinstance(arg, str) or hasattr(arg, "__html__"):
        return escape(arg)
    return arg


# FIXME: the fill character of center/ljust/rjust is escaped like any other
# argument, so padding with "&" or "<" ends in a TypeError from str.
for _name in (
    "__getitem__",
    "capitalize",
    "casefold",
    "center",
    "expandtabs",
    "ljust",
    "lower",
    "lstrip",
    "removeprefix",
    "removesuffix",
    "replace",
    "rjust",
    "rstrip",
    "strip",
    "swapcase",
    "title",
    "translate",
    "upper",
    "zfill",
):
    setattr(Markup, _name, _escaping(_name))
del _name


class _EscapedArg:
    """Stands in for an argument of Markup % args and escapes it when used."""

    __slots__ = ("obj",)

    def __init__(self, obj: Any):
        self.obj = obj

    def __getitem__(self, key):
        return _EscapedArg(self.obj[key])

    def __str__(self) -> str:
        return str(escape(self.obj))

    def __repr__(self) -> str:
        return str(escape(repr(self.obj)))

    def __int__(self) -> int:
        return int(self.obj)

    def __float__(self) -> float:
        return float(self.obj)


class _EscapeFormatter(string.Formatter):
    def format_field(self, value, format_spec):
        if hasattr(value, "__html__"):
            if format_spec:
                raise ValueError(
                    f"format specifier {format_spec!r} can't be applied to markup"
                )
            return str(value.__html__())
        return str(escape(super().format_field(value, str(format_spec))))
