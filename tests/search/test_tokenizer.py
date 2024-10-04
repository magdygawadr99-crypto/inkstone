from __future__ import annotations

import pytest

from inkstone.search import Analyzer, Token, fold, tokenize
from inkstone.search.tokenizer import MAX_TOKEN_LENGTH


def words(text: str) -> list[str]:
    return [token.text for token in tokenize(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("   \n\t ", []),
        ("?!... --- ***", []),
        ("Hello, World!", ["hello", "world"]),
        ("one  two\nthree\tfour", ["one", "two", "three", "four"]),
        (
            "(parenthesised) [bracketed] {braced}",
            ["parenthesised", "bracketed", "braced"],
        ),
        (
            "end of sentence. Start of next",
            ["end", "of", "sentence", "start", "of", "next"],
        ),
        ("os.path.join", ["os", "path", "join"]),
        ("user@example.com", ["user", "example", "com"]),
        ("a/b\\c|d", ["a", "b", "c", "d"]),
        ("dash \u2013 separated \u2014 words", ["dash", "separated", "words"]),
        ("double--hyphen", ["double", "hyphen"]),
        ("emoji \U0001f389 party", ["emoji", "party"]),
    ],
)
def test_splits_on_whitespace_and_punctuation(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("don't", ["dont"]),
        ("don\u2019t", ["dont"]),
        ("it's", ["it"]),
        ("the dog's bone", ["the", "dog", "bone"]),
        ("the dogs' bones", ["the", "dogs", "bones"]),
        ("O'Reilly", ["oreilly"]),
        ("O'Reilly's", ["oreilly"]),
        ("rock'n'roll", ["rocknroll"]),
        ("'quoted'", ["quoted"]),
        ("'s", ["s"]),
        ("90's", ["90"]),
    ],
)
def test_apostrophes(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("well-known", ["wellknown", "well", "known"]),
        ("state-of-the-art", ["stateoftheart", "state", "of", "the", "art"]),
        ("e-mail", ["email", "e", "mail"]),
        ("non\u2010breaking", ["nonbreaking", "non", "breaking"]),
        ("UTF-8", ["utf8", "utf", "8"]),
        ("covid-19", ["covid19", "covid", "19"]),
        ("mother-in-law's", ["motherinlaw", "mother", "in", "law"]),
        ("-leading and trailing-", ["leading", "and", "trailing"]),
        ("2019-2021", ["2019", "2021"]),
    ],
)
def test_hyphenated_words(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("snake_case", ["snakecase", "snake", "case"]),
        ("SCREAMING_SNAKE", ["screamingsnake", "screaming", "snake"]),
        ("__init__", ["init"]),
        ("_private", ["private"]),
        ("a__b", ["ab", "a", "b"]),
        ("camelCase", ["camelcase", "camel", "case"]),
        ("CamelCase", ["camelcase", "camel", "case"]),
        ("HTMLParser", ["htmlparser", "html", "parser"]),
        ("parseXMLDoc", ["parsexmldoc", "parse", "xml", "doc"]),
        ("utf8Decode", ["utf8decode", "utf8", "decode"]),
        ("getHTTP2Response", ["gethttp2response", "get", "http2", "response"]),
        ("iPhone", ["iphone", "i", "phone"]),
        ("macOS", ["macos", "mac", "os"]),
        ("JavaScript", ["javascript", "java", "script"]),
        ("my_HTTPServer", ["myhttpserver", "my", "http", "server"]),
        ("NASA", ["nasa"]),
        ("Hello", ["hello"]),
        ("URLs", ["urls"]),
        ("IDs", ["ids"]),
        ("python3", ["python3"]),
        ("mp3", ["mp3"]),
        ("H264", ["h264"]),
        ("ÉcoleNormale", ["ecolenormale", "ecole", "normale"]),
    ],
)
def test_identifiers_are_split_and_kept_whole(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", ["42"]),
        ("3.14", ["3.14"]),
        ("3.14.", ["3.14"]),
        ("1,000", ["1000"]),
        ("1,234,567.89", ["1234567.89"]),
        ("1,5", ["1,5"]),
        ("v1.2.3", ["v1", "2.3"]),
        ("192.168.1.1", ["192.168.1.1"]),
        ("1.5kg", ["1", "5kg"]),
        ("pages 10, 11 and 12.", ["pages", "10", "11", "and", "12"]),
        ("2nd", ["2nd"]),
        ("x86_64", ["x8664", "x86", "64"]),
    ],
)
def test_numbers(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("C++", ["c++"]),
        ("C++ and C#", ["c++", "and", "c#"]),
        ("F#.", ["f#"]),
        ("g++-12", ["g++", "12"]),
        ("#hashtag", ["hashtag"]),
        ("issue #12", ["issue", "12"]),
        ("a+b", ["a", "b"]),
        ("a#b", ["a", "b"]),
        ("i++", ["i++"]),
    ],
)
def test_plus_plus_and_sharp_stick_to_the_word(text, expected):
    assert words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Crème Brûlée", "creme brulee"),
        ("NAÏVE café", "naive cafe"),
        ("Straße", "strasse"),
        ("Ærøskøbing", "aeroskobing"),
        ("Łódź", "lodz"),
        ("Þingvellir", "thingvellir"),
        ("œuvre", "oeuvre"),
        ("İstanbul", "istanbul"),
        ("ﬁnal ﬂoor", "final floor"),
        ("ＦＵＬＬｗｉｄｔｈ", "fullwidth"),
        ("cafe\u0301", "cafe"),
        ("soft\u00adhyphen", "softhyphen"),
        ("ΟΔΟΣ", "οδοσ"),
        ("Ελληνικά", "ελληνικα"),
        ("Москва", "москва"),
        ("한국어", "한국어"),
    ],
)
def test_fold(text, expected):
    assert fold(text) == expected


