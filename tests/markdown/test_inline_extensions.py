from __future__ import annotations

import pytest

from inkstone.markdown import Abbreviation, Link, Markdown, Strikethrough


def converter(*names: str, **options):
    md = Markdown(extensions=list(names), heading_ids=False, **options)

    def convert(source: str) -> str:
        html = md.convert(source)
        assert html.startswith("<p>") and html.endswith("</p>\n")
        return html[3:-5]

    return convert


strike = converter("strikethrough")
marks = converter("strikethrough", "mark", "sub", "sup")
autolink = converter("autolink")
smart = converter(smart=True)
abbr = converter("abbr")
plain = converter()

EN, EM = "\u2013", "\u2014"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("~~Hi~~ Hello, world!", "<del>Hi</del> Hello, world!"),
        ("~one tilde~ works too", "<del>one tilde</del> works too"),
        ("This ~~has a\nnew line~~.", "This <del>has a\nnew line</del>."),
        ("but ~~~three~~~ is not", "but ~~~three~~~ is not"),
        ("~~ spaced ~~", "~~ spaced ~~"),
        ("a ~~mismatched~ pair", "a ~~mismatched~ pair"),
        (
            "~~*nested* **markup**~~",
            "<del><em>nested</em> <strong>markup</strong></del>",
        ),
        ("*~~inside~~ emphasis*", "<em><del>inside</del> emphasis</em>"),
        ("in~~tra~~word", "in<del>tra</del>word"),
        ("~~[link](/url)~~", '<del><a href="/url">link</a></del>'),
        ("`~~code~~`", "<code>~~code~~</code>"),
        ("\\~~escaped~~", "~~escaped~~"),
        ("~~unclosed", "~~unclosed"),
    ],
)
def test_strikethrough(source, expected):
    assert strike(source) == expected


def test_strikethrough_node():
    doc = Markdown(extensions=["strikethrough"]).parse("a ~~b~~ c")
    kinds = [type(node) for node in doc.children[0].children]
    assert kinds[1] is Strikethrough


def test_strikethrough_can_be_switched_off():
    assert plain("~~Hi~~ there") == "~~Hi~~ there"


def test_tilde_fences_still_work_with_strikethrough():
    md = Markdown(extensions=["strikethrough"])
    assert md.convert("~~~\ncode\n~~~\n") == "<pre><code>code\n</code></pre>\n"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("==marked==", "<mark>marked</mark>"),
        ("H~2~O", "H<sub>2</sub>O"),
        ("x^2^ + y^2^", "x<sup>2</sup> + y<sup>2</sup>"),
        ("~~gone~~ but ~sub~", "<del>gone</del> but <sub>sub</sub>"),
        ("==*both*==", "<mark><em>both</em></mark>"),
        ("a = b == c", "a = b == c"),
        ("=single=", "=single="),
        ("2 ^ 3 ^ 4", "2 ^ 3 ^ 4"),
        ("==a== and ===b===", "<mark>a</mark> and ===b==="),
    ],
)
def test_mark_sub_sup(source, expected):
    assert marks(source) == expected


def test_marks_are_opt_in():
    default = Markdown(heading_ids=False)
    assert default.convert("==x== y^2^") == "<p>==x== y^2^</p>\n"
    # without "sub" the single tilde belongs to strikethrough
    assert default.convert("H~2~O") == "<p>H<del>2</del>O</p>\n"


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "www.commonmark.org",
            '<a href="http://www.commonmark.org">www.commonmark.org</a>',
        ),
        (
            "Visit www.commonmark.org/help for more.",
            'Visit <a href="http://www.commonmark.org/help">www.commonmark.org/help</a>'
            " for more.",
        ),
        (
            "Visit www.commonmark.org.",
            'Visit <a href="http://www.commonmark.org">www.commonmark.org</a>.',
        ),
        (
            "http://commonmark.org",
            '<a href="http://commonmark.org">http://commonmark.org</a>',
        ),
        (
            "(Visit https://encrypted.google.com/search?q=Markup+(business))",
            '(Visit <a href="https://encrypted.google.com/search?q=Markup+(business)">'
            "https://encrypted.google.com/search?q=Markup+(business)</a>)",
        ),
        (
            "www.google.com/search?q=(business))+ok",
            '<a href="http://www.google.com/search?q=(business))+ok">'
            "www.google.com/search?q=(business))+ok</a>",
        ),
        (
            "www.google.com/search?q=commonmark&hl=en",
            '<a href="http://www.google.com/search?q=commonmark&amp;hl=en">'
            "www.google.com/search?q=commonmark&amp;hl=en</a>",
        ),
        (
            "www.google.com/search?q=commonmark&hl;",
            '<a href="http://www.google.com/search?q=commonmark">'
            "www.google.com/search?q=commonmark</a>&amp;hl;",
        ),
        (
            "www.commonmark.org/he<lp",
            '<a href="http://www.commonmark.org/he">www.commonmark.org/he</a>&lt;lp',
        ),
        (
            "ftp://files.example.org/pub!",
            '<a href="ftp://files.example.org/pub">ftp://files.example.org/pub</a>!',
        ),
        (
            "see http://example.com/a_b_c?x=*1*&y=2 now",
            'see <a href="http://example.com/a_b_c?x=*1*&amp;y=2">'
            "http://example.com/a_b_c?x=*1*&amp;y=2</a> now",
        ),
        (
            "*http://example.com/in_emphasis*",
            '<em><a href="http://example.com/in_emphasis">'
            "http://example.com/in_emphasis</a></em>",
        ),
        (
            "http://localhost:8000/x",
            '<a href="http://localhost:8000/x">http://localhost:8000/x</a>',
        ),
    ],
)
def test_bare_urls(source, expected):
    assert autolink(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "www. nothing",
        "xwww.example.com",
        "ahttp://example.com",
        "http://",
        "http://under_score.com",
        "www.x_y.com",
        "`www.example.com`",
        "<span>ok</span> www",
        "just words: here",
    ],
)
def test_not_a_bare_url(source):
    assert "<a " not in autolink(source)


