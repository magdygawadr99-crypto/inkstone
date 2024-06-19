from __future__ import annotations

import base64
import hashlib
import posixpath
import re
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote, unquote, urlsplit

from . import css as _css
from . import html as _html

if TYPE_CHECKING:
    from .manifest import Manifest

_SRI_ALGORITHMS = ("sha256", "sha384", "sha512")
_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*:")
_URL_ATTRS = frozenset(["src", "href", "poster", "data", "data-src", "xlink:href"])
_SRCSET_ATTRS = frozenset(["srcset", "imagesrcset", "data-srcset"])
_INTEGRITY_RELS = frozenset(["stylesheet", "preload", "modulepreload"])
_SRCSET_GAP_RE = re.compile(r"[\s,]*")
_NON_SPACE_RE = re.compile(r"\S+")


def content_hash(data: bytes, length: int = 8) -> str:
    """Short hex digest used in fingerprinted file names."""
    return hashlib.sha256(data).hexdigest()[:length]


def insert_hash(path: str, digest: str) -> str:
    """`css/style.css` + `3f9a1c2e` -> `css/style.3f9a1c2e.css`.

    The hash goes before the last extension so servers still pick the right
    content type. Names without one (LICENSE, .htaccess) get it appended.
    """
    head, name = posixpath.split(path.replace("\\", "/"))
    stem, dot, ext = name.rpartition(".")
    if dot and stem:
        name = f"{stem}.{digest}.{ext}"
    else:
        name = f"{name}.{digest}"
    return posixpath.join(head, name)


def fingerprint_name(path: str, data: bytes, *, length: int = 8) -> str:
    """Name for `path` with a hash of its contents worked in."""
    return insert_hash(path, content_hash(data, length))


def sri_hash(data: bytes, algo: str = "sha384") -> str:
    """Subresource Integrity value, e.g. `sha384-oqVu...`."""
    if algo not in _SRI_ALGORITHMS:
        raise ValueError(f"unsupported SRI algorithm {algo!r}")
    digest = hashlib.new(algo, data).digest()
    return algo + "-" + base64.b64encode(digest).decode("ascii")


def is_local_ref(url: str) -> bool:
    """False for other sites, data: and friends, and bare #fragments."""
    url = url.strip()
    if not url or url.startswith(("#", "?", "//")):
        return False
    return _SCHEME_RE.match(url) is None


def _base_prefixes(base_url: str) -> tuple[str, ...]:
    """Spellings of the site root that an absolute reference may start with."""
    full = base_url.rstrip("/") + "/"
    path = urlsplit(base_url).path.rstrip("/") + "/"
    return (full, path) if full != path else (path,)


def resolve_ref(
    url: str, *, from_path: str = "", base_url: str = "/"
) -> tuple[str, bool] | None:
    """Work out which asset a reference points at.

    `from_path` is the file doing the referring (relative to the site root),
    so relative references can be followed. Returns the logical path and
    whether the reference was absolute, or None if it leaves the site.
    """
    target, _suffix = _css.split_suffix(url.strip())
    if not target or target.startswith("//"):
        return None
    for prefix in _base_prefixes(base_url):
        if target.startswith(prefix):
            logical = posixpath.normpath(unquote(target[len(prefix) :]))
            return (logical, True) if logical != "." else None
    if not is_local_ref(target) or target.startswith("/"):
        return None
    joined = posixpath.join(posixpath.dirname(from_path), unquote(target))
    logical = posixpath.normpath(joined)
    if logical.startswith("..") or logical == ".":
        return None
    return logical, False


def map_ref(
    url: str, manifest: Manifest, *, from_path: str = "", base_url: str = "/"
) -> str | None:
    """New spelling of `url` once assets are fingerprinted, or None to keep it.

    Query strings and fragments ride along, and a relative reference stays
    relative.
    """
    resolved = resolve_ref(url, from_path=from_path, base_url=base_url)
    if resolved is None:
        return None
    logical, absolute = resolved
    entry = manifest.get(logical)
    if entry is None or entry.output == logical:
        return None
    stripped = url.strip()
    target, suffix = _css.split_suffix(stripped)
    if absolute:
        prefix = next(p for p in _base_prefixes(base_url) if target.startswith(p))
        return prefix + quote(entry.output) + suffix
    here = posixpath.dirname(from_path) or "."
    relative = posixpath.relpath(entry.output, here)
    if target.startswith("./"):
        relative = "./" + relative
    return quote(relative) + suffix


