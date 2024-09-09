from __future__ import annotations

import socket
import struct
import threading

import pytest

from inkstone.server import ServerError, websocket
from inkstone.server.websocket import (
    OP_BINARY,
    OP_CLOSE,
    OP_CONT,
    OP_PING,
    OP_PONG,
    OP_TEXT,
    ConnectionClosed,
    Frame,
    FrameDecoder,
    HandshakeError,
    ProtocolError,
    WebSocketError,
    accept_key,
    apply_mask,
    check_handshake,
    encode_frame,
    handshake_response,
    parse_frame,
    rejection_response,
)

from .helpers import fetch, wait_for

# key, mask and expected bytes below are the worked examples from RFC 6455
RFC_KEY = "dGhlIHNhbXBsZSBub25jZQ=="
RFC_ACCEPT = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
RFC_MASK = bytes.fromhex("37fa213d")

UPGRADE_REQUEST = (
    "GET /raw HTTP/1.1\r\n"
    "Host: test\r\n"
    "Upgrade: websocket\r\n"
    "Connection: Upgrade\r\n"
    f"Sec-WebSocket-Key: {RFC_KEY}\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    "\r\n"
).encode("ascii")

GOOD_HEADERS = {
    "Host": "test",
    "Upgrade": "websocket",
    "Connection": "keep-alive, Upgrade",
    "Sec-WebSocket-Key": RFC_KEY,
    "Sec-WebSocket-Version": "13",
}


class EchoServer:
    """Accepts websocket connections on a bare listening socket and echoes."""

    def __init__(self, max_size=websocket.DEFAULT_MAX_SIZE):
        self.max_size = max_size
        self.connections = []
        self.errors = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.address = self._listener.getsockname()
        self._stop = threading.Event()
        self._threads = []
        self._acceptor = threading.Thread(target=self._accept_loop, daemon=True)
        self._acceptor.start()

    def _accept_loop(self):
        while True:
            conn, _ = self._listener.accept()
            if self._stop.is_set():
                conn.close()
                return
            thread = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            thread.start()
            self._threads.append(thread)

    def _serve(self, conn):
        try:
            ws = websocket.accept(conn, max_size=self.max_size)
        except WebSocketError as exc:
            self.errors.append(exc)
            conn.close()
            return
        self.connections.append(ws)
        try:
            for message in ws:
                ws.send(message)
        except WebSocketError as exc:
            self.errors.append(exc)

    def stop(self):
        self._stop.set()
        # accept() can't be interrupted portably, so hand it one last caller
        socket.create_connection(self.address, timeout=5).close()
        self._acceptor.join()
        self._listener.close()
        for ws in self.connections:
            ws.abort()
        for thread in self._threads:
            thread.join(5)


class CannedServer:
    """Answers the first connection with fixed bytes, then hangs up."""

    def __init__(self, answer: bytes):
        self._answer = answer
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.address = self._listener.getsockname()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        conn, _ = self._listener.accept()
        with conn:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            conn.sendall(self._answer)

    def stop(self):
        self._thread.join(5)
        self._listener.close()


@pytest.fixture
def echo():
    server = EchoServer()
    yield server
    server.stop()


@pytest.fixture
def client(echo):
    ws = websocket.connect(*echo.address, "/echo")
    yield ws
    ws.close()


@pytest.fixture
def canned():
    servers = []

    def start(answer: bytes):
        servers.append(CannedServer(answer))
        return servers[-1]

    yield start
    for server in servers:
        server.stop()


def raw_upgrade(address, extra: bytes = b"") -> tuple[socket.socket, bytes]:
    """Handshake by hand; returns the socket and any bytes read past the head."""
    sock = socket.create_connection(address, timeout=5)
    sock.sendall(UPGRADE_REQUEST + extra)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        assert chunk, "server hung up during the handshake"
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    assert head.startswith(b"HTTP/1.1 101 ")
    return sock, rest


def read_frame(sock, initial: bytes = b"") -> Frame:
    decoder = FrameDecoder(masked=False)
    decoder.feed(initial)
    while True:
        frame = decoder.next_frame()
        if frame is not None:
            return frame
        data = sock.recv(4096)
        assert data, "connection closed before a whole frame arrived"
        decoder.feed(data)