def test_bare_url_inside_link_text_is_not_linked_again():
    html = autolink("[go to http://inner.example now](http://outer.example)")
    assert html == '<a href="http://outer.example">go to http://inner.example now</a>'


def test_bare_url_in_image_alt_is_plain_text():
    html = autolink("![see www.example.com](pic.png)")
    assert html == '<img src="pic.png" alt="see www.example.com" />'


def test_angle_autolinks_are_unaffected():
    html = autolink("<http://example.com/a>")
    assert html == '<a href="http://example.com/a">http://example.com/a</a>'


@pytest.mark.parametrize(
    "source, expected",
    [
        ("foo@bar.baz", '<a href="mailto:foo@bar.baz">foo@bar.baz</a>'),
        (
            "hello@mail+xyz.example isn't valid, but hello+xyz@mail.example is.",
            "hello@mail+xyz.example isn't valid, but "
            '<a href="mailto:hello+xyz@mail.example">hello+xyz@mail.example</a> is.',
        ),
        ("a.b-c_d@a.b", '<a href="mailto:a.b-c_d@a.b">a.b-c_d@a.b</a>'),
        ("a.b-c_d@a.b.", '<a href="mailto:a.b-c_d@a.b">a.b-c_d@a.b</a>.'),
        ("a.b-c_d@a.b-", "a.b-c_d@a.b-"),
        ("a.b-c_d@a.b_", "a.b-c_d@a.b_"),
        ("no@tld", "no@tld"),
        ("`code@example.com`", "<code>code@example.com</code>"),
        (
            "**strong@example.com**",
            '<strong><a href="mailto:strong@example.com">strong@example.com</a>'
            "</strong>",
        ),
    ],
)
def test_bare_email_addresses(source, expected):
    assert autolink(source) == expected


def test_email_inside_a_link_is_left_alone():
    html = autolink("[write to me@example.com](/contact)")
    assert html == '<a href="/contact">write to me@example.com</a>'


def test_bare_links_are_flagged_on_the_node():
    doc = Markdown(extensions=["autolink"]).parse("www.example.com and [x](/y)")
    links = list(doc.find_all(Link))
    assert [link.bare for link in links] == [True, False]


def test_autolink_can_be_switched_off():
    assert plain("www.example.com me@example.com") == "www.example.com me@example.com"


