from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path
from typing import Iterable

from ..errors import BuildError
from ..utils.fs import atomic_write
from ..utils.paths import safe_join


def normalise_output_path(path) -> str:
    """Output paths are POSIX strings relative to the output directory."""
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


class OutputWriter:
    """Writes into the output directory, and only into it.

    Files are left alone when their bytes would not change, so modification
    times stay meaningful for rsync and for the dev server's reload logic.
    """

    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.written: list[str] = []
        self.unchanged: list[str] = []
        self.removed: list[str] = []
        # everything this build produced or confirmed, written or not
        self.outputs: set[str] = set()

    def resolve(self, relpath) -> Path:
        rel = normalise_output_path(relpath)
        if not rel:
            raise BuildError("empty output path")
        try:
            return safe_join(self.output_dir, rel)
        except ValueError:
            raise BuildError(
                f"refusing to touch {relpath!r}: it is outside the output "
                f"directory {self.output_dir}"
            ) from None

    def exists(self, relpath) -> bool:
        try:
            return self.resolve(relpath).is_file()
        except BuildError:
            return False

    def keep(self, relpath) -> None:
        """Declare an output current without writing it (a cache hit)."""
        rel = normalise_output_path(relpath)
        self.outputs.add(rel)
        self.unchanged.append(rel)

    def claim(self, relpath) -> None:
        """Mark a path as belonging to this build without counting it."""
        self.outputs.add(normalise_output_path(relpath))

    def write(self, relpath, data: str | bytes) -> bool:
        """Write a file unless it already has these contents; True if written."""
        rel = normalise_output_path(relpath)
        target = self.resolve(rel)
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.outputs.add(rel)
        try:
            if target.is_file() and target.read_bytes() == data:
                self.unchanged.append(rel)
                return False
            if target.is_dir():
                raise BuildError(
                    f"cannot write {rel}: a directory of that name is in the way"
                )
            atomic_write(target, data)
        except OSError as exc:
            raise BuildError(
                f"cannot write {rel}: {exc.strerror or exc}", path=str(target)
            ) from None
        self.written.append(rel)
        return True

    def copy(self, source, relpath) -> bool:
        """Copy a file into the output unless size and mtime say it is there."""
        rel = normalise_output_path(relpath)
        target = self.resolve(rel)
        source = Path(source)
        self.outputs.add(rel)
        try:
            here = source.stat()
            try:
                there = target.stat()
            except OSError:
                there = None
            same = (
                there is not None
                and here.st_size == there.st_size
                and abs(here.st_mtime - there.st_mtime) <= 0.002
            )
            if same:
                self.unchanged.append(rel)
                return False
            target.parent.mkdir(parents=True, exist_ok=True)
            # copy2 keeps the mtime, which is what the check above relies on
            shutil.copy2(source, target)
        except OSError as exc:
            raise BuildError(
                f"cannot copy {source} to {rel}: {exc.strerror or exc}"
            ) from None
        self.written.append(rel)
        return True

    def remove(self, relpath) -> bool:
        """Delete one output file; False when it was not there (or not ours)."""
        rel = normalise_output_path(relpath)
        try:
            target = self.resolve(rel)
        except BuildError:
            # a path from an old or tampered cache: never follow it out
            return False
        if target.is_symlink() or not target.is_file():
            return False
        try:
            target.unlink()
        except OSError:
            return False
        self.removed.append(rel)
        self._prune(target.parent)
        return True

    def remove_stale(self, previous: Iterable[str]) -> list[str]:
        """Delete files an earlier build wrote that this one did not produce."""
        gone = []
        for rel in sorted(set(previous) - self.outputs):
            if self.remove(rel):
                gone.append(rel)
        return gone

    def _prune(self, directory: Path) -> None:
        """Remove directories left empty, stopping at the output root."""
        root = self.output_dir.resolve()
        current = directory
        while current != root and root in current.parents:
            with contextlib.suppress(OSError):
                os.rmdir(current)
            if current.exists():
                break
            current = current.parent
