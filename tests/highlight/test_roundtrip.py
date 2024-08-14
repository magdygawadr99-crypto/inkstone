from __future__ import annotations

import random

import pytest

from inkstone.highlight import get_lexer, list_languages
from inkstone.highlight.token import Error, TokenType

from .samples import SAMPLES

LANGUAGES = [name for name, _, _ in list_languages()]
CASES = [
    pytest.param(lang, code, id=f"{lang}-{index}")
    for lang, snippets in SAMPLES.items()
    for index, code in enumerate(snippets)
]

# Samples that are broken on purpose, to exercise recovery.
EXPECTED_ERRORS = {("css", 1): "$"}


def roundtrip(lang: str, code: str) -> str:
    return "".join(text for _, text in get_lexer(lang).tokenize(code))


def test_every_language_has_samples():
    assert sorted(SAMPLES) == sorted(LANGUAGES)


@pytest.mark.parametrize("lang, code", CASES)
def test_tokens_reproduce_the_sample(lang, code):
    assert roundtrip(lang, code) == code


@pytest.mark.parametrize("lang, code", CASES)
def test_tokens_are_well_formed(lang, code):
    for ttype, text in get_lexer(lang).tokenize(code):
        assert type(ttype) is TokenType
        assert isinstance(text, str) and text


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_samples_lex_without_error_tokens(lang):
    for index, code in enumerate(SAMPLES[lang]):
        errors = "".join(
            text for ttype, text in get_lexer(lang).tokenize(code) if ttype is Error
        )
        assert errors == EXPECTED_ERRORS.get((lang, index), "")


@pytest.mark.parametrize("lang, code", CASES)
def test_scan_offsets_are_contiguous(lang, code):
    expected = 0
    for pos, _, text in get_lexer(lang).scan(code):
        assert pos == expected
        expected += len(text)
    assert expected == len(code)


@pytest.mark.parametrize("lang, code", CASES)
def test_windows_line_endings_survive(lang, code):
    crlf = code.replace("\r\n", "\n").replace("\n", "\r\n")
    assert roundtrip(lang, crlf) == crlf


@pytest.mark.parametrize("lang", LANGUAGES)
def test_truncated_and_spliced_samples_roundtrip(lang):
    # Cutting a snippet anywhere leaves strings, comments and brackets open
    # in every way imaginable; nothing may be lost whatever state that
    # strands the lexer in.
    rng = random.Random(lang)
    for sample in SAMPLES[lang]:
        if len(sample) < 2:
            continue
        for _ in range(25):
            start = rng.randrange(len(sample))
            end = min(len(sample), start + rng.randint(1, 40))
            head, tail = sample[:start], sample[start:]
            for mangled in (head, tail, head + sample[end:]):
                assert roundtrip(lang, mangled) == mangled


@pytest.mark.parametrize("lang", LANGUAGES)
def test_random_garbage_roundtrips(lang):
    rng = random.Random(f"garbage-{lang}")
    alphabet = "abcXYZ019 \t\n\n\\'\"`$#@%&*()[]{}<>=+-/|;:,.!?~^_é"
    for _ in range(150):
        code = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 120)))
        assert roundtrip(lang, code) == code


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize(
    "code",
    [
        "",
        "\n",
        " ",
        "\t\n\t",
        "\\",
        '"',
        "'",
        "`",
        "/*",
        "<!--",
        "${",
        "\x00\x1b",
        "é中文 \U0001f600",
        "no newline at the end",
    ],
)
def test_awkward_fragments_roundtrip(lang, code):
    assert roundtrip(lang, code) == code


@pytest.mark.parametrize("lang", LANGUAGES)
def test_lexer_instances_are_reusable(lang):
    lexer = get_lexer(lang)
    code = SAMPLES[lang][0]
    first = list(lexer.tokenize(code))
    # an abandoned run must not leave state behind for the next one
    partial = lexer.tokenize(code)
    next(partial, None)
    assert list(lexer.tokenize(code)) == first
