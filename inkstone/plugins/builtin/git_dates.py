"""``updated`` from the git history, for pages that do not set it themselves.

What is wanted per file is ``git log -1 --format=%cI -- <file>``. Starting
git once per page gets slow quickly, so one pass over the log of the
content directory answers for nearly all of them and the per-file command
is kept for the few it misses. Without git, or outside a repository, the
plugin does nothing at all.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

from ...utils import log
from ..base import Plugin
from ._common import front_matter, lookup, source_file

_TIMEOUT = 20


class GitDates(Plugin):
    name = "git_dates"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self._top: Path | None = None
        self._dates: dict[str, dt.datetime | None] = {}
        self._tracked: set[str] | None = None

    def git(self, *args: str) -> str | None:
        """Output of a git command run at the site root; None if it failed."""
        root = lookup(self.config, "root") or "."
        try:
            done = subprocess.run(
                ["git", "-c", "core.quotepath=off", *args],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            # no git on the path, or one that hangs
            return None
        return done.stdout if done.returncode == 0 else None

    def _key(self, path) -> str | None:
        """A file as git names it: relative to the top of the work tree."""
        try:
            rel = Path(path).resolve().relative_to(self._top)
        except ValueError:
            return None
        return os.path.normcase(rel.as_posix())

    def _scan(self) -> bool:
        """Read the last commit date of everything below the content dir."""
        self._dates = {}
        self._tracked = None
        top = self.git("rev-parse", "--show-toplevel")
        if not top or not top.strip():
            self._top = None
            return False
        self._top = Path(top.strip()).resolve()
        where = str(lookup(self.config, "content_path") or ".")

        tracked = self.git("ls-files", "--full-name", "--", where)
        if tracked is not None:
            self._tracked = {os.path.normcase(name) for name in tracked.splitlines()}
        history = self.git("log", "--format=%x00%cI", "--name-only", "--", where)
        for commit in (history or "").split("\x00"):
            lines = [line for line in commit.splitlines() if line.strip()]
            if len(lines) < 2:
                continue
            when = _parse(lines[0])
            for name in lines[1:]:
                # newest commit first, so the first date seen is the one
                self._dates.setdefault(os.path.normcase(name), when)
        return True

    def last_commit(self, path) -> dt.datetime | None:
        """When the last commit touching ``path`` was made, if any."""
        if self._top is None:
            return None
        key = self._key(path)
        if key is None:
            return None
        if key not in self._dates:
            if self._tracked is not None and key not in self._tracked:
                # never committed; no point in asking
                self._dates[key] = None
            else:
                # e.g. a file that only ever changed in a merge commit,
                # which --name-only does not list
                out = self.git("log", "-1", "--format=%cI", "--", str(path))
                self._dates[key] = _parse(out or "")
        return self._dates[key]

    def content_loaded(self, site) -> None:
        pages = []
        for page in getattr(site, "all_pages", None) or site.pages:
            if getattr(page, "updated", None) is not None:
                continue
            if front_matter(page, "updated") is not None:
                continue
            path = source_file(page, self.config)
            if path is not None:
                pages.append((page, path))
        if not pages:
            return
        if not self._scan():
            log.debug("git_dates: no git repository here, leaving dates alone")
            return
        zone = lookup(self.config, "tzinfo")
        for page, path in pages:
            when = self.last_commit(path)
            if when is None:
                continue
            if zone is not None:
                when = when.astimezone(zone)
            date = getattr(page, "date", None)
            if date is not None and _day(when, date) <= date.date():
                # committed the day it was written: that is not an update
                continue
            page.updated = when


def _parse(text: str) -> dt.datetime | None:
    text = text.strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _day(when: dt.datetime, reference: dt.datetime) -> dt.date:
    """The calendar day of ``when`` in the time zone ``reference`` is in."""
    if reference.tzinfo is not None:
        when = when.astimezone(reference.tzinfo)
    return when.date()
