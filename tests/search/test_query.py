from __future__ import annotations

import pytest

from inkstone.search import Clause, Query, SearchHit, parse_query
from inkstone.search.query import _within_one_edit

from .corpus import FIELDS, ids, small_index


def clauses(text: str, fields=None) -> list[Clause]:
    return list(parse_query(text, fields).clauses)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("static", [Clause("term", "static")]),
        ("static site", [Clause("term", "static"), Clause("term", "site")]),
        ('"exact phrase"', [Clause("phrase", "exact phrase")]),
        ("+required", [Clause("term", "required", occur="must")]),
        ("-excluded", [Clause("term", "excluded", occur="must_not")]),
        ("title:markdown", [Clause("term", "markdown", field="title")]),
        ("gen*", [Clause("prefix", "gen")]),
        ("pythn~", [Clause("fuzzy", "pythn")]),
        ("pythn~1", [Clause("fuzzy", "pythn")]),
        ("pythn~2", [Clause("fuzzy", "pythn")]),
        ("pythn~0", [Clause("term", "pythn")]),
        ('+"static site"', [Clause("phrase", "static site", occur="must")]),
        (
            '-title:"static site"',
            [Clause("phrase", "static site", "title", "must_not")],
        ),
        ("+tags:pyth*", [Clause("prefix", "pyth", "tags", "must")]),
        ("body:serch~", [Clause("fuzzy", "serch", "body")]),
    ],
)
def test_parse_single_operators(text, expected):
    assert clauses(text) == expected


def test_parse_the_kitchen_sink():
    query = 'static site -wordpress "exact phrase" title:markdown gen*'
    assert clauses(query) == [
        Clause("term", "static"),
        Clause("term", "site"),
        Clause("term", "wordpress", occur="must_not"),
        Clause("phrase", "exact phrase"),
        Clause("term", "markdown", field="title"),
        Clause("prefix", "gen"),
    ]


@pytest.mark.parametrize(
    "text",
    ["", "   ", "+", "-", "+ -", "*", "**", "~", '""', '"   "', "+*", '-""', "?!"],
)
def test_parse_input_without_any_words(text):
    assert clauses(text) == []
    assert not parse_query(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("well-known", [Clause("term", "well-known")]),
        ("a - b", [Clause("term", "a"), Clause("term", "b")]),
        ("a -b", [Clause("term", "a"), Clause("term", "b", occur="must_not")]),
        ("c++", [Clause("term", "c++")]),
        ("+c++", [Clause("term", "c++", occur="must")]),
        ("--verbose", [Clause("term", "-verbose", occur="must_not")]),
        ("a*b", [Clause("term", "a*b")]),
        ("*suffix", [Clause("term", "*suffix")]),
        ("x~y", [Clause("term", "x~y")]),
        ("hello,", [Clause("term", "hello,")]),
        ("12:30", [Clause("term", "12:30")]),
        ("http://example.com/a", [Clause("term", "http://example.com/a")]),
        ("note: something", [Clause("term", "note:"), Clause("term", "something")]),
    ],
)
def test_parse_things_that_only_look_like_operators(text, expected):
    assert clauses(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"never closed', [Clause("phrase", "never closed")]),
        (
            'before "never closed',
            [Clause("term", "before"), Clause("phrase", "never closed")],
        ),
        (
            'glued"phrase here"',
            [Clause("term", "glued"), Clause("phrase", "phrase here")],
        ),
        ('"  padded  "', [Clause("phrase", "padded")]),
        ("“smart quotes”", [Clause("phrase", "smart quotes")]),
        ("«guillemets»", [Clause("phrase", "guillemets")]),
        ('"one" "two"', [Clause("phrase", "one"), Clause("phrase", "two")]),
        ('"with +signs -inside*"', [Clause("phrase", "with +signs -inside*")]),
    ],
)
def test_parse_quotes(text, expected):
    assert clauses(text) == expected


