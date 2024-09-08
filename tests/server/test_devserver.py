from __future__ import annotations

import http.client
import threading
import time
from pathlib import Path

import pytest

from inkstone.errors import ContentError, InkstoneError
from inkstone.server import ChangeSet, DevServer, ServerError, websocket
from inkstone.server.livereload import SCRIPT_TAG, SCRIPT_URL, SOCKET_URL

from .helpers import fetch, receive, wait_for


@pytest.fixture
def source(tmp_path):
    """A source directory next to the built site."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "page.md").write_bytes(b"first draft")
    return src


@pytest.fixture
def start(site):
    servers = []

    def _start(**options):
        options.setdefault("port", 0)
        options.setdefault("debounce", 0.03)
        options.setdefault("poll_interval", 0.02)
        server = DevServer(options.pop("root", site), **options)
        server.start()
        servers.append(server)
        return server

    yield _start
    for server in servers:
        server.stop()


@pytest.fixture
def browser(start):
    """Connect the way a page would. Depends on ``start`` so that the clients
    are closed before the servers they talk to."""
    clients = []

    def _open(server):
        ws = websocket.connect(*server.address, SOCKET_URL)
        clients.append(ws)
        assert receive(ws)["type"] == "hello"
        return ws

    yield _open
    for ws in clients:
        ws.close()


def test_public_names():
    import inkstone.server as package

    for name in ("DevServer", "Watcher", "ChangeSet", "LiveReloadHub", "ServerError"):
        assert name in package.__all__
        assert hasattr(package, name)
    assert issubclass(ServerError, InkstoneError)


def test_address_and_url_before_and_after_start(site):
    server = DevServer(site, port=0)
    assert server.address == ("127.0.0.1", 0)
    assert not server.running
    server.start()
    try:
        host, port = server.address
        assert host == "127.0.0.1"
        assert port > 0
        assert server.url == f"http://127.0.0.1:{port}/"
        assert server.running
    finally:
        server.stop()
    assert not server.running


def test_default_port_is_8000(site):
    server = DevServer(site)
    assert server.address == ("127.0.0.1", 8000)
    assert server.url == "http://127.0.0.1:8000/"


def test_serves_the_site_with_live_reload_wired_in(start, site):
    server = start()
    response, body = fetch(server.address, "/")
    assert response.status == 200
    assert SCRIPT_TAG in body
    assert fetch(server.address, SCRIPT_URL)[0].status == 200
    assert (
        fetch(server.address, "/css/site.css")[1]
        == (site / "css" / "site.css").read_bytes()
    )


def test_live_reload_can_be_switched_off(start, site):
    server = start(livereload=False)
    assert server.hub is None
    assert fetch(server.address, "/")[1] == (site / "index.html").read_bytes()
    assert fetch(server.address, SCRIPT_URL)[0].status == 404


def test_base_path(start):
    server = start(base_path="/docs")
    assert server.url == f"http://127.0.0.1:{server.address[1]}/docs/"
    assert fetch(server.address, "/docs/about")[0].status == 200
    assert fetch(server.address, "/about")[0].status == 404


def test_context_manager(site):
    with DevServer(site, port=0) as server:
        assert fetch(server.address, "/")[0].status == 200
    assert not server.running


def test_starting_twice_is_an_error(start):
    server = start()
    with pytest.raises(ServerError, match="already running"):
        server.start()


def test_port_fallback(start, taken_port):
    lines = []
    server = start(port=taken_port, log=lines.append)
    assert taken_port < server.address[1] < taken_port + 20
    assert f"Port {taken_port} is taken, using {server.address[1]} instead" in lines


def test_taken_port_without_fallback(site, taken_port):
    server = DevServer(site, port=taken_port, port_fallback=False)
    with pytest.raises(ServerError, match="already in use"):
        server.start()
    assert not server.running
    server.stop()


def test_source_change_triggers_rebuild_and_reload(start, browser, source, site):
    seen = []

    def rebuild(changes):
        seen.append(changes)
        (site / "index.html").write_bytes(b"<html><body>second draft</body></html>")

    server = start(watch=[source], rebuild=rebuild)
    ws = browser(server)
    (source / "page.md").write_bytes(b"second draft")

    assert receive(ws) == {"type": "reload", "paths": [], "build": server.hub.build_id}
    assert seen == [ChangeSet(modified=[source / "page.md"])]
    assert b"second draft" in fetch(server.address, "/")[1]


def test_watch_accepts_a_single_path(start, browser, source):
    server = start(watch=str(source), rebuild=lambda changes: None)
    assert server.watch == [source]
    ws = browser(server)
    (source / "another.md").write_bytes(b"x")
    assert receive(ws)["type"] == "reload"


@pytest.mark.parametrize(
    "returned",
    [
        lambda site: [site / "css" / "site.css"],
        lambda site: [str(site / "css" / "site.css")],
        lambda site: ["css/site.css"],
        lambda site: ["css\\site.css"],
        lambda site: ["/css/site.css"],
        lambda site: [Path("css") / "site.css"],
        lambda site: "css/site.css",
        lambda site: (path for path in ["css/site.css"]),
    ],
    ids=[
        "absolute-path",
        "absolute-string",
        "relative",
        "backslashes",
        "url",
        "relative-path",
        "bare-string",
        "generator",
    ],
)
def test_stylesheet_only_rebuild_swaps_css(start, browser, source, site, returned):
    server = start(watch=[source], rebuild=lambda changes: returned(site))
    ws = browser(server)
    (source / "page.md").write_bytes(b"edited")
    message = receive(ws)
    assert (message["type"], message["paths"]) == ("css", ["/css/site.css"])


def test_output_urls_carry_the_base_path(start, browser, source, site):
    outputs = [site / "css" / "site.css", "css/print.css"]
    server = start(watch=[source], rebuild=lambda changes: outputs, base_path="/docs/")
    ws = browser(server)
    (source / "page.md").write_bytes(b"edited")
    assert receive(ws)["paths"] == ["/docs/css/site.css", "/docs/css/print.css"]


def test_rebuild_naming_a_page_reloads_fully(start, browser, source, site):
    outputs = [site / "css" / "site.css", site / "index.html"]
    server = start(watch=[source], rebuild=lambda changes: outputs)
    ws = browser(server)
    (source / "page.md").write_bytes(b"edited")
    message = receive(ws)
    assert message["type"] == "reload"
    assert message["paths"] == ["/css/site.css", "/index.html"]


def test_rebuild_that_changed_no_output_does_not_reload(start, browser, source):
    calls = []
    server = start(watch=[source], rebuild=lambda changes: calls.append(changes) or [])
    ws = browser(server)
    (source / "page.md").write_bytes(b"whitespace  only")
    assert wait_for(lambda: calls)
    with pytest.raises(TimeoutError):
        ws.recv(timeout=0.2)


def test_failed_build_is_shown_until_the_next_good_one(start, browser, source):
    def rebuild(changes):
        if (source / "broken.md").exists():
            raise ContentError("bad front matter", path=source / "broken.md", line=2)

    server = start(watch=[source], rebuild=rebuild)
    ws = browser(server)

    (source / "broken.md").write_bytes(b"---\ntitle: [\n---\n")
    error = receive(ws)
    assert error["type"] == "error"
    assert error["title"] == "Build failed"
    assert "bad front matter" in error["detail"]
    assert "> 2 | title: [" in error["detail"]
    assert "&gt; 2 | title: [" in error["html"]
    assert isinstance(server.last_error, ContentError)
    # a page that isn't there explains itself instead of being a bare 404
    response, body = fetch(server.address, "/not-built-yet/")
    assert response.status == 500
    assert b"bad front matter" in body
    assert fetch(server.address, "/")[0].status == 200

    (source / "broken.md").unlink()
    assert receive(ws) == {"type": "clear"}
    assert receive(ws)["type"] == "reload"
    assert server.last_error is None
    assert fetch(server.address, "/not-built-yet/")[0].status == 404


def test_error_is_shown_to_a_browser_that_opens_later(start, browser, source):
    def rebuild(changes):
        raise ContentError("still broken")

    server = start(watch=[source], rebuild=rebuild)
    (source / "page.md").write_bytes(b"edited")
    assert wait_for(lambda: server.last_error is not None)
    assert wait_for(lambda: server.hub.has_error)
    ws = browser(server)
    assert receive(ws)["detail"] == "still broken"


def test_unexpected_exception_arrives_with_its_traceback(start, browser, source):
    def rebuild(changes):
        raise ZeroDivisionError("a plugin divided by zero")

    server = start(watch=[source], rebuild=rebuild)
    ws = browser(server)
    (source / "page.md").write_bytes(b"edited")
    error = receive(ws)
    assert error["title"] == "Build failed: ZeroDivisionError"
    assert error["detail"].startswith("ZeroDivisionError: a plugin divided by zero")
    assert "Traceback (most recent call last):" in error["detail"]


def test_css_only_fix_still_clears_the_overlay(start, browser, source, site):
    results = iter([RuntimeError("first build breaks"), [site / "css" / "site.css"]])

    def rebuild(changes):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    server = start(watch=[source], rebuild=rebuild)
    ws = browser(server)
    (source / "page.md").write_bytes(b"edit one")
    assert receive(ws)["type"] == "error"
    (source / "page.md").write_bytes(b"edit number two")
    assert receive(ws) == {"type": "clear"}
    assert receive(ws)["type"] == "css"


def test_broken_build_without_live_reload_takes_over_the_pages(start, source):
    def rebuild(changes):
        raise ContentError("no overlay to show this in")

    server = start(livereload=False, watch=[source], rebuild=rebuild)
    (source / "page.md").write_bytes(b"edited")
    assert wait_for(lambda: fetch(server.address, "/")[0].status == 500)
    response, body = fetch(server.address, "/about")
    assert response.status == 500
    assert b"no overlay to show this in" in body
    assert fetch(server.address, "/css/site.css")[0].status == 200


def test_rebuild_returning_nonsense_is_reported_and_survived(start, browser, source):
    results = iter([42, None])
    server = start(watch=[source], rebuild=lambda changes: next(results))
    ws = browser(server)
    (source / "page.md").write_bytes(b"edit one")
    assert receive(ws)["title"] == "Build failed: TypeError"
    (source / "page.md").write_bytes(b"edit number two")
    assert receive(ws) == {"type": "clear"}
    assert receive(ws)["type"] == "reload"


def test_changes_during_a_rebuild_are_coalesced_into_the_next(start, source):
    entered, release = threading.Event(), threading.Event()
    seen = []

    def rebuild(changes):
        seen.append(changes)
        entered.set()
        release.wait(10)

    server = start(watch=[source], rebuild=rebuild)
    (source / "page.md").write_bytes(b"the edit that starts it")
    assert entered.wait(5)
    # the first build is stuck now; pile more work up behind it
    extra = [source / f"extra-{n}.md" for n in range(4)]
    for path in extra:
        server.request_rebuild(ChangeSet(added=[path]))
    server.request_rebuild(ChangeSet(removed=[extra[0]]))
    release.set()

    assert wait_for(lambda: len(seen) == 2)
    server.stop()
    assert seen == [
        ChangeSet(modified=[source / "page.md"]),
        ChangeSet(added=extra[1:]),
    ]


def test_rebuilds_never_overlap(start):
    lock = threading.Lock()
    running = []
    peak = []
    finished = []

    def rebuild(changes):
        with lock:
            running.append(1)
            peak.append(len(running))
        time.sleep(0.01)
        with lock:
            running.pop()
        finished.append(changes)

    server = start(rebuild=rebuild)
    threads = [threading.Thread(target=server.request_rebuild) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert wait_for(lambda: finished)
    server.stop()
    assert max(peak) == 1
    assert 1 <= len(finished) <= 20


def test_request_rebuild_without_a_watcher(start, browser):
    seen = []
    server = start(rebuild=seen.append)
    ws = browser(server)
    server.request_rebuild()
    assert receive(ws)["type"] == "reload"
    assert seen == [ChangeSet()]


def test_without_a_rebuild_the_served_files_are_watched_directly(start, browser, site):
    server = start(watch=[site])
    ws = browser(server)
    (site / "css" / "site.css").write_bytes(b"body { margin: 0; color: teal; }\n")
    message = receive(ws)
    assert (message["type"], message["paths"]) == ("css", ["/css/site.css"])
    (site / "about.html").write_bytes(b"<html><body>About, revised</body></html>")
    message = receive(ws)
    assert (message["type"], message["paths"]) == ("reload", ["/about.html"])


def test_output_inside_the_watched_tree_does_not_retrigger(tmp_path):
    project = tmp_path / "project"
    output = project / "_site"
    output.mkdir(parents=True)
    (project / "index.md").write_bytes(b"one")
    calls = []

    def rebuild(changes):
        calls.append(changes)
        (output / "index.html").write_bytes(b"<p>build %d</p>" % len(calls))

    server = DevServer(
        output,
        port=0,
        watch=[project],
        rebuild=rebuild,
        debounce=0.03,
        poll_interval=0.02,
    )
    server.start()
    try:
        (project / "index.md").write_bytes(b"one, two")
        assert wait_for(lambda: calls)
        # several poll and debounce periods: long enough for a loop to show
        time.sleep(0.3)
        assert calls == [ChangeSet(modified=[project / "index.md"])]
    finally:
        server.stop()


def test_editor_clutter_is_ignored_by_default(start, source):
    calls = []
    start(watch=[source], rebuild=calls.append)
    (source / ".page.md.swp").write_bytes(b"x")
    (source / "page.md~").write_bytes(b"x")
    (source / "real.md").write_bytes(b"x")
    assert wait_for(lambda: calls)
    assert calls[0] == ChangeSet(added=[source / "real.md"])


def test_explicit_ignore_list_replaces_the_default(start, source):
    calls = []
    start(watch=[source], rebuild=calls.append, ignore=["*.draft"])
    (source / "idea.draft").write_bytes(b"x")
    (source / "page.md~").write_bytes(b"x")
    assert wait_for(lambda: calls)
    assert calls[0] == ChangeSet(added=[source / "page.md~"])


def test_status_and_access_lines_go_to_the_log(start, source, site):
    lines = []
    server = start(watch=[source], rebuild=lambda changes: None, log=lines.append)
    assert lines == [f"Serving {site} at {server.url}"]
    fetch(server.address, "/about")
    (source / "page.md").write_bytes(b"edited")
    assert wait_for(lambda: len(lines) == 3)
    assert lines[1] == "GET /about 200"
    assert lines[2].startswith("Rebuilt in ")
    assert lines[2].endswith("(1 modified)")


def test_failed_build_is_logged(start, source):
    lines = []

    def rebuild(changes):
        raise ContentError("bad date", path="posts/a.md", line=3)

    start(watch=[source], rebuild=rebuild, log=lines.append)
    (source / "page.md").write_bytes(b"edited")
    assert wait_for(lambda: len(lines) == 2)
    assert lines[1] == "Build failed: posts/a.md:3: bad date"


def test_missing_root_is_only_a_warning(start, tmp_path):
    lines = []
    server = start(root=tmp_path / "not-built", log=lines.append)
    assert lines[0].startswith("Warning: ")
    assert fetch(server.address, "/")[0].status == 404


def test_open_browser(start, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    server = start(open_browser=True)
    assert wait_for(lambda: opened == [server.url])


def test_browser_is_left_alone_by_default(start, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    start()
    assert opened == []


def test_clients_are_told_the_server_is_going_away(start, browser):
    server = start()
    ws = browser(server)
    stopper = threading.Thread(target=server.stop, daemon=True)
    stopper.start()
    with pytest.raises(websocket.ConnectionClosed) as excinfo:
        ws.recv(timeout=5)
    stopper.join(5)
    assert excinfo.value.code == websocket.CLOSE_GOING_AWAY


def test_stop_is_idempotent_and_leaves_no_threads_behind(site, source):
    before = set(threading.enumerate())
    server = DevServer(
        site,
        port=0,
        watch=[source],
        rebuild=lambda changes: None,
        debounce=0.03,
        poll_interval=0.02,
    )
    server.start()
    try:
        ws = websocket.connect(*server.address, SOCKET_URL)
        reader = threading.Thread(target=lambda: list(ws), daemon=True)
        reader.start()
        idle = http.client.HTTPConnection(*server.address, timeout=5)
        idle.request("GET", "/")
        idle.getresponse().read()
        (source / "page.md").write_bytes(b"edited")
    finally:
        started = time.monotonic()
        server.stop()
        server.stop()
    assert time.monotonic() - started < 5
    reader.join(5)
    idle.close()
    assert wait_for(lambda: set(threading.enumerate()) <= before)


def test_stop_waits_for_a_running_build(start, source):
    entered = threading.Event()
    finished = []

    def rebuild(changes):
        entered.set()
        time.sleep(0.1)
        finished.append(changes)

    server = start(watch=[source], rebuild=rebuild)
    (source / "page.md").write_bytes(b"edited")
    assert entered.wait(5)
    server.stop()
    assert len(finished) == 1


def test_server_can_be_restarted(site):
    server = DevServer(site, port=0)
    for _ in range(2):
        server.start()
        try:
            with websocket.connect(*server.address, SOCKET_URL) as ws:
                assert receive(ws)["type"] == "hello"
            assert fetch(server.address, "/")[0].status == 200
        finally:
            server.stop()


def test_serve_forever_returns_once_stopped(site):
    server = DevServer(site, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert wait_for(lambda: server.running)
        assert fetch(server.address, "/")[0].status == 200
    finally:
        server.stop()
    thread.join(5)
    assert not thread.is_alive()


def test_stop_from_another_thread_waits_for_start_to_finish(site):
    in_start, carry_on = threading.Event(), threading.Event()

    def log(line):
        # start() logs this just before it returns
        if line.startswith("Serving "):
            in_start.set()
            carry_on.wait(5)

    server = DevServer(site, port=0, log=log)
    starter = threading.Thread(target=server.serve_forever, daemon=True)
    starter.start()
    assert in_start.wait(5)
    stopper = threading.Thread(target=server.stop, daemon=True)
    stopper.start()
    stopper.join(0.1)
    assert stopper.is_alive()

    carry_on.set()
    stopper.join(5)
    starter.join(5)
    assert not stopper.is_alive()
    assert not starter.is_alive()
    assert not server.running


def test_serve_forever_takes_ctrl_c_as_a_request_to_stop(site, monkeypatch):
    server = DevServer(site, port=0)
    server.start()

    def interrupted(timeout=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(server._done, "wait", interrupted)
    server.serve_forever()
    assert not server.running


def test_serve_forever_passes_on_a_startup_failure(site, taken_port):
    server = DevServer(site, port=taken_port, port_fallback=False)
    with pytest.raises(ServerError):
        server.serve_forever()
    assert not server.running