def test_accept_key_matches_the_rfc_example():
    assert accept_key(RFC_KEY) == RFC_ACCEPT


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"opcode": OP_TEXT, "payload": b"Hello"}, "810548656c6c6f"),
        (
            {"opcode": OP_TEXT, "payload": b"Hello", "mask": RFC_MASK},
            "818537fa213d7f9f4d5158",
        ),
        ({"opcode": OP_TEXT, "payload": b"Hel", "fin": False}, "010348656c"),
        ({"opcode": OP_CONT, "payload": b"lo"}, "80026c6f"),
        ({"opcode": OP_PING, "payload": b"Hello"}, "890548656c6c6f"),
        (
            {"opcode": OP_PONG, "payload": b"Hello", "mask": RFC_MASK},
            "8a8537fa213d7f9f4d5158",
        ),
        ({"opcode": OP_CLOSE, "payload": b"\x03\xe8"}, "880203e8"),
    ],
    ids=[
        "text",
        "masked-text",
        "first-fragment",
        "last-fragment",
        "ping",
        "pong",
        "close",
    ],
)
def test_encode_frame_matches_the_rfc_examples(kwargs, expected):
    assert encode_frame(**kwargs).hex() == expected


@pytest.mark.parametrize(
    ("size", "header"),
    [
        (0, "8200"),
        (125, "827d"),
        (126, "827e007e"),
        (65535, "827effff"),
        (65536, "827f0000000000010000"),
    ],
)
def test_payload_length_forms(size, header):
    frame = encode_frame(OP_BINARY, b"x" * size)
    assert frame[: len(frame) - size].hex() == header


@pytest.mark.parametrize("masked", [False, True], ids=["unmasked", "masked"])
@pytest.mark.parametrize("size", [0, 1, 125, 126, 127, 65535, 65536, 70001])
def test_frame_round_trip(size, masked):
    payload = bytes(i % 251 for i in range(size))
    data = encode_frame(OP_BINARY, payload, mask=masked)
    frame, used = parse_frame(data + b"start of the next frame")
    assert used == len(data)
    assert frame == Frame(OP_BINARY, payload, fin=True, masked=masked)


def test_masked_frame_carries_the_mask_bit_and_hides_the_payload():
    data = encode_frame(OP_TEXT, b"plain text here", mask=True)
    assert data[1] & 0x80
    assert b"plain text here" not in data
    assert encode_frame(OP_TEXT, b"plain text here")[1] & 0x80 == 0


def test_masking_is_its_own_inverse():
    data = b"\x00\x00leading zero bytes survive\x00"
    masked = apply_mask(data, RFC_MASK)
    assert masked != data
    assert len(masked) == len(data)
    assert apply_mask(masked, RFC_MASK) == data
    assert apply_mask(b"", RFC_MASK) == b""
    assert apply_mask(data, b"\x00\x00\x00\x00") == data


@pytest.mark.parametrize("key", [b"", b"abc", b"abcde"])
def test_mask_key_must_be_four_bytes(key):
    with pytest.raises(ValueError):
        apply_mask(b"data", key)


def test_incomplete_frame_waits_for_more_data():
    data = encode_frame(OP_TEXT, b"x" * 300, mask=True)
    assert all(parse_frame(data[:cut]) is None for cut in range(len(data)))
    assert parse_frame(data) is not None


def test_decoder_copes_with_data_arriving_a_byte_at_a_time():
    stream = (
        encode_frame(OP_TEXT, b"one", mask=True)
        + encode_frame(OP_PING, mask=True)
        + encode_frame(OP_BINARY, b"\x00" * 200, mask=True)
    )
    decoder = FrameDecoder(masked=True)
    frames = []
    for i in range(len(stream)):
        decoder.feed(stream[i : i + 1])
        frames.extend(decoder.frames())
    assert [(f.opcode, f.payload) for f in frames] == [
        (OP_TEXT, b"one"),
        (OP_PING, b""),
        (OP_BINARY, b"\x00" * 200),
    ]


