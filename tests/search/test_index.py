from __future__ import annotations

import json
import math
from datetime import date, datetime

import pytest

from inkstone.errors import InkstoneError
from inkstone.search import (
    FORMAT_VERSION,
    IndexBuilder,
    SearchError,
    SearchIndex,
    register_stopwords,
    stopwords,
)
from inkstone.search.index import _decode_postings, _encode_postings

from .corpus import DOCS, FIELDS, STORE, build_index, ids, small_index


def test_search_error_is_an_inkstone_error():
    assert issubclass(SearchError, InkstoneError)


def test_build_counts_documents_and_terms(index):
    assert len(index) == len(DOCS)
    assert index.doc_ids == [doc_id for doc_id, _, _ in DOCS]
    assert index.vocabulary == sorted(index.vocabulary)
    assert {"generat", "markdown", "wordpress", "stateoftheart"} <= set(
        index.vocabulary
    )
    assert "the" not in index.vocabulary


def test_builder_knows_how_many_documents_it_has():
    builder = IndexBuilder(["body"])
    assert len(builder) == 0
    builder.add("a", {"body": "one"})
    builder.add("b", {"body": "two"})
    assert len(builder) == 2


def test_fields_given_as_names_get_a_boost_of_one():
    assert IndexBuilder(["title", "body"]).fields == {"title": 1.0, "body": 1.0}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fields": {}},
        {"fields": []},
        {"fields": {"title": 0}},
        {"fields": {"title": -1.5}},
        {"fields": {"title": "high"}},
        {"fields": {"title": True}},
        {"fields": {"title": 1.0}, "b": 1.5},
        {"fields": {"title": 1.0}, "k1": -1},
    ],
)
def test_builder_rejects_bad_configuration(kwargs):
    with pytest.raises(SearchError):
        IndexBuilder(**kwargs)


def test_duplicate_document_id_is_an_error():
    builder = IndexBuilder(["body"])
    builder.add("post", {"body": "first"})
    with pytest.raises(SearchError, match="duplicate.*'post'"):
        builder.add("post", {"body": "second"})


def test_fields_that_are_not_indexed_are_ignored():
    index = small_index({"a": {"title": "apple", "author": "banana", "body": None}})
    assert index.vocabulary == ["apple"]


def test_non_string_values_are_indexed_as_text():
    index = small_index({"a": {"title": 2024, "body": 3.5}})
    assert ids(index.search("2024")) == ["a"]
    assert ids(index.search("3.5")) == ["a"]


def test_list_values_are_indexed_item_by_item():
    index = small_index({"a": {"tags": ["static", "site"]}}, fields=["tags"])
    assert ids(index.search("tags:static")) == ["a"]
    assert ids(index.search("tags:site")) == ["a"]
    # the two tags are not the phrase "static site"
    assert index.search('"static site"') == []


def test_phrase_cannot_reach_across_list_items_through_stopwords():
    index = small_index(
        {"a": {"tags": ["state", "of the art"]}}, fields=["tags"], stopwords=True
    )
    assert index.search('"state of the art"') == []
    assert ids(index.search('"of the art"')) == ["a"]


def test_stored_values_come_from_stored_first_then_from_fields(index):
    [hit] = index.search("blowtorch")
    assert hit.stored == {
        "title": "Crème brûlée at the café",
        "url": "/creme-brulee/",
        "summary": "A dessert & a blowtorch.",
        "date": "2024-06-01",
    }


def test_only_names_listed_in_store_are_kept():
    builder = IndexBuilder(["title"], store=["title", "url"])
    builder.add("a", {"title": "Hello"}, stored={"url": "/a/", "secret": "x"})
    builder.add("b", {"title": "Hello again"})
    first, second = builder.build().search("hello")
    assert first.stored == {"title": "Hello", "url": "/a/"}
    assert second.stored == {"title": "Hello again"}


def test_stored_values_are_made_json_friendly():
    builder = IndexBuilder(["title"], store=["date", "updated", "tags", "meta", "n"])
    stored = {
        "date": date(2024, 2, 29),
        "updated": datetime(2024, 3, 1, 12, 30),
        "tags": ("a", "b"),
        "meta": {"words": 120, "when": date(2024, 1, 1)},
        "n": 3,
    }
    builder.add("a", {"title": "Hello"}, stored=stored)
    index = SearchIndex.from_json(builder.build().to_json())
    assert index.search("hello")[0].stored == {
        "date": "2024-02-29",
        "updated": "2024-03-01T12:30:00",
        "tags": ["a", "b"],
        "meta": {"words": 120, "when": "2024-01-01"},
        "n": 3,
    }