def test_any_identifier_is_a_field_when_no_fields_are_given():
    assert clauses("author:knuth") == [Clause("term", "knuth", field="author")]


def test_only_known_fields_count_when_fields_are_given():
    assert clauses("author:knuth title:art", FIELDS) == [
        Clause("term", "author:knuth"),
        Clause("term", "art", field="title"),
    ]


def test_query_prints_back_in_canonical_form():
    text = '+static -tags:draft "exact phrase" title:"two words" gen* pythn~'
    assert str(parse_query(text)) == text
    assert str(parse_query('  a   +b  "c  d" ')) == 'a +b "c  d"'


def test_query_truthiness():
    assert parse_query("word")
    assert not Query()


def test_term_search(index):
    assert ids(index.search("markdown")) == ["markdown-tips", "static-sites"]
    assert index.search("kubernetes") == []


@pytest.mark.parametrize(
    "query", ["generator", "generators", "generating", "GENERATED"]
)
def test_inflections_find_the_same_documents(index, query):
    assert ids(index.search(query)) == ["python-generators", "static-sites"]


def test_plain_terms_are_ored(index):
    assert set(ids(index.search("rsync blowtorch"))) == {"deploying", "creme-brulee"}


def test_documents_matching_more_terms_come_first(index):
    assert ids(index.search("static site")) == [
        "static-sites",
        "leaving-wordpress",
        "deploying",
    ]


def test_scores_are_sorted_and_hits_are_complete(index):
    hits = index.search("static site")
    assert all(isinstance(hit, SearchHit) for hit in hits)
    assert [hit.score for hit in hits] == sorted(
        (hit.score for hit in hits), reverse=True
    )
    assert hits[0].stored["url"] == "/static-sites/"
    assert hits[0].stored["summary"] == "Which static site generator should you pick?"


def test_matches_list_the_terms_found_in_each_field(index):
    best = index.search("static site generators")[0]
    assert best.matches == {
        "title": ["generat", "site", "static"],
        "tags": ["site", "static"],
        "body": ["generat", "site", "static"],
    }
    assert best.terms == {"generat", "site", "static"}
    [other] = index.search("yield")
    assert other.matches == {"body": ["yield"]}


def test_phrase_needs_the_words_in_order(index):
    assert ids(index.search('"exact phrase"')) == ["markdown-tips"]
    assert index.search('"phrase exact"') == []
    assert ids(index.search('"plain html"')) == ["static-sites"]
    assert index.search('"html plain"') == []


def test_phrase_needs_the_words_next_to_each_other(index):
    assert ids(index.search('"static site generator"')) == ["static-sites"]
    assert index.search('"static generator"') == []


def test_phrase_matches_through_stemming(index):
    assert ids(index.search('"static sites generators"')) == ["static-sites"]


def test_phrase_steps_over_stopwords_but_keeps_the_distance(index):
    assert ids(index.search('"state of the art"')) == ["python-generators"]
    assert ids(index.search('"state in an art"')) == ["python-generators"]
    assert index.search('"state art"') == []
    assert index.search('"state of art"') == []


def test_phrase_of_one_word_is_a_term(index):
    assert index.search('"markdown"') == index.search("markdown")


def test_phrase_score_counts_occurrences_like_a_term():
    docs = {
        "once": {"body": "new york is big and old"},
        "twice": {"body": "new york loves new york"},
        "apart": {"body": "new things happen in york"},
    }
    hits = small_index(docs).search('"new york"')
    assert ids(hits) == ["twice", "once"]
    assert hits[0].score > hits[1].score


def test_required_clauses_all_have_to_match(index):
    assert ids(index.search("+python +generators")) == [
        "python-generators",
        "static-sites",
    ]
    assert ids(index.search("+python +yield")) == ["python-generators"]
    assert index.search("+footnotes +rsync") == []


