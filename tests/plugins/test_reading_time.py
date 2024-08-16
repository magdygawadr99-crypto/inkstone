from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.plugins.builtin import _text
from inkstone.plugins.builtin.reading_time import ReadingTime

from .helpers import make_page, make_site

CODE = "```python\n" + "value = compute(first, second)\n" * 50 + "```\n"


def words(count):
    return " ".join(["word"] * count)


def measure(config, raw, settings=None, **attrs):
    page = make_page("Post", source_path="posts/post.md", raw=raw, **attrs)
    ReadingTime(config, settings or {}).content_loaded(make_site(config, [page]))
    return page


@pytest.mark.parametrize(
    "count, minutes",
    [(0, 1), (1, 1), (220, 1), (221, 2), (440, 2), (441, 3), (2200, 10)],
)
def test_minutes_are_rounded_up_and_never_zero(config, count, minutes):
    page = measure(config, words(count))
    assert page.word_count == count
    assert page.reading_time == minutes


def test_words_per_minute_setting(config):
    page = measure(config, words(600), {"words_per_minute": 100})
    assert page.reading_time == 6


def test_markup_is_not_counted(config):
    raw = (
        "# A *title*\n\n"
        "Some [linked text](https://example.com/a/very/long/path?with=query) and "
        "![an image](photo.jpg \"Title\").\n\n"
        "<!-- a comment with many many words -->\n"
        '<div class="box">inside</div>\n\n'
        '{{< figure src="a.png" alt="x" >}}\n\n'
        "[ref]: https://example.com/somewhere\n"
    )
    page = measure(config, raw)
    # A title / Some linked text and an image / inside
    assert page.word_count == 9


def test_code_blocks_count_by_default(config):
    page = measure(config, words(100) + "\n\n" + CODE)
    assert page.code_word_count == 200
    assert page.word_count == 300
    assert page.reading_time == 2


def test_code_blocks_can_be_excluded(config):
    page = measure(config, words(100) + "\n\n" + CODE, {"code_blocks": "exclude"})
    assert page.word_count == 100
    assert page.code_word_count == 200
    assert page.reading_time == 1


def test_code_blocks_counted_separately(config):
    settings = {"code_blocks": "separate", "code_words_per_minute": 50}
    page = measure(config, words(100) + "\n\n" + CODE, settings)
    assert page.word_count == 100
    assert page.code_word_count == 200
    # 100 / 220 + 200 / 50 minutes
    assert page.reading_time == 5


def test_cjk_text_is_counted_by_character(config):
    page = measure(config, "日本語の文章 and three words")
    assert page.word_count == 6 + 3
    long = measure(config, "文" * 900)
    assert long.reading_time == 2


def test_front_matter_wins_over_the_estimate(config):
    page = measure(config, words(5000), meta={"reading_time": 3})
    assert page.reading_time == 3
    assert page.word_count == 5000
    ignored = measure(config, words(5000), meta={"reading_time": "soon"})
    assert ignored.reading_time == 23


def test_generated_pages_are_skipped(config):
    virtual = make_page("Generated", "/generated/", raw="")
    page = make_page("Real", source_path="real.md", raw=words(10))
    ReadingTime(config, {}).content_loaded(make_site(config, [virtual, page]))
    assert page.word_count == 10
    assert not hasattr(virtual, "code_word_count")


@pytest.mark.parametrize(
    "settings",
    [
        {"words_per_minute": 0},
        {"words_per_minute": "fast"},
        {"words_per_minute": 220.5},
        {"code_blocks": "sometimes"},
        {"code_words_per_minute": -5},
    ],
)
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.reading_time\]"):
        ReadingTime(config, settings)


def test_split_code_separates_fences():
    prose, code = _text.split_code("a\n```\nx = 1\n```\nb\n~~~~\ny\n~~~~\nc\n")
    assert prose.split() == ["a", "b", "c"]
    assert code.split() == ["x", "=", "1", "y"]


def test_split_code_edge_cases():
    assert _text.split_code("no code here") == ("no code here", "")
    prose, code = _text.split_code("before\n```\nunclosed runs to the end")
    assert prose.strip() == "before"
    assert "unclosed" in code
    # backticks in the info string: that line is inline code, not a fence
    prose, code = _text.split_code("``` not `a` fence\ntext\n")
    assert code == "" and "text" in prose
    # a longer fence is not closed by a shorter one
    prose, code = _text.split_code("````\n```\ninner\n```\n````\nafter")
    assert "inner" in code and prose.strip() == "after"


def test_count_words_handles_apostrophes_and_hyphens():
    assert _text.count_words("don't over-think it") == (3, 0)
    assert _text.count_words("") == (0, 0)
    assert _text.count_words("... --- !!!") == (0, 0)
