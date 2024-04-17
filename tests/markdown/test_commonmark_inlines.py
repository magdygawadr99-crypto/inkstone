from __future__ import annotations

import pytest

from inkstone.markdown import Markdown

# Second half of the hand-copied CommonMark examples: everything that happens
# inside a paragraph. Sources are given without the final newline.
_core = Markdown(extensions=[], heading_ids=False)


def to_html(source: str) -> str:
    return _core.convert(source)


def paragraph(source: str) -> str:
    html = to_html(source)
    assert html.startswith("<p>") and html.endswith("</p>\n")
    return html[3:-5]


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "\\!\\\"\\#\\$\\%\\&\\'\\(\\)\\*\\+\\,\\-\\.\\/\\:\\;\\<\\=\\>\\?\\@"
            "\\[\\\\\\]\\^\\_\\`\\{\\|\\}\\~",
            "!&quot;#$%&amp;'()*+,-./:;&lt;=&gt;?@[\\]^_`{|}~",
        ),
        ("\\\t\\A\\a\\ \\3\\φ\\«", "\\\t\\A\\a\\ \\3\\φ\\«"),
        (
            "\\*not emphasized*\n\\<br/> not a tag\n\\[not a link](/foo)\n"
            "\\`not code`\n1\\. not a list\n\\* not a list\n\\# not a heading\n"
            '\\[foo]: /url "not a reference"\n\\&ouml; not a character entity',
            "*not emphasized*\n&lt;br/&gt; not a tag\n[not a link](/foo)\n"
            "`not code`\n1. not a list\n* not a list\n# not a heading\n"
            "[foo]: /url &quot;not a reference&quot;\n"
            "&amp;ouml; not a character entity",
        ),
        ("\\\\*emphasis*", "\\<em>emphasis</em>"),
        ("foo\\\nbar", "foo<br />\nbar"),
        ("`` \\[\\` ``", "<code>\\[\\`</code>"),
        (
            "<https://example.com?find=\\*>",
            '<a href="https://example.com?find=%5C*">https://example.com?find=\\*</a>',
        ),
        ('[foo](/bar\\* "ti\\*tle")', '<a href="/bar*" title="ti*tle">foo</a>'),
        (
            '[foo]\n\n[foo]: /bar\\* "ti\\*tle"',
            '<a href="/bar*" title="ti*tle">foo</a>',
        ),
    ],
)
def test_backslash_escapes(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("    \\[\\]\n", "<pre><code>\\[\\]\n</code></pre>\n"),
        ("~~~\n\\[\\]\n~~~\n", "<pre><code>\\[\\]\n</code></pre>\n"),
        ('<a href="/bar\\/)">\n', '<a href="/bar\\/)">\n'),
        (
            "``` foo\\+bar\nfoo\n```\n",
            '<pre><code class="language-foo+bar">foo\n</code></pre>\n',
        ),
    ],
)
def test_backslashes_outside_paragraphs(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "&nbsp; &amp; &copy; &AElig; &Dcaron;\n&frac34; &HilbertSpace; "
            "&DifferentialD;\n&ClockwiseContourIntegral; &ngE;",
            "\u00a0 &amp; © Æ Ď\n¾ ℋ ⅆ\n∲ ≧̸",
        ),
        ("&#35; &#1234; &#992; &#0;", "# Ӓ Ϡ \ufffd"),
        ("&#X22; &#XD06; &#xcab;", "&quot; ആ ಫ"),
        (
            "&nbsp &x; &#; &#x;\n&#87654321;\n&#abcdef0;\n&ThisIsNotDefined; &hi?;",
            "&amp;nbsp &amp;x; &amp;#; &amp;#x;\n&amp;#87654321;\n&amp;#abcdef0;\n"
            "&amp;ThisIsNotDefined; &amp;hi?;",
        ),
        ("&copy", "&amp;copy"),
        ("&MadeUpEntity;", "&amp;MadeUpEntity;"),
        (
            '[foo](/f&ouml;&ouml; "f&ouml;&ouml;")',
            '<a href="/f%C3%B6%C3%B6" title="föö">foo</a>',
        ),
        (
            '[foo]\n\n[foo]: /f&ouml;&ouml; "f&ouml;&ouml;"',
            '<a href="/f%C3%B6%C3%B6" title="föö">foo</a>',
        ),
        ("`f&ouml;&ouml;`", "<code>f&amp;ouml;&amp;ouml;</code>"),
        ("&#42;foo&#42;\n*foo*", "*foo*\n<em>foo</em>"),
        ("foo&#10;&#10;bar", "foo\n\nbar"),
        ("&#9;foo", "\tfoo"),
        ("[a](url &quot;tit&quot;)", "[a](url &quot;tit&quot;)"),
    ],
)
def test_character_references(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('<a href="&ouml;&ouml;.html">\n', '<a href="&ouml;&ouml;.html">\n'),
        (
            "``` f&ouml;&ouml;\nfoo\n```\n",
            '<pre><code class="language-föö">foo\n</code></pre>\n',
        ),
        ("    f&ouml;f&ouml;\n", "<pre><code>f&amp;ouml;f&amp;ouml;\n</code></pre>\n"),
        ("&#42; foo\n\n* foo\n", "<p>* foo</p>\n<ul>\n<li>foo</li>\n</ul>\n"),
        ("- `one\n- two`\n", "<ul>\n<li>`one</li>\n<li>two`</li>\n</ul>\n"),
    ],
)
def test_references_and_code_do_not_cross_block_structure(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("`foo`", "<code>foo</code>"),
        ("`` foo ` bar ``", "<code>foo ` bar</code>"),
        ("` `` `", "<code>``</code>"),
        ("`  ``  `", "<code> `` </code>"),
        ("` a`", "<code> a</code>"),
        ("`\u00a0b\u00a0`", "<code>\u00a0b\u00a0</code>"),
        ("` `\n`  `", "<code> </code>\n<code>  </code>"),
        ("``\nfoo\nbar  \nbaz\n``", "<code>foo bar   baz</code>"),
        ("``\nfoo \n``", "<code>foo </code>"),
        ("`foo   bar \nbaz`", "<code>foo   bar  baz</code>"),
        ("`foo\\`bar`", "<code>foo\\</code>bar`"),
        ("``foo`bar``", "<code>foo`bar</code>"),
        ("` foo `` bar `", "<code>foo `` bar</code>"),
        ("*foo`*`", "*foo<code>*</code>"),
        ("[not a `link](/foo`)", "[not a <code>link](/foo</code>)"),
        ('`<a href="`">`', "<code>&lt;a href=&quot;</code>&quot;&gt;`"),
        ('<a href="`">`', '<a href="`">`'),
        ("`<https://foo.bar.`baz>`", "<code>&lt;https://foo.bar.</code>baz&gt;`"),
        (
            "<https://foo.bar.`baz>`",
            '<a href="https://foo.bar.%60baz">https://foo.bar.`baz</a>`',
        ),
        ("```foo``", "```foo``"),
        ("`foo", "`foo"),
        ("`foo``bar``", "`foo<code>bar</code>"),
    ],
)
def test_code_spans(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("*foo bar*", "<em>foo bar</em>"),
        ("a * foo bar*", "a * foo bar*"),
        ('a*"foo"*', "a*&quot;foo&quot;*"),
        ("*\u00a0a\u00a0*", "*\u00a0a\u00a0*"),
        ("*$*alpha.", "*$*alpha."),
        ("*£*bravo.", "*£*bravo."),
        ("*€*charlie.", "*€*charlie."),
        ("foo*bar*", "foo<em>bar</em>"),
        ("5*6*78", "5<em>6</em>78"),
        ("_foo bar_", "<em>foo bar</em>"),
        ("_ foo bar_", "_ foo bar_"),
        ('a_"foo"_', "a_&quot;foo&quot;_"),
        ("foo_bar_", "foo_bar_"),
        ("5_6_78", "5_6_78"),
        ("пристаням_стремятся_", "пристаням_стремятся_"),
        ('aa_"bb"_cc', "aa_&quot;bb&quot;_cc"),
        ("foo-_(bar)_", "foo-<em>(bar)</em>"),
        ("_foo*", "_foo*"),
        ("*foo bar *", "*foo bar *"),
        ("*foo bar\n*", "*foo bar\n*"),
        ("*(*foo)", "*(*foo)"),
        ("*(*foo*)*", "<em>(<em>foo</em>)</em>"),
        ("*foo*bar", "<em>foo</em>bar"),
        ("_foo bar _", "_foo bar _"),
        ("_(_foo)", "_(_foo)"),
        ("_(_foo_)_", "<em>(<em>foo</em>)</em>"),
        ("_foo_bar", "_foo_bar"),
        ("_пристаням_стремятся", "_пристаням_стремятся"),
        ("_foo_bar_baz_", "<em>foo_bar_baz</em>"),
        ("_(bar)_.", "<em>(bar)</em>."),
    ],
)
def test_emphasis_flanking_rules(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("**foo bar**", "<strong>foo bar</strong>"),
        ("** foo bar**", "** foo bar**"),
        ('a**"foo"**', "a**&quot;foo&quot;**"),
        ("foo**bar**", "foo<strong>bar</strong>"),
        ("__foo bar__", "<strong>foo bar</strong>"),
        ("__ foo bar__", "__ foo bar__"),
        ("__\nfoo bar__", "__\nfoo bar__"),
        ('a__"foo"__', "a__&quot;foo&quot;__"),
        ("foo__bar__", "foo__bar__"),
        ("5__6__78", "5__6__78"),
        ("пристаням__стремятся__", "пристаням__стремятся__"),
        ("__foo, __bar__, baz__", "<strong>foo, <strong>bar</strong>, baz</strong>"),
        ("foo-__(bar)__", "foo-<strong>(bar)</strong>"),
        ("**foo bar **", "**foo bar **"),
        ("**(**foo)", "**(**foo)"),
        ("*(**foo**)*", "<em>(<strong>foo</strong>)</em>"),
        (
            "**Gomphocarpus (*Gomphocarpus physocarpus*, syn.\n"
            "*Asclepias physocarpa*)**",
            "<strong>Gomphocarpus (<em>Gomphocarpus physocarpus</em>, syn.\n"
            "<em>Asclepias physocarpa</em>)</strong>",
        ),
        ('**foo "*bar*" foo**', "<strong>foo &quot;<em>bar</em>&quot; foo</strong>"),
        ("**foo**bar", "<strong>foo</strong>bar"),
        ("__foo bar __", "__foo bar __"),
        ("__(__foo)", "__(__foo)"),
        ("_(__foo__)_", "<em>(<strong>foo</strong>)</em>"),
        ("__foo__bar", "__foo__bar"),
        ("__пристаням__стремятся", "__пристаням__стремятся"),
        ("__foo__bar__baz__", "<strong>foo__bar__baz</strong>"),
        ("__(bar)__.", "<strong>(bar)</strong>."),
    ],
)
def test_strong_emphasis_flanking_rules(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("*foo [bar](/url)*", '<em>foo <a href="/url">bar</a></em>'),
        ("*foo\nbar*", "<em>foo\nbar</em>"),
        ("_foo __bar__ baz_", "<em>foo <strong>bar</strong> baz</em>"),
        ("_foo _bar_ baz_", "<em>foo <em>bar</em> baz</em>"),
        ("__foo_ bar_", "<em><em>foo</em> bar</em>"),
        ("*foo *bar**", "<em>foo <em>bar</em></em>"),
        ("*foo **bar** baz*", "<em>foo <strong>bar</strong> baz</em>"),
        ("*foo**bar**baz*", "<em>foo<strong>bar</strong>baz</em>"),
        ("*foo**bar*", "<em>foo**bar</em>"),
        ("***foo** bar*", "<em><strong>foo</strong> bar</em>"),
        ("*foo **bar***", "<em>foo <strong>bar</strong></em>"),
        ("*foo**bar***", "<em>foo<strong>bar</strong></em>"),
        ("foo***bar***baz", "foo<em><strong>bar</strong></em>baz"),
        (
            "foo******bar*********baz",
            "foo<strong><strong><strong>bar</strong></strong></strong>***baz",
        ),
        (
            "*foo **bar *baz* bim** bop*",
            "<em>foo <strong>bar <em>baz</em> bim</strong> bop</em>",
        ),
        ("*foo [*bar*](/url)*", '<em>foo <a href="/url"><em>bar</em></a></em>'),
        ("** is not an empty emphasis", "** is not an empty emphasis"),
        (
            "**** is not an empty strong emphasis",
            "**** is not an empty strong emphasis",
        ),
        ("**foo [bar](/url)**", '<strong>foo <a href="/url">bar</a></strong>'),
        ("**foo\nbar**", "<strong>foo\nbar</strong>"),
        ("__foo _bar_ baz__", "<strong>foo <em>bar</em> baz</strong>"),
        ("__foo __bar__ baz__", "<strong>foo <strong>bar</strong> baz</strong>"),
        ("____foo__ bar__", "<strong><strong>foo</strong> bar</strong>"),
        ("**foo **bar****", "<strong>foo <strong>bar</strong></strong>"),
        ("**foo *bar* baz**", "<strong>foo <em>bar</em> baz</strong>"),
        ("**foo*bar*baz**", "<strong>foo<em>bar</em>baz</strong>"),
        ("***foo* bar**", "<strong><em>foo</em> bar</strong>"),
        ("**foo *bar***", "<strong>foo <em>bar</em></strong>"),
        (
            "**foo *bar **baz**\nbim* bop**",
            "<strong>foo <em>bar <strong>baz</strong>\nbim</em> bop</strong>",
        ),
        (
            "**foo [*bar*](/url)**",
            '<strong>foo <a href="/url"><em>bar</em></a></strong>',
        ),
        ("__ is not an empty emphasis", "__ is not an empty emphasis"),
        (
            "____ is not an empty strong emphasis",
            "____ is not an empty strong emphasis",
        ),
    ],
)
def test_nested_emphasis(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("foo ***", "foo ***"),
        ("foo *\\**", "foo <em>*</em>"),
        ("foo *_*", "foo <em>_</em>"),
        ("foo *****", "foo *****"),
        ("foo **\\***", "foo <strong>*</strong>"),
        ("foo **_**", "foo <strong>_</strong>"),
        ("**foo*", "*<em>foo</em>"),
        ("*foo**", "<em>foo</em>*"),
        ("***foo**", "*<strong>foo</strong>"),
        ("****foo*", "***<em>foo</em>"),
        ("**foo***", "<strong>foo</strong>*"),
        ("*foo****", "<em>foo</em>***"),
        ("foo ___", "foo ___"),
        ("foo _\\__", "foo <em>_</em>"),
        ("foo _*_", "foo <em>*</em>"),
        ("foo _____", "foo _____"),
        ("foo __\\___", "foo <strong>_</strong>"),
        ("foo __*__", "foo <strong>*</strong>"),
        ("__foo_", "_<em>foo</em>"),
        ("_foo__", "<em>foo</em>_"),
        ("___foo__", "_<strong>foo</strong>"),
        ("____foo_", "___<em>foo</em>"),
        ("__foo___", "<strong>foo</strong>_"),
        ("_foo____", "<em>foo</em>___"),
        ("**foo**", "<strong>foo</strong>"),
        ("*_foo_*", "<em><em>foo</em></em>"),
        ("__foo__", "<strong>foo</strong>"),
        ("_*foo*_", "<em><em>foo</em></em>"),
        ("****foo****", "<strong><strong>foo</strong></strong>"),
        ("____foo____", "<strong><strong>foo</strong></strong>"),
        (
            "******foo******",
            "<strong><strong><strong>foo</strong></strong></strong>",
        ),
        ("***foo***", "<em><strong>foo</strong></em>"),
        ("_____foo_____", "<em><strong><strong>foo</strong></strong></em>"),
        ("*foo _bar* baz_", "<em>foo _bar</em> baz_"),
        (
            "*foo __bar *baz bim__ bam*",
            "<em>foo <strong>bar *baz bim</strong> bam</em>",
        ),
        ("**foo **bar baz**", "**foo <strong>bar baz</strong>"),
        ("*foo *bar baz*", "*foo <em>bar baz</em>"),
        ("*[bar*](/url)", '*<a href="/url">bar*</a>'),
        ("_foo [bar_](/url)", '_foo <a href="/url">bar_</a>'),
        ('*<img src="foo" title="*"/>', '*<img src="foo" title="*"/>'),
        ('**<a href="**">', '**<a href="**">'),
        ('__<a href="__">', '__<a href="__">'),
        ("*a `*`*", "<em>a <code>*</code></em>"),
        ("_a `_`_", "<em>a <code>_</code></em>"),
        (
            "**a<https://foo.bar/?q=**>",
            '**a<a href="https://foo.bar/?q=**">https://foo.bar/?q=**</a>',
        ),
        (
            "__a<https://foo.bar/?q=__>",
            '__a<a href="https://foo.bar/?q=__">https://foo.bar/?q=__</a>',
        ),
    ],
)
def test_unbalanced_delimiters_and_precedence(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('[link](/uri "title")', '<a href="/uri" title="title">link</a>'),
        ("[link](/uri)", '<a href="/uri">link</a>'),
        ("[](./target.md)", '<a href="./target.md"></a>'),
        ("[link]()", '<a href="">link</a>'),
        ("[link](<>)", '<a href="">link</a>'),
        ("[]()", '<a href=""></a>'),
        ("[link](/my uri)", "[link](/my uri)"),
        ("[link](</my uri>)", '<a href="/my%20uri">link</a>'),
        ("[link](foo\nbar)", "[link](foo\nbar)"),
        ("[link](<foo\nbar>)", "[link](<foo\nbar>)"),
        ("[a](<b)c>)", '<a href="b)c">a</a>'),
        ("[link](<foo\\>)", "[link](&lt;foo&gt;)"),
        (
            "[a](<b)c\n[a](<b)c>\n[a](<b>c)",
            "[a](&lt;b)c\n[a](&lt;b)c&gt;\n[a](<b>c)",
        ),
        ("[link](\\(foo\\))", '<a href="(foo)">link</a>'),
        ("[link](foo(and(bar)))", '<a href="foo(and(bar))">link</a>'),
        ("[link](foo(and(bar))", "[link](foo(and(bar))"),
        ("[link](foo\\(and\\(bar\\))", '<a href="foo(and(bar)">link</a>'),
        ("[link](<foo(and(bar)>)", '<a href="foo(and(bar)">link</a>'),
        ("[link](foo\\)\\:)", '<a href="foo):">link</a>'),
        ("[link](#fragment)", '<a href="#fragment">link</a>'),
        (
            "[link](https://example.com?foo=3#frag)",
            '<a href="https://example.com?foo=3#frag">link</a>',
        ),
        ("[link](foo\\bar)", '<a href="foo%5Cbar">link</a>'),
        ("[link](foo%20b&auml;)", '<a href="foo%20b%C3%A4">link</a>'),
        ('[link]("title")', '<a href="%22title%22">link</a>'),
        (
            "[link](/url \"title\")\n[link](/url 'title')\n[link](/url (title))",
            '<a href="/url" title="title">link</a>\n'
            '<a href="/url" title="title">link</a>\n'
            '<a href="/url" title="title">link</a>',
        ),
        (
            '[link](/url "title \\"&quot;")',
            '<a href="/url" title="title &quot;&quot;">link</a>',
        ),
        ('[link](/url\u00a0"title")', '<a href="/url%C2%A0%22title%22">link</a>'),
        (
            '[link](/url "title "and" title")',
            "[link](/url &quot;title &quot;and&quot; title&quot;)",
        ),
        (
            "[link](/url 'title \"and\" title')",
            '<a href="/url" title="title &quot;and&quot; title">link</a>',
        ),
        ('[link](   /uri\n  "title"  )', '<a href="/uri" title="title">link</a>'),
        ("[link] (/uri)", "[link] (/uri)"),
        ("[link [foo [bar]]](/uri)", '<a href="/uri">link [foo [bar]]</a>'),
        ("[link] bar](/uri)", "[link] bar](/uri)"),
        ("[link [bar](/uri)", '[link <a href="/uri">bar</a>'),
        ("[link \\[bar](/uri)", '<a href="/uri">link [bar</a>'),
        (
            "[link *foo **bar** `#`*](/uri)",
            '<a href="/uri">link <em>foo <strong>bar</strong> <code>#</code></em></a>',
        ),
        (
            "[![moon](moon.jpg)](/uri)",
            '<a href="/uri"><img src="moon.jpg" alt="moon" /></a>',
        ),
        ("[foo [bar](/uri)](/uri)", '[foo <a href="/uri">bar</a>](/uri)'),
        (
            "[foo *[bar [baz](/uri)](/uri)*](/uri)",
            '[foo <em>[bar <a href="/uri">baz</a>](/uri)</em>](/uri)',
        ),
        ("![[[foo](uri1)](uri2)](uri3)", '<img src="uri3" alt="[foo](uri2)" />'),
        ("*[foo*](/uri)", '*<a href="/uri">foo*</a>'),
        ("[foo *bar](baz*)", '<a href="baz*">foo *bar</a>'),
        ("*foo [bar* baz]", "<em>foo [bar</em> baz]"),
        ('[foo <bar attr="](baz)">', '[foo <bar attr="](baz)">'),
        ("[foo`](/uri)`", "[foo<code>](/uri)</code>"),
        (
            "[foo<https://example.com/?search=](uri)>",
            '[foo<a href="https://example.com/?search=%5D(uri)">'
            "https://example.com/?search=](uri)</a>",
        ),
    ],
)
def test_inline_links(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('[foo][bar]\n\n[bar]: /url "title"', '<a href="/url" title="title">foo</a>'),
        (
            "[link [foo [bar]]][ref]\n\n[ref]: /uri",
            '<a href="/uri">link [foo [bar]]</a>',
        ),
        ("[link \\[bar][ref]\n\n[ref]: /uri", '<a href="/uri">link [bar</a>'),
        (
            "[foo [bar](/uri)][ref]\n\n[ref]: /uri",
            '[foo <a href="/uri">bar</a>]<a href="/uri">ref</a>',
        ),
        (
            "[foo *bar [baz][ref]*][ref]\n\n[ref]: /uri",
            '[foo <em>bar <a href="/uri">baz</a></em>]<a href="/uri">ref</a>',
        ),
        ('[foo][BaR]\n\n[bar]: /url "title"', '<a href="/url" title="title">foo</a>'),
        ("[ẞ]\n\n[SS]: /url", '<a href="/url">ẞ</a>'),
        ("[Foo\n  bar]: /url\n\n[Baz][Foo bar]", '<a href="/url">Baz</a>'),
        (
            '[foo] [bar]\n\n[bar]: /url "title"',
            '[foo] <a href="/url" title="title">bar</a>',
        ),
        (
            '[foo]\n[bar]\n\n[bar]: /url "title"',
            '[foo]\n<a href="/url" title="title">bar</a>',
        ),
        ("[foo]: /url1\n\n[foo]: /url2\n\n[bar][foo]", '<a href="/url1">bar</a>'),
        ("[bar][foo\\!]\n\n[foo!]: /url", "[bar][foo!]"),
        ("[foo][ref\\[]\n\n[ref\\[]: /uri", '<a href="/uri">foo</a>'),
        ("[bar\\\\]: /uri\n\n[bar\\\\]", '<a href="/uri">bar\\</a>'),
        ('[foo][]\n\n[foo]: /url "title"', '<a href="/url" title="title">foo</a>'),
        (
            '[*foo* bar][]\n\n[*foo* bar]: /url "title"',
            '<a href="/url" title="title"><em>foo</em> bar</a>',
        ),
        ('[Foo][]\n\n[foo]: /url "title"', '<a href="/url" title="title">Foo</a>'),
        (
            '[foo] \n[]\n\n[foo]: /url "title"',
            '<a href="/url" title="title">foo</a>\n[]',
        ),
        ('[foo]\n\n[foo]: /url "title"', '<a href="/url" title="title">foo</a>'),
        (
            '[*foo* bar]\n\n[*foo* bar]: /url "title"',
            '<a href="/url" title="title"><em>foo</em> bar</a>',
        ),
        (
            '[[*foo* bar]]\n\n[*foo* bar]: /url "title"',
            '[<a href="/url" title="title"><em>foo</em> bar</a>]',
        ),
        ("[[bar [foo]\n\n[foo]: /url", '[[bar <a href="/url">foo</a>'),
        ('\\[foo]\n\n[foo]: /url "title"', "[foo]"),
        ("[foo*]: /url\n\n*[foo*]", '*<a href="/url">foo*</a>'),
        ("[foo][bar]\n\n[foo]: /url1\n[bar]: /url2", '<a href="/url2">foo</a>'),
        ("[foo][]\n\n[foo]: /url1", '<a href="/url1">foo</a>'),
        ("[foo]()\n\n[foo]: /url1", '<a href="">foo</a>'),
        ("[foo](not a link)\n\n[foo]: /url1", '<a href="/url1">foo</a>(not a link)'),
        ("[foo][bar][baz]\n\n[baz]: /url", '[foo]<a href="/url">bar</a>'),
        (
            "[foo][bar][baz]\n\n[baz]: /url1\n[bar]: /url2",
            '<a href="/url2">foo</a><a href="/url1">baz</a>',
        ),
        (
            "[foo][bar][baz]\n\n[baz]: /url1\n[foo]: /url2",
            '[foo]<a href="/url1">bar</a>',
        ),
    ],
)
def test_reference_links(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("[foo][ref[]\n\n[ref[]: /uri", "<p>[foo][ref[]</p>\n<p>[ref[]: /uri</p>\n"),
        (
            "[foo][ref[bar]]\n\n[ref[bar]]: /uri",
            "<p>[foo][ref[bar]]</p>\n<p>[ref[bar]]: /uri</p>\n",
        ),
        ("[[[foo]]]\n\n[[[foo]]]: /url", "<p>[[[foo]]]</p>\n<p>[[[foo]]]: /url</p>\n"),
        ("[]\n\n[]: /uri", "<p>[]</p>\n<p>[]: /uri</p>\n"),
        ("[\n ]\n\n[\n ]: /uri", "<p>[\n]</p>\n<p>[\n]: /uri</p>\n"),
        (
            '![[foo]]\n\n[[foo]]: /url "title"',
            "<p>![[foo]]</p>\n<p>[[foo]]: /url &quot;title&quot;</p>\n",
        ),
    ],
)
def test_labels_that_are_not_valid(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ('![foo](/url "title")', '<img src="/url" alt="foo" title="title" />'),
        (
            '![foo *bar*]\n\n[foo *bar*]: train.jpg "train & tracks"',
            '<img src="train.jpg" alt="foo bar" title="train &amp; tracks" />',
        ),
        ("![foo ![bar](/url)](/url2)", '<img src="/url2" alt="foo bar" />'),
        ("![foo [bar](/url)](/url2)", '<img src="/url2" alt="foo bar" />'),
        (
            '![foo *bar*][]\n\n[foo *bar*]: train.jpg "train & tracks"',
            '<img src="train.jpg" alt="foo bar" title="train &amp; tracks" />',
        ),
        (
            '![foo *bar*][foobar]\n\n[FOOBAR]: train.jpg "train & tracks"',
            '<img src="train.jpg" alt="foo bar" title="train &amp; tracks" />',
        ),
        ("![foo](train.jpg)", '<img src="train.jpg" alt="foo" />'),
        (
            'My ![foo bar](/path/to/train.jpg  "title"   )',
            'My <img src="/path/to/train.jpg" alt="foo bar" title="title" />',
        ),
        ("![foo](<url>)", '<img src="url" alt="foo" />'),
        ("![](/url)", '<img src="/url" alt="" />'),
        ("![foo][bar]\n\n[bar]: /url", '<img src="/url" alt="foo" />'),
        ("![foo][bar]\n\n[BAR]: /url", '<img src="/url" alt="foo" />'),
        (
            '![foo][]\n\n[foo]: /url "title"',
            '<img src="/url" alt="foo" title="title" />',
        ),
        (
            '![*foo* bar][]\n\n[*foo* bar]: /url "title"',
            '<img src="/url" alt="foo bar" title="title" />',
        ),
        (
            '![foo] \n[]\n\n[foo]: /url "title"',
            '<img src="/url" alt="foo" title="title" />\n[]',
        ),
        (
            '![foo]\n\n[foo]: /url "title"',
            '<img src="/url" alt="foo" title="title" />',
        ),
        ('!\\[foo]\n\n[foo]: /url "title"', "![foo]"),
        (
            '\\![foo]\n\n[foo]: /url "title"',
            '!<a href="/url" title="title">foo</a>',
        ),
    ],
)
def test_images(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("<http://foo.bar.baz>", '<a href="http://foo.bar.baz">http://foo.bar.baz</a>'),
        (
            "<https://foo.bar.baz/test?q=hello&id=22&boolean>",
            '<a href="https://foo.bar.baz/test?q=hello&amp;id=22&amp;boolean">'
            "https://foo.bar.baz/test?q=hello&amp;id=22&amp;boolean</a>",
        ),
        (
            "<irc://foo.bar:2233/baz>",
            '<a href="irc://foo.bar:2233/baz">irc://foo.bar:2233/baz</a>',
        ),
        ("<MAILTO:FOO@BAR.BAZ>", '<a href="MAILTO:FOO@BAR.BAZ">MAILTO:FOO@BAR.BAZ</a>'),
        ("<a+b+c:d>", '<a href="a+b+c:d">a+b+c:d</a>'),
        (
            "<made-up-scheme://foo,bar>",
            '<a href="made-up-scheme://foo,bar">made-up-scheme://foo,bar</a>',
        ),
        ("<https://../>", '<a href="https://../">https://../</a>'),
        ("<localhost:5001/foo>", '<a href="localhost:5001/foo">localhost:5001/foo</a>'),
        ("<https://foo.bar/baz bim>", "&lt;https://foo.bar/baz bim&gt;"),
        (
            "<https://example.com/\\[\\>",
            '<a href="https://example.com/%5C%5B%5C">https://example.com/\\[\\</a>',
        ),
        (
            "<foo@bar.example.com>",
            '<a href="mailto:foo@bar.example.com">foo@bar.example.com</a>',
        ),
        (
            "<foo+special@Bar.baz-bar0.com>",
            '<a href="mailto:foo+special@Bar.baz-bar0.com">'
            "foo+special@Bar.baz-bar0.com</a>",
        ),
        ("<foo\\+@bar.example.com>", "&lt;foo+@bar.example.com&gt;"),
        ("<>", "&lt;&gt;"),
        ("< https://foo.bar >", "&lt; https://foo.bar &gt;"),
        ("<m:abc>", "&lt;m:abc&gt;"),
        ("<foo.bar.baz>", "&lt;foo.bar.baz&gt;"),
        ("https://example.com", "https://example.com"),
        ("foo@bar.example.com", "foo@bar.example.com"),
    ],
)
def test_autolinks(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "<a><bab><c2c>",
        "<a/><b2/>",
        '<a  /><b2\ndata="foo" >',
        "<a foo=\"bar\" bam = 'baz <em>\"</em>'\n_boolean zoop:33=zoop:33 />",
        'Foo <responsive-image src="foo.jpg" />',
        "</a></foo >",
        "foo <!-- this is a --\ncomment - with hyphens -->",
        "foo <?php echo $a; ?>",
        "foo <!ELEMENT br EMPTY>",
        "foo <![CDATA[>&<]]>",
        'foo <a href="&ouml;">',
        'foo <a href="\\*">',
    ],
)
def test_raw_inline_html_is_kept(source):
    assert paragraph(source) == source


