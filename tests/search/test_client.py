from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from inkstone.search import (
    CLIENT_SCRIPT,
    client_script,
    fold,
    parse_query,
    stem,
    tokenize,
)

from .corpus import DOCS, build_index
from .test_stemmer import STEMS

HARNESS = Path(__file__).with_name("client_harness.js")
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

TEXTS = [
    "Hello, World! It's O'Reilly's state-of-the-art snake_case and CamelCase.",
    "Crème brûlée costs 3.14 or 1,000,000 in C++ and C#, see v1.2.3 on 192.168.1.1",
    "URLs IDs parseXMLDoc utf8Decode iPhone macOS e-mail don't users' __init__",
    "ΟΔΟΣ Straße ﬁne İstanbul Łódź hyphen\u00adation cafe\u0301 Москва 日本語",
    "हिन्दी भाषा, 2019-2021, x86_64, getHTTP2Response, rock'n'roll, #tag, a+b",
    *(fields["body"] for _, fields, _ in DOCS),
]

QUERIES = [
    "static site",
    'static site -wordpress "exact phrase" title:markdown gen*',
    "+python generators",
    "+python +yield",
    "title:search",
    "body:search -tags:search",
    '"state of the art"',
    '"static site generator"',
    "state-of-the-art",
    "publish_site deployHost",
    "generati*",
    "writ*",
    "s*",
    "pythn~",
    "wordpres~ weekand~",
    "ss~",
    "café",
    "the",
    "-python",
    "note: markdown",
    "http://example.com/static",
    '"never closed phrase',
    "“static site”",
    "3.50 bm25 c++",
    "",
]

PREFIXES = ["gen", "generati", "stat", "s", "caf", "publ", "zzz", ""]

HIGHLIGHTS = [
    ("Static site generators compared", ["static", "generat"]),
    ("use snake_case & <b>HTMLParser</b>", ["snakecas", "snake", "case", "parser"]),
    ("Crème brûlée at the café", ["cafe", "creme"]),
    ("nothing to see", ["absent"]),
]

UI_STEPS = [
    {"type": "focus"},
    {"type": "input", "value": "stat"},
    {"type": "key", "key": "ArrowDown"},
    {"type": "key", "key": "ArrowDown"},
    {"type": "key", "key": "ArrowUp"},
    {"type": "key", "key": "ArrowUp"},
    {"type": "key", "key": "Enter"},
    {"type": "key", "key": "Escape"},
    {"type": "key", "key": "Escape"},
    {"type": "input", "value": "zzzz"},
    {"type": "input", "value": "s"},
    {"type": "input", "value": "markdown "},
    {"type": "click-outside"},
    {"type": "focus"},
    {"type": "destroy"},
]