def test_decoder_hands_out_several_frames_from_one_chunk():
    decoder = FrameDecoder()
    decoder.feed(encode_frame(OP_TEXT, b"a") + encode_frame(OP_TEXT, b"b") + b"\x81")
    assert [f.payload for f in decoder.frames()] == [b"a", b"b"]
    assert decoder.next_frame() is None


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xc1\x00", 1002),
        (b"\x83\x00", 1002),
        (b"\x8b\x00", 1002),
        (b"\x09\x00", 1002),
        (b"\x89\x7e\x00\x7e", 1002),
        (b"\x82\x7e\x00\x05", 1002),
        (b"\x82\x7f" + (5).to_bytes(8, "big"), 1002),
        (b"\x82\x7f" + (1 << 63).to_bytes(8, "big"), 1002),
        (b"\x82\x7f" + (1 << 40).to_bytes(8, "big"), 1009),
    ],
    ids=[
        "rsv1",
        "reserved-data-opcode",
        "reserved-control-opcode",
        "fragmented-ping",
        "long-ping",
        "padded-16-bit-length",
        "padded-64-bit-length",
        "length-top-bit",
        "over-the-limit",
    ],
)
def test_malformed_frames(data, code):
    with pytest.raises(ProtocolError) as excinfo:
        parse_frame(data)
    assert excinfo.value.code == code


def test_masking_direction_is_enforced():
    unmasked = encode_frame(OP_TEXT, b"hi")
    masked = encode_frame(OP_TEXT, b"hi", mask=True)
    with pytest.raises(ProtocolError, match="must be masked"):
        parse_frame(unmasked, masked=True)
    with pytest.raises(ProtocolError, match="must not be masked"):
        parse_frame(masked, masked=False)
    assert parse_frame(masked, masked=True)[0].payload == b"hi"
    assert parse_frame(unmasked, masked=False)[0].payload == b"hi"


def test_size_limit_is_checked_before_the_payload_arrives():
    data = encode_frame(OP_BINARY, b"x" * 200)
    with pytest.raises(ProtocolError) as excinfo:
        parse_frame(data[:4], max_size=100)
    assert excinfo.value.code == 1009
    assert parse_frame(data, max_size=200) is not None


def test_check_handshake_returns_the_key():
    assert check_handshake("GET", GOOD_HEADERS) == RFC_KEY


def test_check_handshake_ignores_case():
    headers = {name.lower(): value for name, value in GOOD_HEADERS.items()}
    headers["upgrade"] = "WebSocket"
    headers["connection"] = "UPGRADE"
    assert check_handshake("GET", headers) == RFC_KEY


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"Upgrade": None}, 426),
        ({"Upgrade": "h2c"}, 426),
        ({"Connection": "keep-alive"}, 400),
        ({"Connection": None}, 400),
        ({"Sec-WebSocket-Version": "8"}, 426),
        ({"Sec-WebSocket-Version": None}, 426),
        ({"Sec-WebSocket-Key": None}, 400),
        ({"Sec-WebSocket-Key": "c2hvcnQ="}, 400),
        ({"Sec-WebSocket-Key": "definitely not base64!"}, 400),
    ],
)
def test_check_handshake_rejections(change, status):
    headers = {k: v for k, v in {**GOOD_HEADERS, **change}.items() if v is not None}
    with pytest.raises(HandshakeError) as excinfo:
        check_handshake("GET", headers)
    assert excinfo.value.status == status


def test_handshake_has_to_be_a_get():
    with pytest.raises(HandshakeError) as excinfo:
        check_handshake("POST", GOOD_HEADERS)
    assert excinfo.value.status == 405


def test_version_rejection_says_which_version_we_speak():
    with pytest.raises(HandshakeError) as excinfo:
        check_handshake("GET", {**GOOD_HEADERS, "Sec-WebSocket-Version": "7"})
    assert excinfo.value.headers == {"Sec-WebSocket-Version": "13"}


def test_handshake_response():
    lines = handshake_response(RFC_KEY).split(b"\r\n")
    assert lines[0] == b"HTTP/1.1 101 Switching Protocols"
    assert f"Sec-WebSocket-Accept: {RFC_ACCEPT}".encode() in lines
    assert lines[-2:] == [b"", b""]


