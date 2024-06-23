from __future__ import annotations

import http.client
import json
import socket
import time


def wait_for(predicate, timeout: float = 5.0, interval: float = 0.01):
    """Poll until ``predicate()`` is truthy; returns its last value either way."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value or time.monotonic() >= deadline:
            return value
        time.sleep(interval)


def fetch(address, path, method="GET", headers=None):
    conn = http.client.HTTPConnection(*address[:2], timeout=5)
    try:
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        return response, response.read()
    finally:
        conn.close()


def raw_request(address, data: bytes) -> bytes:
    """Send bytes exactly as given and return all the server says before closing."""
    with socket.create_connection(address[:2], timeout=5) as sock:
        sock.sendall(data)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def receive(ws, timeout: float = 5.0) -> dict:
    return json.loads(ws.recv(timeout=timeout))