def run_client(job: dict, **env: str) -> dict:
    result = subprocess.run(
        [NODE, str(HARNESS), str(CLIENT_SCRIPT)],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def index():
    return build_index()


@pytest.fixture(scope="module")
def client(index):
    job = {
        "words": [word for word, _ in STEMS],
        "fold": TEXTS,
        "texts": TEXTS,
        "index": index.to_dict(),
        "queries": QUERIES,
        "limit": 10,
        "prefixes": PREFIXES,
        "highlights": HIGHLIGHTS,
        "badIndex": {**index.to_dict(), "version": 99},
        "asScript": True,
        "ui": {
            "container": "ul",
            "options": {"url": "/search-index.json", "debounce": 5, "limit": 5},
            "steps": UI_STEPS,
        },
        "uiEmpty": {
            "container": "div",
            "options": {"debounce": 0, "prefix": False, "emptyText": "Nope"},
            "steps": [
                {"type": "input", "value": "stat"},
                {"type": "input", "value": "static"},
            ],
        },
    }
    return run_client(job)


@needs_node
def test_stemmer_agrees_with_python(client):
    expected = [stem(word) for word, _ in STEMS]
    assert client["stems"] == expected


@needs_node
def test_fold_agrees_with_python(client):
    assert client["folded"] == [fold(text) for text in TEXTS]


@needs_node
def test_tokenizer_agrees_with_python(client):
    for text, tokens in zip(TEXTS, client["tokens"]):
        expected = [
            [t.text, t.position, t.start, t.end, t.joined] for t in tokenize(text)
        ]
        assert tokens == expected, text


@needs_node
def test_query_parser_agrees_with_python(client, index):
    for query, parsed in zip(QUERIES, client["parsed"]):
        expected = [
            [clause.kind, clause.text, clause.field, clause.occur]
            for clause in parse_query(query, index.fields).clauses
        ]
        assert parsed == expected, query


@needs_node
def test_search_results_agree_with_python(client, index):
    for query, hits in zip(QUERIES, client["results"]):
        expected = index.search(query, limit=10)
        assert [hit["id"] for hit in hits] == [hit.doc_id for hit in expected], query
        for theirs, ours in zip(hits, expected):
            assert theirs["score"] == pytest.approx(ours.score, rel=1e-9), query
            assert theirs["matches"] == ours.matches, query
            assert theirs["stored"] == ours.stored, query


@needs_node
def test_search_finds_something_for_most_queries(client):
    # guards the comparison above against both sides returning nothing
    found = [query for query, hits in zip(QUERIES, client["results"]) if hits]
    assert len(found) >= 18
    assert client["defaultLimit"] == 3


@needs_node
def test_suggestions_agree_with_python(client, index):
    assert client["suggestions"] == [index.suggest(prefix) for prefix in PREFIXES]


@needs_node
def test_highlight_segments(client):
    first, compound, accents, nothing = client["highlights"]
    assert first == [
        ["Static", True],
        [" site ", False],
        ["generators", True],
        [" compared", False],
    ]
    assert [text for text, match in compound if match] == ["snake_case", "Parser"]
    assert "".join(text for text, _ in compound) == HIGHLIGHTS[1][0]
    assert [text for text, match in accents if match] == ["Crème", "café"]
    assert nothing == [["nothing to see", False]]


@needs_node
def test_index_of_another_format_version_is_refused(client):
    assert "unsupported index format 99" in client["badIndexError"]


@needs_node
def test_script_tag_include_defines_one_global(client):
    assert client["globals"] == ["InkstoneSearch"]
    assert {"load", "search", "suggest", "attach", "Index"} <= set(client["api"])
    assert client["scriptStem"] == "generat"


@needs_node
def test_load_and_module_level_search(client):
    assert "no index yet" in client["searchBeforeLoad"]
    assert "404" in client["missing"]
    assert client["fetched"] == ["/nope.json", "/search-index.json"]
    assert client["searchAfterLoad"] == ["static-sites"]
    assert client["suggestAfterLoad"] == ["generators"]


@needs_node
def test_search_box_wiring(client):
    ui = client["ui"]
    assert ui["role"] == "combobox" and ui["controls"]
    start, focused, typed = ui["snapshots"][:3]
    assert start["hidden"] and start["expanded"] == "false"
    assert focused["hidden"]
    # "stat" is completed as a prefix: static sites, the state of the art
    assert not typed["hidden"] and typed["expanded"] == "true"
    assert len(typed["items"]) == 3
    assert typed["items"][0].startswith("Static site generators compared")
    assert typed["links"][0] == "/static-sites/"
    assert "Static" in typed["marks"] and "static" in typed["marks"]
    assert typed["active"] == -1 and typed["activedescendant"] is None


@needs_node
def test_search_box_keyboard_navigation(client):
    ui = client["ui"]
    down, down_again, up, up_again, enter, escape, escape_again = ui["snapshots"][3:10]
    assert [down["active"], down_again["active"], up["active"]] == [0, 1, 0]
    # going up from the first hit wraps around to the last one
    assert up_again["active"] == 2
    assert up_again["selected"] == 1
    assert up_again["activedescendant"].endswith("-2")
    assert enter["clicked"] == [up_again["links"][2]]
    assert escape["hidden"] and escape["items"] == [] and escape["expanded"] == "false"
    assert escape_again["hidden"]
    # arrows, Enter and the first Escape are ours; the second Escape is not
    assert ui["prevented"] == [True, True, True, True, True, True, False]


@needs_node
def test_search_box_empty_states_and_teardown(client):
    ui = client["ui"]
    snapshots = ui["snapshots"][10:16]
    no_hits, too_short, finished_word, outside, refocus, destroyed = snapshots
    assert no_hits["items"] == [] and no_hits["empty"] == ["No results"]
    assert not no_hits["hidden"]
    assert too_short["hidden"] and too_short["empty"] == []
    # a trailing space ends the word, so no prefix expansion any more
    assert len(finished_word["items"]) == 2
    assert outside["hidden"]
    assert not refocus["hidden"] and len(refocus["items"]) == 2
    assert destroyed["hidden"] and destroyed["items"] == []
    assert ui["listeners"] == 0


@needs_node
def test_search_box_without_prefix_completion(client):
    ui = client["uiEmpty"]
    partial, whole = ui["snapshots"][1:3]
    assert partial["items"] == [] and partial["empty"] == ["Nope"]
    assert len(whole["items"]) == 2
    assert whole["links"] == ["/static-sites/", "/leaving-wordpress/"]


@needs_node
def test_tokenizer_without_unicode_property_escapes(client):
    assert client["refusedPatterns"] == 0
    old = run_client({"texts": TEXTS, "fold": TEXTS}, INKSTONE_NO_PROPERTY_ESCAPES="1")
    assert old["refusedPatterns"] == 1
    assert old["tokens"] == client["tokens"]
    assert old["folded"] == client["folded"]


def test_client_script_is_shipped_with_the_package():
    assert CLIENT_SCRIPT.is_file()
    source = client_script()
    assert "InkstoneSearch" in source
    # plain ASCII, so it works whatever charset the page declares
    assert source.isascii()


def test_client_sticks_to_es2017_syntax():
    source = client_script()
    newer = {
        "optional chaining": r"\?\.[A-Za-z_(\[]",
        "nullish coalescing": r"\?\?",
        "object spread": r"\{\s*\.\.\.",
        "optional catch binding": r"catch\s*\{",
        "lookbehind or named group": r"\(\?<",
        "regex property escape literal": r"/[^/\n]*\\p\{[^/\n]*/[a-z]*u",
        "globalThis": r"\bglobalThis\b",
        "newer builtins": r"\.(matchAll|replaceAll|flat|flatMap|at|trimStart)\(",
        "Object.fromEntries": r"Object\.fromEntries",
        "private fields": r"this\.#",
    }
    found = [name for name, pattern in newer.items() if re.search(pattern, source)]
    assert found == []
