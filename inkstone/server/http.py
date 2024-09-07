from __future__ import annotations

import email.utils
import errno
import html
import http.server
import mimetypes
import os
import re
import select
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
import zlib
from datetime import timezone
from http import HTTPStatus
from typing import Callable

from . import websocket
from .errors import ServerError
from .livereload import SCRIPT_TAG, SCRIPT_URL, SOCKET_URL, LiveReloadHub, client_script

RESERVED_PREFIX = "/__inkstone__/"

# Our own table comes first: the stdlib one defers to the registry on Windows
# and to /etc/mime.types elsewhere, and both are full of surprises.
MIME_TYPES = {
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "application/xhtml+xml",
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".jsonld": "application/ld+json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".xml": "application/xml",
    ".rss": "application/rss+xml",
    ".atom": "application/atom+xml",
    ".xsl": "text/xsl",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".ics": "text/calendar",
    ".vtt": "text/vtt",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".bmp": "image/bmp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject",
    ".wasm": "application/wasm",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".mov": "video/quicktime",
}

_INDEX_NAMES = ("index.html", "index.htm")
_PAGE_SUFFIXES = ("", ".html", ".htm")
_CHUNK = 64 * 1024
_IDLE_POLL = 0.2
_PORT_ATTEMPTS = 20
_RANGE = re.compile(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*$", re.ASCII | re.IGNORECASE)

_NOT_FOUND_PAGE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>404 Not Found</title>
<style>
body {{
  margin: 14vh auto 0;
  max-width: 36rem;
  padding: 0 1.5rem;
  color: #26272b;
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
h1 {{ margin: 0; font-size: 4rem; line-height: 1.1; color: #b4b6c0; }}
code {{ padding: 0.1em 0.3em; border-radius: 3px; background: #f0f0f3; }}
.foot {{ margin-top: 3rem; color: #8b8d98; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>404</h1>
<p>Nothing is being served at <code>{path}</code>.</p>
{hint}<p class="foot">inkstone dev server. Add a <code>404.html</code> to the
site to replace this page.</p>
</body>
</html>
"""


def guess_type(path: str) -> str:
    """Content-Type for a file name, charset included where it makes sense."""
    ext = os.path.splitext(path)[1].lower()
    ctype = MIME_TYPES.get(ext)
    if ctype is None:
        ctype = mimetypes.guess_type("name" + ext)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype.endswith(("/json", "+json", "/xml", "+xml")):
        ctype += "; charset=utf-8"
    return ctype


def normalize_base_path(value: str | None) -> str:
    """Turn ``blog``, ``/blog`` or ``https://example.org/blog/`` into ``/blog/``."""
    value = value or "/"
    if "://" in value:
        value = urllib.parse.urlsplit(value).path
    value = value.strip("/")
    return f"/{value}/" if value else "/"


def site_url(host: str, port: int, base_path: str = "/") -> str:
    """Something to click on or hand to a browser."""
    if host in ("", "0.0.0.0"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}{base_path}"


def split_target(target: str) -> tuple[str, str]:
    """Split a request target into its decoded path and the raw query string.

    Raises ValueError if the path doesn't decode to sensible text.
    """
    if not target.startswith("/"):
        # absolute form, which only proxies are supposed to send
        parts = urllib.parse.urlsplit(target)
        if not parts.scheme or not parts.netloc:
            raise ValueError(f"unsupported request target {target!r}")
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
    path, _, query = target.partition("?")
    path = path.partition("#")[0]
    # http.server decodes the request line as latin-1. Going back to bytes
    # gets both %-escapes and raw UTF-8 (which some clients send) right.
    # FIXME: not quite all raw UTF-8. http.server splits the request line
    # with str.split(), so a character whose encoding contains 0x85 or 0xA0
    # ("à", for one) is taken for whitespace before we ever see the path.
    path = urllib.parse.unquote_to_bytes(path.encode("latin-1")).decode("utf-8")
    if "\0" in path:
        raise ValueError("NUL in request path")
    return path, query


def resolve(root: str, path: str) -> tuple[str, str | None]:
    """Work out what a site-relative URL path refers to.

    Returns ``("file", filename)``, ``("redirect", url_path)`` for a directory
    asked for without its trailing slash, or ``("missing", None)``.
    """
    # TODO: on Windows and macOS this happily serves /About for about.html,
    # which then 404s on a real (case-sensitive) host.
    parts = _segments(path)
    if parts is None:
        return "missing", None
    target = os.path.join(root, *parts)
    # isfile() throughout, never exists(): on Windows NUL, CON and the other
    # device names "exist" in every directory.
    if not parts or path.endswith("/"):
        for name in _INDEX_NAMES:
            candidate = os.path.join(target, name)
            if os.path.isfile(candidate):
                return "file", candidate
        return "missing", None
    if os.path.isfile(target):
        return "file", target
    if os.path.isfile(target + ".html"):
        return "file", target + ".html"
    if os.path.isdir(target):
        return "redirect", "/" + "/".join(parts) + "/"
    return "missing", None


def parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Parse a single-range ``Range`` header into inclusive (start, end).

    Returns None when the header should simply be ignored (another unit,
    several ranges, nonsense) and raises ValueError when it is well-formed
    but can't be satisfied for a file of ``size`` bytes.
    """
    match = _RANGE.match(header)
    if match is None:
        return None
    first, last = match.groups()
    if not first:
        if not last:
            return None
        # suffix form: the last N bytes
        length = int(last)
        if length == 0 or size == 0:
            raise ValueError("unsatisfiable suffix range")
        return max(size - length, 0), size - 1
    start = int(first)
    end = int(last) if last else size - 1
    if last and end < start:
        return None
    if start >= size:
        raise ValueError("range starts past the end of the file")
    return start, min(end, size - 1)


def inject_script(page: bytes, snippet: bytes) -> bytes:
    """Insert ``snippet`` just before the closing body tag.

    The last one, since earlier ones can sit inside code samples. Pages
    without one get it before ``</html>``, or simply at the end.
    """
    lowered = page.lower()
    for marker in (b"</body", b"</html"):
        at = lowered.rfind(marker)
        if at != -1:
            return page[:at] + snippet + page[at:]
    return page + snippet


def _segments(path: str) -> list[str] | None:
    """Split a URL path into file name components.

    None means the path can't be mapped safely into the served directory.
    """
    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif "\\" in part:
            return None
        elif os.name == "nt" and (":" in part or part[-1] in ". "):
            # Drive letters and alternate data streams, plus names Windows
            # quietly trims into something else (".. " is the nasty one).
            return None
        else:
            parts.append(part)
    return parts


def _looks_like_page(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _PAGE_SUFFIXES


def _etag_matches(header: str, etag: str) -> bool:
    """Weak comparison of an If-None-Match value against our ETag."""
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def _http_date(value: str) -> float | None:
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.timestamp()


def _not_found_page(path: str, base_path: str) -> bytes:
    hint = ""
    if base_path != "/" and not path.startswith(base_path):
        link = html.escape(urllib.parse.quote(base_path))
        hint = (
            f'<p>This site is served under <a href="{link}">'
            f"<code>{html.escape(base_path)}</code></a>.</p>\n"
        )
    page = _NOT_FOUND_PAGE.format(path=html.escape(path), hint=hint)
    return page.encode("utf-8")


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "inkstone"
    # Applies to reads and writes in the middle of a request. Waiting for
    # the next request on a kept-alive connection is done in handle().
    timeout = 10
    idle_timeout = 15

    def setup(self):
        super().setup()
        self.url_path = ""
        self.server.track(self.connection)

    def finish(self):
        try:
            super().finish()
        finally:
            self.server.untrack(self.connection)

    def version_string(self):
        return self.server_version

    def handle(self):
        self.close_connection = False
        while not self.close_connection and self._wait_for_request():
            self.handle_one_request()

    def do_GET(self):
        self._respond(head=False)

    def do_HEAD(self):
        self._respond(head=True)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self):
        # whatever body came with it is still unread, so don't reuse this
        self.close_connection = True
        self._send_bytes(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "text/plain; charset=utf-8",
            b"This is a static file server: GET and HEAD only.\n",
            headers={"Allow": "GET, HEAD, OPTIONS", "Connection": "close"},
        )

    do_POST = do_PUT = do_PATCH = do_DELETE = _method_not_allowed

    def log_request(self, code="-", size="-"):
        if isinstance(code, HTTPStatus):
            code = code.value
        path = getattr(self, "path", "-")
        self.server.app.log_access(self.command or "-", path, code)

    def log_error(self, format, *args):
        # send_error() and request timeouts end up here; the access line
        # already says what needs saying
        pass

    def _wait_for_request(self) -> bool:
        """Wait until the next request starts arriving on this connection.

        A recv() blocked in one thread can't be interrupted from another on
        Windows, so instead of blocking, idle connections wait here in short
        select() calls with an eye on the server's closing flag.
        """
        if self._buffered():
            return True
        deadline = time.monotonic() + self.idle_timeout
        while not self.server.closing:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                wait = min(remaining, _IDLE_POLL)
                readable, _, _ = select.select([self.connection], [], [], wait)
            except (OSError, ValueError):
                return False
            if readable:
                return True
        return False

    def _buffered(self) -> bytes:
        """Bytes rfile has read ahead of us, without blocking for more.

        That is either a pipelined request or websocket frames sent right
        behind the handshake.
        """
        self.connection.setblocking(False)
        try:
            return self.rfile.peek()
        except OSError:
            return b""
        finally:
            self.connection.settimeout(self.timeout)

    def _respond(self, head: bool) -> None:
        app = self.server.app
        try:
            path, query = split_target(self.path)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Malformed request path")
            return
        self.url_path = path
        if path.startswith(RESERVED_PREFIX):
            self._reserved(path, head)
            return

        rel = app.strip_base(path)
        if rel is None:
            if path == "/" or path + "/" == app.base_path:
                self._redirect(app.base_path, query, HTTPStatus.FOUND)
            else:
                self._not_found(head)
            return
        kind, target = resolve(app.root, rel)
        if kind == "redirect":
            location = app.base_path.rstrip("/") + target
            self._redirect(location, query, HTTPStatus.MOVED_PERMANENTLY)
        elif kind == "missing":
            self._not_found(head)
        elif (
            app.error_page is not None and app.hub is None and _looks_like_page(target)
        ):
            # no live-reload client to put up an overlay, so a broken build
            # has to be announced in place of the (stale) pages themselves
            self._send_page(HTTPStatus.INTERNAL_SERVER_ERROR, app.error_page, head)
        else:
            self._send_file(target, head)

    def _reserved(self, path: str, head: bool) -> None:
        hub = self.server.app.hub
        if hub is not None and path == SCRIPT_URL:
            body = client_script()
            etag = f'"{zlib.crc32(body):08x}"'
            if _etag_matches(self.headers.get("If-None-Match", ""), etag):
                self._send_not_modified({"ETag": etag})
                return
            ctype = "text/javascript; charset=utf-8"
            self._send_bytes(HTTPStatus.OK, ctype, body, head, {"ETag": etag})
        elif hub is not None and path == SOCKET_URL:
            self._upgrade(hub)
        else:
            ctype = "text/plain; charset=utf-8"
            self._send_bytes(HTTPStatus.NOT_FOUND, ctype, b"Not found\n", head)

    def _upgrade(self, hub: LiveReloadHub) -> None:
        self.close_connection = True
        try:
            if not self._same_origin():
                raise websocket.HandshakeError(
                    "cross-origin websocket connections are refused", 403
                )
            key = websocket.check_handshake(self.command, self.headers)
        except websocket.HandshakeError as exc:
            self.wfile.write(websocket.rejection_response(exc))
            return
        pending = self._buffered()
        self.wfile.write(websocket.handshake_response(key))
        ws = websocket.WebSocket(self.connection, initial=pending)
        ws.path = self.url_path
        self.server.track_websocket(ws)
        try:
            hub.serve(ws)
        finally:
            self.server.untrack_websocket(ws)
            ws.abort()

    def _same_origin(self) -> bool:
        """Only pages we served ourselves get to open the socket.

        Otherwise any site open in the same browser could connect to a local
        dev server and read along as build errors (file paths, source
        excerpts) go by.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # not a browser
        host = self.headers.get("Host", "")
        return urllib.parse.urlsplit(origin).netloc.lower() == host.lower()

    def _send_file(self, path: str, head: bool, status: int = HTTPStatus.OK) -> None:
        app = self.server.app
        try:
            f = open(path, "rb")
        except FileNotFoundError:
            # removed between resolving and opening; rebuilds do that
            self._not_found(head)
            return
        except OSError:
            # on Windows, usually a file the build is still writing
            ctype = "text/plain; charset=utf-8"
            self._send_bytes(HTTPStatus.FORBIDDEN, ctype, b"Can't read file\n", head)
            return
        with f:
            info = os.fstat(f.fileno())
            ctype = guess_type(path)
            size = info.st_size
            body = None
            if app.hub is not None and ctype.startswith("text/html"):
                body = inject_script(f.read(), SCRIPT_TAG)
                size = len(body)
            # the size is that of what actually goes out, so turning
            # live reload on or off changes the tag
            etag = f'"{info.st_mtime_ns:x}-{size:x}"'
            validators = {
                "ETag": etag,
                "Last-Modified": email.utils.formatdate(info.st_mtime, usegmt=True),
                "Accept-Ranges": "bytes",
            }

            start, end = 0, size - 1
            if status == HTTPStatus.OK:
                if self._not_modified(etag, info.st_mtime):
                    self._send_not_modified(validators)
                    return
                requested = self.headers.get("Range")
                if requested and self._range_applies(etag, info.st_mtime):
                    try:
                        span = parse_range(requested, size)
                    except ValueError:
                        self._send_bytes(
                            HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                            "text/plain; charset=utf-8",
                            b"Requested range not satisfiable\n",
                            head,
                            {"Content-Range": f"bytes */{size}"},
                        )
                        return
                    if span is not None:
                        start, end = span
                        status = HTTPStatus.PARTIAL_CONTENT
            else:
                # a 404 page isn't something to revalidate or resume
                validators = {}

            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            for name, value in validators.items():
                self.send_header(name, value)
            self._cache_headers()
            self.end_headers()
            if head:
                return
            if body is not None:
                self.wfile.write(body[start : end + 1])
            else:
                self._copy(f, start, length)

    def _copy(self, f, start: int, length: int) -> None:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(_CHUNK, remaining))
            if not chunk:
                # the file shrank under us, and Content-Length has already
                # promised more than there is
                self.close_connection = True
                return
            self.wfile.write(chunk)
            remaining -= len(chunk)

    def _not_modified(self, etag: str, mtime: float) -> bool:
        tags = self.headers.get("If-None-Match")
        if tags is not None:
            # when both are sent, If-Modified-Since is to be ignored
            return _etag_matches(tags, etag)
        since = _http_date(self.headers.get("If-Modified-Since", ""))
        return since is not None and int(mtime) <= since

    def _range_applies(self, etag: str, mtime: float) -> bool:
        condition = self.headers.get("If-Range")
        if condition is None:
            return True
        if condition.startswith(('"', "W/")):
            return condition == etag
        return _http_date(condition) == int(mtime)

    def _not_found(self, head: bool) -> None:
        app = self.server.app
        if app.error_page is not None and _looks_like_page(self.url_path):
            # more likely missing because the build broke than a bad link
            self._send_page(HTTPStatus.INTERNAL_SERVER_ERROR, app.error_page, head)
            return
        custom = os.path.join(app.root, "404.html")
        if os.path.isfile(custom):
            self._send_file(custom, head, HTTPStatus.NOT_FOUND)
            return
        page = _not_found_page(self.url_path, app.base_path)
        self._send_page(HTTPStatus.NOT_FOUND, page, head)

    def _redirect(self, path: str, query: str, status: int) -> None:
        location = urllib.parse.quote(path)
        if query:
            location += "?" + query
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self._cache_headers()
        self.end_headers()

    def _send_page(self, status: int, page: bytes, head: bool) -> None:
        if self.server.app.hub is not None:
            # also on error pages: that's what brings the browser back once
            # the missing page exists or the build is fixed
            page = inject_script(page, SCRIPT_TAG)
        self._send_bytes(status, "text/html; charset=utf-8", page, head)

    def _send_bytes(
        self,
        status: int,
        ctype: str,
        body: bytes,
        head: bool = False,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self._cache_headers()
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _send_not_modified(self, validators: dict[str, str]) -> None:
        self.send_response(HTTPStatus.NOT_MODIFIED)
        for name, value in validators.items():
            self.send_header(name, value)
        self._cache_headers()
        self.end_headers()

    def _cache_headers(self) -> None:
        value = self.server.app.cache_control
        if value:
            self.send_header("Cache-Control", value)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    # On Windows SO_REUSEADDR means "let me bind even though someone else is
    # listening there", which would make the port-in-use check worthless.
    allow_reuse_address = os.name != "nt"
    allow_reuse_port = False
    # How long handle_request() waits for a connection. Stopping doesn't
    # depend on it (see _wake), it's only the fallback.
    timeout = 0.5

    def __init__(self, address: tuple[str, int], app: StaticServer):
        self.app = app
        self.closing = False
        self._connections: dict[socket.socket, threading.Thread] = {}
        self._websockets: set[websocket.WebSocket] = set()
        self._lock = threading.Lock()
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, _Handler)

    def server_bind(self):
        # HTTPServer.server_bind() calls socket.getfqdn(), which can sit in
        # a reverse DNS lookup for seconds. Nothing here uses server_name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def serve(self) -> None:
        """Accept connections until ``closing`` is set."""
        # Not serve_forever(): its shutdown() can only be as prompt as the
        # poll interval, and a short one means waking up all day for nothing.
        while not self.closing:
            self.handle_request()

    def verify_request(self, request, client_address):
        # turns away latecomers, the connection made by _wake() among them
        return not self.closing

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # the browser went away mid-response; it does that
        super().handle_error(request, client_address)

    def track(self, conn: socket.socket) -> None:
        with self._lock:
            self._connections[conn] = threading.current_thread()

    def untrack(self, conn: socket.socket) -> None:
        with self._lock:
            self._connections.pop(conn, None)

    def track_websocket(self, ws: websocket.WebSocket) -> None:
        with self._lock:
            self._websockets.add(ws)

    def untrack_websocket(self, ws: websocket.WebSocket) -> None:
        with self._lock:
            self._websockets.discard(ws)

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def close_connections(self, timeout: float = 2.0) -> None:
        """Hang up on everyone and give the handler threads a moment to exit."""
        with self._lock:
            websockets = list(self._websockets)
            connections = list(self._connections.items())
        for ws in websockets:
            ws.abort()
        for conn, _ in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = time.monotonic() + timeout
        for _, thread in connections:
            thread.join(max(0.0, deadline - time.monotonic()))


class StaticServer:
    """Serves a directory the way a static host would.

    Given a ``LiveReloadHub`` it also injects the live-reload script into
    HTML pages, serves that script and passes websocket connections on to
    the hub.
    """

    def __init__(
        self,
        root: str | os.PathLike,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        port_fallback: bool = False,
        base_path: str = "/",
        hub: LiveReloadHub | None = None,
        cache_control: str | None = "no-cache",
        log: Callable[[str], None] | None = None,
    ):
        self.root = os.path.abspath(os.fspath(root))
        self.host = host
        self.port = port
        self.port_fallback = port_fallback
        self.base_path = normalize_base_path(base_path)
        self.hub = hub
        # "no-cache" still lets browsers keep a copy as long as they
        # revalidate it, which is what the ETags are for
        self.cache_control = cache_control
        # While set (to a complete HTML document), a build is known to be
        # broken and this is shown where a page can't be.
        self.error_page: bytes | None = None
        self._log = log
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        """(host, port); the real ones once the server has started."""
        if self._httpd is None:
            return self.host, self.port
        host, port = self._httpd.server_address[:2]
        return host, port

    @property
    def url(self) -> str:
        return site_url(*self.address, self.base_path)

    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def connection_count(self) -> int:
        return 0 if self._httpd is None else self._httpd.connection_count

    def start(self) -> None:
        if self._httpd is not None:
            raise ServerError("the server is already running")
        self._httpd = self._bind()
        self._thread = threading.Thread(
            target=self._httpd.serve, name="inkstone-http", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is None:
            return
        httpd.closing = True
        _wake(httpd.server_address)
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        httpd.server_close()
        httpd.close_connections()

    def strip_base(self, path: str) -> str | None:
        """The part of a URL path below base_path; None if it's outside."""
        if self.base_path == "/":
            return path
        if path.startswith(self.base_path):
            return path[len(self.base_path) - 1 :]
        return None

    def log(self, line: str) -> None:
        if self._log is not None:
            self._log(line)

    def log_access(self, method: str, path: str, status) -> None:
        if not path.startswith(RESERVED_PREFIX):
            self.log(f"{method} {path} {status}")

    def _bind(self) -> _Server:
        if not 0 <= self.port <= 65535:
            raise ServerError(f"{self.port} is not a valid port number")
        ports = [self.port]
        if self.port_fallback and self.port:
            ports += range(self.port + 1, min(self.port + _PORT_ATTEMPTS, 65536))
        for port in ports:
            try:
                return _Server((self.host, port), self)
            except OSError as exc:
                if not _port_unavailable(exc):
                    reason = exc.strerror or str(exc)
                    raise ServerError(
                        f"can't listen on {self.host}:{port}: {reason}"
                    ) from exc
        if len(ports) > 1:
            raise ServerError(f"no free port between {ports[0]} and {ports[-1]}")
        raise ServerError(f"port {self.port} is already in use")


def _wake(address) -> None:
    """Make a throwaway connection so a thread blocked in accept() returns."""
    host, port = address[:2]
    # the wildcard addresses can be listened on but, on Windows, not called
    if host in ("", "0.0.0.0"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    try:
        socket.create_connection((host, port), timeout=0.5).close()
    except OSError:
        pass  # the accept loop's own timeout gets there a little later


def _port_unavailable(exc: OSError) -> bool:
    if exc.errno == errno.EADDRINUSE:
        return True
    # Windows answers "access denied" for ports inside a reserved range
    # (Hyper-V and WSL grab big chunks); the next port may well be fine.
    # Elsewhere EACCES means a privileged port, and so will its neighbours.
    return os.name == "nt" and exc.errno == errno.EACCES