def test_optional_clauses_only_add_score_next_to_required_ones(index):
    with_optional = index.search("+wordpress weekend")
    assert ids(with_optional) == ["leaving-wordpress", "static-sites"]
    without = index.search("+wordpress")
    assert with_optional[0].score > without[0].score
    assert with_optional[1].score == pytest.approx(without[1].score)


def test_excluded_clauses_remove_documents(index):
    assert ids(index.search("static site -wordpress")) == ["deploying"]
    assert ids(index.search("python -yield")) == ["static-sites"]
    assert ids(index.search('site -"static site"')) == ["deploying"]
    assert index.search("blowtorch -code") == []


def test_exclusion_alone_matches_nothing(index):
    assert index.search("-python") == []


def test_field_restricted_terms(index):
    assert ids(index.search("search")) == ["search", "markdown-tips"]
    assert ids(index.search("title:search")) == ["search"]
    assert ids(index.search("body:search")) == ["markdown-tips"]
    assert ids(index.search("tags:python")) == ["python-generators", "static-sites"]
    assert index.search("tags:markdown")[0].matches == {"tags": ["markdown"]}


def test_field_restricted_phrase_and_prefix(index):
    assert ids(index.search('title:"static site"')) == ["static-sites"]
    assert index.search('tags:"static site generators"') == []
    assert ids(index.search("title:pyth*")) == ["python-generators"]
    assert ids(index.search("+title:python +body:yield")) == ["python-generators"]


def test_unknown_field_prefix_is_searched_as_text(index):
    # "note:markdown" is two adjacent words, which nothing contains
    assert index.search("note:markdown") == []
    assert ids(index.search("note: markdown")) == ["markdown-tips", "static-sites"]


def test_clause_for_a_field_the_index_lacks_matches_nothing(index):
    query = Query((Clause("term", "markdown", field="author"),))
    assert index.search(query) == []


def test_prefix_search(index):
    assert ids(index.search("gen*")) == ["python-generators", "static-sites"]
    assert ids(index.search("mark*")) == ["markdown-tips", "static-sites"]
    assert ids(index.search("blow*")) == ["creme-brulee"]
    assert index.search("xyz*") == []


def test_prefix_longer_than_the_stem_still_matches(index):
    expected = index.search("gen*")
    for prefix in ("generat*", "generati*", "generatio*", "generation*", "generators*"):
        assert index.search(prefix) == expected


def test_prefix_is_scored_as_one_term(index):
    assert index.search("yiel*")[0].score == pytest.approx(
        index.search("yield")[0].score
    )


def test_prefix_reports_the_terms_it_expanded_to(index):
    hits = index.search("writ*")
    assert ids(hits) == ["markdown-tips", "static-sites"]
    assert hits[0].matches == {"tags": ["write"], "body": ["write"]}
    assert hits[1].matches == {"body": ["written"]}


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("pythn~", ["python-generators", "static-sites"]),
        ("pyhton~", ["python-generators", "static-sites"]),
        ("pythonn~", ["python-generators", "static-sites"]),
        ("markdwon~", ["markdown-tips", "static-sites"]),
        ("wordpres~", ["leaving-wordpress", "static-sites"]),
        ("rsyn~", ["deploying"]),
        ("blowtorsh~", ["creme-brulee"]),
        ("xylophone~", []),
    ],
)
def test_fuzzy_search_forgives_one_typo(index, query, expected):
    assert ids(index.search(query)) == expected
    assert index.search(query.rstrip("~")) == []


def test_fuzzy_match_scores_below_the_exact_word(index):
    [exact] = index.search("weekend~")
    [typo] = index.search("weekand~")
    assert exact.doc_id == typo.doc_id == "leaving-wordpress"
    assert typo.score < exact.score
    assert exact.score == pytest.approx(index.search("weekend")[0].score)


def test_fuzzy_is_limited_to_one_edit(index):
    assert index.search("pthn~") == []
    assert index.search("markdnwo~") == []


