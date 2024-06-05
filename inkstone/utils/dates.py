from __future__ import annotations

import datetime as dt
import email.utils
import os
import re

_MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_MONTHS = {"sept": 9}
for _number, _name in enumerate(_MONTH_NAMES, 1):
    _MONTHS[_name.lower()] = _number
    _MONTHS[_name[:3].lower()] = _number

_ZONE = r"Z|z|UTC|GMT|[+-]\d{1,2}(?::?\d{2})?"
_OFFSET = re.compile(r"(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?\Z", re.I)

# 2024-05-03, 2024/05/03, 20240503, 2024-05 and plain 2024
_ISO_DATE = re.compile(
    r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?|/(\d{1,2})/(\d{1,2})|(\d{2})(\d{2}))?"
)
_CLOCK = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2})(?::(?P<second>\d{2})"
    r"(?:[.,](?P<fraction>\d+))?)?)?"
    r"(?:\s*(?P<half>[AaPp])\.?[Mm]\.?)?"
    rf"\s*(?P<zone>{_ZONE})?\Z"
)
# the "basic" ISO form without colons: 140000, 1400
_BASIC_CLOCK = re.compile(
    r"(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})?"
    r"(?:[.,](?P<fraction>\d+))?"
    rf"\s*(?P<zone>{_ZONE})?\Z"
)
_ORDINAL = r"(?:st|nd|rd|th)?"
_WEEKDAY = r"(?:[A-Za-z]+\.?,?\s+)?"
_TIME_TAIL = r"(?:(?:,|\s+at)?\s+(?P<time>\S.*))?\Z"
# [Friday, ]May 3[rd][,] 2024[, 14:00]
_MONTH_FIRST = re.compile(
    _WEEKDAY
    + r"(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2})"
    + _ORDINAL
    + r",?\s+(?P<year>\d{4})"
    + _TIME_TAIL
)
# [Fri, ]3[rd] May[,] 2024[ 14:00]
_DAY_FIRST = re.compile(
    _WEEKDAY
    + r"(?P<day>\d{1,2})"
    + _ORDINAL
    + r"\s+(?P<month>[A-Za-z]+)\.?,?\s+(?P<year>\d{4})"
    + _TIME_TAIL
)
# Only used to decide whether email.utils gets a look at the string. It must
# not see zones written as "+02:00": it reads those as no zone at all.
_RFC2822 = re.compile(
    r"(?:[A-Za-z]{3},\s*)?\d{1,2}\s+[A-Za-z]{3}\s+\d{4}"
    r"\s+\d{1,2}:\d{2}(?::\d{2})?\s+(?:[+-]\d{4}|[A-Za-z]+)\Z"
)
_FILENAME_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[-_](.*))?\Z")
_UNPADDED = re.compile(r"%%|%-([A-Za-z])")


def parse_tz(text: str) -> dt.timezone:
    """Fixed-offset zones only: "Z", "UTC", "+02:00", "-0530", "+2"."""
    value = text.strip()
    if value.upper() in ("Z", "UTC", "GMT"):
        return dt.timezone.utc
    match = _OFFSET.match(value)
    if match is None:
        raise ValueError(f"unrecognised UTC offset: {text!r}")
    hours, minutes = int(match.group(2)), int(match.group(3) or 0)
    if hours > 14 or minutes > 59:
        raise ValueError(f"UTC offset out of range: {text!r}")
    offset = dt.timedelta(hours=hours, minutes=minutes)
    return dt.timezone(-offset if match.group(1) == "-" else offset)


def parse_date(value, *, default_tz=None) -> dt.datetime:
    """Turn whatever front matter gave us into a datetime.

    Accepts date and datetime objects, ISO 8601 strings in their usual
    shapes, RFC 2822 dates and English forms such as "May 3, 2024" or
    "3 May 2024 14:00". ``default_tz`` (a tzinfo or an offset string) is
    attached to results that carry no zone of their own. Raises ValueError
    for anything else.
    """
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, dt.date):
        moment = dt.datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        moment = _parse_text(value)
    else:
        raise ValueError(f"cannot interpret {value!r} as a date")
    if moment.tzinfo is None and default_tz is not None:
        if isinstance(default_tz, str):
            default_tz = parse_tz(default_tz)
        moment = moment.replace(tzinfo=default_tz)
    return moment


def _parse_text(text: str) -> dt.datetime:
    value = text.strip()
    try:
        for attempt in (_parse_iso, _parse_rfc2822, _parse_english):
            moment = attempt(value)
            if moment is not None:
                return moment
    except ValueError as exc:
        # right shape, impossible values: February 30th, 25 o'clock...
        raise ValueError(f"invalid date {text!r}: {exc}") from None
    raise ValueError(f"unrecognised date format: {text!r}")


def _parse_iso(value: str) -> dt.datetime | None:
    match = _ISO_DATE.match(value)
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or match.group(4) or match.group(6) or 1)
    day = int(match.group(3) or match.group(5) or match.group(7) or 1)
    rest = value[match.end() :]
    if not rest:
        return dt.datetime(year, month, day)
    if rest[0] not in "Tt \t":
        return None
    clock = _parse_clock(rest[1:].strip(), basic=rest[0] in "Tt")
    if clock is None:
        return None
    return dt.datetime(year, month, day, *clock)


