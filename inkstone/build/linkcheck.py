"""Checking the links of a built site (`inkstone check`)."""

from __future__ import annotations

import posixpath
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..content.validate import Problem
from ..utils.fs import walk_files

__all__ = ["LinkChecker", "Problem"]

# (tag, attribute) pairs that hold a URL, and whether a miss is an image
# TODO: url() in style attributes and <meta http-equiv="refresh"> targets
_URL_ATTRS = {
    ("a", "href"): False,
    ("area", "href"): False,
    ("link", "href"): False,
    ("script", "src"): False,
    ("iframe", "src"): False,
    ("img", "src"): True,
    ("source", "src"): False,
    ("video", "src"): False,
    ("video", "poster"): True,
    ("audio", "src"): False,
    ("track", "src"): False,
    ("embed", "src"): False,
    ("object", "data"): False,
    ("input", "src"): True,
}
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "about:", "blob:")
# rel values on <link> that point at things a static host may not have
_UNCHECKED_RELS = frozenset({"preconnect", "dns-prefetch", "canonical", "me"})
_USER_AGENT = "inkstone-linkcheck"


class _Reference:
    __slots__ = ("url", "line", "image")

    def __init__(self, url: str, line: int, image: bool):
        self.url = url
        self.line = line
        self.image = image