def test_fuzzy_leaves_very_short_words_alone(index):
    assert ids(index.search("ssh")) == ["deploying"]
    assert index.search("ss~") == []


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("python", "python", True),
        ("python", "pythn", True),
        ("pythn", "python", True),
        ("python", "pyhton", True),
        ("python", "pithon", True),
        ("python", "pythons", True),
        ("python", "ython", True),
        ("python", "nython", True),
        ("ab", "ba", True),
        ("a", "", True),
        ("python", "pytn", False),
        ("python", "pyhtno", False),
        ("python", "nohtyp", False),
        ("abc", "cab", False),
        ("ab", "", False),
    ],
)
def test_within_one_edit(a, b, expected):
    assert _within_one_edit(a, b) is expected
    assert _within_one_edit(b, a) is expected


@pytest.mark.parametrize("query", ["café", "cafe", "CAFÉ", "Cafe\u0301"])
def test_accents_and_case_do_not_matter(index, query):
    assert ids(index.search(query)) == ["creme-brulee"]


@pytest.mark.parametrize(
    "query",
    [
        "publish_site",
        "publishsite",
        "publish",
        "deployHost",
        "deployhost",
        "deploy_host",
        "HTMLMinifier",
        "htmlminifier",
        "minifier",
        "3.50",
    ],
)
def test_identifiers_and_numbers(index, query):
    hits = index.search(query)
    assert hits and hits[0].doc_id == "deploying"


@pytest.mark.parametrize(
    "query", ["state-of-the-art", "stateoftheart", "state of the art"]
)
def test_hyphenated_compound_is_found_however_it_is_typed(index, query):
    assert ids(index.search(query)) == ["python-generators"]


def test_compound_is_not_counted_twice(index):
    hyphenated = index.search("state-of-the-art")[0]
    joined = index.search("stateoftheart")[0]
    assert hyphenated.score == pytest.approx(joined.score)
    assert hyphenated.matches == {"body": ["art", "state", "stateoftheart"]}


def test_compound_query_also_finds_the_words_written_apart():
    docs = {
        "hyphen": {"body": "a well-known fact"},
        "apart": {"body": "it is well known here"},
        "joined": {"body": "the wellknown case"},
        "neither": {"body": "known to work well"},
    }
    index = small_index(docs)
    assert set(ids(index.search("well-known"))) == {"hyphen", "apart", "joined"}
    assert set(ids(index.search("wellknown"))) == {"hyphen", "joined"}
    assert set(ids(index.search('"well known"'))) == {"hyphen", "apart"}


@pytest.mark.parametrize(
    "query", ["the", "a", "to be or not to be", '"of the"', "+the", "th~"]
)
def test_queries_made_of_stopwords_find_nothing(index, query):
    assert index.search(query) == []


def test_stopwords_inside_a_query_are_ignored(index):
    assert index.search("+the python") == index.search("python")
    assert index.search("the python and the yield") == index.search("python yield")


def test_limit(index):
    assert len(index.search("site")) == 3
    assert ids(index.search("site", limit=1)) == ["static-sites"]
    assert len(index.search("site", limit=None)) == 3
    assert index.search("site", limit=0) == []


def test_default_limit_is_ten():
    index = small_index({f"doc-{n:02}": {"body": "same words"} for n in range(15)})
    assert len(index.search("same")) == 10
    assert len(index.search("same", limit=None)) == 15
    assert ids(index.search("same", limit=3)) == ["doc-00", "doc-01", "doc-02"]


def test_search_accepts_a_parsed_query(index):
    assert index.search(parse_query("title:markdown")) == index.search("title:markdown")


def test_all_operators_in_one_query(index):
    query = 'static site -wordpress "exact phrase" title:markdown gen*'
    assert ids(index.search(query, limit=10)) == [
        "markdown-tips",
        "python-generators",
        "deploying",
    ]
