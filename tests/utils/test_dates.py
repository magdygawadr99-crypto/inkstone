from __future__ import annotations

import datetime as dt

import pytest

from inkstone.utils import dates
from inkstone.utils.dates import parse_date

UTC = dt.timezone.utc


def tz(hours, minutes=0):
    return dt.timezone(dt.timedelta(hours=hours, minutes=minutes))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-05-03", dt.datetime(2024, 5, 3)),
        ("2024-5-3", dt.datetime(2024, 5, 3)),
        ("2024/05/03", dt.datetime(2024, 5, 3)),
        ("20240503", dt.datetime(2024, 5, 3)),
        ("2024-05", dt.datetime(2024, 5, 1)),
        ("2024", dt.datetime(2024, 1, 1)),
        ("  2024-05-03  ", dt.datetime(2024, 5, 3)),
        ("2024-05-03 14:00", dt.datetime(2024, 5, 3, 14, 0)),
        ("2024-05-03T14:00", dt.datetime(2024, 5, 3, 14, 0)),
        ("2024-05-03t14:00:05", dt.datetime(2024, 5, 3, 14, 0, 5)),
        ("2024-05-03   14:00:05", dt.datetime(2024, 5, 3, 14, 0, 5)),
        ("2024-05-03T14", dt.datetime(2024, 5, 3, 14, 0)),
        ("2024-05-03 9:05", dt.datetime(2024, 5, 3, 9, 5)),
        ("2024-05-03T14:00:05.5", dt.datetime(2024, 5, 3, 14, 0, 5, 500000)),
        ("2024-05-03T14:00:05,123456789", dt.datetime(2024, 5, 3, 14, 0, 5, 123456)),
        ("2024-05-03T14:00:05Z", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=UTC)),
        ("2024-05-03T14:00:05z", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=UTC)),
        ("2024-05-03 14:00 UTC", dt.datetime(2024, 5, 3, 14, 0, tzinfo=UTC)),
        ("2024-05-03T14:00:05+02:00", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=tz(2))),
        (
            "2024-05-03T14:00:05-0530",
            dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=tz(-5, -30)),
        ),
        ("2024-05-03 14:00 +01", dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(1))),
        ("20240503T140005Z", dt.datetime(2024, 5, 3, 14, 0, 5, tzinfo=UTC)),
        ("20240503T1400", dt.datetime(2024, 5, 3, 14, 0)),
        ("2024-05-03 2:30 pm", dt.datetime(2024, 5, 3, 14, 30)),
        ("2024-05-03 12:15 AM", dt.datetime(2024, 5, 3, 0, 15)),
    ],
)
def test_parse_iso_shapes(text, expected):
    result = parse_date(text)
    assert result == expected
    assert result.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("May 3, 2024", dt.datetime(2024, 5, 3)),
        ("May 3 2024", dt.datetime(2024, 5, 3)),
        ("may 3rd, 2024", dt.datetime(2024, 5, 3)),
        ("Sep 21, 2023", dt.datetime(2023, 9, 21)),
        ("Sept. 1st 2023", dt.datetime(2023, 9, 1)),
        ("December 31, 1999", dt.datetime(1999, 12, 31)),
        ("3 May 2024", dt.datetime(2024, 5, 3)),
        ("03 may 2024", dt.datetime(2024, 5, 3)),
        ("2nd February, 2021", dt.datetime(2021, 2, 2)),
        ("Friday, May 3, 2024", dt.datetime(2024, 5, 3)),
        ("Fri 3 May 2024", dt.datetime(2024, 5, 3)),
        ("May 3, 2024 14:00", dt.datetime(2024, 5, 3, 14, 0)),
        ("May 3, 2024, 2:30 PM", dt.datetime(2024, 5, 3, 14, 30)),
        ("May 3, 2024 at 9am", dt.datetime(2024, 5, 3, 9, 0)),
        ("3 May 2024 14:00:05", dt.datetime(2024, 5, 3, 14, 0, 5)),
        ("3 May 2024 14:00 +02:00", dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(2))),
    ],
)
def test_parse_english_formats(text, expected):
    result = parse_date(text)
    assert result == expected
    assert result.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Fri, 03 May 2024 14:00:00 +0200",
            dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(2)),
        ),
        ("Fri, 3 May 2024 14:00:00 GMT", dt.datetime(2024, 5, 3, 14, 0, tzinfo=UTC)),
        ("03 May 2024 14:00 -0500", dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(-5))),
        (
            "Tue, 31 Dec 2024 23:59:59 EST",
            dt.datetime(2024, 12, 31, 23, 59, 59, tzinfo=tz(-5)),
        ),
    ],
)
def test_parse_rfc2822(text, expected):
    result = parse_date(text)
    assert result == expected
    assert result.utcoffset() == expected.utcoffset()


