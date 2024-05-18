from __future__ import annotations

import datetime as dt
import re

_NULL = frozenset({"", "~", "null", "Null", "NULL"})
_BOOL = {
    "true": True,
    "True": True,
    "TRUE": True,
    "false": False,
    "False": False,
    "FALSE": False,
}

_INT = re.compile(r"[-+]?[0-9]+\Z")
_OCTAL = re.compile(r"0o[0-7]+\Z")
_HEXADECIMAL = re.compile(r"0x[0-9a-fA-F]+\Z")
_FLOAT = re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?\Z")
_INF = re.compile(r"([-+]?)\.(?:inf|Inf|INF)\Z")
_NAN = re.compile(r"\.(?:nan|NaN|NAN)\Z")

_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\Z")
# Seconds are optional here, unlike in YAML 1.1: "2024-05-03 14:00" is what
# people actually type into front matter.
_TIMESTAMP = re.compile(
    r"(\d{4})-(\d{1,2})-(\d{1,2})"
    r"(?:[Tt]|[ \t]+)(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?"
    r"(?:[ \t]*(Z|z|[-+]\d{1,2}(?::?\d{2})?))?\Z"
)

# Anything that resolves to a non-string starts with one of these, so plain
# words can skip the regexes altogether.
_INTERESTING = frozenset("0123456789+-.~nNtTfF")


def resolve(text: str) -> object:
    """Type a plain scalar following the YAML 1.2 core schema, plus dates."""
    if text in _NULL:
        return None
    if text[0] not in _INTERESTING:
        return text
    if text in _BOOL:
        return _BOOL[text]
    for convert in (to_int, to_float, to_timestamp):
        try:
            return convert(text)
        except ValueError:
            pass
    return text


def to_int(text: str) -> int:
    if _INT.match(text):
        return int(text)
    if _OCTAL.match(text):
        return int(text[2:], 8)
    if _HEXADECIMAL.match(text):
        return int(text[2:], 16)
    raise ValueError(text)


def to_float(text: str) -> float:
    match = _INF.match(text)
    if match:
        return float("-inf") if match.group(1) == "-" else float("inf")
    if _NAN.match(text):
        return float("nan")
    if _FLOAT.match(text):
        return float(text)
    raise ValueError(text)


def to_bool(text: str) -> bool:
    try:
        return _BOOL[text]
    except KeyError:
        raise ValueError(text) from None


def to_null(text: str) -> None:
    if text not in _NULL:
        raise ValueError(text)
    return None


def to_timestamp(text: str) -> dt.date:
    """A date for ``2024-05-03``, a datetime when there is a time part.

    Values that look right but are not real dates (``2024-02-30``) raise
    ValueError like any other mismatch, so they stay strings when resolved
    implicitly.
    """
    match = _DATE.match(text)
    if match:
        return dt.date(*(int(part) for part in match.groups()))
    match = _TIMESTAMP.match(text)
    if not match:
        raise ValueError(text)
    year, month, day, hour, minute = (int(match.group(i)) for i in range(1, 6))
    second = int(match.group(6) or 0)
    fraction = (match.group(7) or "")[:6].ljust(6, "0")
    return dt.datetime(
        year, month, day, hour, minute, second, int(fraction), _zone(match.group(8))
    )


def _zone(text: str | None) -> dt.timezone | None:
    if not text:
        return None
    if text in "Zz":
        return dt.timezone.utc
    digits = text[1:].replace(":", "")
    if len(digits) <= 2:
        hours, minutes = int(digits), 0
    else:
        hours, minutes = int(digits[:-2]), int(digits[-2:])
    offset = dt.timedelta(hours=hours, minutes=minutes)
    return dt.timezone(-offset if text[0] == "-" else offset)