class _PageScanner(HTMLParser):
    """Collects the ids a page defines and the URLs it refers to."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.refs: list[_Reference] = []
        self.base: str | None = None

    def handle_starttag(self, tag, attrs):
        values = {name: value for name, value in attrs if value is not None}
        line = self.getpos()[0]
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "a" and "name" in values:
            self.ids.add(values["name"])
        if tag == "base" and "href" in values:
            self.base = values["href"]
            return
        if tag == "link":
            rels = set(values.get("rel", "").lower().split())
            if rels & _UNCHECKED_RELS:
                return
        for (wanted_tag, attr), image in _URL_ATTRS.items():
            if tag == wanted_tag and attr in values:
                self.refs.append(_Reference(values[attr].strip(), line, image))
        if "srcset" in values and tag in ("img", "source"):
            for candidate in _split_srcset(values["srcset"]):
                self.refs.append(_Reference(candidate, line, True))

    handle_startendtag = handle_starttag


def _split_srcset(value: str) -> list[str]:
    """URLs of a srcset: ``a.png 1x, b.png 2x`` -> ``["a.png", "b.png"]``."""
    urls = []
    for candidate in value.split(","):
        parts = candidate.split()
        if parts:
            urls.append(parts[0])
    return urls


class LinkChecker:
    """Walks the HTML files of an output directory and checks what they link to.

    Internal references are checked against the files on disk, fragments
    against the ids of the page they point into. External links are only
    fetched with ``external=True``, since that needs a network and patience.
    """

    def __init__(
        self,
        output_dir,
        *,
        base_url: str = "",
        external: bool = False,
        timeout: float = 10,
    ):
        self.output_dir = Path(output_dir)
        self.external = external
        self.timeout = timeout
        self.base_url = base_url or ""
        parts = urlsplit(self.base_url)
        self.host = parts.netloc.lower()
        path = parts.path or "/"
        self.base_path = path if path.endswith("/") else path + "/"
        self.problems: list[Problem] = []
        self.checked = 0
        self._ids: dict[str, set[str] | None] = {}
        self._external_cache: dict[str, str | None] = {}

    def html_files(self) -> list[str]:
        if not self.output_dir.is_dir():
            return []
        return [
            path.relative_to(self.output_dir).as_posix()
            for path in walk_files(self.output_dir, include_hidden=True)
            if path.suffix.lower() in (".html", ".htm")
        ]

    def run(self) -> list[Problem]:
        self.problems = []
        self.checked = 0
        self._ids = {}
        for rel in self.html_files():
            self._check_file(rel)
        self.problems.sort(key=lambda problem: problem.sort_key)
        return self.problems

    def _scan(self, rel: str) -> _PageScanner | None:
        try:
            text = (self.output_dir / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        scanner = _PageScanner()
        try:
            scanner.feed(text)
            scanner.close()
        except Exception:
            # html.parser is forgiving, but a truncated file can still trip it;
            # whatever was collected before that is good enough
            pass
        return scanner

    def _ids_of(self, rel: str) -> set[str] | None:
        if rel not in self._ids:
            scanner = self._scan(rel)
            self._ids[rel] = scanner.ids if scanner is not None else None
        return self._ids[rel]

    def _check_file(self, rel: str) -> None:
        scanner = self._scan(rel)
        if scanner is None:
            return
        self._ids[rel] = scanner.ids
        seen: set[str] = set()
        for ref in scanner.refs:
            if not ref.url or ref.url in seen:
                continue
            seen.add(ref.url)
            self.checked += 1
            self._check_reference(rel, ref, scanner)

    def _report(self, kind: str, rel: str, ref: _Reference, message: str) -> None:
        self.problems.append(Problem(kind, rel, message, target=ref.url, line=ref.line))

    def _check_reference(self, rel: str, ref: _Reference, scanner) -> None:
        url = ref.url
        lowered = url.lower()
        if lowered.startswith(_SKIP_SCHEMES):
            return
        parts = urlsplit(url)
        if parts.scheme or url.startswith("//"):
            if parts.scheme in ("http", "https", "") and self._is_ours(parts):
                self._check_internal(rel, ref, parts.path or "/", parts.fragment)
            elif parts.scheme in ("http", "https", ""):
                self._check_external(rel, ref)
            return
        if not parts.path and not parts.query:
            # "#fragment": an anchor on this very page
            self._check_anchor(rel, rel, ref, parts.fragment)
            return
        path = parts.path
        if not path.startswith("/"):
            base = scanner.base or ""
            if base.startswith("/"):
                here = base if base.endswith("/") else posixpath.dirname(base) + "/"
                path = posixpath.join(here, path)
            else:
                path = posixpath.join("/" + posixpath.dirname(rel), path)
            path = self.base_path.rstrip("/") + posixpath.normpath(path)
            if parts.path.endswith("/") and not path.endswith("/"):
                path += "/"
        self._check_internal(rel, ref, path, parts.fragment)

    def _is_ours(self, parts) -> bool:
        return bool(self.host) and parts.netloc.lower() == self.host

    def _to_file(self, path: str) -> str | None:
        """Output file for a site path, or None when nothing is there."""
        path = unquote(path)
        prefix = self.base_path
        if prefix != "/":
            if path == prefix.rstrip("/"):
                path = "/"
            elif path.startswith(prefix):
                path = "/" + path[len(prefix) :]
            else:
                # outside the part of the host this site lives in
                return None
        rel = posixpath.normpath(path.lstrip("/")) if path.strip("/") else ""
        if rel.startswith(".."):
            return None
        candidates = []
        if not rel or path.endswith("/"):
            candidates.append(posixpath.join(rel, "index.html"))
        else:
            # what a static file server does with /about: the file, about.html
            # (GitHub Pages, Netlify), or a redirect to about/
            candidates += [rel, rel + ".html", posixpath.join(rel, "index.html")]
        for candidate in candidates:
            if (self.output_dir / candidate).is_file():
                return candidate
        return None

    def _check_internal(self, rel: str, ref: _Reference, path: str, fragment: str):
        target = self._to_file(path)
        if target is None:
            if ref.image:
                self._report("missing-image", rel, ref, "image not found")
            else:
                self._report("broken-link", rel, ref, "no such page or file")
            return
        if fragment and target.endswith((".html", ".htm")):
            self._check_anchor(rel, target, ref, fragment)

    def _check_anchor(self, rel: str, target: str, ref: _Reference, fragment: str):
        fragment = unquote(fragment)
        if not fragment or fragment == "top":
            # "#" and "#top" scroll to the top of the page by definition
            return
        if fragment.startswith(":~:"):
            return
        ids = self._ids_of(target)
        if ids is None or fragment in ids:
            return
        where = "this page" if target == rel else target
        self._report(
            "missing-anchor", rel, ref, f"nothing with id {fragment!r} on {where}"
        )

    def _check_external(self, rel: str, ref: _Reference) -> None:
        if not self.external:
            return
        url = ref.url if not ref.url.startswith("//") else "https:" + ref.url
        url = url.partition("#")[0]
        if url not in self._external_cache:
            self._external_cache[url] = self._fetch(url)
        failure = self._external_cache[url]
        if failure is not None:
            self._report("external-link", rel, ref, failure)

    def _fetch(self, url: str) -> str | None:
        """None when the URL answers, else a short description of what went wrong."""
        last = "no answer"
        # some servers refuse HEAD outright, so ask again with GET before
        # calling a link dead
        for method in ("HEAD", "GET"):
            request = urllib.request.Request(
                url, method=method, headers={"User-Agent": _USER_AGENT}
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                if status < 400:
                    return None
                last = f"HTTP {status}"
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code not in (403, 405, 501):
                    break
            except (urllib.error.URLError, OSError, ValueError) as exc:
                reason = getattr(exc, "reason", exc)
                last = f"cannot connect: {reason}"
                break
        return last