@pytest.mark.parametrize(
    "source, expected",
    [
        ('"Hello," said the spider.', "“Hello,” said the spider."),
        ("'Shelob' is my name.", "‘Shelob’ is my name."),
        ("'A', 'B', and 'C' are letters.", "‘A’, ‘B’, and ‘C’ are letters."),
        (
            "'Oak,' 'elm,' and 'beech' are names of trees.",
            "‘Oak,’ ‘elm,’ and ‘beech’ are names of trees.",
        ),
        ("'He said, \"I want to go.\"'", "‘He said, “I want to go.”’"),
        ("Were you alive in the 70's?", "Were you alive in the 70’s?"),
        (
            "Here is some quoted '`code`' and a \"[link](url)\".",
            'Here is some quoted ‘<code>code</code>’ and a “<a href="url">link</a>”.',
        ),
        ("'tis the season to be 'jolly'", "’tis the season to be ‘jolly’"),
        (
            "'We'll use Jane's boat and John's truck,' Jenna said.",
            "‘We’ll use Jane’s boat and John’s truck,’ Jenna said.",
        ),
        ('"Second paragraph by same speaker', "“Second paragraph by same speaker"),
        ('\\"This is not smart.\\"', "&quot;This is not smart.&quot;"),
        ("Some dashes:  em---em\nen--en", f"Some dashes:  em{EM}em\nen{EN}en"),
        (
            "one-\ntwo--\nthree---\nfour----\nfive-----",
            f"one-\ntwo{EN}\nthree{EM}\nfour{EN}{EN}\nfive{EM}{EN}",
        ),
        (
            "six------\nseven-------\neight--------",
            f"six{EM}{EM}\nseven{EM}{EN}{EN}\neight{EN}{EN}{EN}{EN}",
        ),
        ("Ellipses...and...and....", "Ellipses…and…and…."),
        ("No ellipses\\.\\.\\.", "No ellipses..."),
        ('`"code"` -- stays', f"<code>&quot;code&quot;</code> {EN} stays"),
    ],
)
def test_smart_punctuation(source, expected):
    assert smart(source) == expected


def test_smart_is_off_by_default():
    assert plain("\"quote\" -- it's...") == "&quot;quote&quot; -- it's..."


def test_smart_as_extension_name_equals_the_option():
    by_name = Markdown(extensions=["smart"])
    by_flag = Markdown(extensions=[], smart=True)
    assert by_name.smart and by_flag.smart
    assert by_name.convert('"a" -- b') == by_flag.convert('"a" -- b')
    assert by_flag.extension_names == ["smart"]


def test_smart_leaves_code_blocks_and_html_alone():
    md = Markdown(extensions=[], smart=True)
    assert md.convert('    a -- "b"\n') == (
        "<pre><code>a -- &quot;b&quot;\n</code></pre>\n"
    )
    assert md.convert('<div title="x--y">\n') == '<div title="x--y">\n'
    assert md.convert('a <span title="x--y">b</span>\n') == (
        '<p>a <span title="x--y">b</span></p>\n'
    )


def test_abbreviations():
    html = Markdown(extensions=["abbr"]).convert(
        "The HTML spec is maintained by the W3C.\n\n"
        "*[HTML]: Hyper Text Markup Language\n"
        "*[W3C]:  World Wide Web Consortium\n"
    )
    assert html == (
        '<p>The <abbr title="Hyper Text Markup Language">HTML</abbr> spec is '
        'maintained by the <abbr title="World Wide Web Consortium">W3C</abbr>.</p>\n'
    )


def test_abbreviation_matches_whole_words_only():
    source = "HTML, XHTML, HTMLish and (HTML).\n\n*[HTML]: Hyper Text Markup Language"
    html = abbr(source)
    assert html.count("<abbr") == 2
    assert "XHTML," in html and "HTMLish" in html


def test_longer_abbreviation_wins():
    source = "HTML5 and HTML\n\n*[HTML]: markup\n*[HTML5]: newer markup"
    assert abbr(source) == (
        '<abbr title="newer markup">HTML5</abbr> and <abbr title="markup">HTML</abbr>'
    )


def test_abbreviation_not_applied_in_code_but_applied_in_links():
    source = "`API` and [the API](/docs)\n\n*[API]: Application Programming Interface"
    html = abbr(source)
    assert "<code>API</code>" in html
    assert '<a href="/docs">the <abbr title=' in html


def test_abbreviation_definition_can_come_first_and_leaves_no_trace():
    md = Markdown(extensions=["abbr"])
    doc = md.parse("*[CSS]: Cascading Style Sheets\n\nCSS rules")
    assert len(doc.children) == 1
    assert doc.abbreviations == {"CSS": "Cascading Style Sheets"}
    assert isinstance(doc.children[0].children[0], Abbreviation)


def test_abbreviation_definition_ends_a_paragraph():
    md = Markdown(extensions=["abbr"])
    html = md.convert("first\n*[ABC]: Alpha Beta\nsecond ABC\n")
    assert html == '<p>first</p>\n<p>second <abbr title="Alpha Beta">ABC</abbr></p>\n'


def test_abbreviation_with_special_characters():
    source = (
        "Use C++ & R&D daily\n\n"
        "*[C++]: a language\n*[R&D]: Research <and> Development"
    )
    html = abbr(source)
    assert '<abbr title="a language">C++</abbr>' in html
    assert '<abbr title="Research &lt;and&gt; Development">R&amp;D</abbr>' in html


def test_abbr_is_opt_in():
    html = Markdown().convert("HTML\n\n*[HTML]: Hyper Text Markup Language\n")
    assert "<abbr" not in html
