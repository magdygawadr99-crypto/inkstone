from __future__ import annotations

import copy
import types

import pytest

from inkstone.utils.collections import (
    AttrDict,
    OrderedSet,
    chunked,
    deep_merge,
    flatten,
    get_path,
    group_by,
    set_path,
    unique,
)


@pytest.mark.parametrize(
    ("items", "size", "expected"),
    [
        ([1, 2, 3, 4, 5], 2, [[1, 2], [3, 4], [5]]),
        ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
        ([1, 2], 5, [[1, 2]]),
        ([], 3, []),
        ("abcde", 3, [["a", "b", "c"], ["d", "e"]]),
        ([1, 2, 3], 1, [[1], [2], [3]]),
    ],
)
def test_chunked(items, size, expected):
    assert list(chunked(items, size)) == expected


def test_chunked_is_lazy_and_validates_size():
    chunks = chunked(iter(range(10**9)), 3)
    assert next(chunks) == [0, 1, 2]
    with pytest.raises(ValueError):
        list(chunked([1], 0))


def test_unique_keeps_first_occurrence_and_order():
    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert unique("mississippi") == ["m", "i", "s", "p"]
    assert unique([]) == []
    assert unique(["B", "a", "b", "A"], key=str.lower) == ["B", "a"]


def test_unique_copes_with_unhashable_items():
    items = [{"a": 1}, [1, 2], {"a": 1}, [1, 2], "x", {"a": 2}]
    assert unique(items) == [{"a": 1}, [1, 2], "x", {"a": 2}]
    people = [{"id": 1, "tags": ["x"]}, {"id": 2, "tags": ["x"]}, {"id": 3, "tags": []}]
    assert unique(people, key=lambda p: p["tags"]) == [people[0], people[2]]


def test_group_by_callable():
    words = ["apple", "avocado", "banana", "blueberry", "cherry", "apricot"]
    assert group_by(words, lambda word: word[0]) == {
        "a": ["apple", "avocado", "apricot"],
        "b": ["banana", "blueberry"],
        "c": ["cherry"],
    }
    assert list(group_by([3, 1, 2, 1], lambda n: n)) == [3, 1, 2]
    assert group_by([], len) == {}


def test_group_by_path():
    posts = [
        {"title": "a", "meta": {"year": 2023}},
        {"title": "b", "meta": {"year": 2024}},
        {"title": "c", "meta": {"year": 2023}},
        {"title": "d"},
    ]
    grouped = group_by(posts, "meta.year")
    assert [post["title"] for post in grouped[2023]] == ["a", "c"]
    assert [post["title"] for post in grouped[None]] == ["d"]
    pages = [types.SimpleNamespace(kind="post"), types.SimpleNamespace(kind="page")]
    assert list(group_by(pages, "kind")) == ["post", "page"]


@pytest.mark.parametrize(
    ("base", "override", "expected"),
    [
        ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}),
        ({"a": 1}, {"a": 2}, {"a": 2}),
        (
            {"a": {"x": 1, "y": 2}},
            {"a": {"y": 3, "z": 4}},
            {"a": {"x": 1, "y": 3, "z": 4}},
        ),
        (
            {"a": {"b": {"c": 1}}},
            {"a": {"b": {"d": 2}}},
            {"a": {"b": {"c": 1, "d": 2}}},
        ),
        ({"a": {"x": 1}}, {"a": "scalar"}, {"a": "scalar"}),
        ({"a": "scalar"}, {"a": {"x": 1}}, {"a": {"x": 1}}),
        ({"a": [1, 2]}, {"a": [3]}, {"a": [3]}),
        ({"a": 1}, {"a": None}, {"a": None}),
        ({}, {}, {}),
        ({"a": 1}, {}, {"a": 1}),
    ],
)
def test_deep_merge(base, override, expected):
    assert deep_merge(base, override) == expected


def test_deep_merge_list_strategies():
    base = {"tags": ["a", "b"], "nested": {"items": [1]}}
    override = {"tags": ["b", "c"], "nested": {"items": [1, 2]}}
    assert deep_merge(base, override, lists="append") == {
        "tags": ["a", "b", "b", "c"],
        "nested": {"items": [1, 1, 2]},
    }
    assert deep_merge(base, override, lists="unique") == {
        "tags": ["a", "b", "c"],
        "nested": {"items": [1, 2]},
    }
    with pytest.raises(ValueError, match="unknown list strategy"):
        deep_merge(base, override, lists="zip")


