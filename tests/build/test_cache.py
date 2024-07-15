from __future__ import annotations

import datetime as dt
import json

import pytest

from inkstone import __version__
from inkstone.build import BuildCache, DepGraph
from inkstone.build.cache import CACHE_VERSION, NotCacheable, decode, encode
from inkstone.markdown import TocEntry
from inkstone.tmpl import Markup


def test_new_cache_is_empty(tmp_path):
    cache = BuildCache.load(tmp_path / "cache")
    assert cache.outputs == {}
    assert cache.previous_outputs == set()
    assert cache.reset_reason == "no cache yet"
    assert len(cache.graph) == 0
    assert not (tmp_path / "cache").exists()


def test_record_save_and_load(tmp_path):
    cache = BuildCache(tmp_path)
    cache.record("a/index.html", "key-a", deps=["source:a.md", "template:page.html"])
    cache.record("rss.xml", "key-rss", kind="file")
    cache.record("b/index.html", "key-b", assets={"asset:css/x.css": "/css/x.123.css"})
    cache.save()

    loaded = BuildCache.load(tmp_path)
    assert loaded.reset_reason is None
    assert loaded.key_of("a/index.html") == "key-a"
    assert loaded.is_fresh("a/index.html", "key-a")
    assert not loaded.is_fresh("a/index.html", "other")
    assert not loaded.is_fresh("zzz.html", "key-a")
    assert loaded.entry("rss.xml") == {"key": "key-rss", "kind": "file"}
    assets = loaded.entry("b/index.html")["assets"]
    assert assets == {"asset:css/x.css": "/css/x.123.css"}
    assert loaded.previous_outputs == {"a/index.html", "rss.xml", "b/index.html"}
    assert loaded.graph.dependencies("output:a/index.html") == {
        "source:a.md",
        "template:page.html",
    }
    assert loaded.graph == cache.graph


def test_state_file_is_versioned_json(tmp_path):
    cache = BuildCache(tmp_path)
    cache.record("a.html", "k")
    cache.save()
    data = json.loads((tmp_path / "build.json").read_text(encoding="utf-8"))
    assert data["version"] == CACHE_VERSION
    assert data["inkstone"] == __version__
    assert data["outputs"] == {"a.html": {"key": "k", "kind": "page"}}
    assert data["deps"] == {"output:a.html": []}


def test_forget_and_retain(tmp_path):
    cache = BuildCache(tmp_path)
    for name in ("a.html", "b.html", "c.html"):
        cache.record(name, "k", deps=[f"source:{name}"])
    cache.forget("a.html")
    assert "a.html" not in cache.outputs
    assert "output:a.html" not in cache.graph
    cache.retain(["b.html", "zzz.html"])
    assert list(cache.outputs) == ["b.html"]
    assert list(cache.graph) == ["output:b.html"]


def test_clear_keeps_the_list_of_previous_outputs(tmp_path):
    cache = BuildCache(tmp_path)
    cache.record("a.html", "k")
    cache.save()
    loaded = BuildCache.load(tmp_path)
    loaded.clear()
    assert loaded.outputs == {}
    assert loaded.previous_outputs == {"a.html"}


def test_destroy_removes_the_directory(tmp_path):
    cache = BuildCache(tmp_path / "cache")
    cache.record("a.html", "k")
    cache.put_render("a.md", "k", {"content": "x"})
    cache.save()
    cache.destroy()
    assert not (tmp_path / "cache").exists()
    assert cache.outputs == {} and cache.previous_outputs == set()


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{ not json", "damaged cache"),
        ("[1, 2]", "damaged cache"),
        ('{"version": %d}' % CACHE_VERSION, "damaged cache"),
        ('{"version": %d, "outputs": []}' % CACHE_VERSION, "damaged cache"),
        (
            '{"version": %d, "outputs": {"a": {"key": 3}}}' % CACHE_VERSION,
            "damaged cache",
        ),
        (
            '{"version": %d, "outputs": {}, "deps": {"a": "b"}}' % CACHE_VERSION,
            "damaged cache",
        ),
        ('{"version": 1, "outputs": {"old.html": {}}}', "cache format changed"),
    ],
)
def test_broken_state_is_treated_as_empty(tmp_path, text, reason):
    (tmp_path / "build.json").write_text(text, encoding="utf-8")
    cache = BuildCache.load(tmp_path)
    assert cache.outputs == {}
    assert cache.reset_reason == reason


def test_old_format_still_tells_which_files_are_ours(tmp_path):
    (tmp_path / "build.json").write_text(
        '{"version": 1, "outputs": {"old.html": {"key": "k"}}}', encoding="utf-8"
    )
    assert BuildCache.load(tmp_path).previous_outputs == {"old.html"}
    (tmp_path / "build.json").write_text(
        '{"version": 0, "outputs": ["listed.html", 3]}', encoding="utf-8"
    )
    assert BuildCache.load(tmp_path).previous_outputs == {"listed.html"}


