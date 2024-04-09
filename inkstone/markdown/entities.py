from __future__ import annotations

# The stdlib already ships the full HTML5 table (keys look like "amp;"), so
# there is no point keeping our own copy in sync with the spec.
from html.entities import html5 as _NAMED

REPLACEMENT = "\ufffd"


def decode_entity(ref: str) -> str | None:
    """Decode one character reference, given with its ``&`` and ``;``.

    Returns None for a named reference nobody has heard of, which the caller
    should then leave in the text as written.
    """
    body = ref[1:-1]
    if not body.startswith("#"):
        return _NAMED.get(body + ";")
    try:
        if body[1:2] in ("x", "X"):
            code = int(body[2:], 16)
        else:
            code = int(body[1:])
    except ValueError:
        return None
    if code == 0 or code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        return REPLACEMENT
    return chr(code)
