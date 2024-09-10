from __future__ import annotations

import json
import socket
import threading

import pytest

from inkstone.server import LiveReloadHub, StaticServer, websocket
from inkstone.server.livereload import (
    SCRIPT_TAG,
    SCRIPT_URL,
    SOCKET_URL,
    client_script,
)
from inkstone.server.overlay import render_error_page, render_overlay

from .helpers import receive, wait_for


class FakeSocket:
    """Stands in for a WebSocket so the heartbeat can be driven by hand."""

    def __init__(self):
        self.sent = []
        self.pings = 0
        self.on_pong = None
        self.gone = threading.Event()

    def send(self, data):
        self.sent.append(json.loads(data))

    def ping(self, payload=b""):
        self.pings += 1

    def close(self, *args, **kwargs):
        self.gone.set()

    def abort(self):
        self.gone.set()

    def __iter__(self):
        self.gone.wait(10)
        return iter(())


@pytest.fixture
def hub():
    hub = LiveReloadHub(heartbeat=60)
    yield hub
    hub.close()


@pytest.fixture
def server(site, hub):
    server = StaticServer(site, hub=hub)
    server.start()
    yield server
    hub.close()
    server.stop()


@pytest.fixture
def connect(server):
    """Open clients the way a page would; each has its greeting in ``.hello``."""
    clients = []

    def _connect(**options):
        ws = websocket.connect(*server.address, SOCKET_URL, **options)
        clients.append(ws)
        ws.hello = receive(ws)
        return ws

    yield _connect
    for ws in clients:
        ws.close()


@pytest.fixture
def attach(hub):
    """Plug FakeSockets into the hub, each on a thread like a real connection."""
    threads = []

    def _attach(*fakes):
        for fake in fakes:
            thread = threading.Thread(target=hub.serve, args=(fake,), daemon=True)
            thread.start()
            threads.append(thread)
        assert wait_for(lambda: all(fake.sent for fake in fakes))

    yield _attach
    hub.close()
    for thread in threads:
        thread.join(5)


def test_client_is_greeted_and_counted(connect, hub):
    assert hub.client_count == 0
    ws = connect()
    assert ws.hello == {"type": "hello", "build": hub.build_id}
    assert hub.client_count == 1


def test_reload_reaches_every_client(connect, hub):
    clients = [connect() for _ in range(3)]
    assert hub.broadcast_reload() == 3
    for ws in clients:
        assert receive(ws) == {"type": "reload", "paths": [], "build": hub.build_id}


@pytest.mark.parametrize(
    ("paths", "kind", "sent_paths"),
    [
        (["css/site.css"], "css", ["css/site.css"]),
        (["/css/a.css", "/css/B.CSS"], "css", ["/css/a.css", "/css/B.CSS"]),
        (["css\\site.css"], "css", ["css/site.css"]),
        (["css/site.css?v=3"], "css", ["css/site.css"]),
        (["css/site.css", "css/site.css.map"], "css", ["css/site.css"]),
        (("css/site.css",), "css", ["css/site.css"]),
        (["css/site.css", "index.html"], "reload", ["css/site.css", "index.html"]),
        (["css/site.css.map"], "reload", ["css/site.css.map"]),
        (["notes/css"], "reload", ["notes/css"]),
        ([], "reload", []),
        (None, "reload", []),
    ],
)
def test_stylesheet_only_changes_do_not_reload_the_page(
    connect, hub, paths, kind, sent_paths
):
    ws = connect()
    hub.broadcast_reload(paths)
    message = receive(ws)
    assert (message["type"], message["paths"]) == (kind, sent_paths)


def test_build_id_moves_with_every_reload(connect, hub):
    ws = connect()
    hub.broadcast_reload()
    hub.broadcast_reload(["a.css"])
    builds = [ws.hello["build"], receive(ws)["build"], receive(ws)["build"]]
    assert len(set(builds)) == 3
    assert builds[-1] == hub.build_id


def test_two_hubs_never_share_a_build_id():
    assert LiveReloadHub().build_id != LiveReloadHub().build_id


def test_error_then_clear(connect, hub):
    ws = connect()
    assert hub.broadcast_error("Build failed", "bad <tag> in page.md") == 1
    message = receive(ws)
    assert message["type"] == "error"
    assert message["title"] == "Build failed"
    assert message["detail"] == "bad <tag> in page.md"
    assert "bad &lt;tag&gt; in page.md" in message["html"]
    assert hub.has_error

    assert hub.broadcast_clear() == 1
    assert receive(ws) == {"type": "clear"}
    assert not hub.has_error


def test_latecomer_is_told_about_a_standing_error(connect, hub):
    hub.broadcast_error("Build failed", "still broken")
    ws = connect()
    message = receive(ws)
    assert (message["type"], message["detail"]) == ("error", "still broken")


def test_reload_ends_a_standing_error(connect, hub):
    hub.broadcast_error("Build failed", "fixed in a moment")
    hub.broadcast_reload()
    ws = connect()
    with pytest.raises(TimeoutError):
        ws.recv(timeout=0.1)


