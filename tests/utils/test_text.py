from __future__ import annotations

import pytest

from inkstone.utils import text
from inkstone.utils.text import slugify


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Hello, World!", "hello-world"),
        ("  padded   title  ", "padded-title"),
        ("already-a-slug", "already-a-slug"),
        ("snake_case_title", "snake-case-title"),
        ("MiXeD CaSe", "mixed-case"),
        ("dots.and/slashes\\here", "dots-and-slashes-here"),
        ("multiple---dashes   and spaces", "multiple-dashes-and-spaces"),
        ("trailing punctuation?!", "trailing-punctuation"),
        ("Version 2.0 released", "version-2-0-released"),
        ("don't stop", "dont-stop"),
        ("Rock ’n’ Roll", "rock-n-roll"),
        ("Crème brûlée", "creme-brulee"),
        ("Ünïcödé Straße", "unicode-strasse"),
        ("Ærøskøbing & Þingvellir", "aeroskobing-and-thingvellir"),
        ("Łódź, Đakovo", "lodz-dakovo"),
        ("Привет, мир", "privet-mir"),
        ("Щёлково подъезд", "shchyolkovo-podezd"),
        ("Київ і Їжак", "kiyiv-i-yizhak"),
        ("Καλημέρα κόσμε", "kalimera-kosme"),
        ("Ελλάδα", "ellada"),
        ("Tom & Jerry", "tom-and-jerry"),
        ("C++ primer", "c-plus-plus-primer"),
        ("100% pure", "100-percent-pure"),
        ("me@example", "me-at-example"),
        ("€5 or $6 or £4", "euro-5-or-dollar-6-or-pound-4"),
        ("ｆｕｌｌｗｉｄｔｈ", "fullwidth"),
        ("日本語のタイトル", ""),
        ("日本語 mixed title", "mixed-title"),
        ("", ""),
        ("!!!", ""),
        (2024, "2024"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Crème brûlée", "crème-brûlée"),
        ("Привет, мир", "привет-мир"),
        ("日本語 のタイトル", "日本語-のタイトル"),
        ("Tom & Jerry", "tom-jerry"),
        ("snake_case", "snake-case"),
        ("ｆｕｌｌ width", "full-width"),
    ],
)
def test_slugify_allow_unicode(title, expected):
    assert slugify(title, allow_unicode=True) == expected


def test_slugify_options():
    assert slugify("Hello World", sep="_") == "hello_world"
    assert slugify("Hello World", sep="") == "helloworld"
    assert slugify("Hello World", lowercase=False) == "Hello-World"
    assert slugify("Ärger im Büro", lowercase=False) == "Arger-im-Buro"


@pytest.mark.parametrize(
    ("max_length", "expected"),
    [
        (100, "the-quick-brown-fox"),
        (19, "the-quick-brown-fox"),
        (18, "the-quick-brown"),
        (15, "the-quick-brown"),
        (10, "the-quick"),
        (9, "the-quick"),
        (4, "the"),
        (3, "the"),
        (2, "th"),
        (0, ""),
    ],
)
def test_slugify_max_length_cuts_at_word_boundaries(max_length, expected):
    assert slugify("The quick brown fox", max_length=max_length) == expected


def test_slugify_max_length_with_one_long_word():
    assert slugify("Supercalifragilistic", max_length=5) == "super"
    assert slugify("a b c", sep="--", max_length=4) == "a--b"


def test_transliterate_keeps_what_it_does_not_know():
    assert text.transliterate("naïve café №5 日本") == "naive cafe No5 日本"
    assert text.transliterate("ЩИ Ёж") == "ShchI Yozh"


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ("<p>one</p><p>two</p>", "one two"),
        ("line<br>break<br/>again", "line break again"),
        ("<ul><li>a</li><li>b</li></ul>", "a b"),
        ("in<b>line</b> tags join", "inline tags join"),
        ("Fish &amp; chips &lt;3 &#233;t&eacute; &#x263a;", "Fish & chips <3 été ☺"),
        (
            "<script>alert('x')</script>visible<style>p { color: red }</style>",
            "visible",
        ),
        ("before<!-- a <b>comment</b> -->after", "beforeafter"),
        ('<a href="x" title="a > b">link</a>', "link"),
        ("<img src='a.png' alt='x'>", ""),
        ("2 < 3 and 5 > 4", "2 < 3 and 5 > 4"),
        ("  lots   of\n\n whitespace ", "lots of whitespace"),
        ("<!DOCTYPE html><h1>Title</h1>", "Title"),
        ("", ""),
    ],
)
def test_strip_html(markup, expected):
    assert text.strip_html(markup) == expected


def test_strip_html_can_keep_whitespace():
    assert text.strip_html("<i>a</i>  b\n c", collapse=False) == "a  b\n c"


