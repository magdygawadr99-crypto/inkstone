from __future__ import annotations

import contextlib
import hashlib
import itertools
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Iterator

from ..errors import ContentError
from .glob import GlobSet

_WINDOWS = os.name == "nt"
_tmp_counter = itertools.count()

# copy2 carries the mtime over exactly on NTFS, ext4 and APFS. On coarser
# filesystems (FAT) the times never line up and we simply copy every time.
_MTIME_SLOP = 0.002


def ensure_dir(path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path, *, normalize_newlines: bool = True) -> str:
    """Read a text file as UTF-8, dropping a byte order mark if present.

    Line endings come back as "\\n" unless ``normalize_newlines`` is off.
    Files that are not valid UTF-8 raise ContentError pointing at the line
    with the offending byte.
    """
    raw = Path(path).read_bytes()
    # Windows Notepad's "Unicode" is UTF-16 with a BOM
    utf16 = raw[:2] in (b"\xff\xfe", b"\xfe\xff")
    try:
        text = raw.decode("utf-16" if utf16 else "utf-8-sig")
    except UnicodeDecodeError as exc:
        name = "UTF-16" if utf16 else "UTF-8"
        line = raw.count(b"\n", 0, exc.start) + 1
        raise ContentError(
            f"file is not valid {name} text "
            f"(byte 0x{raw[exc.start]:02x} at offset {exc.start})",
            path=path,
            line=line,
        ) from None
    if normalize_newlines:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def atomic_write(path, data: str | bytes, *, encoding: str = "utf-8") -> None:
    """Write ``data`` to ``path`` without ever exposing a half-written file.

    The data goes to a temporary file next to the target which is then
    renamed over it. Missing parent directories are created. Text is
    written as is, with no newline translation.
    """
    path = Path(path)
    if isinstance(data, str):
        data = data.encode(encoding)
    path.parent.mkdir(parents=True, exist_ok=True)
    # not mkstemp: that creates the file with mode 0600, which would stick
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{next(_tmp_counter)}.tmp")
    try:
        with open(tmp, "xb") as handle:
            handle.write(data)
        _replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _replace(src, dst) -> None:
    # On Windows the target can be locked for a moment by a virus scanner
    # or by the dev server reading it; a few short retries get past that.
    for attempt in range(5):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not _WINDOWS or attempt == 4:
                raise
            time.sleep(0.02 * (attempt + 1))


def walk_files(root, *, ignore=(), include_hidden: bool = False) -> Iterator[Path]:
    """Yield the files below ``root`` in a stable order.

    ``ignore`` takes gitignore-style patterns (or a ready GlobSet) that are
    matched against paths relative to ``root``. Dotfiles and dot-directories
    are skipped unless ``include_hidden`` is set.
    """
    root = Path(root)
    skip = ignore if isinstance(ignore, GlobSet) else GlobSet(ignore)
    # with "!" patterns around, a file inside an ignored directory may be
    # wanted after all, so directories cannot be pruned wholesale
    prune = not skip.has_negation

    def wanted(name: str, rel: str, is_dir: bool) -> bool:
        if not include_hidden and name.startswith("."):
            return False
        if is_dir and not prune:
            return True
        return not skip.match(rel, is_dir=is_dir)

    for current, dirnames, filenames in os.walk(root):
        rel_dir = Path(current).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        dirnames[:] = sorted(d for d in dirnames if wanted(d, prefix + d, True))
        for name in sorted(filenames):
            if wanted(name, prefix + name, False):
                yield Path(current, name)


def copy_tree(src, dst, *, ignore=()) -> list[Path]:
    """Copy the files below ``src`` into ``dst``, skipping unchanged ones.

    A file counts as unchanged when size and modification time agree.
    Returns the destination paths that were actually written.
    """
    src, dst = Path(src), Path(dst)
    sources = walk_files(src, ignore=ignore, include_hidden=True)
    return _copy_changed(src, dst, sources)


def sync_tree(src, dst, *, ignore=()) -> tuple[list[Path], list[Path]]:
    """Make ``dst`` mirror ``src``: copy what changed, delete what is stale.

    Returns ``(copied, removed)``. Directories left empty are removed too.
    """
    src, dst = Path(src), Path(dst)
    sources = list(walk_files(src, ignore=ignore, include_hidden=True))
    copied = _copy_changed(src, dst, sources)
    keep = {source.relative_to(src) for source in sources}
    removed = []
    for existing in list(walk_files(dst, include_hidden=True)):
        if existing.relative_to(dst) not in keep:
            _unlink(existing)
            removed.append(existing)
    if removed:
        _remove_empty_dirs(dst)
    return copied, removed


def _copy_changed(src: Path, dst: Path, sources: Iterable[Path]) -> list[Path]:
    copied = []
    for source in sources:
        target = dst / source.relative_to(src)
        if _unchanged(source, target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, target)
        except PermissionError:
            # copy2 also copies the read-only bit, so the copy made last
            # time may now refuse to be overwritten
            _make_writable(target)
            shutil.copy2(source, target)
        copied.append(target)
    return copied


def _unchanged(source: Path, target: Path) -> bool:
    try:
        there = target.stat()
    except OSError:
        return False
    here = source.stat()
    if here.st_size != there.st_size:
        return False
    return abs(here.st_mtime - there.st_mtime) <= _MTIME_SLOP


def _make_writable(path) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IRWXU)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except PermissionError:
        _make_writable(path)
        path.unlink()


def _remove_empty_dirs(root: Path) -> None:
    for current, _dirnames, _filenames in os.walk(root, topdown=False):
        if Path(current) != root:
            # fails for directories that still have something in them
            with contextlib.suppress(OSError):
                os.rmdir(current)


def file_hash(path, algo: str = "sha1") -> str:
    """Hex digest of a file's contents, read in chunks."""
    digest = hashlib.new(algo, usedforsecurity=False)
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def remove_tree(path) -> None:
    """Delete a directory tree; fine if it is already gone.

    Read-only entries (git objects on Windows, mostly) are made writable
    and tried again instead of aborting the whole removal.
    """
    path = Path(path)
    if path.is_symlink() or path.is_file():
        _unlink(path)
        return
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_writable)
    else:
        shutil.rmtree(path, onerror=_retry_writable)


def _retry_writable(func, target, _exc) -> None:
    if func not in (os.unlink, os.rmdir):
        # failed to list or open something; nothing we can fix by chmod
        raise
    # On POSIX it is the containing directory that needs to be writable,
    # on Windows the entry itself. Do both and repeat the failed call.
    _make_writable(os.path.dirname(target))
    _make_writable(target)
    func(target)


@contextlib.contextmanager
def tempdir(prefix: str = "inkstone-") -> Iterator[Path]:
    """A temporary directory as a Path, removed again on exit."""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        remove_tree(path)
