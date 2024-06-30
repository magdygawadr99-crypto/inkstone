from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from inkstone.utils.hashing import hash_bytes, hash_text, short_hash, stable_hash


def test_hash_bytes_and_text_match_hashlib():
    assert hash_bytes(b"") == "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    assert hash_bytes(b"abc", "sha256") == hashlib.sha256(b"abc").hexdigest()
    assert hash_text("héllo") == hashlib.sha1("héllo".encode("utf-8")).hexdigest()
    assert hash_text("abc", "md5") == "900150983cd24fb0d6963f7d28e17f72"
    with pytest.raises(ValueError):
        hash_bytes(b"x", "nope")


def test_short_hash():
    full = hash_text("site.css contents")
    assert short_hash("site.css contents") == full[:8]
    assert short_hash(b"site.css contents") == full[:8]
    assert short_hash("x", length=12) == hash_text("x")[:12]
    assert len(short_hash("x", 4, "sha256")) == 4


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
        ({"a": {"x": [1, 2], "y": None}}, {"a": {"y": None, "x": [1, 2]}}),
        ([1, 2, 3], (1, 2, 3)),
        ({1, 2, 3}, {3, 2, 1}),
        ({"mixed", 1, None}, frozenset([None, 1, "mixed"])),
        ({1: "a", "1": "b"}, {"1": "b", 1: "a"}),
        (Path("a") / "b.txt", PurePosixPath("a/b.txt")),
        (PureWindowsPath("a\\b.txt"), PurePosixPath("a/b.txt")),
        (bytearray(b"raw"), b"raw"),
    ],
)
def test_stable_hash_ignores_incidental_differences(left, right):
    assert stable_hash(left) == stable_hash(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (1, "1"),
        (1, 1.0),
        (1, True),
        (0, False),
        (0, None),
        ("", None),
        ("", []),
        ([], {}),
        ([], [[]]),
        ([1, 2], [2, 1]),
        (["ab", "c"], ["a", "bc"]),
        ([["a"], "b"], ["a", ["b"]]),
        ({"a": 1}, {"a": 2}),
        ({"a": 1}, {"b": 1}),
        ({"a": None}, {}),
        ("abc", b"abc"),
        ("a/b", PurePosixPath("a/b")),
        (dt.date(2024, 5, 3), "2024-05-03"),
        (dt.date(2024, 5, 3), dt.datetime(2024, 5, 3)),
        ({1, 2}, [1, 2]),
        ({"12"}, {"1", "2"}),
    ],
)
def test_stable_hash_tells_values_apart(left, right):
    assert stable_hash(left) != stable_hash(right)


def test_stable_hash_is_stable_across_runs():
    # pinned on purpose: cache keys on disk must not change between releases
    assert stable_hash({"title": "Hello", "tags": ["a", "b"], "draft": False}) == (
        stable_hash({"draft": False, "tags": ["a", "b"], "title": "Hello"})
    )
    assert stable_hash(None) == hashlib.sha1(b"n;").hexdigest()
    assert stable_hash("é") == hashlib.sha1(b"s2:\xc3\xa9").hexdigest()
    assert stable_hash([1, "a"]) == hashlib.sha1(b"l2:i1;s1:a").hexdigest()
    assert stable_hash({"k": True}) == hashlib.sha1(b"m1:s1:kb1;").hexdigest()


def test_stable_hash_algorithm_option():
    assert len(stable_hash({"a": 1}, "sha256")) == 64
    assert stable_hash({"a": {1, 2}}, "md5") == stable_hash({"a": {2, 1}}, "md5")


@dataclasses.dataclass
class Asset:
    path: str
    size: int
    tags: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Other:
    path: str
    size: int
    tags: list = dataclasses.field(default_factory=list)


def test_stable_hash_of_dataclasses():
    assert stable_hash(Asset("a.css", 10)) == stable_hash(Asset("a.css", 10, []))
    assert stable_hash(Asset("a.css", 10)) != stable_hash(Asset("a.css", 11))
    assert stable_hash(Asset("a.css", 10)) != stable_hash(Other("a.css", 10))
    as_dict = {"path": "a", "size": 1, "tags": []}
    assert stable_hash(Asset("a", 1)) != stable_hash(as_dict)


def test_stable_hash_rejects_what_it_cannot_pin_down():
    with pytest.raises(TypeError, match="stable hash of object"):
        stable_hash({"x": object()})
    with pytest.raises(TypeError, match="function"):
        stable_hash([lambda: None])
    with pytest.raises(TypeError):
        stable_hash(Asset)


def test_stable_hash_handles_dates_and_times():
    moment = dt.datetime(2024, 5, 3, 14, 0, tzinfo=dt.timezone.utc)
    assert stable_hash(moment) == stable_hash(moment.replace())
    assert stable_hash(moment) != stable_hash(moment.replace(tzinfo=None))
    assert stable_hash(dt.time(14, 0)) != stable_hash(dt.time(14, 1))