def test_postings_are_delta_encoded():
    index = small_index(
        {
            "a": {"title": "red", "body": "red green red"},
            "b": {"body": "green"},
            "c": {"body": "blue red"},
        }
    )
    data = index.to_dict()
    assert data["vocab"] == ["blue", "green", "red"]
    postings = dict(zip(data["vocab"], data["postings"]))
    # field, number of docs, then per doc: doc delta, count, position deltas
    assert postings["blue"] == [1, 1, 2, 1, 0]
    assert postings["green"] == [1, 2, 0, 1, 1, 1, 1, 0]
    assert postings["red"] == [0, 1, 0, 1, 0, 1, 2, 0, 2, 0, 2, 2, 1, 1]


def test_postings_encoding_round_trips():
    postings = {
        0: {3: [0, 7, 8], 40: [2]},
        2: {0: [5], 3: [1, 100, 2000], 41: [0]},
    }
    flat = _encode_postings(postings)
    assert all(isinstance(n, int) and n >= 0 for n in flat)
    assert _decode_postings(flat) == postings


def test_decoded_postings_give_positions_per_field_and_document(index):
    postings = index.postings("yield")
    body = list(FIELDS).index("body")
    assert list(postings) == [body]
    assert list(postings[body]) == [index.doc_ids.index("python-generators")]
    assert index.postings("no-such-term") == {}


def test_joined_form_that_stems_to_its_first_part_is_posted_once():
    index = small_index({"a": {"body": "run-s"}}, stemming=True, min_token_length=1)
    assert index.postings("run") == {1: {0: [0]}}


def test_document_lengths_count_indexed_words(index):
    data = index.to_dict()
    doc_id, lengths, _ = data["docs"][0]
    assert doc_id == "static-sites"
    # "Static site generators compared"; ["python", "static-site"]
    assert lengths[:2] == [4, 3]


def test_dict_layout(index):
    data = index.to_dict()
    assert data["version"] == FORMAT_VERSION == 1
    assert data["config"] == {
        "language": "en",
        "stemmer": "english",
        "min_token_length": 2,
        "k1": 1.2,
        "b": 0.75,
    }
    assert data["fields"] == list(FIELDS)
    assert data["boosts"] == list(FIELDS.values())
    assert data["store"] == list(STORE)
    assert "the" in data["stopwords"]
    assert len(data["vocab"]) == len(data["postings"])
    assert all(isinstance(n, int) for flat in data["postings"] for n in flat)
    generat = data["vocab"].index("generat")
    assert data["forms"][str(generat)] == "generators"


QUERIES = [
    "static site",
    'static site -wordpress "exact phrase" title:markdown gen*',
    "+python generators",
    "pythn~",
    "state-of-the-art",
    "café",
]


@pytest.mark.parametrize("query", QUERIES)
@pytest.mark.parametrize("compact", [True, False])
def test_json_round_trip_gives_the_same_results(index, query, compact):
    loaded = SearchIndex.from_json(index.to_json(compact=compact))
    assert loaded.search(query) == index.search(query)


def test_round_trip_through_dict_is_lossless(index):
    assert SearchIndex.from_dict(index.to_dict()).to_dict() == index.to_dict()


def test_loaded_index_does_not_depend_on_registered_stopwords(index):
    data = index.to_dict()
    data["stopwords"] = ["markdown"]
    loaded = SearchIndex.from_dict(data)
    assert loaded.search("markdown") == []
    assert loaded.analyzer.terms("the") == ["the"]


def test_compact_json_has_no_padding(index):
    compact = index.to_json()
    readable = index.to_json(compact=False)
    assert compact.startswith('{"version":1,"config":{"language":"en",')
    assert "\n" not in compact and "\n" in readable
    assert len(compact) < len(readable)
    assert json.loads(compact) == json.loads(readable)


def test_json_keeps_non_ascii_text_readable(index):
    assert "Crème brûlée" in index.to_json()


def test_from_json_accepts_bytes(index):
    loaded = SearchIndex.from_json(index.to_json().encode("utf-8"))
    assert ids(loaded.search("café")) == ["creme-brulee"]


def test_unsupported_format_version_is_refused(index):
    data = index.to_dict()
    data["version"] = FORMAT_VERSION + 1
    with pytest.raises(SearchError, match="unsupported search index format 2"):
        SearchIndex.from_dict(data)


@pytest.mark.parametrize(
    "missing", ["config", "fields", "boosts", "docs", "vocab", "postings"]
)
def test_missing_sections_are_reported(index, missing):
    data = index.to_dict()
    del data[missing]
    with pytest.raises(SearchError, match="malformed"):
        SearchIndex.from_dict(data)


def test_tables_of_different_sizes_are_reported(index):
    data = index.to_dict()
    data["postings"] = data["postings"][:-1]
    with pytest.raises(SearchError, match="corrupt"):
        SearchIndex.from_dict(data)


