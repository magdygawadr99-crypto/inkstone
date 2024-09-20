"""``width`` and ``height`` on ``<img>`` tags whose files we can find.

With the size known up front the browser reserves the space and the text
does not jump when the image arrives. Only local files are looked at; an
image on another host would mean a network request during the build.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from urllib.parse import unquote

from ...assets import AssetError, image_info
from ...errors import InkstoneError
from ...utils import log, paths
from ..base import Plugin
from . import _html
from ._common import lookup, setting, site_prefix


def _number(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if value.endswith("px"):
        value = value[:-2]
    return int(value) if value.isdigit() and int(value) > 0 else None


class ImageDims(Plugin):
    name = "image_dims"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.lazy = setting(self, "lazy", True)
        self.async_decoding = setting(self, "async", True)
        # the first images of a page are probably above the fold; loading
        # those lazily only delays them
        self.eager = setting(self, "eager", 0, minimum=0)
        self._sizes: dict[Path, tuple[int, int] | None] = {}
        self._resources: dict[str, Path] = {}
        self._static: list[Path] | None = None

    def content_loaded(self, site) -> None:
        self._sizes = {}
        self._static = None
        self._resources = {}
        files = list(getattr(site, "resources", ()))
        for page in getattr(site, "all_pages", None) or site.pages:
            files += getattr(page, "resources", None) or ()
        for resource in files:
            path = self._resource_file(resource)
            if path is not None:
                self._resources[resource.url] = path

    def _resource_file(self, resource) -> Path | None:
        path = getattr(resource, "path", None)
        if path is not None:
            return Path(path)
        content = lookup(self.config, "content_path")
        source = getattr(resource, "source_path", None)
        if content is not None and source:
            return Path(content) / source
        return None

    def _static_dirs(self) -> list[Path]:
        """Where static files come from, the site's own directory first."""
        if self._static is None:
            found = []
            try:
                from ...build.templates import static_search_path, theme_chain

                themes = theme_chain(self.config)
                found = list(reversed(static_search_path(self.config, themes)))
            except (ImportError, AttributeError, TypeError, InkstoneError):
                # a bare config object, or a theme that is not there (which
                # the builder complains about loudly enough on its own)
                static = lookup(self.config, "static_path")
                if static is not None:
                    found = [Path(static)]
            output = lookup(self.config, "output_path")
            if output is not None:
                # last resort: something an earlier build put there
                found.append(Path(output))
            self._static = found
        return self._static

    def locate(self, page, src: str) -> Path | None:
        """The file behind an image URL, if it is one of ours."""
        if paths.is_external(src) or src.startswith("#"):
            return None
        url = unquote(src.partition("#")[0].partition("?")[0])
        if not url:
            return None
        if not url.startswith("/"):
            for resource in getattr(page, "resources", None) or ():
                if resource.name == url:
                    return self._resource_file(resource)
            here = getattr(page, "url", "/") or "/"
            if not here.endswith("/"):
                here = posixpath.dirname(here) + "/"
            url = posixpath.normpath(posixpath.join(here, url))
        else:
            prefix = site_prefix(self.config)
            if prefix and url.startswith(prefix + "/"):
                url = url[len(prefix) :]
        if url in self._resources:
            return self._resources[url]
        for directory in self._static_dirs():
            try:
                candidate = paths.safe_join(directory, url)
            except ValueError:
                return None
            if candidate.is_file():
                return candidate
        return None

    def size(self, path: Path) -> tuple[int, int] | None:
        # FIXME replacing an image in static/ with one of another size does
        # not re-render the pages that show it; only bundle resources are
        # part of a page's cache key. `inkstone build --clean` sorts it out.
        if path not in self._sizes:
            try:
                info = image_info(path)
                self._sizes[path] = (info.width, info.height)
            except AssetError as exc:
                log.verbose("image_dims: %s", exc)
                self._sizes[path] = None
        return self._sizes[path]

    def _dimensions(self, page, tag: _html.Tag) -> None:
        if tag.has("width") and tag.has("height"):
            return
        src = tag.get("src")
        path = self.locate(page, src) if src else None
        size = self.size(path) if path is not None else None
        if size is None or not all(size):
            return
        width, height = size
        given_width = _number(tag.get("width"))
        given_height = _number(tag.get("height"))
        if tag.has("width") or tag.has("height"):
            # one side was set by hand: fill in the other to keep the shape
            if given_width is not None:
                tag.set("height", str(round(given_width * height / width)))
            elif given_height is not None:
                tag.set("width", str(round(given_height * width / height)))
            return
        tag.set("width", str(width))
        tag.set("height", str(height))

    def page_html(self, page, html):
        markup = str(html)
        if "<img" not in markup:
            return html
        seen = 0

        def handle(tag: _html.Tag) -> None:
            nonlocal seen
            seen += 1
            self._dimensions(page, tag)
            if self.lazy and seen > self.eager:
                tag.setdefault("loading", "lazy")
            if self.async_decoding:
                tag.setdefault("decoding", "async")

        return _html.rewrite(markup, handle, ("img",))
