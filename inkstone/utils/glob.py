"""gitignore-style path matching.

    *.tmp          any file or directory called *.tmp, at any depth
    /build         only "build" at the top level
    docs/*.md      anchored too, because it contains a slash
    cache/         directories only (and everything inside them)
    **/drafts/**   everything below any "drafts" directory
    !keep.tmp      re-include something an earlier pattern excluded
"""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple


class _Rule(NamedTuple):
    regex: re.Pattern
    negated: bool
    dir_only: bool


def translate(pattern: str) -> str:
    """Regular expression source for one pattern.

    The expression matches whole relative paths with forward slashes.
    Negation and the directories-only meaning of a trailing "/" are
    :class:`GlobSet`'s business: pass the pattern without its "!", and a
    trailing slash is simply dropped.
    """
    pattern = pattern.rstrip("/")
    # a slash anywhere but at the end ties the pattern to the root
    anchored = "/" in pattern
    # FIXME: this also splits on a "/" inside a [class]. git treats that as
    # a pattern that can never match, we produce something odd instead.
    segments = pattern.lstrip("/").split("/")
    out = [] if anchored else ["(?:.*/)?"]
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            # "a/**" needs something below a, "**/b" allows zero directories
            out.append(".*" if last else "(?:.*/)?")
            continue
        out.append(_translate_segment(segment))
        if not last:
            out.append("/")
    return "(?s:" + "".join(out) + r")\Z"


def _translate_segment(segment: str) -> str:
    out = []
    index = 0
    while index < len(segment):
        char = segment[index]
        index += 1
        if char == "*":
            # "**" glued to other text is just "*"
            while index < len(segment) and segment[index] == "*":
                index += 1
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = _class_end(segment, index)
            if end == -1:
                out.append(r"\[")
            else:
                out.append(_translate_class(segment[index:end]))
                index = end + 1
        elif char == "\\" and index < len(segment):
            out.append(re.escape(segment[index]))
            index += 1
        else:
            out.append(re.escape(char))
    return "".join(out)


def _class_end(segment: str, start: int) -> int:
    """Index of the "]" closing the class that opens just before ``start``."""
    index = start
    if index < len(segment) and segment[index] in "!^":
        index += 1
    # a "]" right at the start is a member, not the end
    if index < len(segment) and segment[index] == "]":
        index += 1
    return segment.find("]", index)


def _translate_class(body: str) -> str:
    negated = body[:1] in ("!", "^")
    if negated:
        body = body[1:]
    body = body.replace("\\", "\\\\").replace("[", "\\[")
    if body.startswith("]"):
        body = "\\" + body
    # the lookahead keeps negated classes and ranges like [+-9] from
    # swallowing a separator
    return f"(?!/)[^{body}]" if negated else f"(?!/)[{body}]"


class GlobSet:
    """An ordered list of patterns; the last one that matches decides.

    Unlike git, a "!" pattern can re-include a file even when one of its
    parent directories is excluded.
    """

    def __init__(self, patterns: Iterable[str] = (), *, ignore_case: bool = False):
        if isinstance(patterns, str):
            patterns = [patterns]
        self.patterns: list[str] = []
        self._rules: list[_Rule] = []
        flags = re.IGNORECASE if ignore_case else 0
        for raw in patterns:
            pattern = raw.strip()
            # blank lines and comments, so the lines of an ignore file can
            # be passed in unfiltered
            if not pattern or pattern.startswith("#"):
                continue
            negated = pattern.startswith("!")
            body = pattern[1:] if negated else pattern
            if not body.strip("/"):
                continue
            try:
                regex = re.compile(translate(body), flags)
            except re.error as exc:
                raise ValueError(f"bad pattern {raw!r}: {exc}") from None
            self.patterns.append(pattern)
            self._rules.append(_Rule(regex, negated, body.endswith("/")))

    @property
    def has_negation(self) -> bool:
        return any(rule.negated for rule in self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __bool__(self) -> bool:
        return bool(self._rules)

    def __repr__(self) -> str:
        return f"GlobSet({self.patterns!r})"

    def match(self, relpath, is_dir: bool = False) -> bool:
        """Is ``relpath`` (relative to the root the patterns apply to) matched?

        A path also counts as matched when one of its parent directories is.
        """
        if not self._rules:
            return False
        path = str(relpath).replace("\\", "/").strip("/")
        while path.startswith("./"):
            path = path[2:]
        if path in ("", "."):
            return False
        parts = path.split("/")
        candidates = [("/".join(parts[:count]), True) for count in range(1, len(parts))]
        candidates.append((path, is_dir))
        matched = False
        for rule in self._rules:
            for candidate, candidate_is_dir in candidates:
                if rule.dir_only and not candidate_is_dir:
                    continue
                if rule.regex.match(candidate):
                    matched = not rule.negated
                    break
        return matched

    def filter(self, paths: Iterable[str]) -> list[str]:
        """The paths that are *not* matched, in their original order."""
        return [path for path in paths if not self.match(path)]
