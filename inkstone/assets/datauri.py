from __future__ import annotations

import base64
import posixpath
import re
from urllib.parse import quote, unquote_to_bytes

from .errors import AssetError

# mimetypes reads the registry on Windows and gives different answers on
# different machines, so the types we care about are spelled out here.
_MIME_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".cur": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
    ".wasm": "application/wasm",
}

_TEXT_MIMES = {
    "image/svg+xml",
    "application/json",
    "application/manifest+json",
    "application/xml",
    "application/javascript",
}

# Left alone when percent-encoding. Quotes, <>, # and % always get encoded so
# the result can sit inside url("...") or an HTML attribute unchanged.
_SAFE = "-_.!~*'();/?:@&=+$,"

_DATA_URI_RE = re.compile(
    r"data:(?P<mime>[^;,]*)(?P<params>(?:;[^;,]*)*?)(?P<b64>;base64)?,(?P<data>.*)",
    re.DOTALL | re.IGNORECASE,
)


def guess_mime(path: str, default: str = "application/octet-stream") -> str:
    ext = posixpath.splitext(str(path).replace("\\", "/"))[1].lower()
    return _MIME_TYPES.get(ext, default)


def _is_text(mime: str) -> bool:
    base = mime.split(";", 1)[0].strip().lower()
    return base.startswith("text/") or base in _TEXT_MIMES or base.endswith("+xml")


def data_uri(data: bytes | str, mime: str) -> str:
    """Encode `data` as a data: URI.

    Binary types are always base64. Text types (SVG above all) are tried both
    ways and the shorter one wins, which for SVG is nearly always the
    percent-encoded form.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    b64 = f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    if not _is_text(mime):
        return b64
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return b64
    header = mime
    needs_charset = not text.isascii() and "charset=" not in mime.lower()
    # XML declares its own encoding and defaults to UTF-8; everything else
    # falls back to US-ASCII unless told otherwise.
    if needs_charset and not mime.lower().split(";")[0].endswith("xml"):
        header += ";charset=utf-8"
    encoded = f"data:{header}," + quote(text, safe=_SAFE)
    return encoded if len(encoded) <= len(b64) else b64


def parse_data_uri(uri: str) -> tuple[str, bytes]:
    """Inverse of data_uri: returns (mime, payload)."""
    match = _DATA_URI_RE.fullmatch(uri.strip())
    if match is None:
        raise AssetError(f"not a data URI: {uri[:40]!r}")
    mime = (match["mime"] or "text/plain").strip().lower()
    if match["b64"]:
        try:
            payload = base64.b64decode(match["data"], validate=False)
        except ValueError as exc:
            raise AssetError(f"bad base64 in data URI: {exc}") from None
    else:
        payload = unquote_to_bytes(match["data"])
    return mime, payload
