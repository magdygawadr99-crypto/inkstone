from __future__ import annotations

import http.client
import os
import socket
import struct
import threading
import time

import pytest

from inkstone.server import ServerError, StaticServer
from inkstone.server.http import (
    guess_type,
    inject_script,
    normalize_base_path,
    parse_range,
    site_url,
    split_target,
)
from inkstone.server.livereload import (
    SCRIPT_TAG,
    SCRIPT_URL,
    SOCKET_URL,
    LiveReloadHub,
)

from .helpers import fetch, raw_request, wait_for


@pytest.fixture
def serve(site):
    servers = []

    def start(root=site, **options):
        server = StaticServer(root, **options)
        server.start()
        servers.append(server)
        return server

    yield start
    for server in servers:
        if server.hub is not None:
            server.hub.close()
        server.stop()


@pytest.fixture
def server(serve):
    return serve()


@pytest.fixture
def live(serve):
    return serve(hub=LiveReloadHub())


def _has_ipv6() -> bool:
    try:
        with socket.socket(socket.AF_INET6) as sock:
            sock.bind(("::1", 0))
    except OSError:
        return False
    return True


def test_root_serves_the_index(server, site):
    response, body = fetch(server.address, "/")
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert response.getheader("Content-Length") == str(len(body))
    assert body == (site / "index.html").read_bytes()


def test_content_type_header(server):
    css, _ = fetch(server.address, "/css/site.css")
    binary, _ = fetch(server.address, "/data.bin")
    assert css.getheader("Content-Type") == "text/css; charset=utf-8"
    assert binary.getheader("Content-Type") == "application/octet-stream"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("index.html", "text/html; charset=utf-8"),
        ("page.HTM", "text/html; charset=utf-8"),
        ("app.js", "text/javascript; charset=utf-8"),
        ("module.mjs", "text/javascript; charset=utf-8"),
        ("data.json", "application/json; charset=utf-8"),
        ("site.css.map", "application/json; charset=utf-8"),
        ("site.webmanifest", "application/manifest+json; charset=utf-8"),
        ("sitemap.xml", "application/xml; charset=utf-8"),
        ("feed.atom", "application/atom+xml; charset=utf-8"),
        ("feed.rss", "application/rss+xml; charset=utf-8"),
        ("logo.svg", "image/svg+xml; charset=utf-8"),
        ("font.woff", "font/woff"),
        ("font.woff2", "font/woff2"),
        ("module.wasm", "application/wasm"),
        ("photo.avif", "image/avif"),
        ("photo.webp", "image/webp"),
        ("photo.JPG", "image/jpeg"),
        ("favicon.ico", "image/x-icon"),
        ("backup.tar.gz", "application/gzip"),
        ("some/dir.with.dots/readme.txt", "text/plain; charset=utf-8"),
        ("thing.inkstone-unknown", "application/octet-stream"),
        ("LICENSE", "application/octet-stream"),
    ],
)
def test_guess_type(name, expected):
    assert guess_type(name) == expected


def test_clean_url_serves_the_html_file(server, site):
    response, body = fetch(server.address, "/about")
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert body == (site / "about.html").read_bytes()


def test_explicit_html_name_still_works(server, site):
    _, body = fetch(server.address, "/about.html")
    assert body == (site / "about.html").read_bytes()


def test_directory_serves_its_index(server, site):
    response, body = fetch(server.address, "/blog/")
    assert response.status == 200
    assert body == (site / "blog" / "index.html").read_bytes()


def test_directory_without_trailing_slash_redirects(server):
    response, body = fetch(server.address, "/blog?page=2")
    assert response.status == 301
    assert response.getheader("Location") == "/blog/?page=2"
    assert body == b""


def test_redirect_location_is_percent_encoded(server, site):
    (site / "my notes").mkdir()
    response, _ = fetch(server.address, "/my%20notes")
    assert response.getheader("Location") == "/my%20notes/"


def test_html_file_wins_over_a_directory_of_the_same_name(server, site):
    (site / "blog.html").write_bytes(b"<p>the blog page</p>")
    response, body = fetch(server.address, "/blog")
    assert response.status == 200
    assert body == b"<p>the blog page</p>"


def test_index_htm_is_an_index_too(server, site):
    (site / "old").mkdir()
    (site / "old" / "index.htm").write_bytes(b"<p>vintage</p>")
    assert fetch(server.address, "/old/")[1] == b"<p>vintage</p>"