def test_rejection_response_is_a_complete_http_response():
    error = HandshakeError("nope", 426, {"Upgrade": "websocket"})
    head, _, body = rejection_response(error).partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    assert lines[0] == b"HTTP/1.1 426 Upgrade Required"
    assert b"Upgrade: websocket" in lines
    assert b"Content-Length: 5" in lines
    assert body == b"nope\n"


def test_errors_belong_to_the_server_error_family():
    for kind in (HandshakeError, ProtocolError, ConnectionClosed):
        assert issubclass(kind, WebSocketError)
    assert issubclass(WebSocketError, ServerError)
    assert str(ConnectionClosed(1001, "bye")) == "websocket closed (1001): bye"


@pytest.mark.parametrize(
    "message", ["hello", "", "héllo wörld ✓", b"\x00\x01\xff", b""]
)
def test_echo(client, message):
    client.send(message)
    assert client.recv(timeout=5) == message


@pytest.mark.parametrize("size", [125, 126, 65535, 65536, 300_000])
def test_echo_across_the_length_encodings(client, size):
    payload = bytes(i % 253 for i in range(size))
    client.send(payload)
    assert client.recv(timeout=5) == payload


def test_server_side_knows_the_request_path(echo, client):
    assert wait_for(lambda: echo.connections)
    assert echo.connections[0].path == "/echo"
    assert client.path == "/echo"


def test_fragmented_message_is_reassembled(client):
    client.send_frame(OP_TEXT, b"frag", fin=False)
    client.send_frame(OP_CONT, b"men", fin=False)
    client.send_frame(OP_CONT, b"ted")
    assert client.recv(timeout=5) == "fragmented"


def test_utf8_character_split_across_fragments(client):
    encoded = "é".encode("utf-8")
    client.send_frame(OP_TEXT, encoded[:1], fin=False)
    client.send_frame(OP_CONT, encoded[1:])
    assert client.recv(timeout=5) == "é"


def test_ping_between_fragments_is_answered_without_disturbing_the_message(client):
    pongs = []
    client.on_pong = pongs.append
    client.send_frame(OP_BINARY, b"ab", fin=False)
    client.ping(b"mid-message")
    client.send_frame(OP_CONT, b"cd")
    assert client.recv(timeout=5) == b"abcd"
    assert pongs == [b"mid-message"]


def test_ping_from_the_server_is_answered_by_the_client(echo, client):
    assert wait_for(lambda: echo.connections)
    server_side = echo.connections[0]
    pongs = []
    server_side.on_pong = pongs.append
    server_side.ping(b"still there?")
    # recv() answers the ping on its way to the echoed message
    client.send("x")
    assert client.recv(timeout=5) == "x"
    assert wait_for(lambda: pongs == [b"still there?"])


def test_ping_payload_is_limited(client):
    with pytest.raises(ValueError):
        client.ping(b"x" * 126)


def test_recv_timeout_leaves_the_connection_usable(client):
    with pytest.raises(TimeoutError):
        client.recv(timeout=0.05)
    with pytest.raises(TimeoutError):
        client.recv(timeout=0)
    client.send("still here")
    assert client.recv(timeout=5) == "still here"


def test_close_handshake_started_by_the_client(echo, client):
    assert wait_for(lambda: echo.connections)
    server_side = echo.connections[0]
    client.close(1000, "all done")
    assert client.closed
    assert client.close_code == 1000
    assert wait_for(lambda: server_side.closed)
    assert (server_side.close_code, server_side.close_reason) == (1000, "all done")
    assert echo.errors == []


def test_close_handshake_started_by_the_server(echo, client):
    assert wait_for(lambda: echo.connections)
    server_side = echo.connections[0]
    closer = threading.Thread(
        target=server_side.close, args=(4001, "bye for now"), daemon=True
    )
    closer.start()
    with pytest.raises(ConnectionClosed) as excinfo:
        client.recv(timeout=5)
    closer.join(5)
    assert (excinfo.value.code, excinfo.value.reason) == (4001, "bye for now")
    assert client.close_code == 4001
    assert server_side.close_code == 4001


