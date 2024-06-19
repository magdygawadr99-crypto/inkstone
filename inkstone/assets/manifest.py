from __future__ import annotations

import difflib
import json
import os
import posixpath
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from .errors import AssetError

_FORMAT_VERSION = 1


def normalise(path) -> str:
    """Canonical manifest key: forward slashes, no leading `./` or `/`."""
    text = str(path).replace("\\", "/").lstrip("/")
    return posixpath.normpath(text) if text else text


@dataclass(frozen=True)
class Entry:
    output: str
    hash: str
    size: int
    integrity: str


class Manifest:
    """Maps the path an asset is written as in templates (`css/site.css`) to
    the file that actually got built (`css/site.3f9a1c2e.css`)."""

    def __init__(self, entries: dict[str, Entry] | None = None):
        self._entries: dict[str, Entry] = {}
        for logical, entry in (entries or {}).items():
            self._entries[normalise(logical)] = entry

    def add(
        self, logical: str, output: str, *, hash: str, size: int, integrity: str
    ) -> Entry:
        entry = Entry(normalise(output), hash, size, integrity)
        self._entries[normalise(logical)] = entry
        return entry

    def get(self, logical: str) -> Entry | None:
        return self._entries.get(normalise(logical))

    def _require(self, logical: str) -> Entry:
        key = normalise(logical)
        entry = self._entries.get(key)
        if entry is None:
            message = "no such asset"
            close = difflib.get_close_matches(key, self._entries, n=1)
            if close:
                message += f" (did you mean {close[0]!r}?)"
            raise AssetError(message, path=key)
        return entry

    def url_for(self, logical: str) -> str:
        """Output path of an asset, relative to the site root."""
        return self._require(logical).output

    def integrity(self, logical: str) -> str:
        return self._require(logical).integrity

    def outputs(self) -> set[str]:
        return {entry.output for entry in self._entries.values()}

    def __contains__(self, logical) -> bool:
        return normalise(logical) in self._entries

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._entries))

    def __len__(self) -> int:
        return len(self._entries)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Manifest):
            return NotImplemented
        return self._entries == other._entries

    def __repr__(self) -> str:
        return f"<Manifest: {len(self)} assets>"

    def items(self) -> Iterator[tuple[str, Entry]]:
        for logical in self:
            yield logical, self._entries[logical]

    def to_dict(self) -> dict:
        return {
            "version": _FORMAT_VERSION,
            "assets": {logical: asdict(entry) for logical, entry in self.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        if not isinstance(data, dict) or not isinstance(data.get("assets"), dict):
            raise AssetError("malformed asset manifest")
        version = data.get("version")
        if version != _FORMAT_VERSION:
            raise AssetError(f"unsupported asset manifest version {version!r}")
        manifest = cls()
        for logical, fields in data["assets"].items():
            try:
                manifest.add(
                    logical,
                    fields["output"],
                    hash=fields["hash"],
                    size=int(fields["size"]),
                    integrity=fields["integrity"],
                )
            except (KeyError, TypeError, ValueError):
                raise AssetError(
                    f"malformed asset manifest entry for {logical!r}"
                ) from None
        return manifest

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        # write-then-rename so a reader never sees half a file
        scratch = path.with_name(path.name + ".tmp")
        scratch.write_text(text, encoding="utf-8")
        os.replace(scratch, path)

    @classmethod
    def load(cls, path) -> Manifest:
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise AssetError(
                f"cannot read asset manifest: {exc.strerror}", path=path
            ) from None
        except ValueError as exc:
            raise AssetError(
                f"asset manifest is not valid JSON: {exc}", path=path
            ) from None
        try:
            return cls.from_dict(data)
        except AssetError as exc:
            raise AssetError(exc.message, path=path) from None
