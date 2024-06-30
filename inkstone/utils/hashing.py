from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from collections.abc import Mapping
from pathlib import PurePath


def _new(algo: str):
    # sha1 is used for cache keys and file names here, never for security
    return hashlib.new(algo, usedforsecurity=False)


def hash_bytes(data: bytes, algo: str = "sha1") -> str:
    digest = _new(algo)
    digest.update(data)
    return digest.hexdigest()


def hash_text(text: str, algo: str = "sha1") -> str:
    return hash_bytes(text.encode("utf-8"), algo)


def short_hash(data: str | bytes, length: int = 8, algo: str = "sha1") -> str:
    """The first ``length`` hex digits; enough for cache-busting file names."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hash_bytes(data, algo)[:length]


def stable_hash(obj, algo: str = "sha1") -> str:
    """Hash a nested structure of plain values.

    The result does not depend on dict ordering, set ordering or the
    process (unlike the built-in hash()), so it can be stored and compared
    across runs. Lists and tuples hash alike; ``1``, ``1.0``, ``"1"`` and
    ``True`` do not.
    """
    digest = _new(algo)
    _feed(digest, obj)
    return digest.hexdigest()


def _feed(digest, obj) -> None:
    # Every value is written as a type tag plus a length-prefixed or
    # terminated payload, so ["ab", "c"] and ["a", "bc"] cannot collide.
    if obj is None:
        digest.update(b"n;")
    elif isinstance(obj, bool):
        digest.update(b"b1;" if obj else b"b0;")
    elif isinstance(obj, int):
        digest.update(b"i%d;" % obj)
    elif isinstance(obj, float):
        digest.update(b"f" + repr(obj).encode("ascii") + b";")
    elif isinstance(obj, str):
        data = obj.encode("utf-8", "surrogatepass")
        digest.update(b"s%d:" % len(data) + data)
    elif isinstance(obj, (bytes, bytearray)):
        digest.update(b"y%d:" % len(obj) + bytes(obj))
    elif isinstance(obj, (dt.date, dt.time)):
        digest.update(b"d" + obj.isoformat().encode("ascii") + b";")
    elif isinstance(obj, PurePath):
        _feed_tagged(digest, b"p", obj.as_posix())
    elif isinstance(obj, Mapping):
        digest.update(b"m%d:" % len(obj))
        for key in sorted(obj, key=_sort_key):
            _feed(digest, key)
            _feed(digest, obj[key])
    elif isinstance(obj, (list, tuple)):
        digest.update(b"l%d:" % len(obj))
        for item in obj:
            _feed(digest, item)
    elif isinstance(obj, (set, frozenset)):
        # hash the members separately and sort the digests; that works for
        # members that cannot be compared with each other
        digest.update(b"t%d:" % len(obj))
        for member in sorted(stable_hash(item, digest.name) for item in obj):
            digest.update(member.encode("ascii"))
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        fields = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
        _feed_tagged(digest, b"c", type(obj).__qualname__)
        _feed(digest, fields)
    else:
        raise TypeError(f"cannot compute a stable hash of {type(obj).__name__}")


def _feed_tagged(digest, tag: bytes, text: str) -> None:
    digest.update(tag)
    _feed(digest, text)


def _sort_key(key) -> tuple[str, str]:
    return type(key).__name__, repr(key)