def _parse_clock(text: str, *, basic: bool = False):
    """Parse a time of day; returns the tail of datetime()'s arguments."""
    match = _CLOCK.match(text)
    if match is None and basic:
        match = _BASIC_CLOCK.match(text)
    if match is None:
        return None
    parts = match.groupdict()
    hour = int(parts["hour"])
    half = parts.get("half")
    if half:
        if not 1 <= hour <= 12:
            raise ValueError("hour must be in 1..12 with am/pm")
        hour = hour % 12 + (12 if half in "Pp" else 0)
    fraction = (parts["fraction"] or "")[:6].ljust(6, "0")
    zone = parse_tz(parts["zone"]) if parts["zone"] else None
    return (
        hour,
        int(parts["minute"] or 0),
        int(parts["second"] or 0),
        int(fraction),
        zone,
    )


def _parse_rfc2822(value: str) -> dt.datetime | None:
    if not _RFC2822.match(value):
        return None
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        # let the more forgiving English parser have a go
        return None


def _parse_english(value: str) -> dt.datetime | None:
    match = _MONTH_FIRST.match(value) or _DAY_FIRST.match(value)
    if match is None:
        return None
    month = _MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    clock = ()
    if match.group("time"):
        clock = _parse_clock(match.group("time"))
        if clock is None:
            return None
    return dt.datetime(int(match.group("year")), month, int(match.group("day")), *clock)


def _aware(moment: dt.datetime) -> dt.datetime:
    # feeds need an offset; a naive time is taken to be UTC
    if moment.tzinfo is None:
        return moment.replace(tzinfo=dt.timezone.utc)
    return moment


def to_rfc3339(value) -> str:
    """Atom/JSON-feed style timestamp: 2024-05-03T14:00:00+02:00, or ...Z."""
    text = _aware(parse_date(value)).replace(microsecond=0).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def to_rfc2822(value) -> str:
    """RSS style timestamp: Fri, 03 May 2024 14:00:00 +0200."""
    return email.utils.format_datetime(_aware(parse_date(value)))


_NAMED_FORMATS = {
    "iso": lambda d: d.date().isoformat(),
    "short": lambda d: f"{_MONTH_NAMES[d.month - 1][:3]} {d.day}, {d.year}",
    "long": lambda d: f"{_MONTH_NAMES[d.month - 1]} {d.day}, {d.year}",
    "full": lambda d: (
        f"{_DAY_NAMES[d.weekday()]}, {_MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"
    ),
    "month": lambda d: f"{_MONTH_NAMES[d.month - 1]} {d.year}",
    "year": lambda d: str(d.year),
    "time": lambda d: f"{d.hour:02d}:{d.minute:02d}",
    "datetime": lambda d: f"{d.date().isoformat()} {d.hour:02d}:{d.minute:02d}",
    "rfc3339": to_rfc3339,
    "rfc2822": to_rfc2822,
}


def format_date(value, fmt: str = "long") -> str:
    """Format a date using a named format or a strftime pattern.

    Named formats (iso, short, long, full, month, year, time, datetime,
    rfc3339, rfc2822) always use English names, whatever the locale.
    """
    moment = parse_date(value)
    named = _NAMED_FORMATS.get(fmt)
    if named is not None:
        return named(moment)
    if "%" not in fmt:
        raise ValueError(f"unknown date format: {fmt!r}")

    def unpad(match: re.Match) -> str:
        if match.group(1) is None:
            return match.group()
        return moment.strftime("%" + match.group(1)).lstrip("0") or "0"

    # "%-d" is a glibc extension that Windows rejects, so do it by hand
    return moment.strftime(_UNPADDED.sub(unpad, fmt))


_SPANS = [
    (3600, 60, "minute"),
    (86400, 3600, "hour"),
    (7 * 86400, 86400, "day"),
    (30 * 86400, 7 * 86400, "week"),
    (365 * 86400, 30 * 86400, "month"),
]


def relative_time(then, now=None) -> str:
    """Distance between two moments in words: "3 days ago", "in 2 hours"."""
    then = parse_date(then)
    if now is None:
        now = dt.datetime.now(then.tzinfo)
    else:
        now = parse_date(now)
    if (then.tzinfo is None) != (now.tzinfo is None):
        then, now = _aware(then), _aware(now)
    seconds = (now - then).total_seconds()
    ahead = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        return "just now"
    for limit, size, unit in _SPANS:
        if seconds < limit:
            break
    else:
        size, unit = 365 * 86400, "year"
    count = int(seconds // size)
    phrase = f"{count} {unit}" if count == 1 else f"{count} {unit}s"
    return f"in {phrase}" if ahead else f"{phrase} ago"


def date_from_filename(name) -> tuple[dt.date | None, str]:
    """Split a Jekyll-style file name into its date and the rest.

    "2024-05-03-my-post.md" gives (date(2024, 5, 3), "my-post"). Without a
    valid leading date the result is (None, stem).
    """
    base = re.split(r"[\\/]", str(name))[-1]
    stem = os.path.splitext(base)[0]
    match = _FILENAME_DATE.match(stem)
    if match:
        try:
            date = dt.date(*(int(part) for part in match.groups()[:3]))
        except ValueError:
            pass
        else:
            return date, match.group(4) or ""
    return None, stem