def test_directory_without_an_index_is_not_listed(server, site):
    (site / "empty").mkdir()
    response, body = fetch(server.address, "/empty/")
    assert response.status == 404
    assert b"data.bin" not in body


def test_trailing_slash_on_a_file_is_not_found(server):
    assert fetch(server.address, "/about.html/")[0].status == 404


def test_query_string_does_not_affect_the_lookup(server, site):
    response, body = fetch(server.address, "/css/site.css?v=42&x=/../y")
    assert response.status == 200
    assert body == (site / "css" / "site.css").read_bytes()


def test_dot_segments_inside_the_site_are_resolved(server, site):
    _, body = fetch(server.address, "/css/../blog/./index.html")
    assert body == (site / "blog" / "index.html").read_bytes()


def test_builtin_404_page(server):
    response, body = fetch(server.address, "/nope/<b>bold</b>")
    assert response.status == 404
    assert response.getheader("Content-Type") == "text/html; charset=utf-8"
    assert b"/nope/&lt;b&gt;bold&lt;/b&gt;" in body
    assert b"<b>" not in body


def test_custom_404_page(server, site):
    page = b"<html><body>Lost? Try the <a href='/'>front page</a>.</body></html>"
    (site / "404.html").write_bytes(page)
    response, body = fetch(server.address, "/nope")
    assert response.status == 404
    assert body == page
    assert response.getheader("ETag") is None


def test_head_sends_headers_only(server):
    get, body = fetch(server.address, "/css/site.css")
    head, head_body = fetch(server.address, "/css/site.css", method="HEAD")
    assert head.status == 200
    assert head_body == b""
    assert head.getheader("Content-Length") == str(len(body))
    assert head.getheader("ETag") == get.getheader("ETag")


def test_head_for_a_missing_page(server):
    response, body = fetch(server.address, "/nope", method="HEAD")
    assert response.status == 404
    assert body == b""


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [
        ("bytes=0-9", 0, 9),
        ("bytes=10-", 10, 1023),
        ("bytes=-5", 1019, 1023),
        ("bytes=0-0", 0, 0),
        ("bytes=1000-5000", 1000, 1023),
        ("bytes=-5000", 0, 1023),
    ],
)
def test_range_request(server, site, header, start, end):
    data = (site / "data.bin").read_bytes()
    response, body = fetch(server.address, "/data.bin", headers={"Range": header})
    assert response.status == 206
    assert response.getheader("Content-Range") == f"bytes {start}-{end}/1024"
    assert response.getheader("Content-Length") == str(end - start + 1)
    assert body == data[start : end + 1]


@pytest.mark.parametrize("header", ["bytes=1024-", "bytes=5000-6000", "bytes=-0"])
def test_unsatisfiable_range(server, header):
    response, _ = fetch(server.address, "/data.bin", headers={"Range": header})
    assert response.status == 416
    assert response.getheader("Content-Range") == "bytes */1024"


@pytest.mark.parametrize(
    "header", ["bytes=0-1,5-6", "lines=0-5", "bytes=abc", "bytes=9-2", "bytes=-"]
)
def test_unusable_range_header_is_ignored(server, header):
    response, body = fetch(server.address, "/data.bin", headers={"Range": header})
    assert response.status == 200
    assert len(body) == 1024


def test_head_with_a_range(server):
    response, body = fetch(
        server.address, "/data.bin", method="HEAD", headers={"Range": "bytes=0-99"}
    )
    assert response.status == 206
    assert response.getheader("Content-Length") == "100"
    assert body == b""


def test_if_range_with_the_current_etag_honours_the_range(server):
    etag = fetch(server.address, "/data.bin")[0].getheader("ETag")
    headers = {"Range": "bytes=0-3", "If-Range": etag}
    response, body = fetch(server.address, "/data.bin", headers=headers)
    assert response.status == 206
    assert body == b"\x00\x01\x02\x03"


def test_if_range_with_a_stale_etag_sends_the_whole_file(server):
    headers = {"Range": "bytes=0-3", "If-Range": '"an-older-version"'}
    response, body = fetch(server.address, "/data.bin", headers=headers)
    assert response.status == 200
    assert len(body) == 1024


def test_if_range_with_a_date(server):
    modified = fetch(server.address, "/data.bin")[0].getheader("Last-Modified")
    headers = {"Range": "bytes=0-3", "If-Range": modified}
    assert fetch(server.address, "/data.bin", headers=headers)[0].status == 206
    headers["If-Range"] = "Sat, 01 Jan 2000 00:00:00 GMT"
    assert fetch(server.address, "/data.bin", headers=headers)[0].status == 200