def test_truncate_words():
    assert text.truncate_words("one two three four", 2) == "one two…"
    assert text.truncate_words("one two", 2) == "one two"
    assert text.truncate_words("  short  ", 5) == "  short  "
    assert text.truncate_words("Hello, world, again", 2) == "Hello, world…"
    assert text.truncate_words("a b c", 1, suffix=" [...]") == "a [...]"
    assert text.truncate_words("a b c", 0) == "…"


@pytest.mark.parametrize(
    ("value", "length", "expected"),
    [
        ("short", 10, "short"),
        ("exactly ten", 11, "exactly ten"),
        ("The quick brown fox jumps", 16, "The quick brown…"),
        ("The quick brown fox jumps", 18, "The quick brown…"),
        ("The quick brown fox jumps", 20, "The quick brown fox…"),
        ("Supercalifragilistic", 8, "Superca…"),
        ("Hello, world and more", 8, "Hello…"),
        ("anything", 1, "…"),
        ("anything", 0, "…"),
    ],
)
def test_truncate_chars(value, length, expected):
    result = text.truncate_chars(value, length)
    assert result == expected
    assert len(result) <= max(length, 1)


def test_truncate_chars_custom_suffix():
    fox = "The quick brown fox"
    assert text.truncate_chars(fox, 12, suffix="...") == "The quick..."
    assert text.truncate_chars(fox, 9, suffix="") == "The quick"


@pytest.mark.parametrize(
    ("markup", "length", "expected"),
    [
        ("<p>Hello world</p>", 20, "<p>Hello world</p>"),
        ("<p>Hello world</p>", 6, "<p>Hello…</p>"),
        ("<p>Hello <b>big world</b> out there</p>", 10, "<p>Hello <b>big…</b></p>"),
        ("Fish &amp; chips forever", 8, "Fish &amp;…"),
        ("Fish &amp; chips forever", 9, "Fish &amp; c…"),
        (
            '<a href="/x?a=1&amp;b=2">a long link text</a>',
            7,
            '<a href="/x?a=1&amp;b=2">a long…</a>',
        ),
        ("<p>one<br>two three</p>", 5, "<p>one<br>t…</p>"),
        (
            "<ul><li>first</li><li>second item</li></ul>",
            9,
            "<ul><li>first</li><li>sec…</li></ul>",
        ),
        (
            "<p>done.</p><!-- trailing comment -->",
            6,
            "<p>done.</p><!-- trailing comment -->",
        ),
        ("<p>fits</p>   ", 5, "<p>fits</p>   "),
        ("<img src='a.png'/>caption text", 8, "<img src='a.png'/>caption…"),
    ],
)
def test_truncate_chars_html(markup, length, expected):
    assert text.truncate_chars(markup, length, html=True) == expected


@pytest.mark.parametrize(
    ("markup", "count", "expected"),
    [
        ("<p>one two three</p>", 5, "<p>one two three</p>"),
        ("<p>one two three</p>", 2, "<p>one two…</p>"),
        (
            "<p>one</p><p>two <em>three four</em></p>",
            3,
            "<p>one</p><p>two <em>three…</em></p>",
        ),
        ("<p>R&amp;D costs money</p>", 2, "<p>R&amp;D costs…</p>"),
        ("<b>a</b> <i>b</i> c", 2, "<b>a</b> <i>b</i>…"),
    ],
)
def test_truncate_words_html(markup, count, expected):
    assert text.truncate_words(markup, count, html=True) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", 0),
        ("   \n ", 0),
        ("one", 1),
        ("Hello, world!", 2),
        ("don't split contractions", 3),
        ("well-known hyphenated words", 3),
        ("numbers like 42 and 3.14 count", 7),
        ("snake_case stays together", 3),
        ("こんにちは", 5),
        ("日本語 and English mixed", 6),
        ("中文English没有空格", 7),
        ("한국어 단어 세 개", 4),
        ("— … !!", 0),
    ],
)
def test_word_count(value, expected):
    assert text.word_count(value) == expected


def test_reading_time():
    assert text.reading_time("") == 0
    assert text.reading_time("just a few words") == 1
    assert text.reading_time("word " * 220) == 1
    assert text.reading_time("word " * 221) == 2
    assert text.reading_time("word " * 1000, wpm=100) == 10
    assert text.reading_time("字" * 900) == 2
    assert text.reading_time("字" * 450 + " word" * 220) == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("the lord of the rings", "The Lord of the Rings"),
        ("a tale of two cities", "A Tale of Two Cities"),
        ("what is this for", "What Is This For"),
        ("OF MICE AND MEN", "Of Mice and Men"),
        ("Of Mice And Men", "Of Mice and Men"),
        ("the iPhone and the HTML spec", "The iPhone and the HTML Spec"),
        (
            "visit example.com or mail me@example.org",
            "Visit example.com or Mail me@example.org",
        ),
        ("rust: the good parts", "Rust: The Good Parts"),
        ("why? a short answer", "Why? A Short Answer"),
        ("a state-of-the-art build tool", "A State-of-the-Art Build Tool"),
        ("how to sign-in", "How to Sign-In"),
        ('"the quoted" title', '"The Quoted" Title'),
        ("don't panic (a guide)", "Don't Panic (a Guide)"),
        ("apples vs. oranges", "Apples vs. Oranges"),
        ("  extra   spaces  ", "Extra Spaces"),
        ("3 ways to use src/main.py", "3 Ways to Use src/main.py"),
        ("", ""),
    ],
)
def test_titlecase(value, expected):
    assert text.titlecase(value) == expected


