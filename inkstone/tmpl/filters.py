from __future__ import annotations

import dataclasses
import datetime
import decimal
import itertools
import json
import math
import os
import pprint
import re
import textwrap
import urllib.parse
from collections.abc import Iterable, Mapping
from pathlib import PurePath
from typing import Any, Callable, NamedTuple

from .errors import TemplateRuntimeError
from .markup import Markup, escape
from .runtime import Undefined, pass_context, pass_environment, type_name

_word_re = re.compile(r"\w+")
_word_start_re = re.compile(r"([-\s({\[<]+)")
_bad_attr_name_re = re.compile(r"[\s/>=\"']")
_url_re = re.compile(
    r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)"
)
_strftime_flag_re = re.compile(r"%[-#]([a-zA-Z])")

# "%-d" (no zero padding) is spelled "%#d" by the Windows C runtime
_NO_PAD_FLAG = "#" if os.name == "nt" else "-"


def _text(value: Any) -> str:
    """str() that leaves Markup alone and turns none into nothing."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _ignore_case(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _is_missing(value: Any) -> bool:
    """True for an Undefined. The strict kind raises as soon as it is asked."""
    return isinstance(value, Undefined) and not value


def _attrgetter(env, attribute, postprocess=None, default=None) -> Callable:
    """A function that digs `attribute` out of an item.

    The attribute can be dotted ("author.name") and numeric parts are list
    indexes ("0.title"); None gives the item itself.
    """
    if attribute is None:
        parts = []
    elif isinstance(attribute, int):
        parts = [attribute]
    else:
        parts = [int(p) if p.isdigit() else p for p in str(attribute).split(".")]

    def getter(item):
        for part in parts:
            item = env.getitem(item, part)
            if default is not None and isinstance(item, Undefined):
                item = default
        if postprocess is not None:
            item = postprocess(item)
        return item

    return getter


def _sort_key(env, attribute, case_sensitive: bool) -> Callable:
    postprocess = None if case_sensitive else _ignore_case
    if isinstance(attribute, str) and "," in attribute:
        # "lastname,firstname" sorts by several attributes at once
        getters = [
            _attrgetter(env, part.strip(), postprocess)
            for part in attribute.split(",")
        ]
        return lambda item: [getter(item) for getter in getters]
    return _attrgetter(env, attribute, postprocess)


def do_upper(value):
    return _text(value).upper()


def do_lower(value):
    return _text(value).lower()


def do_capitalize(value):
    return _text(value).capitalize()


def do_title(value):
    # str.title() makes "They'Re" out of "they're", so only start a new word
    # after whitespace, a hyphen or an opening bracket
    parts = _word_start_re.split(_text(value))
    return "".join(part[0].upper() + part[1:].lower() for part in parts if part)


def do_trim(value, chars=None):
    return _text(value).strip(chars)


def do_center(value, width=80):
    return _text(value).center(width)


def do_string(value):
    return _text(value)


def do_default(value, default_value="", boolean=False):
    """`default_value` if the value is undefined, or falsy with boolean=True."""
    if isinstance(value, Undefined) or (boolean and not value):
        return default_value
    return value


def do_escape(value):
    return escape("" if value is None else value)


def do_forceescape(value):
    """Escape even what is marked safe already."""
    return escape(str(_text(value)))


def do_safe(value):
    return Markup(_text(value))


def do_striptags(value):
    return Markup(_text(value)).striptags()


@pass_context
def do_replace(ctx, value, old, new, count=None):
    if count is None:
        count = -1
    text = _text(value)
    if ctx.autoescape and not isinstance(text, Markup):
        if hasattr(old, "__html__") or hasattr(new, "__html__"):
            # putting markup into plain text: escape the text first, or the
            # result would be half escaped
            text = escape(text)
    return text.replace(_text(old), _text(new), count)


def do_truncate(value, length=255, killwords=False, end="...", leeway=5):
    """Cut text down to `length` characters, `end` included.

    Text that is over by `leeway` characters at most is left alone, cutting
    a word or two off a sentence just looks silly. Without `killwords` a word
    that would be cut in half is dropped completely.
    """
    text = _text(value)
    if length < len(end):
        raise TemplateRuntimeError(
            f"truncate: a length of {length} leaves no room for {end!r}"
        )
    if len(text) <= length + leeway:
        return text
    kept = text[: length - len(end)]
    if not killwords and not text[len(kept)].isspace():
        kept = kept.rsplit(" ", 1)[0]
    return kept.rstrip() + end


def do_wordcount(value):
    return len(_word_re.findall(_text(value)))


def do_wordwrap(
    value, width=79, break_long_words=True, wrapstring="\n", break_on_hyphens=True
):
    # line by line, textwrap would swallow the empty lines between paragraphs
    lines = []
    for line in _text(value).splitlines():
        wrapped = textwrap.wrap(
            line,
            width=width,
            expand_tabs=False,
            replace_whitespace=False,
            break_long_words=break_long_words,
            break_on_hyphens=break_on_hyphens,
        )
        lines.append(wrapstring.join(wrapped))
    return wrapstring.join(lines)


def do_indent(value, width=4, first=False, blank=False):
    """Indent all lines but the first, and no blank ones, unless asked to.

    `width` can also be the string to indent with.
    """
    text = _text(value)
    indention = width if isinstance(width, str) else " " * width
    newline = "\n"
    if isinstance(text, Markup):
        indention = Markup(indention)
        newline = Markup(newline)
    # the extra newline keeps splitlines() from dropping a trailing empty line
    lines = (text + newline).splitlines()
    if blank:
        result = (newline + indention).join(lines)
    else:
        result = lines.pop(0)
        if lines:
            rest = (indention + line if line else line for line in lines)
            result += newline + newline.join(rest)
    if first:
        result = indention + result
    return result


def do_format(value, *args, **kwargs):
    """printf-style formatting: "%s has %d items" | format(name, count)."""
    if args and kwargs:
        raise TemplateRuntimeError(
            "format: pass positional or keyword arguments, not both"
        )
    return _text(value) % (kwargs or args)


def _quote(value, for_query: bool = False) -> str:
    quoted = urllib.parse.quote(str(_text(value)), safe="" if for_query else "/")
    return quoted.replace("%20", "+") if for_query else quoted


def do_urlencode(value):
    """Percent-encode a string, or turn a dict or pairs into a query string."""
    if isinstance(value, str) or not isinstance(value, Iterable):
        return _quote(value)
    pairs = value.items() if isinstance(value, Mapping) else value
    return "&".join(
        f"{_quote(key, True)}={_quote(item, True)}" for key, item in pairs
    )


def _split_trailing(url: str) -> tuple[str, str]:
    """Punctuation after a URL belongs to the sentence, not to the link."""
    end = len(url)
    while end > 1:
        char = url[end - 1]
        if char in ".,;:!?":
            end -= 1
        elif char == ")" and url.count(")", 0, end) > url.count("(", 0, end):
            # a closing bracket stays if the URL opened it, as in
            # https://en.wikipedia.org/wiki/Ink_(disambiguation)
            end -= 1
        else:
            break
    return url[:end], url[end:]


@pass_context
def do_urlize(ctx, value, trim_url_limit=None, nofollow=False, target=None, rel=None):
    """Turn URLs and e-mail addresses in plain text into links."""
    rel_values = set((rel or "").split())
    if nofollow:
        rel_values.add("nofollow")
    attrs = ""
    if rel_values:
        attrs += f' rel="{escape(" ".join(sorted(rel_values)))}"'
    if target:
        attrs += f' target="{escape(target)}"'
    # text that is markup already must not be escaped a second time
    quote = str if hasattr(value, "__html__") else escape

    out = []
    for index, piece in enumerate(_url_re.split(str(_text(value)))):
        if index % 2 == 0:
            out.append(str(quote(piece)))
            continue
        piece, trail = _split_trailing(piece)
        if piece.startswith("www."):
            href = "https://" + piece
        elif "@" in piece and "://" not in piece:
            href = "mailto:" + piece
        else:
            href = piece
        label = piece
        if trim_url_limit is not None and len(label) > trim_url_limit:
            label = label[:trim_url_limit] + "..."
        out.append(f'<a href="{quote(href)}"{attrs}>{quote(label)}</a>{quote(trail)}')
    result = "".join(out)
    return Markup(result) if ctx.autoescape else result


def do_length(value):
    try:
        return len(value)
    except TypeError:
        # generators and the like
        return sum(1 for _ in value)


@pass_environment
def do_first(env, value):
    try:
        return next(iter(value))
    except StopIteration:
        return env.undefined(hint="first: the sequence is empty")


@pass_environment
def do_last(env, value):
    try:
        return next(iter(reversed(value)))
    except StopIteration:
        pass
    except TypeError:
        items = list(value)
        if items:
            return items[-1]
    return env.undefined(hint="last: the sequence is empty")


def do_reverse(value):
    if isinstance(value, str):
        return value[::-1]
    try:
        return list(reversed(value))
    except TypeError:
        items = list(value)
        items.reverse()
        return items


def do_list(value):
    return list(value)


@pass_context
def do_join(ctx, value, d="", attribute=None):
    if attribute is not None:
        value = map(_attrgetter(ctx.env, attribute), value)
    items = [item if hasattr(item, "__html__") else _text(item) for item in value]
    if ctx.autoescape:
        if hasattr(d, "__html__") or any(hasattr(i, "__html__") for i in items):
            # one piece of markup makes the result markup, and Markup.join
            # escapes whatever is not
            return escape(d).join(items)
    return str(_text(d)).join(items)


@pass_environment
def do_sort(env, value, reverse=False, case_sensitive=False, attribute=None):
    return sorted(value, key=_sort_key(env, attribute, case_sensitive), reverse=reverse)


@pass_environment
def do_unique(env, value, case_sensitive=False, attribute=None):
    """Drop duplicates, keeping the first of each and the original order."""
    getter = _attrgetter(env, attribute, None if case_sensitive else _ignore_case)
    seen = set()
    unhashable = []
    result = []
    for item in value:
        key = getter(item)
        try:
            if key in seen:
                continue
            seen.add(key)
        except TypeError:
            if key in unhashable:
                continue
            unhashable.append(key)
        result.append(item)
    return result


class _Group(NamedTuple):
    grouper: Any
    list: list


@pass_environment
def do_groupby(env, value, attribute, default=None, case_sensitive=False):
    """Group items by an attribute; gives (grouper, list) pairs, sorted."""
    postprocess = None if case_sensitive else _ignore_case
    key = _attrgetter(env, attribute, postprocess, default)
    as_written = _attrgetter(env, attribute, default=default)
    groups = []
    for _, members in itertools.groupby(sorted(value, key=key), key):
        members = list(members)
        # "Python" and "python" end up in one group, labelled like the first
        groups.append(_Group(as_written(members[0]), members))
    return groups


def do_batch(value, linecount, fill_with=None):
    """Rows of `linecount` items, the last one padded with `fill_with`."""
    if linecount < 1:
        raise TemplateRuntimeError("batch: a row needs at least one item")
    rows = []
    row: list = []
    for item in value:
        if len(row) == linecount:
            rows.append(row)
            row = []
        row.append(item)
    if row:
        if fill_with is not None:
            row.extend([fill_with] * (linecount - len(row)))
        rows.append(row)
    return rows


def do_slice(value, slices, fill_with=None):
    """Split into `slices` columns of (nearly) equal length."""
    if slices < 1:
        raise TemplateRuntimeError("slice: there has to be at least one column")
    items = list(value)
    per_slice, with_extra = divmod(len(items), slices)
    columns = []
    offset = 0
    for number in range(slices):
        start = offset + number * per_slice
        if number < with_extra:
            offset += 1
        end = offset + (number + 1) * per_slice
        column = items[start:end]
        if fill_with is not None and with_extra and number >= with_extra:
            column.append(fill_with)
        columns.append(column)
    return columns


@pass_environment
def do_sum(env, value, attribute=None, start=0):
    if attribute is not None:
        value = map(_attrgetter(env, attribute), value)
    return sum(value, start)


def _extreme(env, value, pick, case_sensitive, attribute):
    items = list(value)
    if not items:
        return env.undefined(hint=f"{pick.__name__}: the sequence is empty")
    key = _attrgetter(env, attribute, None if case_sensitive else _ignore_case)
    return pick(items, key=key)


@pass_environment
def do_min(env, value, case_sensitive=False, attribute=None):
    return _extreme(env, value, min, case_sensitive, attribute)


@pass_environment
def do_max(env, value, case_sensitive=False, attribute=None):
    return _extreme(env, value, max, case_sensitive, attribute)


@pass_context
def do_map(ctx, value, *args, **kwargs):
    """Apply a filter to every item, or pull out an attribute.

    users | map("upper"), users | map(attribute="name", default="?")
    """
    env = ctx.env
    if not args and "attribute" in kwargs:
        attribute = kwargs.pop("attribute")
        default = kwargs.pop("default", None)
        if kwargs:
            unexpected = next(iter(kwargs))
            raise TemplateRuntimeError(f"map: unexpected argument {unexpected!r}")
        func = _attrgetter(env, attribute, default=default)
    elif args:
        name, rest = args[0], args[1:]

        def func(item):
            return env.call_filter(name, item, rest, kwargs, ctx)

    else:
        raise TemplateRuntimeError("map: needs a filter name or attribute=...")
    return [func(item) for item in value]


def _selector(ctx, name: str, args: tuple, kwargs: dict, by_attribute: bool):
    """The yes/no function behind select, reject, selectattr and rejectattr."""
    env = ctx.env
    pick = None
    if by_attribute:
        if not args:
            raise TemplateRuntimeError(f"{name}: needs the name of an attribute")
        pick = _attrgetter(env, args[0])
        args = args[1:]
    if args:
        test, rest = args[0], args[1:]

        def check(item):
            return env.call_test(test, item, rest, kwargs, ctx)

    else:
        check = bool
    if pick is None:
        return check
    return lambda item: check(pick(item))


@pass_context
def do_select(ctx, value, *args, **kwargs):
    keep = _selector(ctx, "select", args, kwargs, False)
    return [item for item in value if keep(item)]


@pass_context
def do_reject(ctx, value, *args, **kwargs):
    drop = _selector(ctx, "reject", args, kwargs, False)
    return [item for item in value if not drop(item)]


@pass_context
def do_selectattr(ctx, value, *args, **kwargs):
    keep = _selector(ctx, "selectattr", args, kwargs, True)
    return [item for item in value if keep(item)]


@pass_context
def do_rejectattr(ctx, value, *args, **kwargs):
    drop = _selector(ctx, "rejectattr", args, kwargs, True)
    return [item for item in value if not drop(item)]


def do_abs(value):
    return abs(value)


def do_int(value, default=0, base=10):
    try:
        if isinstance(value, str):
            return int(value, base)
        return int(value)
    except (TypeError, ValueError):
        # "42.7" and the like
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return default


def do_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def do_round(value, precision=0, method="common"):
    """Round to `precision` digits; method is "common", "ceil" or "floor"."""
    if method not in ("common", "ceil", "floor"):
        raise TemplateRuntimeError(
            'round: the method has to be "common", "ceil" or "floor"'
        )
    number = float(value)
    if not math.isfinite(number):
        return number
    if method == "common":
        # round() rounds halves to even and works on the binary value, so
        # 2.5 becomes 2 and 2.675 becomes 2.67. Nobody wants that for prices.
        exponent = decimal.Decimal(1).scaleb(-precision)
        rounded = decimal.Decimal(repr(number)).quantize(
            exponent, rounding=decimal.ROUND_HALF_UP
        )
        return float(rounded)
    factor = 10**precision
    func = math.ceil if method == "ceil" else math.floor
    return func(number * factor) / factor


def do_filesizeformat(value, binary=False):
    """13 kB, 4.1 MB and so on; binary=True gives KiB, MiB..."""
    size = float(value)
    base = 1024 if binary else 1000
    if size == 1:
        return "1 Byte"
    if size < base:
        return f"{int(size)} Bytes"
    prefixes = "KMGTPEZY" if binary else "kMGTPEZY"
    suffix = "iB" if binary else "B"
    for exponent, prefix in enumerate(prefixes, 2):
        unit = base**exponent
        if size < unit:
            break
    return f"{base * size / unit:.1f} {prefix}{suffix}"


def do_dictsort(value, case_sensitive=False, by="key", reverse=False):
    if by not in ("key", "value"):
        raise TemplateRuntimeError('dictsort: by has to be "key" or "value"')
    position = 0 if by == "key" else 1

    def sort_key(pair):
        part = pair[position]
        return part if case_sensitive else _ignore_case(part)

    return sorted(value.items(), key=sort_key, reverse=reverse)


def do_items(value):
    if _is_missing(value):
        return []
    if not isinstance(value, Mapping):
        raise TemplateRuntimeError(f"items: {type_name(value)} is not a mapping")
    return list(value.items())


@pass_environment
def do_attr(env, obj, name):
    """obj.name, without falling back to obj["name"] like the dot does."""
    name = str(name)
    if name.startswith("_"):
        return env.private_attribute(name)
    try:
        return getattr(obj, name)
    except AttributeError:
        return env.undefined(obj=obj, name=name)


def _json_default(obj: Any) -> Any:
    if _is_missing(obj):
        return None
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, PurePath):
        return obj.as_posix()
    if hasattr(obj, "__html__"):
        return str(obj.__html__())
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    if isinstance(obj, Iterable):
        return list(obj)
    raise TypeError(f"{type_name(obj)} can't be turned into JSON")


def do_tojson(value, indent=None):
    """JSON that can go into a <script> block or an attribute as it is."""
    text = json.dumps(value, indent=indent, ensure_ascii=False, default=_json_default)
    for char in "<>&'\u2028\u2029":
        text = text.replace(char, f"\\u{ord(char):04x}")
    return Markup(text)


def do_pprint(value):
    return pprint.pformat(value)


@pass_context
def do_xmlattr(ctx, value, autospace=True):
    """Render a dict as HTML attributes.

    none and undefined values are left out, true gives a bare attribute and
    false none at all, which is how boolean attributes work in HTML.
    """
    attrs = []
    for key, item in value.items():
        if item is None or item is False or isinstance(item, Undefined):
            continue
        if _bad_attr_name_re.search(key):
            raise TemplateRuntimeError(f"xmlattr: {key!r} is not a usable name")
        if item is True:
            attrs.append(str(escape(key)))
        else:
            attrs.append(f'{escape(key)}="{escape(item)}"')
    result = " ".join(attrs)
    if autospace and result:
        result = " " + result
    return Markup(result) if ctx.autoescape else result


def _to_datetime(value: Any) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in ("now", "today"):
            return datetime.datetime.now()
        # fromisoformat only learned about the Z suffix in Python 3.11
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            raise TemplateRuntimeError(
                f"date: can't read {value!r} as an ISO 8601 date"
            ) from None
    raise TemplateRuntimeError(f"date: {type_name(value)} is not a date")


def do_date(value, fmt="%Y-%m-%d"):
    """strftime for dates, datetimes, ISO 8601 strings and unix timestamps.

    "now" stands for the current time, which is handy for a copyright year.
    Use "%-d" for a day without the leading zero, it is translated to
    whatever the platform wants.
    """
    if value is None or _is_missing(value) or value == "":
        return ""
    fmt = _strftime_flag_re.sub("%" + _NO_PAD_FLAG + r"\1", fmt)
    return _to_datetime(value).strftime(fmt)


FILTERS: dict[str, Callable] = {
    "abs": do_abs,
    "attr": do_attr,
    "batch": do_batch,
    "capitalize": do_capitalize,
    "center": do_center,
    "count": do_length,
    "d": do_default,
    "date": do_date,
    "default": do_default,
    "dictsort": do_dictsort,
    "e": do_escape,
    "escape": do_escape,
    "filesizeformat": do_filesizeformat,
    "first": do_first,
    "float": do_float,
    "forceescape": do_forceescape,
    "format": do_format,
    "groupby": do_groupby,
    "indent": do_indent,
    "int": do_int,
    "items": do_items,
    "join": do_join,
    "last": do_last,
    "length": do_length,
    "list": do_list,
    "lower": do_lower,
    "map": do_map,
    "max": do_max,
    "min": do_min,
    "pprint": do_pprint,
    "reject": do_reject,
    "rejectattr": do_rejectattr,
    "replace": do_replace,
    "reverse": do_reverse,
    "round": do_round,
    "safe": do_safe,
    "select": do_select,
    "selectattr": do_selectattr,
    "slice": do_slice,
    "sort": do_sort,
    "string": do_string,
    "striptags": do_striptags,
    "sum": do_sum,
    "title": do_title,
    "tojson": do_tojson,
    "trim": do_trim,
    "truncate": do_truncate,
    "unique": do_unique,
    "upper": do_upper,
    "urlencode": do_urlencode,
    "urlize": do_urlize,
    "wordcount": do_wordcount,
    "wordwrap": do_wordwrap,
    "xmlattr": do_xmlattr,
}
