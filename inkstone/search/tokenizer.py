from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple

# Longer runs are base64 blobs, hashes and the like; nobody searches for them.
MAX_TOKEN_LENGTH = 64

_APOSTROPHES = "'\u2019"
_HYPHENS = "-\u2010\u2011"
_SOFT_HYPHEN = "\u00ad"

# Letters NFKD leaves alone but that people type without the decoration.
_FOLDS = str.maketrans(
    {
        "ß": "ss",
        "æ": "ae",
        "œ": "oe",
        "ø": "o",
        "đ": "d",
        "ð": "d",
        "þ": "th",
        "ł": "l",
        "ħ": "h",
        "ı": "i",
        "ς": "σ",
    }
)

_THOUSANDS = re.compile(r"[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_DIGITS = re.compile(r"[0-9]+")
_PIECE = re.compile(f"[^{_HYPHENS}_]+")
_APOSTROPHE = re.compile(f"[{_APOSTROPHES}]")
_POSSESSIVE = re.compile(f"[{_APOSTROPHES}][sS]$")


class Token(NamedTuple):
    text: str
    position: int
    start: int
    end: int
    # Set on the run-together form of a word that was split ("snakecase" for
    # snake_case). It shares the position of the first part.
    joined: bool = False


def _mark_ranges() -> str:
    # re has no \p{M} and \w stops at combining marks, which cuts decomposed
    # accents and most Indic scripts to pieces. Astral planes beyond the SMP
    # have no marks worth the scan time.
    ranges = []
    start = prev = -1
    for cp in range(0x300, 0x20000):
        if unicodedata.category(chr(cp))[0] != "M":
            continue
        if cp != prev + 1:
            if start >= 0:
                ranges.append((start, prev))
            start = cp
        prev = cp
    ranges.append((start, prev))
    return "".join(f"\\U{a:08x}-\\U{b:08x}" for a, b in ranges)


@lru_cache(maxsize=None)
def _chunk_pattern() -> re.Pattern[str]:
    word = f"(?:[^\\W_]|[{_SOFT_HYPHEN}{_mark_ranges()}])"
    joiner = f"(?:[{_APOSTROPHES}]|[{_HYPHENS}]|_+)"
    # No lookbehind and no named groups: the same expression is assembled in
    # search.js, which is limited to ES2017 regex syntax.
    return re.compile(
        f"([0-9]+(?:[.,][0-9]+)+)(?!{word})"
        f"|{word}+(?:{joiner}{word}+)*(?:(?:\\+\\+|#)(?!{word}))?"
    )


def fold(text: str) -> str:
    """Lowercase and strip accents: "Crème Brûlée" -> "creme brulee"."""
    text = text.lower()
    if text.isascii():
        return text
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        ch for ch in text if not "\u0300" <= ch <= "\u036f" and ch != _SOFT_HYPHEN
    )
    return unicodedata.normalize("NFC", text.translate(_FOLDS))


def _is_upper(ch: str) -> bool:
    return ch != ch.lower()


def _is_lower(ch: str) -> bool:
    return ch != ch.upper()


def _camel_spans(word: str) -> list[tuple[int, int]]:
    cuts = [0]
    for i in range(1, len(word)):
        ch, prev = word[i], word[i - 1]
        if not _is_upper(ch):
            continue
        if _is_lower(prev) or "0" <= prev <= "9":
            cuts.append(i)
        elif _is_upper(prev) and i + 1 < len(word) and _is_lower(word[i + 1]):
            # HTMLParser -> HTML|Parser, but keep plural acronyms (URLs, IDs)
            # in one piece.
            if word[i + 1 :] != "s":
                cuts.append(i)
    cuts.append(len(word))
    return list(zip(cuts, cuts[1:]))


def _split_chunk(chunk: str, offset: int) -> list[tuple[str, int, int]]:
    if chunk.isalnum() and chunk[1:] == chunk[1:].lower():
        # Nine words out of ten are just a word. Not running the general
        # code for those takes about a third off the time to index a site.
        return [(fold(chunk), offset, offset + len(chunk))]
    parts = []
    for match in _PIECE.finditer(chunk):
        piece = match.group()
        start = offset + match.start()
        possessive = _POSSESSIVE.search(piece)
        if possessive and possessive.start() > 0:
            piece = piece[: possessive.start()]
        if _APOSTROPHE.search(piece):
            # don't -> dont, O'Reilly -> oreilly. Not worth camel-splitting.
            spans = [(0, len(piece))]
        else:
            spans = _camel_spans(piece)
        for a, b in spans:
            text = fold(_APOSTROPHE.sub("", piece[a:b]))
            if text:
                parts.append((text, start + a, start + b))
    return parts


def tokenize(text: str) -> list[Token]:
    """Split text into normalised tokens with word positions and offsets.

    Hyphenated words and identifiers come out as their parts on consecutive
    positions, preceded by a `joined` token for the whole thing, so both
    "snake" and "snakecase" find snake_case.
    """
    # TODO: no segmentation for CJK; a run of ideographs is a single token.
    tokens = []
    position = 0
    for match in _chunk_pattern().finditer(text):
        chunk = match.group()
        start, end = match.span()
        if match.group(1) is not None:
            if _THOUSANDS.fullmatch(chunk):
                chunk = chunk.replace(",", "")
            if len(chunk) <= MAX_TOKEN_LENGTH:
                tokens.append(Token(chunk, position, start, end))
            position += 1
            continue

        parts = _split_chunk(chunk, start)
        if len(parts) > 1 and not all(_DIGITS.fullmatch(p[0]) for p in parts):
            whole = "".join(p[0] for p in parts)
            if len(whole) <= MAX_TOKEN_LENGTH:
                tokens.append(Token(whole, position, start, end, True))
        for part, a, b in parts:
            if len(part) <= MAX_TOKEN_LENGTH:
                tokens.append(Token(part, position, a, b))
            position += 1
    return tokens
