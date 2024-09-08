from __future__ import annotations

import os
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Iterable

from . import overlay
from .errors import ServerError
from .http import StaticServer, normalize_base_path, site_url
from .livereload import LiveReloadHub
from .watcher import DEFAULT_IGNORE, ChangeSet, Watcher

# how long stop() waits for a build that is still running
_STOP_GRACE = 5.0


class DevServer:
    """Static file server, source watcher and live reload, wired together.

    Building is the caller's business. ``rebuild`` is called with a ChangeSet
    whenever watched files change, never more than one call at a time; it
    may return the output files it touched (absolute, or relative to
    ``root``) so that a stylesheet-only change can skip the full page
    reload. If it raises, browsers show the error until a later build works.

    Without a ``rebuild`` the watched files are taken to be the served ones,
    which makes this a plain live-reloading file server.
    """

    def __init__(
        self,
        root: str | os.PathLike,
        host: str = "127.0.0.1",
        port: int = 8000,
        port_fallback: bool = True,
        watch: Iterable[str | os.PathLike] = (),
        ignore: Iterable[str] | None = None,
        rebuild: Callable[[ChangeSet], Iterable[str] | None] | None = None,
        livereload: bool = True,
        base_path: str = "/",
        open_browser: bool = False,
        debounce: float = 0.25,
        poll_interval: float = 0.5,
        log: Callable[[str], None] | None = None,
    ):
        self.root = Path(os.path.abspath(root))
        self.host = host
        self.port = port
        self.port_fallback = port_fallback
        if isinstance(watch, (str, os.PathLike)):
            watch = [watch]
        self.watch = [Path(p) for p in watch]
        # None means the usual editor and VCS clutter; a list replaces it
        self.ignore = list(DEFAULT_IGNORE if ignore is None else ignore)
        self.rebuild = rebuild
        self.base_path = normalize_base_path(base_path)
        self.open_browser = open_browser
        self.debounce = debounce
        self.poll_interval = poll_interval
        self.hub = LiveReloadHub() if livereload else None
        self.last_error: Exception | None = None
        self._log = log
        self._http: StaticServer | None = None
        self._watcher: Watcher | None = None
        self._worker: threading.Thread | None = None
        # start() and stop() can come from different threads (serve_forever
        # on one, a signal handler or a test on another) and must not
        # interleave. Reentrant, in case a log callback decides to stop us.
        self._lifecycle = threading.RLock()
        self._cond = threading.Condition()
        self._pending: ChangeSet | None = None
        self._running = False
        self._done = threading.Event()

    def __enter__(self) -> DevServer:
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def address(self) -> tuple[str, int]:
        """(host, port) actually bound; before start(), the ones asked for."""
        if self._http is None:
            return self.host, self.port
        return self._http.address

    @property
    def url(self) -> str:
        return site_url(*self.address, self.base_path)

    def start(self) -> None:
        """Start serving and watching in the background."""
        with self._lifecycle:
            if self._running:
                raise ServerError("the dev server is already running")
            server = StaticServer(
                self.root,
                host=self.host,
                port=self.port,
                port_fallback=self.port_fallback,
                base_path=self.base_path,
                hub=self.hub,
                log=self._log,
            )
            server.start()
            self._http = server
            self._done.clear()
            self._running = True
            if self.hub is not None:
                self.hub.start()
            self._worker = threading.Thread(
                target=self._rebuild_loop, name="inkstone-rebuild", daemon=True
            )
            self._worker.start()
            if self.watch:
                # With a build in between, the output must not be able to
                # trigger the build that writes it.
                exclude = [self.root] if self.rebuild is not None else []
                self._watcher = Watcher(
                    self.watch,
                    ignore=self.ignore,
                    exclude=exclude,
                    callback=self.request_rebuild,
                    debounce=self.debounce,
                    poll_interval=self.poll_interval,
                )
                self._watcher.start()

            if not self.root.is_dir():
                self.log(f"Warning: {self.root} doesn't exist (yet)")
            port = self.address[1]
            if self.port and port != self.port:
                self.log(f"Port {self.port} is taken, using {port} instead")
            self.log(f"Serving {self.root} at {self.url}")
            if self.open_browser:
                # webbrowser.open() can block for a while on some desktops
                threading.Thread(
                    target=webbrowser.open,
                    args=(self.url,),
                    name="inkstone-browser",
                    daemon=True,
                ).start()

    def serve_forever(self) -> None:
        """Serve until stop() is called or the user hits Ctrl-C."""
        try:
            if not self._running:
                self.start()
            # an untimed wait() can't be interrupted by Ctrl-C on Windows
            while not self._done.wait(0.5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """Shut everything down. Fine to call twice, and from any thread."""
        with self._lifecycle:
            with self._cond:
                if not self._running:
                    return
                self._running = False
                self._cond.notify_all()
            if self._watcher is not None:
                self._watcher.stop()
                self._watcher = None
            worker, self._worker = self._worker, None
            if worker is not None and worker is not threading.current_thread():
                worker.join(_STOP_GRACE)
            if self.hub is not None:
                self.hub.close()
            self._http.stop()
            self._done.set()

    def request_rebuild(self, changes: ChangeSet | None = None) -> None:
        """Queue a rebuild, as if ``changes`` had just been noticed.

        Returns immediately. Requests that pile up while a build is running
        are folded into a single follow-up build.
        """
        if changes is None:
            changes = ChangeSet()
        with self._cond:
            if self._pending is not None:
                changes = self._pending.merge(changes)
            self._pending = changes
            self._cond.notify_all()

    def log(self, line: str) -> None:
        if self._log is not None:
            self._log(line)

    def _rebuild_loop(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and self._running:
                    self._cond.wait()
                if not self._running:
                    return
                changes, self._pending = self._pending, None
            self._rebuild_once(changes)

    def _rebuild_once(self, changes: ChangeSet) -> None:
        started = time.monotonic()
        try:
            result = self.rebuild(changes) if self.rebuild is not None else None
            # inside the try on purpose: a build returning something odd
            # should land in the overlay, not kill this thread
            outputs = self._changed_urls(result, changes)
        except Exception as exc:
            self._build_failed(exc)
            return
        was_broken = self.last_error is not None
        self.last_error = None
        self._http.error_page = None
        if self.rebuild is not None:
            took = _format_duration(time.monotonic() - started)
            self.log(f"Rebuilt in {took} ({changes.summary()})")
        else:
            self.log(f"Reloading ({changes.summary()})")
        if self.hub is None:
            return
        if was_broken:
            self.hub.broadcast_clear()
        if outputs is None or outputs:
            self.hub.broadcast_reload(outputs)

    def _build_failed(self, exc: Exception) -> None:
        self.last_error = exc
        title, detail = overlay.describe_error(exc)
        page = overlay.render_error_page(title, detail)
        self._http.error_page = page.encode("utf-8")
        self.log(f"Build failed: {detail.splitlines()[0]}")
        if self.hub is not None:
            self.hub.broadcast_error(title, detail)

    def _changed_urls(self, result, changes: ChangeSet) -> list[str] | None:
        """URLs of the output files that changed; None if there's no telling.

        An empty list is a build saying that nothing came out differently.
        """
        if result is not None:
            if isinstance(result, (str, os.PathLike)):
                result = [result]
            return [self._url_for(path) for path in result]
        if self.rebuild is not None:
            return None
        urls = []
        for path in changes.paths:
            rel = self._below_root(path)
            if rel is None:
                return None
            urls.append(self.base_path + rel)
        return urls or None

    def _url_for(self, path) -> str:
        rel = self._below_root(path)
        if rel is None:
            # already relative to the root, or as good as a URL
            rel = os.fspath(path).replace("\\", "/").lstrip("/")
        return self.base_path + rel

    def _below_root(self, path) -> str | None:
        path = os.fspath(path)
        if not os.path.isabs(path):
            return None
        try:
            rel = os.path.relpath(path, self.root)
        except ValueError:
            return None  # another drive
        if rel == os.curdir or rel.split(os.sep, 1)[0] == os.pardir:
            return None
        return rel.replace(os.sep, "/")


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.2f} s"
