"""`inkstone serve`: build, serve the output, rebuild when something changes.

No live reload yet, you still have to hit F5.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import time
from pathlib import Path

from .errors import InkstoneError
from .server.watcher import Watcher
from .site import build


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # browsers hold on to the css otherwise
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def serve(src: Path, out: Path, host="127.0.0.1", port=8000, drafts=False):
    def rebuild(changes=None):
        started = time.perf_counter()
        try:
            count = build(src, out, drafts=drafts)
        except InkstoneError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return
        took = time.perf_counter() - started
        what = f" ({changes.summary()})" if changes else ""
        print(f"built {count} pages in {took:.2f}s{what}")

    rebuild()
    watched = [p for p in (src / "content", src / "templates", src / "static") if p.exists()]
    config = src / "inkstone.toml"
    if config.exists():
        watched.append(config)
    watcher = Watcher(watched, callback=rebuild, debounce=0)
    watcher.start()

    handler = functools.partial(_Handler, directory=str(out))
    httpd = _Server((host, port), handler)
    print(f"serving {out} at http://{host}:{port}/ (ctrl-c to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        watcher.stop()
        httpd.server_close()