def test_etag_revalidation(server):
    first, _ = fetch(server.address, "/css/site.css")
    etag = first.getheader("ETag")
    assert etag.startswith('"') and etag.endswith('"')
    again, body = fetch(
        server.address, "/css/site.css", headers={"If-None-Match": etag}
    )
    assert again.status == 304
    assert body == b""
    assert again.getheader("ETag") == etag
    assert again.getheader("Cache-Control") == "no-cache"


@pytest.mark.parametrize("template", ["W/{etag}", '"something-else", {etag}', "*"])
def test_if_none_match_forms(server, template):
    etag = fetch(server.address, "/css/site.css")[0].getheader("ETag")
    headers = {"If-None-Match": template.format(etag=etag)}
    assert fetch(server.address, "/css/site.css", headers=headers)[0].status == 304


def test_if_none_match_with_another_tag_sends_the_file(server):
    headers = {"If-None-Match": '"not-this-one"'}
    response, body = fetch(server.address, "/css/site.css", headers=headers)
    assert response.status == 200
    assert body


def test_etag_changes_when_the_file_does(server, site):
    before = fetch(server.address, "/css/site.css")[0].getheader("ETag")
    (site / "css" / "site.css").write_bytes(b"body { margin: 0; color: #222; }\n")
    response, _ = fetch(
        server.address, "/css/site.css", headers={"If-None-Match": before}
    )
    assert response.status == 200
    assert response.getheader("ETag") != before


def test_if_modified_since(server):
    modified = fetch(server.address, "/css/site.css")[0].getheader("Last-Modified")
    assert modified.endswith(" GMT")
    headers = {"If-Modified-Since": modified}
    response, body = fetch(server.address, "/css/site.css", headers=headers)
    assert response.status == 304
    assert body == b""


@pytest.mark.parametrize("value", ["Sat, 01 Jan 2000 00:00:00 GMT", "last tuesday", ""])
def test_if_modified_since_that_does_not_apply(server, value):
    headers = {"If-Modified-Since": value}
    assert fetch(server.address, "/css/site.css", headers=headers)[0].status == 200


def test_if_none_match_takes_precedence_over_if_modified_since(server):
    modified = fetch(server.address, "/css/site.css")[0].getheader("Last-Modified")
    headers = {"If-None-Match": '"stale"', "If-Modified-Since": modified}
    assert fetch(server.address, "/css/site.css", headers=headers)[0].status == 200


@pytest.mark.parametrize("path", ["/", "/css/site.css", "/blog", "/nope"])
def test_responses_are_marked_no_cache(server, path):
    assert fetch(server.address, path)[0].getheader("Cache-Control") == "no-cache"


def test_cache_control_can_be_left_out(serve):
    server = serve(cache_control=None)
    assert fetch(server.address, "/")[0].getheader("Cache-Control") is None


@pytest.mark.parametrize(
    "path",
    [
        "/../secret.txt",
        "/../../secret.txt",
        "/css/../../secret.txt",
        "//../secret.txt",
        "/%2e%2e/secret.txt",
        "/..%2fsecret.txt",
        "/%2e%2e%2f%2e%2e%2fsecret.txt",
        "/..%5csecret.txt",
        "/css/..%5c..%5csecret.txt",
        "/css/%2e%2e%5c%2e%2e%5csecret.txt",
        "/..%20/secret.txt",
        "/.../secret.txt",
    ],
)
def test_path_traversal_is_refused(server, site, path):
    (site.parent / "secret.txt").write_bytes(b"top secret")
    response, body = fetch(server.address, path)
    assert response.status == 404
    assert b"top secret" not in body


@pytest.mark.parametrize(
    "path", ["/C:/Windows/win.ini", "/data.bin::$DATA", "/NUL", "/css/site.css."]
)
def test_windows_path_oddities_are_not_found(server, path):
    assert fetch(server.address, path)[0].status == 404


def test_percent_encoded_and_utf8_file_names(server, site):
    (site / "café.html").write_bytes(b"<p>coffee</p>")
    (site / "my notes.txt").write_bytes(b"notes")
    assert fetch(server.address, "/caf%C3%A9.html")[1] == b"<p>coffee</p>"
    assert fetch(server.address, "/caf%C3%A9")[0].status == 200
    assert fetch(server.address, "/my%20notes.txt")[1] == b"notes"
    assert fetch(server.address, "/my+notes.txt")[0].status == 404


