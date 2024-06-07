from __future__ import annotations

from datetime import date, datetime, timezone
from email.utils import format_datetime

from .errors import FeedError


def aware(value: date | datetime) -> datetime:
    """Turn a date or datetime into an aware datetime.

    Naive values are taken to be UTC and plain dates become midnight UTC.
    Front matter rarely carries a zone and the build machine's local time is
    nobody's business, so guessing UTC is the least surprising thing to do.
    """
    if not isinstance(value, datetime):
        if not isinstance(value, date):
            raise FeedError(f"expected a date or datetime, got {value!r}")
        value = datetime(value.year, value.month, value.day)
    if value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def rfc822(value: date | datetime) -> str:
    """Mon, 02 Jan 2006 15:04:05 +0000, the format RSS inherited from email."""
    return format_datetime(aware(value).replace(microsecond=0))


def rfc3339(value: date | datetime) -> str:
    """2006-01-02T15:04:05Z, for Atom, JSON Feed and sitemaps."""
    text = aware(value).isoformat(timespec="seconds")
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text
