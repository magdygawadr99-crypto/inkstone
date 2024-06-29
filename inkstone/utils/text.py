from __future__ import annotations

import math
import re
import textwrap
import unicodedata
from html import unescape

# Letters that do not decompose into "base letter + accent", so stripping
# combining marks would leave them untouched.
_LATIN = (
    "ß:ss æ:ae Æ:AE œ:oe Œ:OE ø:o Ø:O đ:d Đ:D ð:d Ð:D þ:th Þ:Th ł:l Ł:L "
    "ħ:h Ħ:H ı:i ŋ:n Ŋ:N"
)
# Russian, plus the extra letters of Ukrainian and Belarusian. The hard and
# soft signs map to nothing. Letters the languages share follow the Russian
# reading, so Ukrainian "и" comes out as "i" rather than "y".
_CYRILLIC = (
    "а:a б:b в:v г:g д:d е:e ё:yo ж:zh з:z и:i й:y к:k л:l м:m н:n о:o п:p "
    "р:r с:s т:t у:u ф:f х:kh ц:ts ч:ch ш:sh щ:shch ъ: ы:y ь: э:e ю:yu я:ya "
    "є:ye і:i ї:yi ґ:g ў:u"
)
_GREEK = (
    "α:a β:b γ:g δ:d ε:e ζ:z η:i θ:th ι:i κ:k λ:l μ:m ν:n ξ:x ο:o π:p ρ:r "
    "σ:s ς:s τ:t υ:y φ:f χ:ch ψ:ps ω:o"
)

_SYMBOL_WORDS = {
    "&": "and",
    "@": "at",
    "%": "percent",
    "+": "plus",
    "€": "euro",
    "$": "dollar",
    "£": "pound",
}
_SYMBOLS = re.compile("[" + re.escape("".join(_SYMBOL_WORDS)) + "]")
_APOSTROPHES = re.compile("['’‘ʼ]")


def _build_translit_table() -> dict[str, str]:
    table = dict(pair.split(":") for pair in _LATIN.split())
    for alphabet in (_CYRILLIC, _GREEK):
        for pair in alphabet.split():
            char, latin = pair.split(":")
            table[char] = latin
            upper = char.upper()
            if upper != char and len(upper) == 1:
                table.setdefault(upper, latin.capitalize())
    return table


_TRANSLIT = _build_translit_table()


def transliterate(text: str) -> str:
    """Best-effort Latin rendering of accented, Cyrillic and Greek text.

    Characters we know nothing about (CJK, emoji, ...) pass through as is.
    """
    out = []
    for char in text:
        if char < "\x80":
            out.append(char)
            continue
        mapped = _TRANSLIT.get(char)
        if mapped is None:
            # é -> e + combining accent; drop the accent and look again,
            # which is also what gets accented Greek into the table
            decomposed = unicodedata.normalize("NFKD", char)
            base = "".join(c for c in decomposed if not unicodedata.combining(c))
            mapped = "".join(_TRANSLIT.get(c, c) for c in base)
        out.append(mapped)
    return "".join(out)


def slugify(
    text: str,
    *,
    sep: str = "-",
    lowercase: bool = True,
    max_length: int | None = None,
    allow_unicode: bool = False,
) -> str:
    """Turn a title into something that is safe in a URL or file name.

    By default the result is plain ASCII. With ``allow_unicode`` letters and
    digits of any script are kept and nothing is transliterated.
    """
    text = _APOSTROPHES.sub("", str(text))
    if allow_unicode:
        words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text))
    else:
        text = _SYMBOLS.sub(lambda m: f" {_SYMBOL_WORDS[m.group()]} ", text)
        words = re.findall(r"[A-Za-z0-9]+", transliterate(text))
    slug = sep.join(words)
    if lowercase:
        slug = slug.lower()
    if max_length is not None and len(slug) > max_length:
        slug = _shorten_slug(slug, max_length, sep)
    return slug


def _shorten_slug(slug: str, max_length: int, sep: str) -> str:
    cut = slug[:max_length]
    if not sep:
        return cut
    # drop a partial last word, unless it is the only one
    if not slug.startswith(sep, max_length) and sep in cut:
        cut = cut.rpartition(sep)[0]
    while cut.endswith(sep):
        cut = cut[: -len(sep)]
    return cut