def test_raw_utf8_in_the_request_line(server, site):
    (site / "日本語.html").write_bytes(b"<p>nihongo</p>")
    request = "GET /日本語 HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n"
    answer = raw_request(server.address, request.encode("utf-8"))
    assert answer.startswith(b"HTTP/1.1 200 ")
    assert answer.endswith(b"<p>nihongo</p>")


@pytest.mark.parametrize("path", ["/%ff%fe.html", "/caf%E9.html", "/a%00b.html"])
def test_undecodable_path_is_a_bad_request(server, path):
    assert fetch(server.address, path)[0].status == 400


def test_base_path_prefix(serve, site):
    server = serve(base_path="/docs/")
    assert server.url == f"http://127.0.0.1:{server.address[1]}/docs/"
    assert fetch(server.address, "/docs/")[1] == (site / "index.html").read_bytes()
    assert fetch(server.address, "/docs/about")[0].status == 200
    assert fetch(server.address, "/docs/css/site.css")[0].status == 200


def test_base_path_redirects(serve):
    server = serve(base_path="docs")
    for path, status, location in [
        ("/", 302, "/docs/"),
        ("/docs", 302, "/docs/"),
        ("/docs/blog", 301, "/docs/blog/"),
    ]:
        response, _ = fetch(server.address, path)
        assert (response.status, response.getheader("Location")) == (status, location)


def test_paths_outside_the_base_path_are_not_found(serve):
    server = serve(base_path="/docs/")
    response, body = fetch(server.address, "/about")
    assert response.status == 404
    assert b'href="/docs/"' in body
    assert fetch(server.address, "/docsify/")[0].status == 404


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("/", "/"),
        ("", "/"),
        (None, "/"),
        ("blog", "/blog/"),
        ("/blog", "/blog/"),
        ("/a/b/", "/a/b/"),
        ("https://example.org/blog/", "/blog/"),
        ("https://example.org", "/"),
    ],
)
def test_normalize_base_path(given, expected):
    assert normalize_base_path(given) == expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "http://127.0.0.1:8000/blog/"),
        ("localhost", "http://localhost:8000/blog/"),
        ("0.0.0.0", "http://127.0.0.1:8000/blog/"),
        ("::1", "http://[::1]:8000/blog/"),
        ("::", "http://[::1]:8000/blog/"),
    ],
)
def test_site_url(host, expected):
    assert site_url(host, 8000, "/blog/") == expected


def test_script_is_injected_before_the_closing_body_tag(live, site):
    original = (site / "index.html").read_bytes()
    response, body = fetch(live.address, "/")
    assert SCRIPT_TAG + b"</body>" in body
    assert len(body) == len(original) + len(SCRIPT_TAG)
    assert response.getheader("Content-Length") == str(len(body))


def test_head_content_length_counts_the_injected_script(live):
    _, body = fetch(live.address, "/about")
    head, _ = fetch(live.address, "/about", method="HEAD")
    assert head.getheader("Content-Length") == str(len(body))


def test_range_on_an_injected_page_uses_the_injected_size(live):
    _, body = fetch(live.address, "/about")
    response, part = fetch(live.address, "/about", headers={"Range": "bytes=-20"})
    assert response.status == 206
    assert response.getheader("Content-Range").endswith(f"/{len(body)}")
    assert part == body[-20:]


def test_only_html_gets_the_script(live, site):
    assert (
        fetch(live.address, "/css/site.css")[1]
        == (site / "css" / "site.css").read_bytes()
    )


def test_nothing_is_injected_without_a_hub(server, site):
    assert fetch(server.address, "/")[1] == (site / "index.html").read_bytes()


def test_error_pages_get_the_script_as_well(live, site):
    assert SCRIPT_TAG in fetch(live.address, "/nope")[1]
    (site / "404.html").write_bytes(b"<html><body>custom</body></html>")
    response, body = fetch(live.address, "/nope")
    assert body == b"<html><body>custom" + SCRIPT_TAG + b"</body></html>"
    assert response.getheader("Content-Length") == str(len(body))