def test_document_rows_of_the_wrong_shape_are_reported(index):
    data = index.to_dict()
    data["docs"] = [[doc[0], doc[1][:-1], doc[2]] for doc in data["docs"]]
    with pytest.raises(SearchError, match="corrupt"):
        SearchIndex.from_dict(data)


def test_unknown_stemmer_is_refused(index):
    data = index.to_dict()
    data["config"] = {**data["config"], "stemmer": "klingon"}
    with pytest.raises(SearchError, match="klingon"):
        SearchIndex.from_dict(data)


@pytest.mark.parametrize("text", ["", "{not json", "[1, 2, 3]", '"a string"', "null"])
def test_garbage_is_not_an_index(text):
    with pytest.raises(SearchError):
        SearchIndex.from_json(text)


def test_truncated_postings_surface_as_search_error(index):
    data = index.to_dict()
    position = data["vocab"].index("markdown")
    data["postings"] = list(data["postings"])
    data["postings"][position] = data["postings"][position][:-2]
    loaded = SearchIndex.from_dict(data)
    with pytest.raises(SearchError, match="corrupt.*markdown"):
        loaded.search("markdown")


def test_empty_index_works():
    index = IndexBuilder(FIELDS).build()
    assert len(index) == 0
    assert index.search("anything") == []
    assert index.suggest("any") == []
    assert len(SearchIndex.from_json(index.to_json())) == 0


def test_score_matches_the_bm25f_formula():
    index = small_index(
        {
            "a": {"title": "apple pie", "body": "apple apple cinnamon sugar"},
            "b": {"title": "pear tart", "body": "pear butter"},
            "c": {"title": "plum jam", "body": "plum sugar apple"},
        },
        fields={"title": 2.0, "body": 1.0},
    )
    first, second = index.search("apple")
    k1, b = 1.2, 0.75
    idf = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    # all titles have two words; bodies have 4, 2 and 3, so 3 on average
    tf_a = 2.0 * 1 / (1 - b + b * 2 / 2) + 1.0 * 2 / (1 - b + b * 4 / 3)
    tf_c = 1.0 * 1 / (1 - b + b * 3 / 3)
    assert (first.doc_id, second.doc_id) == ("a", "c")
    assert first.score == pytest.approx(idf * tf_a / (k1 + tf_a))
    assert second.score == pytest.approx(idf * tf_c / (k1 + tf_c))


def test_title_match_outranks_body_match():
    docs = {
        "in-body": {"title": "something else", "body": "about kittens today"},
        "in-title": {"title": "kittens today", "body": "about something else"},
    }
    index = small_index(docs, fields={"title": 3.0, "body": 1.0})
    assert ids(index.search("kittens")) == ["in-title", "in-body"]


def test_boosts_decide_which_field_wins():
    docs = {
        "in-body": {"title": "something else", "body": "about kittens today"},
        "in-title": {"title": "kittens today", "body": "about something else"},
    }
    index = small_index(docs, fields={"title": 1.0, "body": 5.0})
    assert ids(index.search("kittens")) == ["in-body", "in-title"]


def test_more_occurrences_rank_higher():
    docs = {
        "once": {"body": "tea coffee water juice"},
        "thrice": {"body": "tea tea tea juice"},
    }
    assert ids(small_index(docs).search("tea")) == ["thrice", "once"]


def test_term_frequency_saturates():
    docs = {
        "once": {"body": "tea " + "x " * 19},
        "often": {"body": "tea " * 10 + "x " * 10},
        "other": {"body": "x " * 20},
    }
    often, once = small_index(docs, min_token_length=1).search("tea")
    assert often.doc_id == "often"
    assert once.score < often.score < 3 * once.score


def test_shorter_documents_rank_higher_for_the_same_frequency():
    docs = {
        "long": {"body": "tea " + "filler " * 30},
        "short": {"body": "tea time"},
    }
    assert ids(small_index(docs).search("tea")) == ["short", "long"]


def test_length_normalisation_can_be_switched_off():
    docs = {
        "long": {"body": "tea " + "filler " * 30},
        "short": {"body": "tea time"},
    }
    long, short = small_index(docs, b=0.0).search("tea")
    assert long.score == pytest.approx(short.score)
    # equal scores fall back to the order the documents were added in
    assert (long.doc_id, short.doc_id) == ("long", "short")


def test_rare_terms_weigh_more_than_common_ones():
    docs = {f"common-{n}": {"body": "bread and butter"} for n in range(6)}
    docs["rare"] = {"body": "bread and saffron"}
    hits = small_index(docs).search("bread saffron")
    assert hits[0].doc_id == "rare"
    assert hits[0].score > 3 * hits[1].score


