from __future__ import annotations

import base64
import hashlib
import os
import select
import socket
import struct
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable, Iterator, Mapping

from .errors import ServerError

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

_DATA_OPCODES = (OP_CONT, OP_TEXT, OP_BINARY)
_CONTROL_OPCODES = (OP_CLOSE, OP_PING, OP_PONG)

CLOSE_NORMAL = 1000
CLOSE_GOING_AWAY = 1001
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_NO_STATUS = 1005
CLOSE_ABNORMAL = 1006
CLOSE_INVALID_DATA = 1007
CLOSE_TOO_BIG = 1009

# What a peer may put in a close frame. 1005 and 1006 only exist as local
# "nothing was sent" markers and must never show up on the wire.
_WIRE_CLOSE_CODES = frozenset(
    {1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014}
)

# Live-reload messages are tiny; this is only a lid on what a confused peer
# can make us buffer.
DEFAULT_MAX_SIZE = 4 * 1024 * 1024

_MAX_HEAD = 16 * 1024
_RECV_SIZE = 64 * 1024
_SEND_TIMEOUT = 5.0
# shutdown() from another thread doesn't wake a select() on Windows, so a
# reader has to come up for air this often to notice it has been closed.
_POLL = 0.25


class WebSocketError(ServerError):
    pass


class HandshakeError(WebSocketError):
    """The opening handshake failed.

    ``status`` is the HTTP status the server answers with (server side) or
    answered with (client side).
    """

    def __init__(
        self, message: str, status: int = 400, headers: dict[str, str] | None = None
    ):
        super().__init__(message)
        self.status = status
        self.headers = headers or {}


class ProtocolError(WebSocketError):
    """The peer broke the framing rules; ``code`` is the close code it earned."""

    def __init__(self, message: str, code: int = CLOSE_PROTOCOL_ERROR):
        super().__init__(message)
        self.code = code


class ConnectionClosed(WebSocketError):
    def __init__(self, code: int = CLOSE_ABNORMAL, reason: str = ""):
        text = f"websocket closed ({code})"
        if reason:
            text += f": {reason}"
        super().__init__(text)
        self.code = code
        self.reason = reason


@dataclass
class Frame:
    opcode: int
    payload: bytes = b""
    fin: bool = True
    masked: bool = False

    @property
    def is_control(self) -> bool:
        return self.opcode in _CONTROL_OPCODES