def test_deep_merge_does_not_touch_or_share_its_inputs():
    base = {"a": {"x": [1]}, "keep": {"k": 1}}
    override = {"a": {"y": [2]}}
    before = copy.deepcopy((base, override))
    merged = deep_merge(base, override)
    merged["a"]["x"].append(99)
    merged["a"]["y"].append(99)
    merged["keep"]["k"] = 2
    assert (base, override) == before


def test_deep_merge_accepts_any_mapping():
    merged = deep_merge(AttrDict(a={"x": 1}), types.MappingProxyType({"a": {"y": 2}}))
    assert merged == {"a": {"x": 1, "y": 2}}
    assert type(merged) is dict


DATA = {
    "site": {"title": "Blog", "authors": [{"name": "Sam"}, {"name": "Alex"}]},
    "empty": None,
    "zero": 0,
    "dotted.key": "literal",
}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("site.title", "Blog"),
        ("site.authors.0.name", "Sam"),
        ("site.authors.-1.name", "Alex"),
        ("site.authors.5.name", "fallback"),
        ("site.authors.first.name", "fallback"),
        ("site.missing", "fallback"),
        ("site.title.deeper", "fallback"),
        ("missing.entirely", "fallback"),
        ("empty", None),
        ("empty.below", "fallback"),
        ("zero", 0),
        ("site", DATA["site"]),
    ],
)
def test_get_path(path, expected):
    assert get_path(DATA, path, "fallback") == expected


def test_get_path_options():
    assert get_path(DATA, "nope") is None
    assert get_path(DATA, "site/title", sep="/") == "Blog"
    assert get_path(DATA, "dotted.key", sep="/") == "literal"
    page = types.SimpleNamespace(meta={"tags": ("a", "b")}, title="Hi")
    assert get_path(page, "title") == "Hi"
    assert get_path(page, "meta.tags.1") == "b"
    assert get_path(page, "missing", 0) == 0


def test_set_path_creates_intermediate_dicts():
    data: dict = {}
    set_path(data, "a.b.c", 1)
    set_path(data, "a.b.d", 2)
    set_path(data, "top", 3)
    assert data == {"a": {"b": {"c": 1, "d": 2}}, "top": 3}


def test_set_path_overwrites_and_walks_lists():
    data = {"a": "scalar", "items": [{"n": 1}, {"n": 2}], "flat": [1, 2, 3]}
    set_path(data, "a.b", 1)
    set_path(data, "items.1.n", 20)
    set_path(data, "items.0.extra.deep", True)
    set_path(data, "flat.0", 100)
    assert data == {
        "a": {"b": 1},
        "items": [{"n": 1, "extra": {"deep": True}}, {"n": 20}],
        "flat": [100, 2, 3],
    }
    set_path(data, "x/y", 1, sep="/")
    assert data["x"] == {"y": 1}
    with pytest.raises(IndexError):
        set_path(data, "flat.10", 1)


@pytest.mark.parametrize(
    ("items", "depth", "expected"),
    [
        ([1, [2, [3, [4]]]], None, [1, 2, 3, 4]),
        ([1, [2, [3, [4]]]], 1, [1, 2, [3, [4]]]),
        ([1, [2, [3, [4]]]], 0, [1, [2, [3, [4]]]]),
        ([[1, 2], (3, 4), [[5]]], None, [1, 2, 3, 4, 5]),
        (["ab", ["cd"], {"k": [1]}], None, ["ab", "cd", {"k": [1]}]),
        ([[], [[]], [[], []]], None, []),
        ([], None, []),
    ],
)
def test_flatten(items, depth, expected):
    assert flatten(items, depth=depth) == expected


def test_flatten_takes_any_iterable():
    assert flatten(iter([[1], [2, [3]]])) == [1, 2, 3]
    assert flatten(([1], (2,))) == [1, 2]