def test_scores_are_positive_even_when_every_document_matches():
    docs = {"a": {"body": "tea"}, "b": {"body": "tea"}}
    assert all(hit.score > 0 for hit in small_index(docs).search("tea"))


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("gen", ["generators"]),
        ("GEN", ["generators"]),
        ("generati", ["generators"]),
        ("pyt", ["python"]),
        ("stat", ["static", "state", "state-of-the-art", "static-site"]),
        ("caf", ["cafe"]),
        ("café", ["cafe"]),
        ("publ", ["publish", "publish_site"]),
        ("zzz", []),
        ("", []),
        ("?!", []),
    ],
)
def test_suggest(index, prefix, expected):
    assert index.suggest(prefix) == expected


def test_suggest_puts_widely_used_words_first(index):
    # "site" is in three documents, the others in fewer
    assert index.suggest("s", limit=3) == ["site", "script", "search"]


def test_suggest_respects_the_limit(index):
    assert index.suggest("stat", limit=2) == ["static", "state"]
    assert index.suggest("stat", limit=0) == []


def test_suggest_without_stemming_completes_plain_words():
    index = build_index(stemming=False)
    assert index.suggest("generat") == ["generator", "generators"]


def test_expand_prefix_finds_stems_the_prefix_has_outgrown(index):
    assert index.expand_prefix("gener") == ["generat"]
    assert index.expand_prefix("generat") == ["generat"]
    assert index.expand_prefix("generati") == ["generat"]
    assert index.expand_prefix("generatio") == ["generat"]
    assert index.expand_prefix("generators") == ["generat"]
    assert index.expand_prefix("generalx") == []


def test_expand_prefix_can_be_limited(index):
    everything = index.expand_prefix("s", limit=None)
    assert len(everything) > 5
    assert index.expand_prefix("s", limit=5) == everything[:5]


def test_display_form(index):
    assert index.display_form("generat") == "generators"
    assert index.display_form("python") == "python"
    assert index.display_form("stateoftheart") == "state-of-the-art"
    assert index.display_form("unknown") == "unknown"


def test_document_frequency(index):
    assert index.doc_frequency("python") == 2
    assert index.doc_frequency("site") == 3
    assert index.doc_frequency("unknown") == 0


def test_stemming_can_be_turned_off():
    index = build_index(stemming=False)
    assert "generators" in index.vocabulary and "generat" not in index.vocabulary
    assert ids(index.search("generators")) == ["python-generators", "static-sites"]
    assert ids(index.search("generating")) == []
    assert index.to_dict()["config"]["stemmer"] is None


def test_stopwords_can_be_turned_off():
    index = build_index(stopwords=False)
    assert "the" in index.vocabulary
    assert index.to_dict()["stopwords"] == []
    assert index.search("the") != []


def test_custom_stopword_list():
    index = build_index(stopwords=["Markdown", "café"])
    assert index.search("markdown") == []
    assert index.search("cafe") == []
    assert index.search("the") != []


def test_minimum_token_length():
    docs = {"a": {"body": "go to x in rust"}}
    assert small_index(docs, min_token_length=1).vocabulary == [
        "go",
        "in",
        "rust",
        "to",
        "x",
    ]
    assert small_index(docs, min_token_length=3).vocabulary == ["rust"]


def test_other_languages_are_indexed_without_english_processing():
    builder = IndexBuilder(["body"], language="de")
    builder.add("a", {"body": "Die Katzen schlafen in der Sonne"})
    index = builder.build()
    assert index.vocabulary == ["der", "die", "in", "katzen", "schlafen", "sonne"]
    config = index.to_dict()["config"]
    assert (config["language"], config["stemmer"]) == ("de", None)
    assert ids(SearchIndex.from_json(index.to_json()).search("Katzen")) == ["a"]


def test_registered_stopwords_are_used_and_travel_with_the_index(monkeypatch):
    monkeypatch.setattr(stopwords, "_registry", dict(stopwords._registry))
    register_stopwords("de", ["der", "die", "in"])
    builder = IndexBuilder(["body"], language="de-AT")
    builder.add("a", {"body": "Die Katzen schlafen in der Sonne"})
    index = builder.build()
    assert index.vocabulary == ["katzen", "schlafen", "sonne"]
    assert index.to_dict()["stopwords"] == ["der", "die", "in"]


def test_regional_variants_of_english_get_the_english_treatment():
    builder = IndexBuilder(["body"], language="en-GB")
    builder.add("a", {"body": "The colours are running"})
    assert builder.build().vocabulary == ["colour", "run"]


def test_repr_mentions_sizes(index):
    assert repr(index) == f"<SearchIndex 7 docs, {len(index.vocabulary)} terms>"
