from __future__ import annotations

import os
import re
import stat
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# Editor and VCS droppings nobody wants a rebuild for. "4913" is the probe
# file vim creates to find out whether it may write to a directory.
DEFAULT_IGNORE = (
    "*.swp",
    "*.swo",
    "*.swx",
    "*~",
    "*.tmp",
    ".#*",
    "#*#",
    "4913",
    ".DS_Store",
    "Thumbs.db",
    "*.pyc",
    "__pycache__/",
    ".git/",
    ".hg/",
    ".svn/",
)

# A file that never stops changing (a log, a download in progress) would keep
# pushing the debounce window back for ever; flush after this long regardless.
_MAX_HOLD = 2.0


@dataclass
class ChangeSet:
    """What changed between two looks at the watched paths."""

    added: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)

    def __post_init__(self):
        self.added = sorted(Path(p) for p in self.added)
        self.modified = sorted(Path(p) for p in self.modified)
        self.removed = sorted(Path(p) for p in self.removed)

    def __len__(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    @property
    def paths(self) -> list[Path]:
        """Every path touched, whatever happened to it."""
        return sorted({*self.added, *self.modified, *self.removed})

    def merge(self, later: ChangeSet) -> ChangeSet:
        """Fold a later batch into this one.

        The result describes the net effect: a file that was added and then
        edited is still just added, one that came and went again isn't
        mentioned at all.
        """
        added, modified, removed = (
            set(self.added),
            set(self.modified),
            set(self.removed),
        )
        for path in later.added:
            if path in removed:
                # deleted and recreated: to anyone downstream that's an edit
                removed.discard(path)
                modified.add(path)
            else:
                added.add(path)
        for path in later.modified:
            if path not in added:
                modified.add(path)
        for path in later.removed:
            if path in added:
                added.discard(path)
            else:
                modified.discard(path)
                removed.add(path)
        return ChangeSet(added, modified, removed)

    def summary(self) -> str:
        counts = (
            (len(self.added), "added"),
            (len(self.modified), "modified"),
            (len(self.removed), "removed"),
        )
        return ", ".join(f"{n} {what}" for n, what in counts if n) or "no changes"


def _glob_to_regex(pattern: str) -> str:
    """Translate a gitignore-flavoured glob.

    ``*`` and ``?`` stay within one path segment, ``**`` crosses them, and
    ``**/`` also matches no directory at all.
    """
    out = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern.startswith("**", i):
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            # start looking one further on so "[]]" and "[!]]" work
            end = pattern.find("]", i + 2)
            if end == -1:
                out.append(re.escape(char))
            else:
                body = pattern[i + 1 : end].replace("\\", "\\\\")
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = end
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


class _IgnoreRules:
    """A small subset of .gitignore.

    A pattern without a slash is matched against the bare name at any depth,
    one with a slash against the path relative to the watched directory, and
    a trailing slash restricts it to directories. There is no ``!`` negation.
    """

    def __init__(self, patterns: Iterable[str]):
        self._rules: list[tuple[re.Pattern[str], bool, bool]] = []
        for raw in patterns:
            pattern = raw.strip()
            if os.sep != "/":
                pattern = pattern.replace(os.sep, "/")
            dirs_only = pattern.endswith("/")
            pattern = pattern.rstrip("/")
            by_path = "/" in pattern
            pattern = pattern.lstrip("/")
            if not pattern:
                continue
            regex = re.compile(_glob_to_regex(pattern))
            self._rules.append((regex, dirs_only, by_path))

    def match(self, rel: str, is_dir: bool) -> bool:
        name = rel.rpartition("/")[2]
        for regex, dirs_only, by_path in self._rules:
            if dirs_only and not is_dir:
                continue
            if regex.fullmatch(rel if by_path else name):
                return True
        return False


class Watcher:
    """Polls files and directory trees and reports what changed.

    Polling isn't glamorous, but it behaves the same everywhere, network
    drives and containers included, and a site's sources are rarely more
    than a few thousand files.
    """

    def __init__(
        self,
        paths: Iterable[str | os.PathLike],
        *,
        ignore: Iterable[str] = (),
        exclude: Iterable[str | os.PathLike] = (),
        callback: Callable[[ChangeSet], None] | None = None,
        debounce: float = 0.25,
        poll_interval: float = 0.5,
    ):
        self.paths = [Path(os.path.abspath(p)) for p in paths]
        self.callback = callback
        self.debounce = debounce
        self.poll_interval = poll_interval
        self._rules = _IgnoreRules(ignore)
        # directories that are skipped wherever the walk runs into them,
        # e.g. the build output when it lives inside a watched source tree
        self._exclude = {os.path.normcase(os.path.abspath(p)) for p in exclude}
        self._snapshot: dict[str, tuple[int, int]] | None = None
        self._scan_lock = threading.Lock()
        self._pending = ChangeSet()
        self._first_change = 0.0
        self._last_change = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Watcher:
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def scan(self) -> ChangeSet:
        """Compare the watched paths with how they looked at the last scan.

        The very first scan only records a baseline and reports nothing.
        """
        with self._scan_lock:
            current = self._take_snapshot()
            previous, self._snapshot = self._snapshot, current
        if previous is None:
            return ChangeSet()
        return ChangeSet(
            added=[p for p in current if p not in previous],
            modified=[p for p, sig in current.items() if previous.get(p, sig) != sig],
            removed=[p for p in previous if p not in current],
        )

    def tick(self, now: float | None = None) -> ChangeSet | None:
        """Scan once and return a batch of changes if one is due.

        Changes are held back until nothing has moved for ``debounce``
        seconds, so an editor's write-rename-touch routine or a branch
        switch comes out as one ChangeSet instead of a dozen.
        """
        if now is None:
            now = time.monotonic()
        changes = self.scan()
        if changes:
            if not self._pending:
                self._first_change = now
            self._pending = self._pending.merge(changes)
            self._last_change = now
        if not self._pending:
            return None
        quiet = now - self._last_change >= self.debounce
        held_long_enough = now - self._first_change >= max(_MAX_HOLD, self.debounce)
        if not (quiet or held_long_enough):
            return None
        batch, self._pending = self._pending, ChangeSet()
        return batch

    def start(self) -> None:
        if self._thread is not None:
            return
        if self._snapshot is None:
            # take the baseline here rather than on the thread, so that
            # nothing saved after start() returns can be missed
            self.scan()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="inkstone-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stop.set()
        if thread is not threading.current_thread():
            thread.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                batch = self.tick()
                if batch and self.callback is not None:
                    self.callback(batch)
            except Exception:
                # a callback blowing up shouldn't end the watching; the next
                # save may well go through
                traceback.print_exc()
            delay = self.poll_interval
            if self._pending:
                # look more often while a batch is forming, or the debounce
                # window would be rounded up to a whole poll interval
                delay = min(delay, max(self.debounce / 4, 0.01))
            self._stop.wait(delay)

    def _take_snapshot(self) -> dict[str, tuple[int, int]]:
        found: dict[str, tuple[int, int]] = {}
        seen_links: set[str] = set()
        for root in self.paths:
            try:
                info = os.stat(root)
            except OSError:
                # fine: if it turns up later its files are reported as added
                continue
            if stat.S_ISDIR(info.st_mode):
                self._walk(str(root), found, seen_links)
            elif not self._rules.match(root.name, False):
                found[str(root)] = (info.st_mtime_ns, info.st_size)
        return found

    def _walk(self, top: str, found: dict, seen_links: set[str]) -> None:
        stack = [(top, "")]
        while stack:
            directory, prefix = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    children = list(entries)
            except OSError:
                # deleted or made unreadable since its parent was listed
                continue
            for entry in children:
                rel = prefix + entry.name
                try:
                    is_dir = entry.is_dir()
                    if self._rules.match(rel, is_dir):
                        continue
                    if not is_dir:
                        info = entry.stat()
                        found[entry.path] = (info.st_mtime_ns, info.st_size)
                        continue
                    if os.path.normcase(entry.path) in self._exclude:
                        continue
                    if entry.is_symlink():
                        # Follow directory links, but only once each, which
                        # is enough to survive a link pointing back up the
                        # tree.
                        target = os.path.realpath(entry.path)
                        if target in seen_links:
                            continue
                        seen_links.add(target)
                except OSError:
                    continue
                stack.append((entry.path, rel + "/"))
