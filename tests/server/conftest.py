from __future__ import annotations

import socket

import pytest


@pytest.fixture
def site(tmp_path):
    """A small built site."""
    root = tmp_path / "site"
    (root / "blog").mkdir(parents=True)
    (root / "css").mkdir()
    (root / "index.html").write_bytes(
        b"<!doctype html>\n<html><head><title>Home</title></head>"
        b"<body><h1>Home</h1></body></html>\n"
    )
    (root / "about.html").write_bytes(b"<html><body><h1>About</h1></body></html>\n")
    (root / "blog" / "index.html").write_bytes(
        b"<html><body><h1>Blog</h1></body></html>\n"
    )
    (root / "css" / "site.css").write_bytes(b"body { margin: 0; }\n")
    (root / "data.bin").write_bytes(bytes(range(256)) * 4)
    return root


@pytest.fixture
def taken_port():
    """A port on 127.0.0.1 that something else is already listening on."""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    yield blocker.getsockname()[1]
    blocker.close()