def apply_mask(data: bytes, key: bytes) -> bytes:
    """XOR ``data`` with the repeating 4-byte ``key`` (its own inverse)."""
    if len(key) != 4:
        raise ValueError("masking key must be 4 bytes")
    size = len(data)
    if not size:
        return b""
    # one big-int XOR is far quicker than a Python loop over the bytes
    pad = (key * (size // 4 + 1))[:size]
    masked = int.from_bytes(data, "big") ^ int.from_bytes(pad, "big")
    return masked.to_bytes(size, "big")


def encode_frame(
    opcode: int, payload: bytes = b"", *, fin: bool = True, mask: bytes | bool = False
) -> bytes:
    """Serialise one frame.

    ``mask`` is a 4-byte key, or True for a random one. This is deliberately
    permissive about what it will encode (oversized control frames and so
    on); the rules are enforced on the way in, and by ``WebSocket`` on the
    way out.
    """
    head = bytearray([(0x80 if fin else 0) | opcode])
    mask_bit = 0x80 if mask else 0
    size = len(payload)
    if size < 126:
        head.append(mask_bit | size)
    elif size < 1 << 16:
        head.append(mask_bit | 126)
        head += struct.pack("!H", size)
    else:
        head.append(mask_bit | 127)
        head += struct.pack("!Q", size)
    if not mask:
        return bytes(head) + payload
    key = os.urandom(4) if mask is True else mask
    return bytes(head) + key + apply_mask(payload, key)


def parse_frame(
    buf: bytes | bytearray,
    *,
    masked: bool | None = None,
    max_size: int = DEFAULT_MAX_SIZE,
) -> tuple[Frame, int] | None:
    """Parse one frame from the start of ``buf``.

    Returns the frame and how many bytes it took up, or None if the buffer
    doesn't hold a whole frame yet. ``masked`` is what the peer is required
    to do (clients mask, servers don't); None accepts either. Violations are
    reported as early as the header allows, without waiting for the payload.
    """
    if len(buf) < 2:
        return None
    first, second = buf[0], buf[1]
    fin = bool(first & 0x80)
    opcode = first & 0x0F
    has_mask = bool(second & 0x80)
    size = second & 0x7F

    if first & 0x70:
        raise ProtocolError("reserved bits set, but no extension was negotiated")
    if opcode not in _DATA_OPCODES and opcode not in _CONTROL_OPCODES:
        raise ProtocolError(f"unknown opcode 0x{opcode:x}")
    if opcode in _CONTROL_OPCODES:
        if not fin:
            raise ProtocolError("control frames can't be fragmented")
        if size > 125:
            raise ProtocolError("control frame payload is over 125 bytes")
    if masked is not None and has_mask != masked:
        if masked:
            raise ProtocolError("frames from a client must be masked")
        raise ProtocolError("frames from a server must not be masked")

    pos = 2
    if size == 126:
        if len(buf) < 4:
            return None
        (size,) = struct.unpack_from("!H", buf, 2)
        if size < 126:
            raise ProtocolError("payload length isn't in its shortest form")
        pos = 4
    elif size == 127:
        if len(buf) < 10:
            return None
        (size,) = struct.unpack_from("!Q", buf, 2)
        if size >> 63:
            raise ProtocolError("payload length has its top bit set")
        if size < 1 << 16:
            raise ProtocolError("payload length isn't in its shortest form")
        pos = 10
    if size > max_size:
        raise ProtocolError(f"{size} byte frame is over the limit", CLOSE_TOO_BIG)

    key = None
    if has_mask:
        if len(buf) < pos + 4:
            return None
        key = bytes(buf[pos : pos + 4])
        pos += 4
    end = pos + size
    if len(buf) < end:
        return None
    payload = bytes(buf[pos:end])
    if key is not None:
        payload = apply_mask(payload, key)
    return Frame(opcode, payload, fin, has_mask), end


class FrameDecoder:
    """Incremental parser: feed it whatever the socket hands over."""

    def __init__(self, *, masked: bool | None = None, max_size: int = DEFAULT_MAX_SIZE):
        self.masked = masked
        self.max_size = max_size
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf += data

    def next_frame(self) -> Frame | None:
        parsed = parse_frame(self._buf, masked=self.masked, max_size=self.max_size)
        if parsed is None:
            return None
        frame, used = parsed
        del self._buf[:used]
        return frame

    def frames(self) -> Iterator[Frame]:
        while True:
            frame = self.next_frame()
            if frame is None:
                return
            yield frame


class WebSocket:
    """One end of an established connection.

    Sending is safe from any thread. Receiving is meant for a single reader,
    which is also what answers pings and completes the closing handshake, so
    somebody should be sitting in ``recv()`` for as long as the peer matters.
    """

    def __init__(
        self,
        sock: socket.socket,
        *,
        client: bool = False,
        initial: bytes = b"",
        max_size: int = DEFAULT_MAX_SIZE,
    ):
        self._sock = sock
        self._client = client
        self._max_size = max_size
        self._decoder = FrameDecoder(masked=not client, max_size=max_size)
        self._decoder.feed(initial)
        self._send_lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._closed = threading.Event()
        self._close_sent = False
        self._parts: list[bytes] = []
        self._parts_opcode: int | None = None
        self._parts_size = 0
        self.close_code: int | None = None
        self.close_reason = ""
        self.path: str | None = None
        self.on_pong: Callable[[bytes], None] | None = None
        # Reads wait in select() first, so this only ever bites on a send to
        # a peer that has stopped reading.
        sock.settimeout(_SEND_TIMEOUT)

    def __enter__(self) -> WebSocket:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __iter__(self) -> Iterator[str | bytes]:
        try:
            while True:
                yield self.recv()
        except ConnectionClosed:
            return

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def send(self, message: str | bytes) -> None:
        if isinstance(message, str):
            self.send_frame(OP_TEXT, message.encode("utf-8"))
        else:
            self.send_frame(OP_BINARY, bytes(message))

    def send_frame(
        self, opcode: int, payload: bytes = b"", *, fin: bool = True
    ) -> None:
        """Send a single raw frame; this is how to fragment a message by hand."""
        frame = encode_frame(opcode, payload, fin=fin, mask=self._client)
        with self._send_lock:
            if self._close_sent or self._closed.is_set():
                raise ConnectionClosed(
                    self.close_code or CLOSE_ABNORMAL, self.close_reason
                )
            if opcode == OP_CLOSE:
                self._close_sent = True
            try:
                self._sock.sendall(frame)
            except OSError:
                # including a timeout: half a frame may be out, so the
                # stream is useless from here on
                self._finish(CLOSE_ABNORMAL)
                raise ConnectionClosed(CLOSE_ABNORMAL) from None

    def ping(self, payload: bytes = b"") -> None:
        if len(payload) > 125:
            raise ValueError("ping payload is limited to 125 bytes")
        self.send_frame(OP_PING, payload)

    def recv(self, timeout: float | None = None) -> str | bytes:
        """Return the next complete message (str for text, bytes for binary).

        Raises ConnectionClosed once the connection is over, TimeoutError if
        nothing complete arrives in time (the connection stays usable), and
        ProtocolError if the peer misbehaves, after failing the connection.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._read_lock:
            while True:
                message = self._handle(self._next_frame(deadline))
                if message is not None:
                    return message

    def close(
        self, code: int = CLOSE_NORMAL, reason: str = "", *, timeout: float = 1.0
    ) -> None:
        """Run the closing handshake (as far as the peer plays along) and hang up."""
        if self._closed.is_set():
            return
        self._send_close(code, reason)
        if self._read_lock.acquire(blocking=False):
            # nobody is in recv(), so it's on us to wait for the reply
            try:
                self._drain(time.monotonic() + timeout)
            finally:
                self._read_lock.release()
        else:
            self._closed.wait(timeout)
        self._finish(code, reason)

    def abort(self) -> None:
        """Drop the connection without the closing handshake."""
        self._finish(CLOSE_ABNORMAL)

    def _send_close(self, code: int, reason: str = "") -> None:
        payload = b""
        if code != CLOSE_NO_STATUS:
            # a control payload tops out at 125 bytes; don't cut a character in half
            text = reason.encode("utf-8")[:123].decode("utf-8", "ignore")
            payload = struct.pack("!H", code) + text.encode("utf-8")
        try:
            self.send_frame(OP_CLOSE, payload)
        except ConnectionClosed:
            pass

    def _finish(self, code: int, reason: str = "") -> None:
        if self.close_code is None:
            self.close_code, self.close_reason = code, reason
        self._closed.set()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._sock.close()

    def _fail(self, message: str, code: int = CLOSE_PROTOCOL_ERROR):
        self._send_close(code, message)
        self._finish(code, message)
        raise ProtocolError(message, code)

    def _drain(self, deadline: float) -> None:
        try:
            while True:
                self._handle(self._next_frame(deadline))
        except (WebSocketError, TimeoutError):
            pass

    def _next_frame(self, deadline: float | None) -> Frame:
        while True:
            if self._closed.is_set():
                raise ConnectionClosed(self.close_code, self.close_reason)
            try:
                frame = self._decoder.next_frame()
            except ProtocolError as exc:
                self._fail(exc.message, exc.code)
            if frame is not None:
                return frame
            data = self._read_some(deadline)
            if not data:
                self._finish(CLOSE_ABNORMAL)
                raise ConnectionClosed(self.close_code, self.close_reason)
            self._decoder.feed(data)

    def _read_some(self, deadline: float | None) -> bytes:
        """Next chunk from the socket; b"" means the connection is gone."""
        # XXX select() can't take descriptors above 1023 on POSIX. A dev
        # server with that many files open has other problems, and such a
        # connection is simply treated as lost.
        while not self._closed.is_set():
            wait = _POLL
            if deadline is not None:
                wait = max(0.0, min(wait, deadline - time.monotonic()))
            try:
                readable, _, _ = select.select([self._sock], [], [], wait)
            except (OSError, ValueError):
                return b""
            if readable:
                try:
                    return self._sock.recv(_RECV_SIZE)
                except (BlockingIOError, InterruptedError, TimeoutError):
                    continue
                except OSError:
                    return b""
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("no websocket message arrived in time")
        return b""

    def _handle(self, frame: Frame) -> str | bytes | None:
        """Process one frame; returns a message when it completes one."""
        opcode = frame.opcode
        if opcode == OP_PING:
            try:
                self.send_frame(OP_PONG, frame.payload)
            except ConnectionClosed:
                pass
            return None
        if opcode == OP_PONG:
            if self.on_pong is not None:
                self.on_pong(frame.payload)
            return None
        if opcode == OP_CLOSE:
            code, reason = self._parse_close(frame.payload)
            # Note it before echoing: if the peer has already hung up, the
            # echo fails, and that mustn't turn a clean close into a 1006.
            if self.close_code is None:
                self.close_code, self.close_reason = code, reason
            self._send_close(code)
            self._finish(code, reason)
            raise ConnectionClosed(self.close_code, self.close_reason)

        if opcode == OP_CONT:
            if self._parts_opcode is None:
                self._fail("continuation frame with nothing to continue")
        elif self._parts_opcode is not None:
            self._fail("new message started before the last one finished")
        else:
            self._parts_opcode = opcode
        self._parts.append(frame.payload)
        self._parts_size += len(frame.payload)
        if self._parts_size > self._max_size:
            self._fail("message is over the size limit", CLOSE_TOO_BIG)
        if not frame.fin:
            return None

        data = b"".join(self._parts)
        kind = self._parts_opcode
        self._parts, self._parts_opcode, self._parts_size = [], None, 0
        if kind == OP_BINARY:
            return data
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            self._fail("text message isn't valid UTF-8", CLOSE_INVALID_DATA)

    def _parse_close(self, payload: bytes) -> tuple[int, str]:
        if not payload:
            return CLOSE_NO_STATUS, ""
        if len(payload) == 1:
            self._fail("close frame with half a status code")
        (code,) = struct.unpack_from("!H", payload)
        if code not in _WIRE_CLOSE_CODES and not 3000 <= code <= 4999:
            self._fail(f"invalid close code {code}")
        try:
            return code, payload[2:].decode("utf-8")
        except UnicodeDecodeError:
            self._fail("close reason isn't valid UTF-8", CLOSE_INVALID_DATA)


def accept_key(key: str) -> str:
    """The Sec-WebSocket-Accept value for a client's Sec-WebSocket-Key."""
    digest = hashlib.sha1(key.strip().encode("ascii") + GUID).digest()
    return base64.b64encode(digest).decode("ascii")


def check_handshake(method: str, headers: Mapping[str, str]) -> str:
    """Validate an upgrade request and return its Sec-WebSocket-Key.

    ``headers`` can be a plain dict or the message object http.server parses
    requests into. Raises HandshakeError carrying the status to answer with.
    """
    fields = _fold_headers(headers)
    if method != "GET":
        raise HandshakeError("a websocket handshake is a GET", 405, {"Allow": "GET"})
    if "websocket" not in _tokens(fields.get("upgrade", "")):
        raise HandshakeError(
            "this endpoint only speaks websocket",
            426,
            {"Upgrade": "websocket", "Connection": "Upgrade"},
        )
    if "upgrade" not in _tokens(fields.get("connection", "")):
        raise HandshakeError("missing 'Connection: Upgrade'")
    version = fields.get("sec-websocket-version", "").strip()
    if version != "13":
        raise HandshakeError(
            f"unsupported websocket version {version!r}",
            426,
            {"Sec-WebSocket-Version": "13"},
        )
    key = fields.get("sec-websocket-key", "").strip()
    try:
        nonce = base64.b64decode(key, validate=True)
    except ValueError:
        nonce = b""
    if len(nonce) != 16:
        raise HandshakeError("missing or malformed Sec-WebSocket-Key")
    return key


def handshake_response(key: str) -> bytes:
    lines = [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Accept: {accept_key(key)}",
    ]
    return "\r\n".join(lines).encode("ascii") + b"\r\n\r\n"


def rejection_response(error: HandshakeError) -> bytes:
    """A complete HTTP response turning down a handshake."""
    body = (error.message + "\n").encode("utf-8")
    lines = [
        f"HTTP/1.1 {error.status} {_reason_phrase(error.status)}",
        "Content-Type: text/plain; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    lines += [f"{name}: {value}" for name, value in error.headers.items()]
    return "\r\n".join(lines).encode("latin-1") + b"\r\n\r\n" + body


def accept(
    sock: socket.socket, *, timeout: float = 5.0, max_size: int = DEFAULT_MAX_SIZE
) -> WebSocket:
    """Do the server half of the opening handshake on a fresh connection.

    On failure the client gets a proper HTTP error and HandshakeError is
    raised; closing the socket is left to the caller.
    """
    try:
        head, rest = _read_head(sock, timeout)
        request_line, fields = _parse_head(head)
        try:
            method, target, version = request_line.split(" ")
        except ValueError:
            raise HandshakeError(f"malformed request line {request_line!r}") from None
        if not version.startswith("HTTP/1.") or version == "HTTP/1.0":
            raise HandshakeError("websocket needs HTTP/1.1", 505)
        key = check_handshake(method, fields)
    except HandshakeError as exc:
        try:
            sock.sendall(rejection_response(exc))
        except OSError:
            pass
        raise
    sock.sendall(handshake_response(key))
    ws = WebSocket(sock, initial=rest, max_size=max_size)
    ws.path = target
    return ws


def connect(
    host: str,
    port: int,
    path: str = "/",
    *,
    timeout: float = 5.0,
    origin: str | None = None,
    headers: Mapping[str, str] | None = None,
    max_size: int = DEFAULT_MAX_SIZE,
) -> WebSocket:
    """Open a client connection.

    This exists for the test suite and for poking at a dev server by hand:
    no TLS, no redirects, no extensions. ``headers`` are merged over the
    standard handshake headers, so it can also be used to send a bad one.
    """
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    fields = {
        "Host": _host_header(host, port),
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Key": key,
        "Sec-WebSocket-Version": "13",
    }
    if origin is not None:
        fields["Origin"] = origin
    fields.update(headers or {})
    lines = [f"GET {path} HTTP/1.1"]
    lines += [f"{name}: {value}" for name, value in fields.items()]

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise WebSocketError(f"can't connect to {host}:{port}: {exc}") from exc
    try:
        sock.sendall("\r\n".join(lines).encode("latin-1") + b"\r\n\r\n")
        head, rest = _read_head(sock, timeout)
        status_line, answer = _parse_head(head)
        status = _status_code(status_line)
        if status != 101:
            raise HandshakeError(f"server answered {status_line!r}", status)
        if "websocket" not in _tokens(answer.get("upgrade", "")):
            raise HandshakeError("101 response without 'Upgrade: websocket'", status)
        # compare against what *we* sent, even if the caller overrode the key
        expected = accept_key(fields["Sec-WebSocket-Key"])
        if answer.get("sec-websocket-accept", "").strip() != expected:
            raise HandshakeError("server sent the wrong Sec-WebSocket-Accept", status)
    except BaseException:
        sock.close()
        raise
    ws = WebSocket(sock, client=True, initial=rest, max_size=max_size)
    ws.path = path
    return ws


def _tokens(value: str) -> set[str]:
    return {token.strip().lower() for token in value.split(",") if token.strip()}


def _fold_headers(headers: Mapping[str, str]) -> dict[str, str]:
    folded: dict[str, str] = {}
    for name, value in headers.items():
        name = name.lower()
        folded[name] = f"{folded[name]}, {value}" if name in folded else value
    return folded


def _reason_phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def _host_header(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _status_code(status_line: str) -> int:
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/") or not parts[1].isdigit():
        raise HandshakeError(f"not an HTTP response: {status_line!r}", 0)
    return int(parts[1])


def _read_head(sock: socket.socket, timeout: float) -> tuple[bytes, bytes]:
    """Read up to the blank line that ends an HTTP head.

    Returns the head and whatever arrived after it; a peer is allowed to
    start sending frames without waiting.
    """
    deadline = time.monotonic() + timeout
    buf = b""
    while b"\r\n\r\n" not in buf:
        if len(buf) > _MAX_HEAD:
            raise HandshakeError("handshake headers are too large", 431)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HandshakeError("timed out waiting for the handshake", 408)
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            raise HandshakeError("timed out waiting for the handshake", 408) from None
        except OSError as exc:
            raise HandshakeError(
                f"connection lost during the handshake: {exc}"
            ) from exc
        if not chunk:
            raise HandshakeError("connection closed during the handshake")
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    return head, rest


def _parse_head(head: bytes) -> tuple[str, dict[str, str]]:
    lines = head.decode("latin-1").split("\r\n")
    fields: dict[str, str] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(":")
        name = name.strip().lower()
        if not colon or not name:
            raise HandshakeError(f"malformed header line {line!r}")
        value = value.strip()
        fields[name] = f"{fields[name]}, {value}" if name in fields else value
    return lines[0], fields
