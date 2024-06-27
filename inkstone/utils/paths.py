from __future__ import annotations

import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

# At least two characters before the colon, so "C:\site" is not a scheme.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]+:")
_SUFFIX_START = re.compile(r"[?#]")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def is_external(url: str) -> bool:
    """True for absolute URLs (https:, mailto:, //host/...), False for site paths."""
    return url.startswith("//") or _SCHEME.match(url) is not None


def _split_suffix(url: str) -> tuple[str, str]:
    """Separate the path from its ?query and #fragment."""
    match = _SUFFIX_START.search(url)
    if match is None:
        return url, ""
    return url[: match.start()], url[match.start() :]


def url_join(base: str, *parts: str) -> str:
    """Join URL pieces with exactly one slash between them.

    Unlike urllib's urljoin this never throws away part of the base:
    ``url_join("/blog", "post/")`` is ``/blog/post/``. A part that is an
    absolute URL in its own right starts over.
    """
    result = base
    for part in parts:
        if not part:
            continue
        if not result or is_external(part):
            result = part
        else:
            result = result.rstrip("/") + "/" + part.lstrip("/")
    return result


def relative_url(from_url: str, to_url: str) -> str:
    """The relative link leading from the page at ``from_url`` to ``to_url``.

    Both are site paths starting with a slash; a ``from_url`` ending in one
    is taken to be a directory. External and already relative targets are
    returned unchanged.
    """
    if is_external(to_url) or not to_url.startswith("/"):
        return to_url
    target, suffix = _split_suffix(to_url)
    here = _split_suffix(from_url)[0]
    if not here.endswith("/"):
        here = posixpath.dirname(here)
    start = [part for part in here.split("/") if part]
    goal = [part for part in target.split("/") if part]
    shared = 0
    while shared < min(len(start), len(goal)) and start[shared] == goal[shared]:
        shared += 1
    steps = [".."] * (len(start) - shared) + goal[shared:]
    if not steps:
        return "./" + suffix
    link = "/".join(steps)
    if target.endswith("/"):
        link += "/"
    return link + suffix


def path_to_url(path, *, pretty: bool = True) -> str:
    """Site URL for an output file, given relative to the output directory.

    With ``pretty`` the index.html of a directory is addressed by the
    directory itself: ``blog/post/index.html`` -> ``/blog/post/``.
    """
    pieces = str(path).replace("\\", "/").split("/")
    parts = [part for part in pieces if part not in ("", ".")]
    is_index = pretty and bool(parts) and parts[-1] == "index.html"
    if is_index:
        parts.pop()
    url = "/" + "/".join(quote(part) for part in parts)
    if is_index and parts:
        url += "/"
    return url


def url_to_path(url: str, *, index: str = "index.html") -> str:
    """Output file (relative, forward slashes) that a site URL refers to.

    ``/a/b/`` -> ``a/b/index.html``, ``/a/b.html`` -> ``a/b.html``. Query and
    fragment are ignored. Raises ValueError if the URL climbs out of the
    site root.
    """
    if is_external(url):
        path = urlsplit(url).path
    else:
        path = _split_suffix(url)[0]
    path = unquote(path).replace("\\", "/")
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"URL points outside the site: {url!r}")
            parts.pop()
        else:
            parts.append(part)
    if not parts or path.endswith(("/", "/.", "/..")):
        parts.append(index)
    return "/".join(parts)


def normalize_url(url: str) -> str:
    """Tidy up a URL without changing what it points at.

    Lower-cases scheme and host, drops default ports, resolves ``.`` and
    ``..`` and collapses repeated slashes. A trailing slash is kept.
    """
    if not is_external(url):
        path, suffix = _split_suffix(url)
        return _normalize_path(path) + suffix
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if not parts.netloc:
        # mailto:, tel: and friends; nothing in there to normalise
        return urlunsplit(parts._replace(scheme=scheme))
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = host
    if parts.port is not None and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc += f":{parts.port}"
    if "@" in parts.netloc:
        netloc = parts.netloc.rpartition("@")[0] + "@" + netloc
    path = _normalize_path(parts.path) or "/"
    return urlunsplit((scheme, netloc, path, parts.query, parts.fragment))


def _normalize_path(path: str) -> str:
    if not path:
        return path
    absolute = path.startswith("/")
    segments: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment != "..":
            segments.append(segment)
        elif segments and segments[-1] != "..":
            segments.pop()
        elif not absolute:
            # a relative path may keep climbing; an absolute one stops at "/"
            segments.append("..")
    result = "/".join(segments)
    if absolute:
        result = "/" + result
    if not result:
        return "./"
    if path.endswith(("/", "/.", "/..")) or path in (".", ".."):
        result = result.rstrip("/") + "/"
    return result


def safe_join(root, *parts) -> Path:
    """Join ``parts`` onto ``root``, refusing results outside of ``root``.

    Leading slashes are ignored so URL paths can be passed straight in, and
    backslashes count as separators on every platform. Raises ValueError
    when the path would escape (via "..", a drive letter, a symlink...).
    """
    base = Path(root).resolve()
    target = base
    for part in parts:
        target = target / str(part).replace("\\", "/").lstrip("/")
    target = target.resolve()
    if target != base and base not in target.parents:
        requested = "/".join(str(part) for part in parts)
        raise ValueError(f"path {requested!r} escapes {base}")
    return target


def strip_ext(path) -> str:
    """Drop the last extension: ``a/b.tar.gz`` -> ``a/b.tar``.

    Dotfiles such as ``.htaccess`` have no extension to drop.
    """
    text = str(path)
    name_start = max(text.rfind("/"), text.rfind("\\")) + 1
    dot = text.rfind(".")
    if dot <= name_start:
        return text
    return text[:dot]


def ensure_trailing_slash(url: str) -> str:
    """Add a trailing slash to the path part, leaving ?query/#fragment alone."""
    path, suffix = _split_suffix(url)
    if not path.endswith("/"):
        path += "/"
    return path + suffix
