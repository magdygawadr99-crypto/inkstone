from __future__ import annotations

import pytest

from inkstone.search import SearchError, get_stopwords, register_stopwords, stopwords
from inkstone.search.stopwords import primary_language, stopword_languages
from inkstone.search.tokenizer import tokenize


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    monkeypatch.setattr(stopwords, "_registry", dict(stopwords._registry))


def test_english_list_has_the_usual_suspects():
    english = get_stopwords("en")
    assert {"the", "and", "of", "is", "dont", "youre", "themselves"} <= english
    assert 100 < len(english) < 250


@pytest.mark.parametrize("word", ["shell", "well", "ill", "id", "wed", "hell", "shed"])
def test_contractions_that_are_also_words_are_not_stopwords(word):
    assert word not in get_stopwords("en")


def test_english_list_matches_what_the_tokenizer_emits():
    for word in get_stopwords("en"):
        assert [token.text for token in tokenize(word)] == [word]


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "en"),
        ("en-GB", "en"),
        ("en_US", "en"),
        ("PT-br", "pt"),
        ("", ""),
        (None, ""),
    ],
)
def test_primary_language(language, expected):
    assert primary_language(language) == expected


def test_regional_codes_share_the_list():
    assert get_stopwords("en-GB") == get_stopwords("en_US") == get_stopwords("EN")


@pytest.mark.parametrize("language", ["tlh", "", None])
def test_unknown_language_has_no_stopwords(language):
    assert get_stopwords(language) == frozenset()


def test_register_adds_a_language():
    register_stopwords("nl", ["de", "het", " Een ", ""])
    assert get_stopwords("nl") == {"de", "het", "een"}
    assert get_stopwords("nl-BE") == {"de", "het", "een"}
    assert stopword_languages() == ["en", "nl"]


def test_register_replaces_by_default():
    register_stopwords("nl", ["de", "het"])
    register_stopwords("nl", ["een"])
    assert get_stopwords("nl") == {"een"}


def test_register_can_extend_an_existing_list():
    before = get_stopwords("en")
    register_stopwords("en", ["lorem", "ipsum"], extend=True)
    assert get_stopwords("en") == before | {"lorem", "ipsum"}


def test_register_needs_a_language_code():
    with pytest.raises(SearchError):
        register_stopwords("", ["a"])