def test_attrdict_reads_and_writes_both_ways():
    author = {"name": "Sam", "links": [{"url": "/"}]}
    config = AttrDict({"title": "Blog", "author": author})
    assert config.title == "Blog"
    assert config.author.name == "Sam"
    assert config.author.links[0].url == "/"
    assert config["author"]["name"] == "Sam"
    config.subtitle = "Notes"
    config.author.email = "sam@example.com"
    config["extra"] = {"k": "v"}
    assert config["subtitle"] == "Notes"
    assert config.author["email"] == "sam@example.com"
    assert config.extra.k == "v"
    del config.subtitle
    assert "subtitle" not in config


def test_attrdict_missing_attributes():
    config = AttrDict(a=1)
    with pytest.raises(AttributeError, match="missing"):
        config.missing
    with pytest.raises(AttributeError):
        del config.missing
    assert getattr(config, "missing", "default") == "default"
    assert not hasattr(config, "missing")
    assert config.get("missing") is None


def test_attrdict_wraps_everything_that_goes_in():
    config = AttrDict()
    config.update({"a": {"b": 1}}, c={"d": 2})
    config.setdefault("e", {"f": 3})
    config.setdefault("e", {"ignored": True})
    config["list"] = [{"g": 4}, [{"h": 5}]]
    assert config.a.b == 1
    assert config.c.d == 2
    assert config.e.f == 3
    assert config.list[0].g == 4
    assert config.list[1][0].h == 5
    assert isinstance(config.a, AttrDict)


def test_attrdict_is_still_a_dict():
    config = AttrDict(zeta=1, alpha={"x": 1})
    assert isinstance(config, dict)
    assert config == {"zeta": 1, "alpha": {"x": 1}}
    assert list(config) == ["zeta", "alpha"]
    assert config.items is not None and callable(config.items)
    assert repr(config) == "{'zeta': 1, 'alpha': {'x': 1}}"
    config["items"] = "shadowed by the method"
    assert callable(config.items)
    assert config["items"] == "shadowed by the method"


def test_attrdict_copy_and_to_dict():
    config = AttrDict(a={"b": [{"c": 1}]})
    clone = config.copy()
    assert type(clone) is AttrDict and clone == config
    clone.top = 1
    assert "top" not in config
    plain = config.to_dict()
    assert plain == {"a": {"b": [{"c": 1}]}}
    assert type(plain) is dict
    assert type(plain["a"]) is dict
    assert type(plain["a"]["b"][0]) is dict
    deep = copy.deepcopy(config)
    deep.a.b[0].c = 2
    assert config.a.b[0].c == 1
    assert type(deep.a) is AttrDict


def test_ordered_set_keeps_insertion_order():
    items = OrderedSet([3, 1, 3, 2, 1])
    assert list(items) == [3, 1, 2]
    assert len(items) == 3
    assert 1 in items and 9 not in items
    items.add(9)
    items.add(3)
    assert list(items) == [3, 1, 2, 9]
    items.discard(1)
    items.discard("not there")
    assert list(items) == [3, 2, 9]
    assert list(reversed(items)) == [9, 2, 3]
    assert items[0] == 3 and items[-1] == 9
    assert repr(items) == "OrderedSet([3, 2, 9])"


def test_ordered_set_mutation_helpers():
    items = OrderedSet("abc")
    items.update("cde")
    assert list(items) == ["a", "b", "c", "d", "e"]
    items.remove("a")
    with pytest.raises(KeyError):
        items.remove("a")
    assert items.pop() in "bcde"
    items.clear()
    assert not items
    assert list(OrderedSet()) == []


def test_ordered_set_operators_keep_order():
    left = OrderedSet([1, 2, 3, 4])
    assert list(left | [9, 2, 8]) == [1, 2, 3, 4, 9, 8]
    assert list(left & {4, 2}) == [2, 4]
    assert list(left - {1, 3}) == [2, 4]
    assert isinstance(left | [5], OrderedSet)
    assert left <= {1, 2, 3, 4, 5}
    assert left.isdisjoint([7, 8])


def test_ordered_set_equality():
    assert OrderedSet([1, 2]) == OrderedSet([1, 2])
    assert OrderedSet([1, 2]) != OrderedSet([2, 1])
    assert OrderedSet([1, 2]) == {2, 1}
    assert OrderedSet([1, 2]) != {1, 2, 3}
    assert OrderedSet([1, 2]) != [1, 2]
    with pytest.raises(TypeError):
        hash(OrderedSet())