@pytest.mark.parametrize(
    ("count", "word", "expected"),
    [
        (0, "page", "0 pages"),
        (1, "page", "1 page"),
        (2, "page", "2 pages"),
        (3, "category", "3 categories"),
        (2, "day", "2 days"),
        (2, "box", "2 boxes"),
        (4, "match", "4 matches"),
        (2, "dish", "2 dishes"),
        (5, "class", "5 classes"),
        (2, "Entry", "2 Entries"),
        (-1, "error", "-1 errors"),
    ],
)
def test_pluralize(count, word, expected):
    assert text.pluralize(count, word) == expected


def test_pluralize_explicit_plural_and_bare_word():
    assert text.pluralize(2, "person", "people") == "2 people"
    assert text.pluralize(1, "person", "people") == "1 person"
    assert text.pluralize(3, "file", show_count=False) == "files"
    assert text.pluralize(1, "file", show_count=False) == "file"


def test_natural_sort_key():
    names = ["page10.md", "page2.md", "Page1.md", "page.md", "page02.md", "10", "9"]
    assert sorted(names, key=text.natural_sort_key) == [
        "9",
        "10",
        "Page1.md",
        "page2.md",
        "page02.md",
        "page10.md",
        "page.md",
    ]
    assert sorted(["v1.10", "v1.9", "v1.2b", "v1.2a"], key=text.natural_sort_key) == [
        "v1.2a",
        "v1.2b",
        "v1.9",
        "v1.10",
    ]


def test_dedent_block():
    block = """

        first line
          indented more

        last line
    """
    assert text.dedent_block(block) == "first line\n  indented more\n\nlast line\n"
    assert text.dedent_block("  a  \n  b\t\n") == "a\nb\n"
    assert text.dedent_block("") == ""
    assert text.dedent_block("  \n\n  ") == ""
    assert text.dedent_block("no indent") == "no indent\n"


def test_wrap():
    paragraph = "The quick brown fox jumps over the lazy dog. " * 3
    wrapped = text.wrap(paragraph, 30)
    assert all(len(line) <= 30 for line in wrapped.split("\n"))
    assert wrapped.split() == paragraph.split()
    assert text.wrap("one two\nthree\n\n\nnext   paragraph", 80) == (
        "one two three\n\nnext paragraph"
    )
    assert text.wrap("aaa bbb ccc", 7, indent="> ") == "> aaa\n> bbb\n> ccc"
    assert text.wrap("aaa bbb ccc", 8, indent="- ", subsequent_indent="  ") == (
        "- aaa\n  bbb\n  ccc"
    )
    assert text.wrap("https://example.com/a-very-long-url/that-cannot-break", 20) == (
        "https://example.com/a-very-long-url/that-cannot-break"
    )


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 B"),
        (1, "1 B"),
        (1023, "1023 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (10 * 1024, "10 KB"),
        (1024 * 1024 - 1, "1.0 MB"),
        (5 * 1024**2, "5.0 MB"),
        (123 * 1024**2, "123 MB"),
        (3 * 1024**3, "3.0 GB"),
        (2 * 1024**4, "2.0 TB"),
        (5000 * 1024**4, "5000 TB"),
        (-2048, "-2.0 KB"),
    ],
)
def test_humanize_bytes(size, expected):
    assert text.humanize_bytes(size) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 ms"),
        (0.0002, "<1 ms"),
        (0.004, "4 ms"),
        (0.85, "850 ms"),
        (0.9999, "1.00 s"),
        (1.5, "1.50 s"),
        (9.999, "10.0 s"),
        (12.34, "12.3 s"),
        (59.99, "1 min"),
        (60, "1 min"),
        (125, "2 min 5 s"),
        (3600, "1 h"),
        (3725, "1 h 2 min"),
        (-1.5, "-1.50 s"),
    ],
)
def test_humanize_duration(seconds, expected):
    assert text.humanize_duration(seconds) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (0, "0th"),
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (10, "10th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (23, "23rd"),
        (101, "101st"),
        (111, "111th"),
        (112, "112th"),
        (1003, "1003rd"),
        (-1, "-1st"),
    ],
)
def test_ordinal(number, expected):
    assert text.ordinal(number) == expected