_TAG_SOURCE = r"</?[A-Za-z][^\s>/]*(?:\"[^\"]*\"|'[^']*'|[^'\">])*>"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HIDDEN_ELEMENT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_BLOCK_TAG = re.compile(
    r"</?(?:p|div|br|hr|li|ul|ol|dl|dt|dd|h[1-6]|tr|td|th|table|blockquote|pre"
    r"|section|article|header|footer|figure|figcaption)\b[^>]*>",
    re.I,
)
_TAG = re.compile(_TAG_SOURCE + r"|<![^>]*>")
_HTML_TOKEN = re.compile(
    r"(?P<comment><!--.*?-->)"
    r"|(?P<tag>" + _TAG_SOURCE + ")"
    r"|(?P<entity>&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9a-fA-F]+);)",
    re.S,
)
_TAG_NAME = re.compile(r"</?([A-Za-z][^\s>/]*)")
_VOID_ELEMENTS = frozenset(
    "area base br col embed hr img input link meta source track wbr".split()
)
_TRAILING_PUNCTUATION = " \t\n.,;:!?-–—"


def strip_html(markup: str, *, collapse: bool = True) -> str:
    """Plain text of an HTML fragment, entities decoded.

    Block-level tags turn into spaces so "<p>a</p><p>b</p>" does not come
    out as "ab". With ``collapse`` runs of whitespace are squeezed too.
    """
    text = _COMMENT.sub("", markup)
    text = _HIDDEN_ELEMENT.sub("", text)
    text = _BLOCK_TAG.sub(" ", text)
    text = unescape(_TAG.sub("", text))
    if collapse:
        text = " ".join(text.split())
    return text


def truncate_words(
    text: str, count: int, *, suffix: str = "…", html: bool = False
) -> str:
    """Keep the first ``count`` words. ``html=True`` leaves markup intact."""
    if html:
        return _truncate_html(text, count, True, suffix)
    words = text.split()
    if len(words) <= count:
        return text
    return " ".join(words[:count]).rstrip(_TRAILING_PUNCTUATION) + suffix


def truncate_chars(
    text: str, length: int, *, suffix: str = "…", html: bool = False
) -> str:
    """Shorten ``text`` to at most ``length`` characters, suffix included.

    The cut moves back to a word boundary when there is one nearby. With
    ``html=True`` tags and entities are never cut in half, tags do not count
    towards the length, and anything left open gets closed.
    """
    room = max(length - len(suffix), 0)
    if html:
        return _truncate_html(text, room, False, suffix)
    if len(text) <= length:
        return text
    cut = text[:room]
    if not text[room].isspace():
        boundary = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"))
        # falling back more than half way would waste too much room
        if boundary > room // 2:
            cut = cut[:boundary]
    return cut.rstrip(_TRAILING_PUNCTUATION) + suffix


def _truncate_html(markup: str, limit: int, by_words: bool, suffix: str) -> str:
    out: list[str] = []
    open_tags: list[str] = []
    used = 0
    in_word = False
    pos = 0
    while pos < len(markup):
        match = _HTML_TOKEN.match(markup, pos)
        if match is not None and not match.group("entity"):
            # tags and comments take no room
            out.append(match.group())
            if match.group("tag"):
                _track_tag(match.group(), open_tags)
                if _BLOCK_TAG.match(match.group()):
                    # "</p><p>" separates words even without a space
                    in_word = False
            pos = match.end()
            continue
        piece = match.group() if match else markup[pos]
        counts = True
        if by_words:
            # only the first character of each word uses up budget
            is_space = unescape(piece).isspace()
            counts = not is_space and not in_word
            in_word = not is_space
        if counts:
            if used == limit:
                break
            used += 1
        out.append(piece)
        pos += len(piece)
    if not strip_html(markup[pos:]):
        # nothing visible would be lost, so there is nothing to shorten
        return markup
    closing = "".join(f"</{name}>" for name in reversed(open_tags))
    return "".join(out).rstrip() + suffix + closing


def _track_tag(tag: str, open_tags: list[str]) -> None:
    name = _TAG_NAME.match(tag).group(1).lower()
    if tag.startswith("</"):
        if name in open_tags:
            # also drops anything left unclosed inside it
            while open_tags.pop() != name:
                pass
    elif name not in _VOID_ELEMENTS and not tag.endswith("/>"):
        open_tags.append(name)


# Japanese kana and CJK ideographs; these scripts do not put spaces between
# words, so every character counts as one. Hangul does use spaces.
_CJK = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def _count_words(text: str) -> tuple[int, int]:
    ideographs = len(_CJK.findall(text))
    return len(_WORD.findall(_CJK.sub(" ", text))), ideographs


def word_count(text: str) -> int:
    words, ideographs = _count_words(text)
    return words + ideographs