@pytest.mark.parametrize(
    "source, expected",
    [
        ("<33> <__>", "&lt;33&gt; &lt;__&gt;"),
        ('<a h*#ref="hi">', "&lt;a h*#ref=&quot;hi&quot;&gt;"),
        ("<a href=\"hi'> <a href=hi'>", "&lt;a href=&quot;hi'&gt; &lt;a href=hi'&gt;"),
        (
            "< a><\nfoo><bar/ >\n<foo bar=baz\nbim!bop />",
            "&lt; a&gt;&lt;\nfoo&gt;&lt;bar/ &gt;\n&lt;foo bar=baz\nbim!bop /&gt;",
        ),
        ("<a href='bar'title=title>", "&lt;a href='bar'title=title&gt;"),
        ('</a href="foo">', "&lt;/a href=&quot;foo&quot;&gt;"),
        ("foo <!--> foo -->", "foo <!--> foo --&gt;"),
        ("foo <!---> foo -->", "foo <!---> foo --&gt;"),
        ('<a href="\\"">', "&lt;a href=&quot;&quot;&quot;&gt;"),
    ],
)
def test_things_that_only_look_like_html(source, expected):
    assert paragraph(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("foo  \nbaz", "foo<br />\nbaz"),
        ("foo\\\nbaz", "foo<br />\nbaz"),
        ("foo       \nbaz", "foo<br />\nbaz"),
        ("foo  \n     bar", "foo<br />\nbar"),
        ("foo\\\n     bar", "foo<br />\nbar"),
        ("*foo  \nbar*", "<em>foo<br />\nbar</em>"),
        ("*foo\\\nbar*", "<em>foo<br />\nbar</em>"),
        ("`code  \nspan`", "<code>code   span</code>"),
        ("`code\\\nspan`", "<code>code\\ span</code>"),
        ('<a href="foo  \nbar">', '<a href="foo  \nbar">'),
        ('<a href="foo\\\nbar">', '<a href="foo\\\nbar">'),
        ("foo\\", "foo\\"),
        ("foo  ", "foo"),
        ("foo\nbaz", "foo\nbaz"),
        ("foo \n baz", "foo\nbaz"),
        ("hello $.;'there", "hello $.;'there"),
        ("Foo χρῆν", "Foo χρῆν"),
        ("Multiple     spaces", "Multiple     spaces"),
    ],
)
def test_line_breaks_and_plain_text(source, expected):
    assert paragraph(source) == expected


def test_trailing_break_markers_in_headings_are_literal():
    assert to_html("### foo\\") == "<h3>foo\\</h3>\n"
    assert to_html("### foo  ") == "<h3>foo</h3>\n"
