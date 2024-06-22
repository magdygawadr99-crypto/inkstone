from __future__ import annotations

import json

import pytest

from inkstone.assets import AssetError, Manifest
from inkstone.assets.manifest import Entry, normalise


def sample():
    manifest = Manifest()
    for logical, output, digest, size, integrity in [
        ("css/site.css", "css/site.3f9a1c2e.css", "3f9a", 120, "sha384-A"),
        ("robots.txt", "robots.txt", "77aa", 15, "sha384-B"),
        ("img/a.png", "img/a.01020304.png", "0102", 900, "sha384-C"),
    ]:
        manifest.add(logical, output, hash=digest, size=size, integrity=integrity)
    return manifest


@pytest.mark.parametrize(
    "path, expected",
    [
        ("css/site.css", "css/site.css"),
        ("css\\site.css", "css/site.css"),
        ("/css/site.css", "css/site.css"),
        ("./css/site.css", "css/site.css"),
        ("css//x/../site.css", "css/site.css"),
        ("", ""),
    ],
)
def test_normalise(path, expected):
    assert normalise(path) == expected


def test_lookup():
    manifest = sample()
    assert manifest.url_for("css/site.css") == "css/site.3f9a1c2e.css"
    assert manifest.integrity("css/site.css") == "sha384-A"
    assert manifest.url_for("robots.txt") == "robots.txt"
    assert manifest.get("img/a.png") == Entry(
        "img/a.01020304.png", "0102", 900, "sha384-C"
    )
    assert manifest.get("nope.css") is None


@pytest.mark.parametrize(
    "spelling", ["css\\site.css", "/css/site.css", "./css/site.css"]
)
def test_lookup_is_forgiving_about_spelling(spelling):
    manifest = sample()
    assert manifest.url_for(spelling) == "css/site.3f9a1c2e.css"
    assert spelling in manifest


def test_container_protocol():
    manifest = sample()
    assert len(manifest) == 3
    assert list(manifest) == ["css/site.css", "img/a.png", "robots.txt"]
    assert "css/site.css" in manifest
    assert "css/site.3f9a1c2e.css" not in manifest
    assert [logical for logical, _entry in manifest.items()] == list(manifest)
    assert manifest.outputs() == {
        "css/site.3f9a1c2e.css",
        "img/a.01020304.png",
        "robots.txt",
    }
    assert repr(manifest) == "<Manifest: 3 assets>"
    assert len(Manifest()) == 0


def test_adding_again_replaces():
    manifest = sample()
    manifest.add("css\\site.css", "css/site.aaaa.css", hash="a", size=1, integrity="x")
    assert len(manifest) == 3
    assert manifest.url_for("css/site.css") == "css/site.aaaa.css"


def test_unknown_asset():
    manifest = sample()
    with pytest.raises(AssetError) as info:
        manifest.url_for("css/sit.css")
    assert info.value.path == "css/sit.css"
    assert str(info.value) == (
        "css/sit.css: no such asset (did you mean 'css/site.css'?)"
    )
    with pytest.raises(AssetError) as info:
        manifest.integrity("fonts/totally-different.woff2")
    assert info.value.message == "no such asset"


def test_dict_round_trip():
    manifest = sample()
    data = manifest.to_dict()
    assert data["version"] == 1
    assert data["assets"]["css/site.css"] == {
        "output": "css/site.3f9a1c2e.css",
        "hash": "3f9a",
        "size": 120,
        "integrity": "sha384-A",
    }
    assert Manifest.from_dict(data) == manifest
    assert Manifest.from_dict(json.loads(json.dumps(data))) == manifest
    assert Manifest.from_dict(data) != Manifest()
    assert manifest != data


@pytest.mark.parametrize(
    "data, message",
    [
        ([], "malformed asset manifest"),
        ({}, "malformed asset manifest"),
        ({"version": 1, "assets": []}, "malformed asset manifest"),
        ({"version": 2, "assets": {}}, "unsupported asset manifest version 2"),
        ({"assets": {}}, "unsupported asset manifest version None"),
        (
            {"version": 1, "assets": {"a.css": {"output": "a.css"}}},
            "malformed asset manifest entry for 'a.css'",
        ),
        (
            {"version": 1, "assets": {"a.css": "a.css"}},
            "malformed asset manifest entry for 'a.css'",
        ),
    ],
)
def test_from_dict_rejects_junk(data, message):
    with pytest.raises(AssetError) as info:
        Manifest.from_dict(data)
    assert info.value.message == message


def test_save_and_load(tmp_path):
    path = tmp_path / "deep" / "dir" / "assets.json"
    manifest = sample()
    manifest.save(path)
    text = path.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert json.loads(text) == manifest.to_dict()
    assert Manifest.load(path) == manifest
    assert Manifest.load(str(path)) == manifest
    # no scratch file left behind, and saving twice is fine
    manifest.save(path)
    assert [p.name for p in path.parent.iterdir()] == ["assets.json"]


def test_saved_file_is_stable(tmp_path):
    first = Manifest()
    first.add("b.css", "b.css", hash="1", size=1, integrity="x")
    first.add("a.css", "a.css", hash="2", size=2, integrity="y")
    second = Manifest()
    second.add("a.css", "a.css", hash="2", size=2, integrity="y")
    second.add("b.css", "b.css", hash="1", size=1, integrity="x")
    first.save(tmp_path / "1.json")
    second.save(tmp_path / "2.json")
    assert (tmp_path / "1.json").read_bytes() == (tmp_path / "2.json").read_bytes()


def test_load_errors_name_the_file(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(AssetError, match="cannot read asset manifest") as info:
        Manifest.load(missing)
    assert info.value.path == missing

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(AssetError, match="not valid JSON") as info:
        Manifest.load(broken)
    assert info.value.path == broken

    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"version": 99, "assets": {}}', encoding="utf-8")
    with pytest.raises(AssetError, match="version 99") as info:
        Manifest.load(wrong)
    assert info.value.path == wrong
