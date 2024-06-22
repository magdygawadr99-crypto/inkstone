from __future__ import annotations

import pytest

from inkstone.assets import AssetError, data_uri
from inkstone.assets.datauri import guess_mime, parse_data_uri

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">'
    '<path d="M0 0h8v8z"/></svg>'
)


def test_binary_data_is_base64():
    assert data_uri(b"\x89PNG", "image/png") == "data:image/png;base64,iVBORw=="
    assert data_uri(b"", "image/png") == "data:image/png;base64,"


def test_svg_is_percent_encoded():
    assert data_uri('<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml") == (
        "data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22/%3E"
    )


def test_str_and_bytes_give_the_same_result():
    assert data_uri(SVG, "image/svg+xml") == data_uri(SVG.encode(), "image/svg+xml")


def test_awkward_characters_are_escaped():
    uri = data_uri("<a href=\"#x\" title='50% (off)'>", "image/svg+xml")
    assert uri == "data:image/svg+xml,%3Ca%20href=%22%23x%22%20title='50%25%20(off)'%3E"


def test_base64_wins_when_it_is_shorter():
    # every one of these characters costs nine bytes percent-encoded
    svg = "<svg><text>" + "\u65e5\u672c\u8a9e" * 20 + "</text></svg>"
    uri = data_uri(svg, "image/svg+xml")
    assert uri.startswith("data:image/svg+xml;base64,")
    assert parse_data_uri(uri) == ("image/svg+xml", svg.encode("utf-8"))


def test_text_gets_a_charset_only_when_it_needs_one():
    assert data_uri("a{b:c}", "text/css") == "data:text/css,a{b:c}".replace(
        "{", "%7B"
    ).replace("}", "%7D")
    uri = data_uri("x" * 100 + "\u00e9", "text/plain")
    assert uri == "data:text/plain;charset=utf-8," + "x" * 100 + "%C3%A9"
    uri = data_uri("x" * 100 + "\u00e9", "text/plain;charset=utf-8")
    assert uri.count("charset") == 1
    # XML carries its own encoding declaration
    svg = "<svg>" + "x" * 100 + "\u00e9</svg>"
    assert "charset" not in data_uri(svg, "image/svg+xml")


def test_undecodable_text_falls_back_to_base64():
    assert data_uri(b"\xff\xfe\x00", "text/plain") == "data:text/plain;base64,//4A"


@pytest.mark.parametrize(
    "payload, mime",
    [
        (b"", "image/png"),
        (bytes(range(256)), "application/octet-stream"),
        (SVG.encode(), "image/svg+xml"),
        ("line one\r\nline two\n".encode(), "text/plain"),
        ('{"a": "b c", "d": [1, 2]}'.encode(), "application/json"),
        ("caf\u00e9 \u2603".encode(), "text/plain"),
    ],
)
def test_round_trip(payload, mime):
    assert parse_data_uri(data_uri(payload, mime)) == (mime, payload)


def test_parse_data_uri_details():
    assert parse_data_uri("data:,hello%20world") == ("text/plain", b"hello world")
    assert parse_data_uri("DATA:text/html;charset=utf-8;base64,PGI+") == (
        "text/html",
        b"<b>",
    )
    assert parse_data_uri("  data:image/gif;base64,R0lG\n") == ("image/gif", b"GIF")


@pytest.mark.parametrize("uri", ["", "http://example.com/a.png", "data:image/png"])
def test_parse_rejects_other_things(uri):
    with pytest.raises(AssetError, match="not a data URI"):
        parse_data_uri(uri)


@pytest.mark.parametrize(
    "path, expected",
    [
        ("a.png", "image/png"),
        ("img/Photo.JPG", "image/jpeg"),
        ("img\\icon.svg", "image/svg+xml"),
        ("fonts/a.woff2", "font/woff2"),
        ("site.webmanifest", "application/manifest+json"),
        ("app.min.js", "text/javascript"),
        ("archive.tar.gz", "application/octet-stream"),
        ("LICENSE", "application/octet-stream"),
    ],
)
def test_guess_mime(path, expected):
    assert guess_mime(path) == expected


def test_guess_mime_default():
    assert guess_mime("x.unknown", default="text/plain") == "text/plain"
