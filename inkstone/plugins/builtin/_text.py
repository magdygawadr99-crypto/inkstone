"""Getting at the words of a Markdown source without rendering it.

Rough on purpose: this feeds word counts and similarity scores, where being
off by a few words does not matter and parsing every page twice would.
"""

from __future__ import annotations

import html
import re

_FENCE_OPEN = re.compile(r"^[ \t>]*(`{3,}|~{3,})[^\n]*$", re.M)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SHORTCODE = re.compile(r"\{\{[<%].*?[>%]\}\}", re.S)
_RAW_ELEMENT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>\n]*>")
_REFERENCE_DEF = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*\S+.*$", re.M)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")
_REFERENCE_LINK = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_FOOTNOTE_REF = re.compile(r"\[\^[^\]\s]+\]:?")
_AUTOLINK = re.compile(r"<(?:https?://|mailto:)[^>\s]+>|https?://\S+")


def split_code(markdown: str) -> tuple[str, str]:
    """Separate fenced code blocks from the rest: ``(prose, code)``.

    Indented code blocks stay with the prose; telling them from list
    continuations needs a real parser.
    """
    prose: list[str] = []
    code: list[str] = []
    pos = 0
    while True:
        opening = _FENCE_OPEN.search(markdown, pos)
        if opening is None:
            break
        marker = opening.group(1)
        if marker[0] == "`" and "`" in markdown[opening.end(1) : opening.end()]:
            # backticks in the info string: an inline code span, not a fence
            prose.append(markdown[pos : opening.end()])
            pos = opening.end()
            continue
        closing = re.compile(
            rf"^[ \t>]*{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$", re.M
        ).search(markdown, opening.end())
        prose.append(markdown[pos : opening.start()])
        body_end = closing.start() if closing else len(markdown)
        code.append(markdown[opening.end() : body_end])
        pos = closing.end() if closing else len(markdown)
    prose.append(markdown[pos:])
    return "\n".join(prose), "\n".join(code)


def plain(markdown: str) -> str:
    """Markdown with the markup taken out, close enough for counting words.

    Fenced code is kept as it is; use split_code() first to leave it out.
    """
    text = _COMMENT.sub(" ", markdown)
    text = _RAW_ELEMENT.sub(" ", text)
    text = _SHORTCODE.sub(" ", text)
    text = _REFERENCE_DEF.sub(" ", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _FOOTNOTE_REF.sub(" ", text)
    text = _AUTOLINK.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    return html.unescape(text)


# Japanese kana and CJK ideographs are written without spaces, so every
# character counts as a word of its own.
_CJK = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORD = re.compile(r"\w+(?:['’-]\w+)*")


def count_words(text: str) -> tuple[int, int]:
    """``(words, ideographs)`` in a piece of plain text."""
    ideographs = len(_CJK.findall(text))
    return len(_WORD.findall(_CJK.sub(" ", text))), ideographs