def test_cache_from_another_inkstone_version_keeps_only_the_file_list(tmp_path):
    cache = BuildCache(tmp_path)
    cache.record("a.html", "k", deps=["source:a.md"])
    cache.save()
    path = tmp_path / "build.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["inkstone"] = "0.0.1"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = BuildCache.load(tmp_path)
    assert loaded.reset_reason == "inkstone was upgraded"
    assert loaded.outputs == {} and len(loaded.graph) == 0
    assert loaded.previous_outputs == {"a.html"}


def test_binary_garbage_in_the_state_file(tmp_path):
    (tmp_path / "build.json").write_bytes(b"\xff\xfe\x00\x01garbage")
    cache = BuildCache.load(tmp_path)
    assert cache.outputs == {}
    assert cache.reset_reason.startswith("unreadable cache")


def test_renders_round_trip(tmp_path):
    cache = BuildCache(tmp_path)
    fields = {
        "content": Markup("<p>Hi</p>"),
        "summary": Markup("<p>Hi</p>"),
        "truncated": False,
        "toc": [TocEntry(2, "a", "A", [TocEntry(3, "b", "B")])],
        "toc_html": Markup("<ul></ul>"),
        "word_count": None,
        "reading_time": 3,
        "extras": {"when": dt.datetime(2024, 5, 3, 14, 0, tzinfo=dt.timezone.utc)},
    }
    assert cache.put_render("posts/a.md", "key-1", fields) is True
    assert cache.get_render("posts/a.md", "key-1") == fields
    restored = cache.get_render("posts/a.md", "key-1")
    assert isinstance(restored["content"], Markup)
    assert isinstance(restored["toc"][0], TocEntry)
    assert restored["toc"][0].children[0].title == "B"
    assert cache.get_render("posts/a.md", "key-2") is None
    assert cache.get_render("posts/b.md", "key-1") is None


def test_render_that_cannot_be_stored_is_dropped(tmp_path):
    cache = BuildCache(tmp_path)
    assert cache.put_render("a.md", "k", {"content": "x"}) is True
    assert cache.put_render("a.md", "k2", {"extras": {"thing": object()}}) is False
    # the stale entry is gone too, rather than being served for the old key
    assert cache.get_render("a.md", "k") is None
    assert cache.get_render("a.md", "k2") is None


@pytest.mark.parametrize(
    "junk", ["", "{", "[]", '{"key": "k"}', '{"key": "k", "source": 1}']
)
def test_broken_render_files_are_ignored(tmp_path, junk):
    cache = BuildCache(tmp_path)
    cache.put_render("a.md", "k", {"content": "x"})
    (render_file,) = cache.render_dir.iterdir()
    render_file.write_text(junk, encoding="utf-8")
    assert cache.get_render("a.md", "k") is None


def test_prune_renders_drops_the_ones_nobody_asked_for(tmp_path):
    cache = BuildCache(tmp_path)
    for name in ("a.md", "b.md", "c.md"):
        cache.put_render(name, "k", {"content": name})
    fresh = BuildCache(tmp_path)
    assert fresh.get_render("a.md", "k") == {"content": "a.md"}
    fresh.put_render("d.md", "k", {"content": "d"})
    assert fresh.prune_renders() == 2
    assert fresh.get_render("a.md", "k") is not None
    assert fresh.get_render("d.md", "k") is not None
    assert fresh.get_render("b.md", "k") is None
    assert BuildCache(tmp_path / "empty").prune_renders() == 0


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        7,
        1.5,
        "text",
        Markup("<b>bold</b>"),
        [1, "two", [3]],
        {"a": {"b": [Markup("<i>x</i>")]}},
        dt.date(2024, 5, 3),
        dt.datetime(2024, 5, 3, 14, 30, tzinfo=dt.timezone(dt.timedelta(hours=2))),
        TocEntry(2, "id", "Title", [TocEntry(3, "sub", "Sub")]),
        {"$type": "looks like ours", "value": 1},
        {"nested": {"$type": "markup"}},
    ],
)
def test_encode_decode_round_trip(value):
    encoded = encode(value)
    json.dumps(encoded)
    decoded = decode(json.loads(json.dumps(encoded)))
    assert decoded == value
    assert type(decoded) is type(value)


def test_tuples_come_back_as_lists():
    assert decode(encode((1, 2))) == [1, 2]


@pytest.mark.parametrize("value", [object(), {1: "int key"}, {"a": {2, 3}}, [b"bytes"]])
def test_values_that_cannot_be_cached(value):
    with pytest.raises(NotCacheable):
        encode(value)


def test_decode_rejects_unknown_tags():
    with pytest.raises(ValueError, match="unknown cached type"):
        decode({"$type": "mystery"})


def test_graph_is_a_dep_graph(tmp_path):
    assert isinstance(BuildCache(tmp_path).graph, DepGraph)
