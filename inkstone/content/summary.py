"""Page summaries: the <!-- more --> marker, the first paragraph, truncation."""

from __future__ import annotations

import re
from typing import NamedTuple

from ..utils import text as textutil

MORE_MARKER = re.compile(r"<!--\s*more\s*-->", re.I)

_TAG = re.compile(
    r"<!--.*?-->|<(?P<close>/)?(?P<name>[A-Za-z][A-Za-z0-9-]*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^'\">])*?(?P<self>/)?>",
    re.S,
)
# one step of walking through HTML: a comment, a tag, an entity or a character
_PIECE = re.compile(
    _TAG.pattern + r"|&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#[xX][0-9a-fA-F]+);|.", re.S
)
_VOID = frozenset(
    "area base br col embed hr img input link meta source track wbr".split()
)
_PARAGRAPH = re.compile(r"<p\b[^>]*>.*?</p\s*>", re.S | re.I)
_EMPTY_TAIL = re.compile(r"(?:<(p|div|span|li|ul|ol|blockquote)\b[^>]*>\s*</\1>\s*)+\Z")
_FOOTNOTE_REF = re.compile(r'<sup class="footnote-ref">.*?</sup>', re.S)
# raw-text elements: whatever is inside is not markup
_RAW_TEXT = re.compile(r"<(script|style|textarea)\b.*?</\1\s*>", re.S | re.I)


class Summary(NamedTuple):
    html: str
    # True when the page has more to say than the summary shows
    truncated: bool


def has_more_marker(text: str) -> bool:
    return MORE_MARKER.search(text) is not None


def _track(match: re.Match, open_tags: list[str]) -> None:
    """Update the stack of open elements for one tag (comments do nothing)."""
    name = match.group("name")
    if name is None:
        return
    name = name.lower()
    if match.group("close"):
        if name in open_tags:
            # closes anything left open inside it as well, like a browser
            while open_tags.pop() != name:
                pass
    elif name not in _VOID and not match.group("self"):
        open_tags.append(name)


def _closing(open_tags: list[str]) -> str:
    return "".join(f"</{name}>" for name in reversed(open_tags))


def close_open_tags(fragment: str) -> str:
    """Append the closing tags that a cut-off piece of HTML is missing."""
    open_tags: list[str] = []
    for match in _TAG.finditer(_RAW_TEXT.sub("", fragment)):
        _track(match, open_tags)
    return fragment + _closing(open_tags)


def split_at_marker(html: str) -> tuple[str, str] | None:
    """Split rendered HTML at the first <!-- more --> marker.

    Returns ``(summary, content_without_marker)``, or None when there is no
    marker. The summary is balanced even when the marker sits inside a list
    or a paragraph.
    """
    match = MORE_MARKER.search(html)
    if match is None:
        return None
    before, after = html[: match.start()], html[match.end() :]
    summary = close_open_tags(before.rstrip())
    summary = _EMPTY_TAIL.sub("", summary).rstrip()
    if summary:
        summary += "\n"
    # a marker on a line of its own should not leave a blank line behind
    if before.endswith("\n") and after.startswith("\n"):
        after = after[1:]
    content = MORE_MARKER.sub("", before + after)
    return summary, content


def detach(html: str) -> str:
    """Make a piece of a page safe to show somewhere else.

    Footnote markers go: their notes stay behind on the page, and on a list
    of ten summaries ten links to "#fn-1" would all be broken.
    """
    return _FOOTNOTE_REF.sub("", html)


def strip_marker(html: str) -> str:
    parts = split_at_marker(html)
    return html if parts is None else parts[1]


def first_paragraph(html: str) -> str:
    """The first paragraph that has text in it ("" when there is none)."""
    # XXX a <p> inside a blockquote or list item counts too, so a post that
    # opens with a quotation gets the quotation as its summary, unquoted
    for match in _PARAGRAPH.finditer(html):
        if textutil.strip_html(match.group()):
            return match.group()
    return ""


def truncate_html(
    html: str, length: int = 300, suffix: str = "…", *, words: bool = False
) -> str:
    """Shorten HTML to ``length`` characters (or words) of text.

    Tags do not count and are never cut in half, an entity counts as the
    one character it shows, and whatever is still open at the cut gets
    closed. The cut moves back to the end of a word when one is near.
    """
    if words:
        return textutil.truncate_words(html, length, suffix=suffix, html=True)
    length = max(int(length), 0)
    out: list[str] = []
    open_tags: list[str] = []
    used = 0
    # (len(out), open tags, characters used) at the last gap between words
    boundary: tuple[int, list[str], int] | None = None
    in_word = False
    for match in _PIECE.finditer(html):
        piece = match.group()
        if match.group("name") is not None or piece.startswith("<!--"):
            out.append(piece)
            _track(match, open_tags)
            continue
        if piece.isspace():
            if in_word:
                boundary = (len(out), list(open_tags), used)
            in_word = False
        elif used >= length:
            if not textutil.strip_html(html[match.start() :]):
                # only markup is left, nothing would be gained by cutting
                return html
            # in the middle of a word: go back to its start, unless that
            # throws away more than half of what there was room for
            if in_word and boundary is not None and boundary[2] > length // 2:
                del out[boundary[0] :]
                open_tags = boundary[1]
            return "".join(out).rstrip() + suffix + _closing(open_tags)
        else:
            in_word = True
        out.append(piece)
        used += 1
    return html


def make_summary(
    html: str, *, explicit: str | None = None, fallback_words: int = 70
) -> tuple[Summary, str]:
    """Work out the summary of a rendered page.

    In order: the text before a <!-- more --> marker, ``explicit`` (the
    rendered front matter summary), the first paragraph, and for pages
    without any paragraph the first ``fallback_words`` words. Returns the
    summary and the content with the marker taken out.
    """
    parts = split_at_marker(html)
    if parts is not None:
        summary, content = parts
        if summary.strip():
            after = html[MORE_MARKER.search(html).end() :]
            truncated = bool(textutil.strip_html(after))
            return Summary(detach(summary), truncated), content
        # a marker before any text: nothing to show, fall through
        html = content
    if explicit is not None and explicit.strip():
        return Summary(explicit, bool(textutil.strip_html(html))), html
    paragraph = first_paragraph(html)
    if paragraph:
        truncated = textutil.strip_html(paragraph) != textutil.strip_html(html)
        return Summary(detach(paragraph) + "\n", truncated), html
    if not textutil.strip_html(html):
        return Summary("", False), html
    shortened = truncate_html(html, fallback_words, words=True)
    return Summary(shortened, shortened != html), html


def plain_summary(html: str, length: int = 160) -> str:
    """Text-only version for meta descriptions and feed readers."""
    return textutil.truncate_chars(textutil.strip_html(html), length)
