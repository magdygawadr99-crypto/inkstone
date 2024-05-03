from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from typing import Callable, Iterable, Optional

from .errors import TemplateError, TemplateNotFound

# (source, file name or None, "is this still current?" or None)
Source = tuple[str, Optional[str], Optional[Callable[[], bool]]]


def split_template_path(name: str) -> list[str]:
    """Split a template name into path segments, refusing to leave the root.

    Template names always use forward slashes, whatever the platform.
    """
    parts = []
    for part in name.split("/"):
        if (
            part == os.pardir
            or os.sep in part
            or (os.altsep and os.altsep in part)
            or os.path.splitdrive(part)[0]
        ):
            raise TemplateNotFound(name)
        if part and part != os.curdir:
            parts.append(part)
    if not parts:
        raise TemplateNotFound(name)
    return parts


class BaseLoader:
    """Loaders turn a template name into source text.

    get_source() returns (source, filename, uptodate). `filename` is None for
    templates that don't live in a file, and `uptodate` is a function that
    tells whether the source is still what get_source() would return now
    (None if it can't change).
    """

    def get_source(self, name: str) -> Source:
        raise TemplateNotFound(name)

    def list_templates(self) -> list[str]:
        return []


class FileSystemLoader(BaseLoader):
    """Loads templates from one or more directories, searched in order."""

    def __init__(
        self,
        searchpath: str | os.PathLike | Iterable[str | os.PathLike],
        encoding: str = "utf-8",
        followlinks: bool = False,
    ):
        if isinstance(searchpath, (str, os.PathLike)):
            searchpath = [searchpath]
        self.searchpath = [os.fspath(path) for path in searchpath]
        self.encoding = encoding
        self.followlinks = followlinks

    def _locate(self, name: str) -> tuple[str, int] | None:
        parts = split_template_path(name)
        for root in self.searchpath:
            path = os.path.join(root, *parts)
            try:
                info = os.stat(path)
            except (OSError, ValueError):
                # ValueError is what a NUL byte in the name gets us
                continue
            if stat.S_ISREG(info.st_mode):
                return path, info.st_mtime_ns
        return None

    def get_source(self, name: str) -> Source:
        found = self._locate(name)
        if found is None:
            raise TemplateNotFound(name)
        path, mtime = found
        try:
            with open(path, encoding=self.encoding) as f:
                source = f.read()
        except UnicodeDecodeError as exc:
            raise TemplateError(
                f"can't read the template as {self.encoding}: {exc}", path=path
            ) from exc
        # Windows editors like to put a BOM in front, we don't want it in the
        # middle of a page once the template gets included somewhere
        if source.startswith("\ufeff"):
            source = source[1:]

        def uptodate() -> bool:
            # Looking the name up again, instead of just checking the mtime,
            # also catches a file that now shadows this one from a directory
            # earlier in the search path.
            return self._locate(name) == (path, mtime)

        return source, path, uptodate

    def list_templates(self) -> list[str]:
        found = set()
        for root in self.searchpath:
            walker = os.walk(root, followlinks=self.followlinks)
            for dirpath, _dirnames, filenames in walker:
                for filename in filenames:
                    full = os.path.join(dirpath, filename)
                    found.add(os.path.relpath(full, root).replace(os.sep, "/"))
        return sorted(found)


class DictLoader(BaseLoader):
    """Loads templates from a dict of name -> source. Mostly for tests."""

    def __init__(self, mapping: Mapping[str, str]):
        self.mapping = mapping

    def get_source(self, name: str) -> Source:
        if name not in self.mapping:
            raise TemplateNotFound(name)
        source = self.mapping[name]
        return source, None, lambda: self.mapping.get(name) == source

    def list_templates(self) -> list[str]:
        return sorted(self.mapping)


class ChoiceLoader(BaseLoader):
    """Asks several loaders in turn and takes the first that has the template."""

    def __init__(self, loaders: Iterable[BaseLoader]):
        self.loaders = list(loaders)

    def get_source(self, name: str) -> Source:
        for loader in self.loaders:
            try:
                return loader.get_source(name)
            except TemplateNotFound:
                continue
        raise TemplateNotFound(name)

    def list_templates(self) -> list[str]:
        found: set[str] = set()
        for loader in self.loaders:
            found.update(loader.list_templates())
        return sorted(found)