def test_broadcasting_to_nobody(hub):
    assert hub.broadcast_reload() == 0
    assert hub.broadcast_error("Build failed", "nobody is watching") == 0
    assert hub.broadcast_clear() == 0


def test_client_closing_is_noticed(connect, hub):
    staying, leaving = connect(), connect()
    leaving.close()
    assert wait_for(lambda: hub.client_count == 1)
    assert hub.broadcast_reload() == 1
    assert receive(staying)["type"] == "reload"


def test_client_vanishing_without_a_close_is_noticed(connect, hub):
    ws = connect()
    ws.abort()
    assert wait_for(lambda: hub.client_count == 0)


def test_broadcasts_from_many_threads_all_arrive_intact(connect, hub):
    ws = connect()
    pages = {f"page-{n}.html" for n in range(25)}
    threads = [
        threading.Thread(target=hub.broadcast_reload, args=([page],)) for page in pages
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {receive(ws)["paths"][0] for _ in pages} == pages


def test_cross_origin_page_cannot_connect(server, hub):
    with pytest.raises(websocket.HandshakeError) as excinfo:
        websocket.connect(*server.address, SOCKET_URL, origin="http://evil.example")
    assert excinfo.value.status == 403
    assert hub.client_count == 0


def test_same_origin_page_can_connect(connect, server):
    host, port = server.address
    ws = connect(origin=f"http://{host}:{port}")
    assert ws.hello["type"] == "hello"


def test_frames_sent_with_the_handshake_do_not_confuse_the_server(server, hub):
    request = (
        f"GET {SOCKET_URL} HTTP/1.1\r\n"
        "Host: test\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")
    close = websocket.encode_frame(websocket.OP_CLOSE, b"\x03\xe8", mask=True)
    with socket.create_connection(server.address, timeout=5) as sock:
        sock.sendall(request + close)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    # handshake, greeting, and then our close echoed back
    assert data.startswith(b"HTTP/1.1 101 ")
    assert data.endswith(websocket.encode_frame(websocket.OP_CLOSE, b"\x03\xe8"))
    assert wait_for(lambda: hub.client_count == 0)


def test_heartbeat_drops_whoever_stopped_answering(hub, attach):
    quiet, chatty = FakeSocket(), FakeSocket()
    attach(quiet, chatty)
    assert hub.client_count == 2

    hub.check_clients()
    assert (quiet.pings, chatty.pings) == (1, 1)
    chatty.on_pong(b"")
    hub.check_clients()
    assert quiet.gone.is_set()
    assert not chatty.gone.is_set()
    assert hub.client_count == 1
    assert chatty.pings == 2


def test_client_that_cannot_be_sent_to_is_dropped(hub, attach):
    class Broken(FakeSocket):
        def send(self, data):
            if self.sent:
                raise websocket.ConnectionClosed()
            super().send(data)

    broken, fine = Broken(), FakeSocket()
    attach(broken, fine)
    assert hub.broadcast_reload() == 1
    assert broken.gone.is_set()
    assert hub.client_count == 1
    assert fine.sent[-1]["type"] == "reload"


def test_heartbeat_thread_gets_rid_of_a_dead_connection(site):
    hub = LiveReloadHub(heartbeat=0.05)
    server = StaticServer(site, hub=hub)
    server.start()
    try:
        ws = websocket.connect(*server.address, SOCKET_URL)
        assert receive(ws)["type"] == "hello"
        # from here on nobody reads on our side, so pings go unanswered
        assert wait_for(lambda: hub.client_count == 0)
        ws.abort()
    finally:
        hub.close()
        server.stop()


def test_closing_the_hub_says_goodbye(connect, hub):
    ws = connect()
    closer = threading.Thread(target=hub.close, daemon=True)
    closer.start()
    with pytest.raises(websocket.ConnectionClosed) as excinfo:
        ws.recv(timeout=5)
    closer.join(5)
    assert excinfo.value.code == websocket.CLOSE_GOING_AWAY
    assert hub.client_count == 0


def test_closed_hub_turns_new_clients_away(server, hub):
    hub.close()
    ws = websocket.connect(*server.address, SOCKET_URL)
    with pytest.raises(websocket.ConnectionClosed) as excinfo:
        ws.recv(timeout=5)
    assert excinfo.value.code == websocket.CLOSE_GOING_AWAY
    assert hub.client_count == 0


def test_hub_can_be_reopened(connect, hub):
    hub.close()
    hub.start()
    connect()
    assert hub.client_count == 1
    assert hub.broadcast_reload() == 1


def test_client_script_agrees_with_the_server():
    script = client_script().decode("utf-8")
    assert f'const SOCKET_PATH = "{SOCKET_URL}";' in script
    assert SCRIPT_URL.encode() in SCRIPT_TAG
    for kind in ("hello", "reload", "css", "error", "clear"):
        assert f'case "{kind}":' in script
    # the hooks the overlay markup and the client have to agree on
    assert "[data-inkstone-dismiss]" in script
    assert "data-inkstone-dismiss" in render_overlay("t", "d")
    assert '"data-inkstone-error"' in script
    assert "data-inkstone-error" in render_error_page("t", "d")