def test_close_frame_without_a_status(client):
    client.send_frame(OP_CLOSE)
    with pytest.raises(ConnectionClosed) as excinfo:
        client.recv(timeout=5)
    assert excinfo.value.code == 1005


def test_long_close_reason_is_cut_at_a_character_boundary(echo, client):
    assert wait_for(lambda: echo.connections)
    client.close(1000, "é" * 200)
    server_side = echo.connections[0]
    assert wait_for(lambda: server_side.closed)
    assert server_side.close_reason == "é" * 61
    assert echo.errors == []


def test_nothing_works_after_close(client):
    client.close()
    client.close()
    with pytest.raises(ConnectionClosed):
        client.send("too late")
    with pytest.raises(ConnectionClosed):
        client.recv(timeout=1)


def test_peer_vanishing_counts_as_abnormal_closure(echo, client):
    assert wait_for(lambda: echo.connections)
    echo.connections[0].abort()
    with pytest.raises(ConnectionClosed) as excinfo:
        client.recv(timeout=5)
    assert excinfo.value.code == 1006


def test_iteration_ends_with_the_connection(client):
    client.send("a")
    client.send(b"b")
    client.send_frame(OP_CLOSE, struct.pack("!H", 1000))
    assert list(client) == ["a", b"b"]
    assert client.close_code == 1000


def test_context_manager_closes(echo):
    with websocket.connect(*echo.address) as ws:
        ws.send("in")
        assert ws.recv(timeout=5) == "in"
    assert ws.closed


def test_senders_on_several_threads_do_not_corrupt_the_stream(client):
    messages = {f"{n}:" + chr(97 + n) * 20_000 for n in range(16)}
    threads = [threading.Thread(target=client.send, args=(m,)) for m in messages]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert {client.recv(timeout=5) for _ in messages} == messages


def test_frames_sent_right_behind_the_handshake_are_not_lost(echo):
    early = encode_frame(OP_TEXT, b"early bird", mask=RFC_MASK)
    sock, rest = raw_upgrade(echo.address, extra=early)
    try:
        frame = read_frame(sock, rest)
        assert (frame.opcode, frame.payload) == (OP_TEXT, b"early bird")
    finally:
        sock.close()


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (encode_frame(OP_TEXT, b"unmasked"), 1002),
        (b"\xc1\x80" + RFC_MASK, 1002),
        (encode_frame(0x3, mask=RFC_MASK), 1002),
        (encode_frame(OP_CONT, b"orphan", mask=RFC_MASK), 1002),
        (
            encode_frame(OP_TEXT, b"a", fin=False, mask=RFC_MASK)
            + encode_frame(OP_TEXT, b"b", mask=RFC_MASK),
            1002,
        ),
        (encode_frame(OP_PING, b"x" * 126, mask=RFC_MASK), 1002),
        (encode_frame(OP_PING, fin=False, mask=RFC_MASK), 1002),
        (encode_frame(OP_TEXT, b"\xff\xfe", mask=RFC_MASK), 1007),
        (encode_frame(OP_CLOSE, b"\x03", mask=RFC_MASK), 1002),
        (encode_frame(OP_CLOSE, struct.pack("!H", 1005), mask=RFC_MASK), 1002),
        (encode_frame(OP_CLOSE, struct.pack("!H", 999), mask=RFC_MASK), 1002),
        (
            encode_frame(OP_CLOSE, struct.pack("!H", 1000) + b"\xff", mask=RFC_MASK),
            1007,
        ),
    ],
    ids=[
        "unmasked",
        "rsv1",
        "reserved-opcode",
        "orphan-continuation",
        "interleaved-messages",
        "long-ping",
        "fragmented-ping",
        "invalid-utf8",
        "half-a-close-code",
        "close-code-1005",
        "close-code-999",
        "close-reason-not-utf8",
    ],
)
def test_protocol_violation_fails_the_connection(echo, data, code):
    sock, rest = raw_upgrade(echo.address)
    try:
        sock.sendall(data)
        frame = read_frame(sock, rest)
        assert frame.opcode == OP_CLOSE
        assert struct.unpack("!H", frame.payload[:2]) == (code,)
        assert sock.recv(1024) == b""
    finally:
        sock.close()
    assert wait_for(lambda: echo.errors)
    assert isinstance(echo.errors[0], ProtocolError)
    assert echo.errors[0].code == code