def test_etag_differs_between_plain_and_injected_pages(serve):
    plain = fetch(serve().address, "/")[0].getheader("ETag")
    injected = fetch(serve(hub=LiveReloadHub()).address, "/")[0].getheader("ETag")
    assert plain != injected


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (b"<html><body><p>x</p></body></html>", b"<html><body><p>x</p>@</body></html>"),
        (b"<BODY>x</BODY >", b"<BODY>x@</BODY >"),
        (
            b"<body><pre>&lt;/body&gt; </body></pre>real end</body>",
            b"<body><pre>&lt;/body&gt; </body></pre>real end@</body>",
        ),
        (b"<html><p>no body tag</html>", b"<html><p>no body tag@</html>"),
        (b"<p>fragment", b"<p>fragment@"),
        (b"", b"@"),
    ],
)
def test_inject_script(page, expected):
    assert inject_script(page, b"@") == expected


def test_client_script_is_served(live):
    response, body = fetch(live.address, SCRIPT_URL)
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/javascript; charset=utf-8"
    assert SOCKET_URL.encode() in body
    headers = {"If-None-Match": response.getheader("ETag")}
    assert fetch(live.address, SCRIPT_URL, headers=headers)[0].status == 304


def test_reserved_urls_do_not_exist_without_a_hub(server):
    assert fetch(server.address, SCRIPT_URL)[0].status == 404
    assert fetch(server.address, SOCKET_URL)[0].status == 404


def test_reserved_prefix_is_never_served_from_disk(live, site):
    (site / "__inkstone__").mkdir()
    (site / "__inkstone__" / "notes.txt").write_bytes(b"shadowed")
    response, body = fetch(live.address, "/__inkstone__/notes.txt")
    assert response.status == 404
    assert body != b"shadowed"


def test_plain_get_on_the_socket_url_asks_for_an_upgrade(live):
    response, _ = fetch(live.address, SOCKET_URL)
    assert response.status == 426
    assert response.getheader("Upgrade") == "websocket"


def test_connection_is_kept_alive(server):
    conn = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        conn.request("GET", "/")
        conn.getresponse().read()
        sock = conn.sock
        for path in ("/about", "/nope", "/blog", "/css/site.css"):
            conn.request("GET", path)
            conn.getresponse().read()
        assert conn.sock is sock
    finally:
        conn.close()


def test_pipelined_requests_are_both_answered(server):
    request = (
        b"GET /css/site.css HTTP/1.1\r\nHost: test\r\n\r\n"
        b"GET /about HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n"
    )
    answer = raw_request(server.address, request)
    assert answer.count(b"HTTP/1.1 200 OK\r\n") == 2
    assert answer.endswith(b"<h1>About</h1></body></html>\n")


def test_http_1_0_client_gets_its_response(server):
    answer = raw_request(server.address, b"GET /css/site.css HTTP/1.0\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 200 ")
    assert answer.endswith(b"body { margin: 0; }\n")


def test_garbage_instead_of_a_request_is_survived(server):
    answer = raw_request(server.address, b"this is not http\r\n\r\n")
    assert b"400" in answer
    assert fetch(server.address, "/")[0].status == 200


def test_other_methods_are_refused(server):
    response, _ = fetch(server.address, "/", method="POST")
    assert response.status == 405
    assert response.getheader("Allow") == "GET, HEAD, OPTIONS"


def test_options(server):
    response, body = fetch(server.address, "/", method="OPTIONS")
    assert response.status == 204
    assert "GET" in response.getheader("Allow")
    assert body == b""


