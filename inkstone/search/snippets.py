from __future__ import annotations

import html
import re
from collections import Counter
from typing import Iterable

from .analyzer import Analyzer

_WHITESPACE = re.compile(r"\s+")

_Span = tuple[int, int, frozenset]


def _match_spans(text: str, terms: Iterable[str], analyzer: Analyzer) -> list[_Span]:
    wanted = set(terms)
    spans: list[_Span] = []
    if not wanted:
        return spans
    for token in analyzer.analyze(text):
        if token.text not in wanted:
            continue
        if spans and token.start < spans[-1][1]:
            # the joined form of snake_case overlaps its own parts
            start, end, found = spans[-1]
            spans[-1] = (start, max(end, token.end), found | {token.text})
        else:
            spans.append((token.start, token.end, frozenset([token.text])))
    return spans


def _render(text: str, start: int, end: int, spans: list[_Span], tag: str) -> str:
    out = []
    cursor = start
    for a, b, _ in spans:
        if b <= start or a >= end:
            continue
        a, b = max(a, start), min(b, end)
        out.append(html.escape(text[cursor:a]))
        out.append(f"<{tag}>{html.escape(text[a:b])}</{tag}>")
        cursor = b
    out.append(html.escape(text[cursor:end]))
    return "".join(out)


def _best_window(spans: list[_Span], max_length: int) -> tuple[int, int]:
    """The run of matches that fits in max_length and covers the most terms.

    Distinct terms win over repeats of the same one; the earliest run wins a
    tie.
    """
    best, best_key = (0, 1), (0, 0)
    counts: Counter[str] = Counter()
    j = 0
    for i, (start, _, _) in enumerate(spans):
        while j < len(spans) and (j == i or spans[j][1] - start <= max_length):
            counts.update(spans[j][2])
            j += 1
        key = (len(counts), j - i)
        if key > best_key:
            best, best_key = (i, j), key
        counts.subtract(spans[i][2])
        counts = +counts
    return best


def _snap_start(text: str, start: int, limit: int) -> int:
    if start <= 0 or text[start - 1].isspace():
        return start
    gap = _WHITESPACE.search(text, start, limit)
    return gap.end() if gap else start


def _snap_end(text: str, end: int, limit: int) -> int:
    if end >= len(text) or text[end].isspace():
        return end
    cut = end
    while cut > limit and not text[cut - 1].isspace():
        cut -= 1
    return cut if cut > limit else end


def _excerpt_bounds(
    text: str, first: int, last: int, max_length: int
) -> tuple[int, int]:
    room = max(max_length, last - first)
    start = max(first - (room - (last - first)) // 2, 0)
    end = min(start + room, len(text))
    # close to the end of the text the unused room goes to the left instead
    start = max(min(start, end - room), 0)
    return _snap_start(text, start, first), _snap_end(text, end, last)


def highlight(
    text: str,
    terms: Iterable[str],
    *,
    analyzer: Analyzer | None = None,
    tag: str = "mark",
) -> str:
    """HTML-escape text and wrap every word that matches a term in <mark>.

    `terms` are index terms as found in SearchHit.matches, not raw query
    words. Pass the index's analyzer unless it uses the defaults.
    """
    spans = _match_spans(text, terms, analyzer or Analyzer())
    return _render(text, 0, len(text), spans, tag)


def snippet(
    text: str,
    terms: Iterable[str],
    *,
    analyzer: Analyzer | None = None,
    max_length: int = 200,
    tag: str = "mark",
    ellipsis: str = "…",
) -> str:
    """An excerpt of roughly max_length characters around the best matches.

    Falls back to the start of the text when nothing matches. The result is
    escaped HTML with whitespace collapsed.
    """
    spans = _match_spans(text, terms, analyzer or Analyzer())
    if len(text) <= max_length:
        start, end = 0, len(text)
    elif not spans:
        start, end = 0, _snap_end(text, max_length, 0)
    else:
        i, j = _best_window(spans, max_length)
        start, end = _excerpt_bounds(text, spans[i][0], spans[j - 1][1], max_length)
    body = _WHITESPACE.sub(" ", _render(text, start, end, spans, tag)).strip()
    if text[:start].strip():
        body = ellipsis + body
    if text[end:].strip():
        body += ellipsis
    return body