def reading_time(text: str, *, wpm: int = 220, cjk_cpm: int = 450) -> int:
    """Estimated minutes to read ``text``, rounded up; 0 for no text."""
    words, ideographs = _count_words(text)
    if not words and not ideographs:
        return 0
    return max(1, math.ceil(words / wpm + ideographs / cjk_cpm))


_SMALL_WORDS = frozenset(
    "a an and as at but by en for if in nor of on or per the to v vs via".split()
)
_WORD_PARTS = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def titlecase(text: str) -> str:
    """Capitalise a headline the way a style guide would.

    Small words (of, the, and...) stay lower case unless they come first,
    last or right after a colon. Words that already contain capitals
    (iPhone, HTML) or look like file names and URLs are left alone.
    """
    if text.isupper():
        text = text.lower()
    words = text.split()
    out = []
    force = True
    for index, word in enumerate(words):
        last = index == len(words) - 1
        out.append(_title_word(word, force, last))
        force = word.endswith((":", "!", "?", "—"))
    return " ".join(out)


def _title_word(word: str, first: bool, last: bool) -> str:
    lead, core, trail = _WORD_PARTS.match(word).groups()
    if not core or "." in core or "/" in core or "@" in core:
        return word
    if core[1:] != core[1:].lower():
        # capitals inside a word are deliberate
        return word
    parts = core.split("-")
    cased = []
    for index, part in enumerate(parts):
        edge = (first and index == 0) or (last and index == len(parts) - 1)
        if part.lower() in _SMALL_WORDS and not edge:
            cased.append(part.lower())
        else:
            cased.append(part[:1].upper() + part[1:])
    return lead + "-".join(cased) + trail


def pluralize(
    count: int, singular: str, plural: str | None = None, *, show_count: bool = True
) -> str:
    """Count plus noun: "1 page", "3 pages".

    Regular English plurals are guessed; pass ``plural`` for the others.
    """
    word = singular if count == 1 else plural or _plural(singular)
    return f"{count} {word}" if show_count else word


def _plural(word: str) -> str:
    lower = word.lower()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if lower.endswith("y") and lower[-2:-1] not in ("a", "e", "i", "o", "u", ""):
        return word[:-1] + "ies"
    return word + "s"


def natural_sort_key(text: str) -> tuple:
    """Sort key that orders "page2" before "page10", ignoring case."""
    parts = re.split(r"(\d+)", str(text).casefold())
    # re.split alternates text and digits, so the tuples always compare
    # str with str and int with int
    return tuple(int(part) if index % 2 else part for index, part in enumerate(parts))


def dedent_block(text: str) -> str:
    """Clean up a triple-quoted literal for writing to a file.

    Removes the common indentation and surrounding blank lines; the result
    ends with exactly one newline unless it is empty.
    """
    lines = textwrap.dedent(text).split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    return "\n".join(line.rstrip() for line in lines) + "\n"


def wrap(
    text: str,
    width: int = 80,
    *,
    indent: str = "",
    subsequent_indent: str | None = None,
) -> str:
    """Re-flow ``text`` to ``width`` columns, one paragraph at a time."""
    if subsequent_indent is None:
        subsequent_indent = indent
    paragraphs = re.split(r"\n[ \t]*\n", text.strip())
    filled = [
        textwrap.fill(
            " ".join(paragraph.split()),
            width=width,
            initial_indent=indent,
            subsequent_indent=subsequent_indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        for paragraph in paragraphs
    ]
    return "\n\n".join(filled)


def humanize_bytes(size: int) -> str:
    """1536 -> "1.5 KB". Units are powers of 1024."""
    sign = "-" if size < 0 else ""
    value = float(abs(size))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        # 1023.5 and up would round to "1024 KB"
        if value < 1023.5 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{sign}{int(value)} B"
    if value < 9.95:
        return f"{sign}{value:.1f} {unit}"
    return f"{sign}{value:.0f} {unit}"


def humanize_duration(seconds: float) -> str:
    """0.85 -> "850 ms", 1.5 -> "1.50 s", 125 -> "2 min 5 s"."""
    if seconds < 0:
        return "-" + humanize_duration(-seconds)
    if 0 < seconds < 0.001:
        return "<1 ms"
    if seconds < 0.9995:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 9.995:
        return f"{seconds:.2f} s"
    if seconds < 59.95:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {secs} s" if secs else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def ordinal(number: int) -> str:
    """1 -> "1st", 22 -> "22nd", 113 -> "113th"."""
    tail = abs(number) % 100
    if 10 <= tail <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(tail % 10, "th")
    return f"{number}{suffix}"
