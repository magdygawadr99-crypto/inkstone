"""Word count and reading time, worked out from the Markdown source.

Counting happens before anything is rendered so that the numbers are there
for every page, including the ones an incremental build does not touch.
"""

from __future__ import annotations

import math

from ..base import Plugin
from ._common import front_matter, setting
from ._text import count_words, plain, split_code

_CODE_MODES = ("include", "exclude", "separate")


class ReadingTime(Plugin):
    name = "reading_time"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.words_per_minute = setting(self, "words_per_minute", 220, minimum=1)
        # include: code counts like prose. exclude: it is skipped.
        # separate: counted on its own and read at code_words_per_minute.
        self.code_blocks = setting(self, "code_blocks", "include", choices=_CODE_MODES)
        self.code_words_per_minute = setting(
            self, "code_words_per_minute", 100, minimum=1
        )
        self.cjk_chars_per_minute = setting(
            self, "cjk_chars_per_minute", 450, minimum=1
        )

    def measure(self, markdown: str) -> tuple[int, int, int]:
        """``(word_count, code_word_count, minutes)`` for a Markdown source."""
        prose, code = split_code(markdown)
        words, ideographs = count_words(plain(prose))
        code_words = sum(count_words(code))
        minutes = words / self.words_per_minute
        minutes += ideographs / self.cjk_chars_per_minute
        total = words + ideographs
        if self.code_blocks == "include":
            total += code_words
            minutes += code_words / self.words_per_minute
        elif self.code_blocks == "separate":
            minutes += code_words / self.code_words_per_minute
        return total, code_words, max(1, math.ceil(minutes))

    def content_loaded(self, site) -> None:
        pages = getattr(site, "all_pages", None) or site.pages
        for page in pages:
            if getattr(page, "source_path", None) is None:
                continue
            words, code_words, minutes = self.measure(page.raw or "")
            page.word_count = words
            page.code_word_count = code_words
            # a number in the front matter is the author knowing better
            fixed = front_matter(page, "reading_time")
            if isinstance(fixed, int) and not isinstance(fixed, bool) and fixed > 0:
                minutes = fixed
            page.reading_time = minutes