def rewrite_css(
    css: str, manifest: Manifest, *, css_path: str = "", base_url: str = "/"
) -> str:
    """Point every url() in a stylesheet at the fingerprinted file."""

    def fix(url: str) -> str | None:
        return map_ref(url, manifest, from_path=css_path, base_url=base_url)

    return _css.rewrite_urls(css, fix, path=css_path or None)


def rewrite_srcset(value: str, fix: Callable[[str], str | None]) -> str:
    """Apply `fix` to each URL of a srcset, keeping descriptors and spacing."""
    out: list[str] = []
    pos = 0
    while pos < len(value):
        gap = _SRCSET_GAP_RE.match(value, pos)
        out.append(gap.group())
        pos = gap.end()
        if pos >= len(value):
            break
        url = _NON_SPACE_RE.match(value, pos).group()
        pos += len(url)
        # commas are legal inside a URL (think data:), only trailing ones
        # separate candidates
        bare = url.rstrip(",")
        out.append(fix(bare) or bare)
        if bare != url:
            out.append(url[len(bare) :])
            continue
        comma = value.find(",", pos)
        stop = comma if comma >= 0 else len(value)
        out.append(value[pos:stop])
        pos = stop
    return "".join(out)


def _wants_integrity(tok: _html.Token) -> str | None:
    """Name of the URL attribute to protect, if this tag takes integrity."""
    if tok.get("integrity") is not None:
        return None
    if tok.name == "script":
        return "src"
    if tok.name == "link":
        rels = (tok.get("rel") or "").lower().split()
        if _INTEGRITY_RELS.intersection(rels):
            return "href"
    return None


def rewrite_html(
    html: str,
    manifest: Manifest,
    *,
    page_path: str = "",
    base_url: str = "/",
    integrity: bool = False,
) -> str:
    """Swap asset references in a page for their fingerprinted names.

    Looks at src, href, poster and srcset attributes, url() in style
    attributes and in <style> blocks. Everything else is passed through
    byte for byte. With `integrity`, scripts and stylesheets that we built
    also get an integrity attribute.
    """

    def fix(url: str) -> str | None:
        return map_ref(url, manifest, from_path=page_path, base_url=base_url)

    def fix_css(text: str) -> str:
        return _css.rewrite_urls(text, fix, path=page_path or None)

    edits: list[tuple[int, int, str]] = []
    opener = None
    for tok in _html.tokenize(html, page_path or None):
        if tok.type == "raw" and opener is not None and opener.name == "style":
            edits.append((tok.pos, tok.pos + len(tok.data), fix_css(tok.data)))
        if tok.type != "start":
            continue
        opener = tok
        if tok.name == "base":
            continue
        guarded = _wants_integrity(tok) if integrity else None
        for attr in tok.attrs:
            value = attr.value
            if not value:
                continue
            name = attr.name.lower()
            new = None
            if name == "data" and tok.name != "object":
                continue
            if name in _URL_ATTRS:
                new = fix(value)
                if name == guarded:
                    found = resolve_ref(value, from_path=page_path, base_url=base_url)
                    entry = manifest.get(found[0]) if found else None
                    if entry is not None:
                        at = attr.end + len(attr.quote)
                        edits.append((at, at, f' integrity="{entry.integrity}"'))
            elif name in _SRCSET_ATTRS:
                new = rewrite_srcset(value, fix)
            elif name == "style" and "url(" in value.lower() and "&" not in value:
                new = fix_css(value)
            if new is not None and new != value:
                edits.append((attr.start, attr.end, new))

    edits.sort(key=lambda edit: edit[0])
    out: list[str] = []
    last = 0
    for start, end, text in edits:
        out.append(html[last:start])
        out.append(text)
        last = end
    out.append(html[last:])
    return "".join(out)