def test_fold_leaves_ascii_alone_apart_from_case():
    assert fold("Plain ASCII 123 +-*/") == "plain ascii 123 +-*/"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Crème brûlée", ["creme", "brulee"]),
        ("cafe\u0301 society", ["cafe", "society"]),
        ("hyphen\u00adation", ["hyphenation"]),
        ("Москва слезам не верит", ["москва", "слезам", "не", "верит"]),
        ("हिन्दी भाषा", ["हिन्दी", "भाषा"]),
        ("日本語 テキスト", ["日本語", "テキスト"]),
        ("Ελληνικά", ["ελληνικα"]),
        ("x² + y²", ["x2", "y2"]),
    ],
)
def test_unicode_text(text, expected):
    assert words(text) == expected


def test_positions_count_words():
    tokens = tokenize("the quick brown fox")
    assert [token.position for token in tokens] == [0, 1, 2, 3]


def test_joined_token_shares_the_position_of_its_first_part():
    tokens = tokenize("a well-known fact")
    assert [(t.text, t.position, t.joined) for t in tokens] == [
        ("a", 0, False),
        ("wellknown", 1, True),
        ("well", 1, False),
        ("known", 2, False),
        ("fact", 3, False),
    ]


def test_only_real_compounds_get_a_joined_token():
    assert not any(token.joined for token in tokenize("plain words, 2019-2021, 3.14"))


def test_offsets_point_back_into_the_text():
    text = "Crème brûlée, O'Reilly's snake_case & HTMLParser!"
    tokens = tokenize(text)
    assert [text[t.start : t.end] for t in tokens] == [
        "Crème",
        "brûlée",
        "O'Reilly",
        "snake_case",
        "snake",
        "case",
        "HTMLParser",
        "HTML",
        "Parser",
    ]


def test_offsets_with_surrounding_whitespace():
    assert tokenize("  hi  ") == [Token("hi", 0, 2, 4)]


def test_overlong_tokens_are_dropped_but_keep_their_position():
    blob = "x" * (MAX_TOKEN_LENGTH + 1)
    tokens = tokenize(f"before {blob} after")
    assert [(t.text, t.position) for t in tokens] == [("before", 0), ("after", 2)]


def test_token_of_exactly_the_maximum_length_is_kept():
    assert words("y" * MAX_TOKEN_LENGTH) == ["y" * MAX_TOKEN_LENGTH]


def test_overlong_joined_form_is_dropped_but_parts_stay():
    parts = ["segment"] * 12
    tokens = tokenize("_".join(parts))
    assert [t.text for t in tokens] == parts
    assert not any(t.joined for t in tokens)


def test_analyzer_applies_stopwords_stemming_and_length():
    analyzer = Analyzer()
    assert analyzer.terms("The generators are running in a C# loop") == [
        "generat",
        "run",
        "c#",
        "loop",
    ]


def test_analyzer_leaves_holes_where_words_were_dropped():
    tokens = Analyzer().analyze("state of the art")
    assert [(t.text, t.position) for t in tokens] == [("state", 0), ("art", 3)]


def test_analyzer_without_filters():
    analyzer = Analyzer(stopwords=False, stemming=False, min_token_length=1)
    assert analyzer.terms("The generators are running in a loop") == [
        "the",
        "generators",
        "are",
        "running",
        "in",
        "a",
        "loop",
    ]


def test_analyzer_term_reports_dropped_words_as_none():
    analyzer = Analyzer(min_token_length=3)
    assert analyzer.term("the") is None
    assert analyzer.term("ox") is None
    assert analyzer.term("oxen") == "oxen"
