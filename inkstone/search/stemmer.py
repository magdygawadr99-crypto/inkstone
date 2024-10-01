"""Porter2 ("Snowball English") stemmer.

Follows the description of the algorithm on snowballstem.org. Newer Snowball
releases have picked up a few more special cases which are not tracked here;
what matters for search is that index and query agree, not that we match
upstream word for word.

The client-side copy in client/search.js has to produce exactly the same
stems, so any change here needs the same change there
(tests/search/test_client.py compares the two).
"""

from __future__ import annotations

from functools import lru_cache

_VOWELS = frozenset("aeiouy")
_DOUBLES = ("bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt")
_LI_ENDINGS = frozenset("cdeghkmnrt")

# Words where R1 would otherwise start too early (generate -> gener|ate).
_R1_PREFIXES = ("gener", "commun", "arsen")

_EXCEPTIONS = {
    "skis": "ski",
    "skies": "sky",
    "dying": "die",
    "lying": "lie",
    "tying": "tie",
    "idly": "idl",
    "gently": "gentl",
    "ugly": "ugli",
    "early": "earli",
    "only": "onli",
    "singly": "singl",
    "sky": "sky",
    "news": "news",
    "howe": "howe",
    "atlas": "atlas",
    "cosmos": "cosmos",
    "bias": "bias",
    "andes": "andes",
}

# Left alone once step 1a has run.
_EXCEPTIONS_AFTER_1A = frozenset(
    "inning outing canning herring earring proceed exceed succeed".split()
)

_STEP_1B = ("eedly", "ingly", "edly", "eed", "ing", "ed")

# Each table is ordered longest suffix first; only the first hit is considered,
# even when its condition then fails.
_STEP_2 = (
    ("ization", "ize"),
    ("ational", "ate"),
    ("fulness", "ful"),
    ("ousness", "ous"),
    ("iveness", "ive"),
    ("tional", "tion"),
    ("biliti", "ble"),
    ("lessli", "less"),
    ("entli", "ent"),
    ("ation", "ate"),
    ("alism", "al"),
    ("aliti", "al"),
    ("ousli", "ous"),
    ("iviti", "ive"),
    ("fulli", "ful"),
    ("enci", "ence"),
    ("anci", "ance"),
    ("abli", "able"),
    ("izer", "ize"),
    ("ator", "ate"),
    ("alli", "al"),
    ("bli", "ble"),
    ("ogi", "og"),
    ("li", ""),
)

_STEP_3 = (
    ("ational", "ate"),
    ("tional", "tion"),
    ("alize", "al"),
    ("icate", "ic"),
    ("iciti", "ic"),
    ("ative", ""),
    ("ical", "ic"),
    ("ness", ""),
    ("ful", ""),
)

_STEP_4 = (
    "ement",
    "ance",
    "ence",
    "able",
    "ible",
    "ment",
    "ant",
    "ent",
    "ism",
    "ate",
    "iti",
    "ous",
    "ive",
    "ize",
    "ion",
    "al",
    "er",
    "ic",
)


def _mark_consonant_y(word: str) -> str:
    # y at the start of the word or after a vowel acts as a consonant; it is
    # written Y until the end so the vowel tests stay simple.
    if "y" not in word:
        return word
    chars = list(word)
    for i, ch in enumerate(chars):
        if ch == "y" and (i == 0 or chars[i - 1] in _VOWELS):
            chars[i] = "Y"
    return "".join(chars)


def _region_after(word: str, start: int) -> int:
    """Index just past the first consonant that follows a vowel, from start."""
    for i in range(start + 1, len(word)):
        if word[i] not in _VOWELS and word[i - 1] in _VOWELS:
            return i + 1
    return len(word)


def _regions(word: str) -> tuple[int, int]:
    for prefix in _R1_PREFIXES:
        if word.startswith(prefix):
            r1 = len(prefix)
            break
    else:
        r1 = _region_after(word, 0)
    return r1, _region_after(word, r1)


def _has_vowel(text: str) -> bool:
    return any(ch in _VOWELS for ch in text)


def _ends_in_short_syllable(word: str) -> bool:
    if len(word) == 2:
        return word[0] in _VOWELS and word[1] not in _VOWELS
    if len(word) < 3:
        return False
    a, b, c = word[-3], word[-2], word[-1]
    return a not in _VOWELS and b in _VOWELS and c not in _VOWELS and c not in "wxY"


def _step_0(word: str) -> str:
    for suffix in ("'s'", "'s", "'"):
        if word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _step_1a(word: str) -> str:
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith(("ied", "ies")):
        # ties -> tie, but cries -> cri
        return word[:-2] if len(word) > 4 else word[:-1]
    if word.endswith(("us", "ss")):
        return word
    if word.endswith("s") and _has_vowel(word[:-2]):
        return word[:-1]
    return word


def _step_1b(word: str, r1: int) -> str:
    for suffix in _STEP_1B:
        if word.endswith(suffix):
            break
    else:
        return word
    base = word[: -len(suffix)]
    if suffix in ("eed", "eedly"):
        return base + "ee" if len(base) >= r1 else word
    if not _has_vowel(base):
        return word
    if base.endswith(("at", "bl", "iz")):
        return base + "e"
    if base.endswith(_DOUBLES):
        return base[:-1]
    if r1 >= len(base) and _ends_in_short_syllable(base):
        return base + "e"
    return base


def _step_1c(word: str) -> str:
    if len(word) > 2 and word[-1] in "yY" and word[-2] not in _VOWELS:
        return word[:-1] + "i"
    return word


def _step_2(word: str, r1: int) -> str:
    for suffix, replacement in _STEP_2:
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        if len(base) < r1:
            return word
        if suffix == "ogi":
            return base + "og" if base.endswith("l") else word
        if suffix == "li":
            return base if base[-1:] in _LI_ENDINGS else word
        return base + replacement
    return word


def _step_3(word: str, r1: int, r2: int) -> str:
    for suffix, replacement in _STEP_3:
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        if len(base) < r1:
            return word
        if suffix == "ative" and len(base) < r2:
            return word
        return base + replacement
    return word


def _step_4(word: str, r2: int) -> str:
    for suffix in _STEP_4:
        if not word.endswith(suffix):
            continue
        base = word[: -len(suffix)]
        if len(base) < r2:
            return word
        if suffix == "ion" and base[-1:] not in ("s", "t"):
            return word
        return base
    return word


def _step_5(word: str, r1: int, r2: int) -> str:
    last = len(word) - 1
    if word.endswith("e"):
        if last >= r2:
            return word[:-1]
        if last >= r1 and not _ends_in_short_syllable(word[:-1]):
            return word[:-1]
    elif word.endswith("ll") and last >= r2:
        return word[:-1]
    return word


@lru_cache(maxsize=50_000)
def stem(word: str) -> str:
    """Stem a single English word. Input is lowercased, nothing else."""
    word = word.lower().replace("\u2019", "'")
    if word.startswith("'"):
        word = word[1:]
    if len(word) <= 2:
        return word
    if word in _EXCEPTIONS:
        return _EXCEPTIONS[word]

    word = _mark_consonant_y(word)
    r1, r2 = _regions(word)

    word = _step_1a(_step_0(word))
    if word in _EXCEPTIONS_AFTER_1A:
        return word
    word = _step_1b(word, r1)
    word = _step_1c(word)
    word = _step_2(word, r1)
    word = _step_3(word, r1, r2)
    word = _step_4(word, r2)
    word = _step_5(word, r1, r2)
    return word.replace("Y", "y")
