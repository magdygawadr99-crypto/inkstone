from __future__ import annotations

import json
import secrets
import threading
import time
from importlib import resources
from typing import Iterable

from . import overlay, websocket

SCRIPT_URL = "/__inkstone__/livereload.js"
SOCKET_URL = "/__inkstone__/livereload"
SCRIPT_TAG = f'<script src="{SCRIPT_URL}" defer></script>'.encode("ascii")

_GOING_AWAY = "dev server is shutting down"
_CLOSE_GRACE = 1.0


def client_script() -> bytes:
    """The browser half, livereload.js, from next to this module."""
    # Read on every request on purpose: it's small, and it means the client
    # can be edited without restarting the server.
    return resources.files(__package__).joinpath("livereload.js").read_bytes()


def _as_url_path(path) -> str:
    return str(path).replace("\\", "/").partition("?")[0]


def _is_stylesheet(path: str) -> bool:
    return path.lower().endswith(".css")


def _is_sourcemap(path: str) -> bool:
    return path.lower().endswith(".css.map")


class _Client:
    def __init__(self, ws: websocket.WebSocket):
        self.ws = ws
        self.awaiting_pong = False

    def saw_pong(self, payload: bytes) -> None:
        self.awaiting_pong = False


class LiveReloadHub:
    """Keeps track of the browsers that are listening and tells them things.

    The HTTP server hands every upgraded connection to ``serve()``; whoever
    runs builds calls the ``broadcast_*`` methods, from any thread.
    """

    def __init__(self, *, heartbeat: float = 20.0):
        self.heartbeat = heartbeat
        self._clients: list[_Client] = []
        # Held while sending, not just while touching the list: that keeps a
        # greeting and a broadcast from overtaking each other, so a browser
        # that connects mid-build can't end up with stale state. Sends are
        # tiny and time out, so nothing sits on the lock for long.
        self._lock = threading.RLock()
        self._error: dict | None = None
        # Lets a reconnecting browser tell whether it missed a build, and
        # whether it's even talking to the same server process as before.
        self._instance = secrets.token_hex(4)
        self._generation = 0
        self._closed = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def has_error(self) -> bool:
        return self._error is not None

    @property
    def build_id(self) -> str:
        return f"{self._instance}-{self._generation}"

    def start(self) -> None:
        """Reopen a hub that was closed.

        A new hub doesn't need this; the heartbeat starts with the first
        browser that connects.
        """
        with self._lock:
            self._closed = False
            self._ensure_heartbeat()

    def close(self) -> None:
        """Say goodbye to every browser and stop the heartbeat."""
        with self._lock:
            self._closed = True
            clients, self._clients = self._clients, []
            thread, self._thread = self._thread, None
            self._stop.set()
        deadline = time.monotonic() + _CLOSE_GRACE
        for client in clients:
            remaining = max(0.0, deadline - time.monotonic())
            client.ws.close(websocket.CLOSE_GOING_AWAY, _GOING_AWAY, timeout=remaining)
        if thread is not None:
            thread.join()

    def serve(self, ws: websocket.WebSocket) -> None:
        """Look after one browser until it goes away.

        Blocks, so it wants a thread of its own; the HTTP server calls it on
        the connection's handler thread.
        """
        client = _Client(ws)
        ws.on_pong = client.saw_pong
        with self._lock:
            if self._closed:
                ws.close(websocket.CLOSE_GOING_AWAY, _GOING_AWAY, timeout=0)
                return
            self._ensure_heartbeat()
            self._clients.append(client)
            try:
                self._greet(client)
            except websocket.WebSocketError:
                self._drop(client)
                return
        try:
            for _ in ws:
                # Browsers have nothing to tell us yet. Reading is still
                # what answers pings and notices the close.
                pass
        except websocket.WebSocketError:
            pass
        finally:
            self._drop(client)

    def broadcast_reload(self, paths: Iterable[str] | None = None) -> int:
        """Tell every browser the site changed; returns how many heard it.

        ``paths`` are the output files that changed, if known. When they are
        all stylesheets the browsers swap those in place and keep the page;
        anything else, or not knowing, means a full reload.
        """
        urls = [_as_url_path(path) for path in paths or ()]
        styles = [url for url in urls if _is_stylesheet(url)]
        css_only = bool(styles) and all(
            _is_stylesheet(url) or _is_sourcemap(url) for url in urls
        )
        with self._lock:
            self._generation += 1
            self._error = None
            if css_only:
                message = {"type": "css", "paths": styles}
            else:
                message = {"type": "reload", "paths": urls}
            message["build"] = self.build_id
            return self._broadcast(message)

    def broadcast_error(self, title: str, detail: str = "") -> int:
        """Put the error overlay up in every browser.

        The error sticks: browsers that connect later are shown it too, until
        ``broadcast_clear()`` or the next reload.
        """
        message = {
            "type": "error",
            "title": title,
            "detail": detail,
            "html": overlay.render_overlay(title, detail),
        }
        with self._lock:
            self._error = message
            return self._broadcast(message)

    def broadcast_clear(self) -> int:
        with self._lock:
            self._error = None
            return self._broadcast({"type": "clear"})

    def check_clients(self) -> None:
        """One heartbeat: drop whoever ignored the last ping, ping the rest."""
        with self._lock:
            for client in list(self._clients):
                if client.awaiting_pong:
                    self._drop(client)
                    continue
                client.awaiting_pong = True
                try:
                    client.ws.ping()
                except websocket.WebSocketError:
                    self._drop(client)

    def _greet(self, client: _Client) -> None:
        hello = {"type": "hello", "build": self.build_id}
        client.ws.send(json.dumps(hello))
        if self._error is not None:
            client.ws.send(json.dumps(self._error))

    def _broadcast(self, message: dict) -> int:
        data = json.dumps(message)
        delivered = 0
        with self._lock:
            for client in list(self._clients):
                try:
                    client.ws.send(data)
                    delivered += 1
                except websocket.WebSocketError:
                    self._drop(client)
        return delivered

    def _drop(self, client: _Client) -> None:
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        client.ws.abort()

    def _ensure_heartbeat(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop, name="inkstone-heartbeat", daemon=True
        )
        self._thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self.heartbeat):
            self.check_clients()