def test_client_rejects_masked_frames_from_a_server(canned):
    answer = handshake_response(RFC_KEY) + encode_frame(OP_TEXT, b"hi", mask=RFC_MASK)
    server = canned(answer)
    ws = websocket.connect(*server.address, headers={"Sec-WebSocket-Key": RFC_KEY})
    with pytest.raises(ProtocolError, match="must not be masked"):
        ws.recv(timeout=5)
    assert ws.closed


def test_oversized_message_is_refused():
    server = EchoServer(max_size=1024)
    try:
        with websocket.connect(*server.address) as ws:
            ws.send(b"x" * 2000)
            with pytest.raises(ConnectionClosed) as excinfo:
                ws.recv(timeout=5)
            assert excinfo.value.code == 1009
    finally:
        server.stop()


def test_fragments_adding_up_past_the_limit_are_refused():
    server = EchoServer(max_size=1024)
    try:
        with websocket.connect(*server.address) as ws:
            ws.send_frame(OP_BINARY, b"x" * 600, fin=False)
            ws.send_frame(OP_CONT, b"x" * 600)
            with pytest.raises(ConnectionClosed) as excinfo:
                ws.recv(timeout=5)
            assert excinfo.value.code == 1009
    finally:
        server.stop()


def test_wrong_protocol_version_is_turned_down(echo):
    with pytest.raises(HandshakeError) as excinfo:
        websocket.connect(*echo.address, headers={"Sec-WebSocket-Version": "8"})
    assert excinfo.value.status == 426
    assert wait_for(lambda: echo.errors)
    assert isinstance(echo.errors[0], HandshakeError)


def test_plain_http_request_gets_a_proper_refusal(echo):
    response, body = fetch(echo.address, "/")
    assert response.status == 426
    assert response.getheader("Upgrade") == "websocket"
    assert body == b"this endpoint only speaks websocket\n"


def test_http_1_0_cannot_upgrade(echo):
    request = UPGRADE_REQUEST.replace(b"HTTP/1.1", b"HTTP/1.0")
    with socket.create_connection(echo.address, timeout=5) as sock:
        sock.sendall(request)
        assert sock.recv(1024).startswith(b"HTTP/1.1 505 ")


@pytest.mark.parametrize(
    ("answer", "status", "message"),
    [
        (b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", 200, "server answered"),
        (
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: bm90IHRoZSByaWdodCBvbmU=\r\n\r\n",
            101,
            "wrong Sec-WebSocket-Accept",
        ),
        (
            b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\n\r\n",
            101,
            "without 'Upgrade: websocket'",
        ),
        (b"SSH-2.0-OpenSSH_9.6\r\n\r\n", 0, "not an HTTP response"),
        (b"HTTP/1.1 101", 400, "closed during the handshake"),
    ],
    ids=["not-101", "wrong-accept", "no-upgrade-header", "not-http", "cut-short"],
)
def test_client_refuses_a_bad_handshake_answer(canned, answer, status, message):
    server = canned(answer)
    with pytest.raises(HandshakeError, match=message) as excinfo:
        websocket.connect(*server.address)
    assert excinfo.value.status == status


def test_connecting_to_nothing_is_a_websocket_error():
    with socket.socket() as placeholder:
        placeholder.bind(("127.0.0.1", 0))
        address = placeholder.getsockname()
    with pytest.raises(WebSocketError, match="can't connect"):
        websocket.connect(*address, timeout=0.5)


def test_accept_gives_up_on_a_silent_client():
    listener = socket.create_server(("127.0.0.1", 0))
    try:
        with socket.create_connection(listener.getsockname(), timeout=5):
            conn, _ = listener.accept()
            with conn, pytest.raises(HandshakeError, match="timed out") as excinfo:
                websocket.accept(conn, timeout=0.05)
            assert excinfo.value.status == 408
    finally:
        listener.close()