def test_client_hanging_up_mid_download_is_handled_quietly(server, site, capfd):
    (site / "big.bin").write_bytes(b"\0" * (32 * 1024 * 1024))
    sock = socket.create_connection(server.address, timeout=5)
    sock.sendall(b"GET /big.bin HTTP/1.1\r\nHost: test\r\n\r\n")
    assert sock.recv(1024).startswith(b"HTTP/1.1 200 ")
    # with linger set to zero, close() sends a reset instead of a polite FIN
    linger = struct.pack("hh" if os.name == "nt" else "ii", 1, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
    sock.close()

    assert wait_for(lambda: server.connection_count == 0)
    assert fetch(server.address, "/")[0].status == 200
    assert capfd.readouterr().err == ""


def test_requests_are_logged(serve):
    lines = []
    server = serve(log=lines.append, hub=LiveReloadHub())
    fetch(server.address, "/about?x=1")
    fetch(server.address, "/nope")
    fetch(server.address, "/blog", method="HEAD")
    fetch(server.address, SCRIPT_URL)
    assert lines == ["GET /about?x=1 200", "GET /nope 404", "HEAD /blog 301"]


def test_error_page_stands_in_for_missing_pages(live):
    live.error_page = b"<html data-inkstone-error><body>the build broke</body></html>"
    response, body = fetch(live.address, "/not-built-yet/")
    assert response.status == 500
    assert b"the build broke" in body
    assert SCRIPT_TAG in body
    # pages that exist are left to the overlay, and assets stay plain 404s
    assert fetch(live.address, "/")[0].status == 200
    assert fetch(live.address, "/missing.css")[0].status == 404


def test_error_page_replaces_every_page_without_live_reload(server):
    server.error_page = b"<html><body>the build broke</body></html>"
    for path in ("/", "/about", "/blog/", "/nope"):
        response, body = fetch(server.address, path)
        assert response.status == 500
        assert body == b"<html><body>the build broke</body></html>"
    assert fetch(server.address, "/css/site.css")[0].status == 200
    server.error_page = None
    assert fetch(server.address, "/about")[0].status == 200


def test_port_zero_picks_a_free_port(server):
    assert server.address[0] == "127.0.0.1"
    assert server.address[1] > 0


def test_port_fallback_moves_past_a_taken_port(serve, taken_port):
    server = serve(port=taken_port, port_fallback=True)
    assert taken_port < server.address[1] < taken_port + 20
    assert fetch(server.address, "/")[0].status == 200


def test_taken_port_without_fallback_is_an_error(site, taken_port):
    server = StaticServer(site, port=taken_port)
    with pytest.raises(ServerError, match=f"port {taken_port} is already in use"):
        server.start()
    assert not server.running


def test_invalid_port_is_an_error(site):
    with pytest.raises(ServerError, match="not a valid port"):
        StaticServer(site, port=70000).start()


def test_starting_twice_is_an_error(server):
    with pytest.raises(ServerError, match="already running"):
        server.start()


def test_ipv6_loopback(serve):
    if not _has_ipv6():
        pytest.skip("no IPv6 loopback on this machine")
    server = serve(host="::1")
    assert server.url == f"http://[::1]:{server.address[1]}/"
    assert fetch(server.address, "/")[0].status == 200


def test_missing_root_just_means_nothing_is_found(serve, tmp_path):
    server = serve(root=tmp_path / "not-built")
    assert fetch(server.address, "/")[0].status == 404


def test_stop_hangs_up_on_idle_connections(site):
    before = threading.active_count()
    server = StaticServer(site)
    server.start()
    conn = http.client.HTTPConnection(*server.address, timeout=5)
    conn.request("GET", "/")
    conn.getresponse().read()

    # the handler would sit out its 15 second idle timeout if left alone
    started = time.monotonic()
    server.stop()
    assert time.monotonic() - started < 5
    assert not server.running
    assert wait_for(lambda: threading.active_count() <= before)
    conn.close()
    server.stop()


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=90-", (90, 99)),
        ("bytes=-10", (90, 99)),
        ("bytes=50-500", (50, 99)),
        ("BYTES=5-5", (5, 5)),
        ("bytes=0-0,5-9", None),
        ("items=0-5", None),
        ("bytes=5", None),
        ("bytes=7-3", None),
        ("bytes=\u00b2-5", None),
        ("", None),
    ],
)
def test_parse_range(header, expected):
    assert parse_range(header, 100) == expected


@pytest.mark.parametrize(
    ("header", "size"),
    [("bytes=100-", 100), ("bytes=250-300", 100), ("bytes=-0", 100), ("bytes=0-", 0)],
)
def test_parse_range_that_cannot_be_satisfied(header, size):
    with pytest.raises(ValueError):
        parse_range(header, size)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("/a/b?x=1", ("/a/b", "x=1")),
        ("/a?b?c", ("/a", "b?c")),
        ("/caf%C3%A9", ("/café", "")),
        ("/a%20b#frag", ("/a b", "")),
        ("/a%2Fb", ("/a/b", "")),
        ("http://localhost:8000/x?y=1", ("/x", "y=1")),
        ("http://localhost:8000", ("/", "")),
    ],
)
def test_split_target(target, expected):
    assert split_target(target) == expected


@pytest.mark.parametrize("target", ["/%ff", "/a%00b", "*", "about.html", ""])
def test_split_target_rejects_what_it_cannot_decode(target):
    with pytest.raises(ValueError):
        split_target(target)
