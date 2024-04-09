from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

from .entities import decode_entity

ESCAPABLE = r"""[!"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}~-]"""
ENTITY = r"&(?:#[xX][a-fA-F0-9]{1,6}|#[0-9]{1,7}|[a-zA-Z][a-zA-Z0-9]{1,31});"

_BACKSLASH_OR_ENTITY = re.compile(r"\\" + ESCAPABLE + "|" + ENTITY)
_ASCII_PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

# Everything that may appear in a URL as is. "%" is handled separately so
# that existing escapes survive but a stray percent sign gets encoded.
_URI_UNSAFE = re.compile(r"%(?![0-9A-Fa-f]{2})|[^A-Za-z0-9;/?:@&=+$,\-_.!~*'()#%]+")

_UNSAFE_SCHEME = re.compile(r"(?:javascript|vbscript|file|data):", re.I)
_SAFE_DATA_URL = re.compile(r"data:image/(?:png|gif|jpeg|webp)[;,]", re.I)

_SLUG_DROP = re.compile(r"[^\w\s-]")
_SLUG_SEPARATOR = re.compile(r"[\s-]+")

_ATTR_TOKEN = re.compile(
    r"""\s*(?:
        \#(?P<id>[^\s#.{}="']+)
      | \.(?P<cls>[^\s#.{}="']+)
      | (?P<key>[A-Za-z_:][\w:.-]*)
        (?P<eq>=(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s{}"']*)))?
    )""",
    re.X,
)


def escape_html(text: str) -> str:
    if not ("&" in text or "<" in text or ">" in text or '"' in text):
        return text
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _unescape_match(m: re.Match) -> str:
    found = m.group()
    if found[0] == "\\":
        return found[1]
    decoded = decode_entity(found)
    return found if decoded is None else decoded


def unescape_string(text: str) -> str:
    """Resolve backslash escapes and character references."""
    if "\\" not in text and "&" not in text:
        return text
    return _BACKSLASH_OR_ENTITY.sub(_unescape_match, text)


def normalize_uri(uri: str) -> str:
    """Percent-encode whatever cannot go into an href untouched."""
    return _URI_UNSAFE.sub(lambda m: quote(m.group(), safe="", errors="replace"), uri)


def normalize_label(label: str) -> str:
    """Canonical form of a reference label, for matching [Foo  Bar] to [foo bar]."""
    return " ".join(label.split()).casefold()


def is_unsafe_url(url: str, *, image: bool = False) -> bool:
    """True for link targets that can run script (or read local files)."""
    url = url.lstrip()
    if not _UNSAFE_SCHEME.match(url):
        return False
    return not (image and _SAFE_DATA_URL.match(url))


def is_punctuation(char: str) -> bool:
    if char in _ASCII_PUNCTUATION:
        return True
    if char < "\x80":
        return False
    return unicodedata.category(char)[0] in "PS"


def slugify(text: str, fallback: str = "section") -> str:
    """Make an id out of heading text: "Hello, World!" -> "hello-world"."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = _SLUG_DROP.sub("", text)
    text = _SLUG_SEPARATOR.sub("-", text).strip("-")
    return text or fallback


def unique_id(wanted: str, seen: dict[str, int]) -> str:
    """Return wanted, or wanted-1, wanted-2... if it has been handed out before."""
    if wanted not in seen:
        seen[wanted] = 0
        return wanted
    while True:
        seen[wanted] += 1
        candidate = f"{wanted}-{seen[wanted]}"
        if candidate not in seen:
            seen[candidate] = 0
            return candidate


def parse_attrs(text: str) -> dict | None:
    """Parse the inside of ``{#id .class key="value" flag}``.

    Classes are collected into one space separated "class" entry and bare
    words map to True. Returns None if the text is not an attribute list.
    """
    ident = None
    classes: list[str] = []
    others: dict = {}
    text = text.strip()
    pos = 0
    while pos < len(text):
        m = _ATTR_TOKEN.match(text, pos)
        if m is None or m.end() == pos:
            return None
        if m.group("id"):
            ident = m.group("id")
        elif m.group("cls"):
            classes.append(m.group("cls"))
        else:
            key = m.group("key")
            if m.group("eq") is None:
                value: str | bool = True
            else:
                value = m.group("dq") or m.group("sq") or m.group("bare") or ""
            if key == "id" and isinstance(value, str):
                ident = value
            elif key == "class" and isinstance(value, str):
                classes.extend(value.split())
            else:
                others[key] = value
        pos = m.end()

    # id and class go first so the generated markup reads naturally
    attrs: dict = {}
    if ident:
        attrs["id"] = ident
    if classes:
        attrs["class"] = " ".join(classes)
    attrs.update(others)
    return attrs


def parse_line_numbers(spec: str | bool | None) -> set[int]:
    """Turn "1 3 5-7" (as in hl_lines) into {1, 3, 5, 6, 7}."""
    lines: set[int] = set()
    if not isinstance(spec, str):
        return lines
    for part in spec.replace(",", " ").split():
        first, sep, last = part.partition("-")
        try:
            start = int(first)
            end = int(last) if sep else start
        except ValueError:
            continue
        lines.update(range(start, end + 1))
    return lines