def test_parse_date_objects():
    moment = dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(2))
    assert parse_date(moment) is moment
    assert parse_date(dt.date(2024, 5, 3)) == dt.datetime(2024, 5, 3)
    assert type(parse_date(dt.date(2024, 5, 3))) is dt.datetime


def test_default_tz_only_applies_to_naive_values():
    assert parse_date("2024-05-03", default_tz=UTC).tzinfo is UTC
    from_string = parse_date("2024-05-03 10:00", default_tz="+02:00")
    assert from_string.utcoffset() == dt.timedelta(hours=2)
    from_date = parse_date(dt.date(2024, 5, 3), default_tz=tz(-3))
    assert from_date.utcoffset() == dt.timedelta(hours=-3)
    explicit = parse_date("2024-05-03T10:00:00Z", default_tz=tz(5))
    assert explicit.utcoffset() == dt.timedelta(0)
    assert parse_date("2024-05-03").tzinfo is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "tomorrow",
        "2024-05-03x",
        "24-05-03",
        "2024-05-03T",
        "2024-05-03 25",
        "2024-13-01",
        "2024-02-30",
        "2023-02-29",
        "2024-05-03 24:30",
        "2024-05-03 14:61",
        "2024-05-03 13:00 pm",
        "2024-05-03 14:00 +25:00",
        "Maybe 3, 2024",
        "May 32, 2024",
        "3 Mayo 2024",
        "May 2024",
        "12345",
    ],
)
def test_parse_rejects_bad_dates(text):
    with pytest.raises(ValueError) as info:
        parse_date(text)
    assert repr(text) in str(info.value)


@pytest.mark.parametrize("value", [None, 20240503, 1714744800.0, ["2024-05-03"], True])
def test_parse_rejects_other_types(value):
    with pytest.raises(ValueError, match="cannot interpret"):
        parse_date(value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Z", dt.timedelta(0)),
        ("z", dt.timedelta(0)),
        ("UTC", dt.timedelta(0)),
        ("gmt", dt.timedelta(0)),
        ("+02:00", dt.timedelta(hours=2)),
        ("-05:30", -dt.timedelta(hours=5, minutes=30)),
        ("+0200", dt.timedelta(hours=2)),
        ("+02", dt.timedelta(hours=2)),
        ("-7", dt.timedelta(hours=-7)),
        ("+530", dt.timedelta(hours=5, minutes=30)),
        ("UTC+1", dt.timedelta(hours=1)),
        ("GMT-03:00", dt.timedelta(hours=-3)),
        (" +14:00 ", dt.timedelta(hours=14)),
        ("+00:00", dt.timedelta(0)),
    ],
)
def test_parse_tz(text, expected):
    zone = dates.parse_tz(text)
    assert zone.utcoffset(None) == expected


@pytest.mark.parametrize(
    "text", ["", "Europe/Paris", "EST", "+15:00", "+02:60", "02:00", "+2:0"]
)
def test_parse_tz_rejects(text):
    with pytest.raises(ValueError):
        dates.parse_tz(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(2)), "2024-05-03T14:00:00+02:00"),
        (dt.datetime(2024, 5, 3, 14, 0, tzinfo=UTC), "2024-05-03T14:00:00Z"),
        (dt.datetime(2024, 5, 3, 14, 0, 5, 999999), "2024-05-03T14:00:05Z"),
        (
            dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(-5, -30)),
            "2024-05-03T14:00:00-05:30",
        ),
        (dt.date(2024, 5, 3), "2024-05-03T00:00:00Z"),
        ("2024-05-03 08:15", "2024-05-03T08:15:00Z"),
    ],
)
def test_to_rfc3339(value, expected):
    assert dates.to_rfc3339(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            dt.datetime(2024, 5, 3, 14, 0, tzinfo=tz(2)),
            "Fri, 03 May 2024 14:00:00 +0200",
        ),
        (dt.datetime(2024, 5, 3, 14, 0, tzinfo=UTC), "Fri, 03 May 2024 14:00:00 +0000"),
        (dt.datetime(2024, 12, 31, 23, 59, 59), "Tue, 31 Dec 2024 23:59:59 +0000"),
        (dt.date(2024, 1, 1), "Mon, 01 Jan 2024 00:00:00 +0000"),
    ],
)
def test_to_rfc2822(value, expected):
    assert dates.to_rfc2822(value) == expected
    assert parse_date(expected) == parse_date(value, default_tz=UTC)


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("iso", "2024-09-03"),
        ("short", "Sep 3, 2024"),
        ("long", "September 3, 2024"),
        ("full", "Tuesday, September 3, 2024"),
        ("month", "September 2024"),
        ("year", "2024"),
        ("time", "08:05"),
        ("datetime", "2024-09-03 08:05"),
        ("rfc3339", "2024-09-03T08:05:00+02:00"),
        ("rfc2822", "Tue, 03 Sep 2024 08:05:00 +0200"),
        ("%Y/%m/%d", "2024/09/03"),
        ("%d.%m.%Y %H:%M", "03.09.2024 08:05"),
        ("%-d.%-m.%Y", "3.9.2024"),
        ("%-H h %-M min", "8 h 5 min"),
        ("100%% on %-d/%m", "100% on 3/09"),
        ("%j", "247"),
    ],
)
def test_format_date(fmt, expected):
    moment = dt.datetime(2024, 9, 3, 8, 5, tzinfo=tz(2))
    assert dates.format_date(moment, fmt) == expected


def test_format_date_defaults_and_inputs():
    assert dates.format_date(dt.date(2024, 5, 3)) == "May 3, 2024"
    assert dates.format_date("2024-05-03", "full") == "Friday, May 3, 2024"
    assert dates.format_date(dt.datetime(2024, 1, 1, 0, 0), "%-H:%M") == "0:00"
    with pytest.raises(ValueError, match="unknown date format"):
        dates.format_date(dt.date(2024, 5, 3), "fancy")


NOW = dt.datetime(2024, 5, 3, 12, 0, 0)


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (dt.timedelta(0), "just now"),
        (dt.timedelta(seconds=59), "just now"),
        (dt.timedelta(seconds=60), "1 minute ago"),
        (dt.timedelta(minutes=59, seconds=59), "59 minutes ago"),
        (dt.timedelta(hours=1), "1 hour ago"),
        (dt.timedelta(hours=23, minutes=59), "23 hours ago"),
        (dt.timedelta(days=1), "1 day ago"),
        (dt.timedelta(days=3), "3 days ago"),
        (dt.timedelta(days=7), "1 week ago"),
        (dt.timedelta(days=29), "4 weeks ago"),
        (dt.timedelta(days=30), "1 month ago"),
        (dt.timedelta(days=364), "12 months ago"),
        (dt.timedelta(days=365), "1 year ago"),
        (dt.timedelta(days=800), "2 years ago"),
        (-dt.timedelta(seconds=30), "just now"),
        (-dt.timedelta(minutes=5), "in 5 minutes"),
        (-dt.timedelta(hours=2), "in 2 hours"),
        (-dt.timedelta(days=1), "in 1 day"),
        (-dt.timedelta(days=45), "in 1 month"),
    ],
)
def test_relative_time(delta, expected):
    assert dates.relative_time(NOW - delta, NOW) == expected


def test_relative_time_mixed_inputs():
    aware_now = dt.datetime(2024, 5, 3, 12, 0, tzinfo=tz(2))
    in_utc = dt.datetime(2024, 5, 3, 9, 0, tzinfo=UTC)
    assert dates.relative_time(in_utc, aware_now) == "1 hour ago"
    # a naive value next to an aware one is read as UTC
    naive = dt.datetime(2024, 5, 3, 8, 0)
    assert dates.relative_time(naive, aware_now) == "2 hours ago"
    assert dates.relative_time(dt.date(2024, 5, 1), NOW) == "2 days ago"
    assert dates.relative_time("2024-05-03 11:30", NOW) == "30 minutes ago"


def test_relative_time_defaults_to_the_current_time():
    recent = dt.datetime.now(UTC) - dt.timedelta(hours=5, minutes=1)
    assert dates.relative_time(recent) == "5 hours ago"
    local = dt.datetime.now() - dt.timedelta(days=2, hours=1)
    assert dates.relative_time(local) == "2 days ago"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("2024-05-03-my-post.md", (dt.date(2024, 5, 3), "my-post")),
        ("2024-05-03_my_post.md", (dt.date(2024, 5, 3), "my_post")),
        ("2024-5-3-short.markdown", (dt.date(2024, 5, 3), "short")),
        ("2024-05-03.md", (dt.date(2024, 5, 3), "")),
        ("2024-05-03-v1.2-notes.md", (dt.date(2024, 5, 3), "v1.2-notes")),
        ("content/blog/2024-05-03-nested.md", (dt.date(2024, 5, 3), "nested")),
        ("content\\blog\\2024-05-03-windows.md", (dt.date(2024, 5, 3), "windows")),
        ("2024-05-03-no-extension", (dt.date(2024, 5, 3), "no-extension")),
        ("about.md", (None, "about")),
        ("2024-13-45-not-a-date.md", (None, "2024-13-45-not-a-date")),
        ("2024-05-031-odd.md", (None, "2024-05-031-odd")),
        ("12-05-2024-wrong-order.md", (None, "12-05-2024-wrong-order")),
        ("notes-2024-05-03.md", (None, "notes-2024-05-03")),
    ],
)
def test_date_from_filename(name, expected):
    assert dates.date_from_filename(name) == expected
