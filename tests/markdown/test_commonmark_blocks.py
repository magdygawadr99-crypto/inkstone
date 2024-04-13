from __future__ import annotations

import pytest

from inkstone.markdown import Markdown

# Examples from the CommonMark spec (block structure half), typed in by hand.
# Extensions and heading ids are off so the output is exactly the spec's.
_core = Markdown(extensions=[], heading_ids=False)


def to_html(source: str) -> str:
    return _core.convert(source)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("\tfoo\tbaz\t\tbim\n", "<pre><code>foo\tbaz\t\tbim\n</code></pre>\n"),
        ("  \tfoo\tbaz\t\tbim\n", "<pre><code>foo\tbaz\t\tbim\n</code></pre>\n"),
        ("    a\ta\n    ὐ\ta\n", "<pre><code>a\ta\nὐ\ta\n</code></pre>\n"),
        ("  - foo\n\n\tbar\n", "<ul>\n<li>\n<p>foo</p>\n<p>bar</p>\n</li>\n</ul>\n"),
        (
            "- foo\n\n\t\tbar\n",
            "<ul>\n<li>\n<p>foo</p>\n<pre><code>  bar\n</code></pre>\n</li>\n</ul>\n",
        ),
        (
            ">\t\tfoo\n",
            "<blockquote>\n<pre><code>  foo\n</code></pre>\n</blockquote>\n",
        ),
        ("-\t\tfoo\n", "<ul>\n<li>\n<pre><code>  foo\n</code></pre>\n</li>\n</ul>\n"),
        ("    foo\n\tbar\n", "<pre><code>foo\nbar\n</code></pre>\n"),
        (
            " - foo\n   - bar\n\t - baz\n",
            "<ul>\n<li>foo\n<ul>\n<li>bar\n<ul>\n<li>baz</li>\n</ul>\n</li>\n</ul>\n"
            "</li>\n</ul>\n",
        ),
        ("#\tFoo\n", "<h1>Foo</h1>\n"),
        ("*\t*\t*\t\n", "<hr />\n"),
    ],
)
def test_tabs(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("***\n---\n___\n", "<hr />\n<hr />\n<hr />\n"),
        ("+++\n", "<p>+++</p>\n"),
        ("===\n", "<p>===</p>\n"),
        ("--\n**\n__\n", "<p>--\n**\n__</p>\n"),
        (" ***\n  ***\n   ***\n", "<hr />\n<hr />\n<hr />\n"),
        ("    ***\n", "<pre><code>***\n</code></pre>\n"),
        ("Foo\n    ***\n", "<p>Foo\n***</p>\n"),
        ("_____________________________________\n", "<hr />\n"),
        (" - - -\n", "<hr />\n"),
        (" **  * ** * ** * **\n", "<hr />\n"),
        ("-     -      -      -\n", "<hr />\n"),
        ("- - - -    \n", "<hr />\n"),
        (
            "_ _ _ _ a\n\na------\n\n---a---\n",
            "<p>_ _ _ _ a</p>\n<p>a------</p>\n<p>---a---</p>\n",
        ),
        (" *-*\n", "<p><em>-</em></p>\n"),
        (
            "- foo\n***\n- bar\n",
            "<ul>\n<li>foo</li>\n</ul>\n<hr />\n<ul>\n<li>bar</li>\n</ul>\n",
        ),
        ("Foo\n***\nbar\n", "<p>Foo</p>\n<hr />\n<p>bar</p>\n"),
        ("Foo\n---\nbar\n", "<h2>Foo</h2>\n<p>bar</p>\n"),
        (
            "* Foo\n* * *\n* Bar\n",
            "<ul>\n<li>Foo</li>\n</ul>\n<hr />\n<ul>\n<li>Bar</li>\n</ul>\n",
        ),
        ("- Foo\n- * * *\n", "<ul>\n<li>Foo</li>\n<li>\n<hr />\n</li>\n</ul>\n"),
    ],
)
def test_thematic_breaks(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "# foo\n## foo\n### foo\n#### foo\n##### foo\n###### foo\n",
            "<h1>foo</h1>\n<h2>foo</h2>\n<h3>foo</h3>\n<h4>foo</h4>\n<h5>foo</h5>\n"
            "<h6>foo</h6>\n",
        ),
        ("####### foo\n", "<p>####### foo</p>\n"),
        ("#5 bolt\n\n#hashtag\n", "<p>#5 bolt</p>\n<p>#hashtag</p>\n"),
        ("\\## foo\n", "<p>## foo</p>\n"),
        ("# foo *bar* \\*baz\\*\n", "<h1>foo <em>bar</em> *baz*</h1>\n"),
        ("#                  foo                     \n", "<h1>foo</h1>\n"),
        (
            " ### foo\n  ## foo\n   # foo\n",
            "<h3>foo</h3>\n<h2>foo</h2>\n<h1>foo</h1>\n",
        ),
        ("    # foo\n", "<pre><code># foo\n</code></pre>\n"),
        ("foo\n    # bar\n", "<p>foo\n# bar</p>\n"),
        ("## foo ##\n  ###   bar    ###\n", "<h2>foo</h2>\n<h3>bar</h3>\n"),
        (
            "# foo ##################################\n##### foo ##\n",
            "<h1>foo</h1>\n<h5>foo</h5>\n",
        ),
        ("### foo ###     \n", "<h3>foo</h3>\n"),
        ("### foo ### b\n", "<h3>foo ### b</h3>\n"),
        ("# foo#\n", "<h1>foo#</h1>\n"),
        (
            "### foo \\###\n## foo #\\##\n# foo \\#\n",
            "<h3>foo ###</h3>\n<h2>foo ###</h2>\n<h1>foo #</h1>\n",
        ),
        ("****\n## foo\n****\n", "<hr />\n<h2>foo</h2>\n<hr />\n"),
        ("Foo bar\n# baz\nBar foo\n", "<p>Foo bar</p>\n<h1>baz</h1>\n<p>Bar foo</p>\n"),
        ("## \n#\n### ###\n", "<h2></h2>\n<h1></h1>\n<h3></h3>\n"),
    ],
)
def test_atx_headings(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "Foo *bar*\n=========\n\nFoo *bar*\n---------\n",
            "<h1>Foo <em>bar</em></h1>\n<h2>Foo <em>bar</em></h2>\n",
        ),
        ("Foo *bar\nbaz*\n====\n", "<h1>Foo <em>bar\nbaz</em></h1>\n"),
        ("  Foo *bar\nbaz*\t\n====\n", "<h1>Foo <em>bar\nbaz</em></h1>\n"),
        ("Foo\n-------------------------\n\nFoo\n=\n", "<h2>Foo</h2>\n<h1>Foo</h1>\n"),
        (
            "   Foo\n---\n\n  Foo\n-----\n\n  Foo\n  ===\n",
            "<h2>Foo</h2>\n<h2>Foo</h2>\n<h1>Foo</h1>\n",
        ),
        (
            "    Foo\n    ---\n\n    Foo\n---\n",
            "<pre><code>Foo\n---\n\nFoo\n</code></pre>\n<hr />\n",
        ),
        ("Foo\n   ----      \n", "<h2>Foo</h2>\n"),
        ("Foo\n    ---\n", "<p>Foo\n---</p>\n"),
        ("Foo\n= =\n\nFoo\n--- -\n", "<p>Foo\n= =</p>\n<p>Foo</p>\n<hr />\n"),
        ("Foo  \n-----\n", "<h2>Foo</h2>\n"),
        ("Foo\\\n----\n", "<h2>Foo\\</h2>\n"),
        (
            '`Foo\n----\n`\n\n<a title="a lot\n---\nof dashes"/>\n',
            "<h2>`Foo</h2>\n<p>`</p>\n<h2>&lt;a title=&quot;a lot</h2>\n"
            "<p>of dashes&quot;/&gt;</p>\n",
        ),
        ("> Foo\n---\n", "<blockquote>\n<p>Foo</p>\n</blockquote>\n<hr />\n"),
        ("> foo\nbar\n===\n", "<blockquote>\n<p>foo\nbar\n===</p>\n</blockquote>\n"),
        ("- Foo\n---\n", "<ul>\n<li>Foo</li>\n</ul>\n<hr />\n"),
        ("Foo\nBar\n---\n", "<h2>Foo\nBar</h2>\n"),
        (
            "---\nFoo\n---\nBar\n---\nBaz\n",
            "<hr />\n<h2>Foo</h2>\n<h2>Bar</h2>\n<p>Baz</p>\n",
        ),
        ("\n====\n", "<p>====</p>\n"),
        ("---\n---\n", "<hr />\n<hr />\n"),
        ("- foo\n-----\n", "<ul>\n<li>foo</li>\n</ul>\n<hr />\n"),
        ("    foo\n---\n", "<pre><code>foo\n</code></pre>\n<hr />\n"),
        ("> foo\n-----\n", "<blockquote>\n<p>foo</p>\n</blockquote>\n<hr />\n"),
        ("\\> foo\n------\n", "<h2>&gt; foo</h2>\n"),
        ("Foo\n\nbar\n---\nbaz\n", "<p>Foo</p>\n<h2>bar</h2>\n<p>baz</p>\n"),
        ("Foo\nbar\n\n---\n\nbaz\n", "<p>Foo\nbar</p>\n<hr />\n<p>baz</p>\n"),
        ("Foo\nbar\n* * *\nbaz\n", "<p>Foo\nbar</p>\n<hr />\n<p>baz</p>\n"),
        ("Foo\nbar\n\\---\nbaz\n", "<p>Foo\nbar\n---\nbaz</p>\n"),
    ],
)
def test_setext_headings(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "    a simple\n      indented code block\n",
            "<pre><code>a simple\n  indented code block\n</code></pre>\n",
        ),
        ("  - foo\n\n    bar\n", "<ul>\n<li>\n<p>foo</p>\n<p>bar</p>\n</li>\n</ul>\n"),
        (
            "1.  foo\n\n    - bar\n",
            "<ol>\n<li>\n<p>foo</p>\n<ul>\n<li>bar</li>\n</ul>\n</li>\n</ol>\n",
        ),
        (
            "    <a/>\n    *hi*\n\n    - one\n",
            "<pre><code>&lt;a/&gt;\n*hi*\n\n- one\n</code></pre>\n",
        ),
        (
            "    chunk1\n\n    chunk2\n  \n \n \n    chunk3\n",
            "<pre><code>chunk1\n\nchunk2\n\n\n\nchunk3\n</code></pre>\n",
        ),
        (
            "    chunk1\n      \n      chunk2\n",
            "<pre><code>chunk1\n  \n  chunk2\n</code></pre>\n",
        ),
        ("Foo\n    bar\n", "<p>Foo\nbar</p>\n"),
        ("    foo\nbar\n", "<pre><code>foo\n</code></pre>\n<p>bar</p>\n"),
        (
            "# Heading\n    foo\nHeading\n------\n    foo\n----\n",
            "<h1>Heading</h1>\n<pre><code>foo\n</code></pre>\n<h2>Heading</h2>\n"
            "<pre><code>foo\n</code></pre>\n<hr />\n",
        ),
        ("        foo\n    bar\n", "<pre><code>    foo\nbar\n</code></pre>\n"),
        ("\n    \n    foo\n    \n\n", "<pre><code>foo\n</code></pre>\n"),
        ("    foo  \n", "<pre><code>foo  \n</code></pre>\n"),
    ],
)
def test_indented_code_blocks(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("```\n<\n >\n```\n", "<pre><code>&lt;\n &gt;\n</code></pre>\n"),
        ("~~~\n<\n >\n~~~\n", "<pre><code>&lt;\n &gt;\n</code></pre>\n"),
        ("``\nfoo\n``\n", "<p><code>foo</code></p>\n"),
        ("```\naaa\n~~~\n```\n", "<pre><code>aaa\n~~~\n</code></pre>\n"),
        ("~~~\naaa\n```\n~~~\n", "<pre><code>aaa\n```\n</code></pre>\n"),
        ("````\naaa\n```\n``````\n", "<pre><code>aaa\n```\n</code></pre>\n"),
        ("~~~~\naaa\n~~~\n~~~~\n", "<pre><code>aaa\n~~~\n</code></pre>\n"),
        ("```\n", "<pre><code></code></pre>\n"),
        ("`````\n\n```\naaa\n", "<pre><code>\n```\naaa\n</code></pre>\n"),
        (
            "> ```\n> aaa\n\nbbb\n",
            "<blockquote>\n<pre><code>aaa\n</code></pre>\n</blockquote>\n<p>bbb</p>\n",
        ),
        ("```\n\n  \n```\n", "<pre><code>\n  \n</code></pre>\n"),
        ("```\n```\n", "<pre><code></code></pre>\n"),
        (" ```\n aaa\naaa\n```\n", "<pre><code>aaa\naaa\n</code></pre>\n"),
        (
            "  ```\naaa\n  aaa\naaa\n  ```\n",
            "<pre><code>aaa\naaa\naaa\n</code></pre>\n",
        ),
        (
            "   ```\n   aaa\n    aaa\n  aaa\n   ```\n",
            "<pre><code>aaa\n aaa\naaa\n</code></pre>\n",
        ),
        ("    ```\n    aaa\n    ```\n", "<pre><code>```\naaa\n```\n</code></pre>\n"),
        ("```\naaa\n  ```\n", "<pre><code>aaa\n</code></pre>\n"),
        ("   ```\naaa\n  ```\n", "<pre><code>aaa\n</code></pre>\n"),
        ("```\naaa\n    ```\n", "<pre><code>aaa\n    ```\n</code></pre>\n"),
        ("``` ```\naaa\n", "<p><code> </code>\naaa</p>\n"),
        ("~~~~~~\naaa\n~~~ ~~\n", "<pre><code>aaa\n~~~ ~~\n</code></pre>\n"),
        (
            "foo\n```\nbar\n```\nbaz\n",
            "<p>foo</p>\n<pre><code>bar\n</code></pre>\n<p>baz</p>\n",
        ),
        (
            "foo\n---\n~~~\nbar\n~~~\n# baz\n",
            "<h2>foo</h2>\n<pre><code>bar\n</code></pre>\n<h1>baz</h1>\n",
        ),
        (
            "```ruby\ndef foo(x)\n  return 3\nend\n```\n",
            '<pre><code class="language-ruby">def foo(x)\n  return 3\nend\n'
            "</code></pre>\n",
        ),
        (
            "~~~~    ruby startline=3 $%@#$\ndef foo(x)\n  return 3\nend\n~~~~~~~\n",
            '<pre><code class="language-ruby">def foo(x)\n  return 3\nend\n'
            "</code></pre>\n",
        ),
        ("````;\n````\n", '<pre><code class="language-;"></code></pre>\n'),
        ("``` aa ```\nfoo\n", "<p><code>aa</code>\nfoo</p>\n"),
        (
            "~~~ aa ``` ~~~\nfoo\n~~~\n",
            '<pre><code class="language-aa">foo\n</code></pre>\n',
        ),
        ("```\n``` aaa\n```\n", "<pre><code>``` aaa\n</code></pre>\n"),
    ],
)
def test_fenced_code_blocks(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "<table><tr><td>\n<pre>\n**Hello**,\n\n_world_.\n</pre>\n"
            "</td></tr></table>\n",
            "<table><tr><td>\n<pre>\n**Hello**,\n<p><em>world</em>.\n</pre></p>\n"
            "</td></tr></table>\n",
        ),
        (
            "<table>\n  <tr>\n    <td>\n           hi\n    </td>\n  </tr>\n</table>\n\n"
            "okay.\n",
            "<table>\n  <tr>\n    <td>\n           hi\n    </td>\n  </tr>\n</table>\n"
            "<p>okay.</p>\n",
        ),
        (
            '<DIV CLASS="foo">\n\n*Markdown*\n\n</DIV>\n',
            '<DIV CLASS="foo">\n<p><em>Markdown</em></p>\n</DIV>\n',
        ),
        ("<div>\n*foo*\n\n*bar*\n", "<div>\n*foo*\n<p><em>bar</em></p>\n"),
        ("<del>\n\n*foo*\n\n</del>\n", "<del>\n<p><em>foo</em></p>\n</del>\n"),
        ("<del>*foo*</del>\n", "<p><del><em>foo</em></del></p>\n"),
        (
            "<style>p{color:red;}</style>\n*foo*\n",
            "<style>p{color:red;}</style>\n<p><em>foo</em></p>\n",
        ),
        (
            "<!-- foo -->*bar*\n*baz*\n",
            "<!-- foo -->*bar*\n<p><em>baz</em></p>\n",
        ),
        (
            "<!-- Foo\n\nbar\n   baz -->\nokay\n",
            "<!-- Foo\n\nbar\n   baz -->\n<p>okay</p>\n",
        ),
        (
            "<?php\n\n  echo '>';\n\n?>\nokay\n",
            "<?php\n\n  echo '>';\n\n?>\n<p>okay</p>\n",
        ),
        (
            "<![CDATA[\nfunction matchwo(a,b)\n{\n  if (a < b && a < 0) then {\n"
            "    return 1;\n\n  } else {\n\n    return 0;\n  }\n}\n]]>\nokay\n",
            "<![CDATA[\nfunction matchwo(a,b)\n{\n  if (a < b && a < 0) then {\n"
            "    return 1;\n\n  } else {\n\n    return 0;\n  }\n}\n]]>\n<p>okay</p>\n",
        ),
        (
            "  <!-- foo -->\n\n    <!-- foo -->\n",
            "  <!-- foo -->\n<pre><code>&lt;!-- foo --&gt;\n</code></pre>\n",
        ),
        (
            "  <div>\n\n    <div>\n",
            "  <div>\n<pre><code>&lt;div&gt;\n</code></pre>\n",
        ),
        ("Foo\n<div>\nbar\n</div>\n", "<p>Foo</p>\n<div>\nbar\n</div>\n"),
        ('Foo\n<a href="bar">\nbaz\n', '<p>Foo\n<a href="bar">\nbaz</p>\n'),
        (
            "<div>\n\n*Emphasized* text.\n\n</div>\n",
            "<div>\n<p><em>Emphasized</em> text.</p>\n</div>\n",
        ),
        (
            "<table>\n\n<tr>\n\n<td>\nHi\n</td>\n\n</tr>\n\n</table>\n",
            "<table>\n<tr>\n<td>\nHi\n</td>\n</tr>\n</table>\n",
        ),
        (
            "<table>\n\n  <tr>\n\n    <td>\n      Hi\n    </td>\n\n  </tr>\n\n"
            "</table>\n",
            "<table>\n  <tr>\n<pre><code>&lt;td&gt;\n  Hi\n&lt;/td&gt;\n</code></pre>\n"
            "  </tr>\n</table>\n",
        ),
        (
            "> <div>\n> foo\n\nbar\n",
            "<blockquote>\n<div>\nfoo\n</blockquote>\n<p>bar</p>\n",
        ),
        ("- <div>\n- foo\n", "<ul>\n<li>\n<div>\n</li>\n<li>foo</li>\n</ul>\n"),
        (
            '<pre language="haskell"><code>\nimport Text.HTML.TagSoup\n\n'
            "main :: IO ()\nmain = print $ parseTags tags\n</code></pre>\nokay\n",
            '<pre language="haskell"><code>\nimport Text.HTML.TagSoup\n\n'
            "main :: IO ()\nmain = print $ parseTags tags\n</code></pre>\n"
            "<p>okay</p>\n",
        ),
        (
            '<style\n  type="text/css">\nh1 {color:red;}\n\np {color:blue;}\n</style>\n'
            "okay\n",
            '<style\n  type="text/css">\nh1 {color:red;}\n\np {color:blue;}\n</style>\n'
            "<p>okay</p>\n",
        ),
    ],
)
def test_html_blocks(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        " <div>\n  *hello*\n         <foo><a>\n",
        "</div>\n*foo*\n",
        '<div id="foo"\n  class="bar">\n</div>\n',
        '<div id="foo" class="bar\n  baz">\n</div>\n',
        '<div id="foo"\n*hi*\n',
        "<div class\nfoo\n",
        "<div *???-&&&-<---\n*foo*\n",
        '<div><a href="bar">*foo*</a></div>\n',
        "<table><tr><td>\nfoo\n</td></tr></table>\n",
        "<div></div>\n``` c\nint x = 33;\n```\n",
        '<a href="foo">\n*bar*\n</a>\n',
        "<Warning>\n*bar*\n</Warning>\n",
        '<i class="foo">\n*bar*\n</i>\n',
        "</ins>\n*bar*\n",
        "<del>\n*foo*\n</del>\n",
        "<script>\nfoo\n</script>1. *bar*\n",
        "<!DOCTYPE html>\n",
        '<style\n  type="text/css">\n\nfoo\n',
        "<div>\nbar\n</div>\n*foo*\n",
        "<div>\n*Emphasized* text.\n</div>\n",
    ],
)
def test_html_blocks_pass_through_untouched(source):
    assert to_html(source) == source


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            '[foo]: /url "title"\n\n[foo]\n',
            '<p><a href="/url" title="title">foo</a></p>\n',
        ),
        (
            "   [foo]: \n      /url  \n           'the title'  \n\n[foo]\n",
            '<p><a href="/url" title="the title">foo</a></p>\n',
        ),
        (
            "[Foo*bar\\]]:my_(url) 'title (with parens)'\n\n[Foo*bar\\]]\n",
            '<p><a href="my_(url)" title="title (with parens)">Foo*bar]</a></p>\n',
        ),
        (
            "[Foo bar]:\n<my url>\n'title'\n\n[Foo bar]\n",
            '<p><a href="my%20url" title="title">Foo bar</a></p>\n',
        ),
        (
            "[foo]: /url '\ntitle\nline1\nline2\n'\n\n[foo]\n",
            '<p><a href="/url" title="\ntitle\nline1\nline2\n">foo</a></p>\n',
        ),
        (
            "[foo]: /url 'title\n\nwith blank line'\n\n[foo]\n",
            "<p>[foo]: /url 'title</p>\n<p>with blank line'</p>\n<p>[foo]</p>\n",
        ),
        ("[foo]:\n/url\n\n[foo]\n", '<p><a href="/url">foo</a></p>\n'),
        ("[foo]:\n\n[foo]\n", "<p>[foo]:</p>\n<p>[foo]</p>\n"),
        ("[foo]: <>\n\n[foo]\n", '<p><a href="">foo</a></p>\n'),
        ("[foo]: <bar>(baz)\n\n[foo]\n", "<p>[foo]: <bar>(baz)</p>\n<p>[foo]</p>\n"),
        (
            '[foo]: /url\\bar\\*baz "foo\\"bar\\baz"\n\n[foo]\n',
            '<p><a href="/url%5Cbar*baz" title="foo&quot;bar\\baz">foo</a></p>\n',
        ),
        ("[foo]\n\n[foo]: url\n", '<p><a href="url">foo</a></p>\n'),
        ("[foo]\n\n[foo]: first\n[foo]: second\n", '<p><a href="first">foo</a></p>\n'),
        ("[FOO]: /url\n\n[Foo]\n", '<p><a href="/url">Foo</a></p>\n'),
        ("[ΑΓΩ]: /φου\n\n[αγω]\n", '<p><a href="/%CF%86%CE%BF%CF%85">αγω</a></p>\n'),
        ("[foo]: /url\n", ""),
        ("[\nfoo\n]: /url\nbar\n", "<p>bar</p>\n"),
        ('[foo]: /url "title" ok\n', "<p>[foo]: /url &quot;title&quot; ok</p>\n"),
        ('[foo]: /url\n"title" ok\n', "<p>&quot;title&quot; ok</p>\n"),
        (
            '    [foo]: /url "title"\n\n[foo]\n',
            "<pre><code>[foo]: /url &quot;title&quot;\n</code></pre>\n<p>[foo]</p>\n",
        ),
        (
            "```\n[foo]: /url\n```\n\n[foo]\n",
            "<pre><code>[foo]: /url\n</code></pre>\n<p>[foo]</p>\n",
        ),
        ("Foo\n[bar]: /baz\n\n[bar]\n", "<p>Foo\n[bar]: /baz</p>\n<p>[bar]</p>\n"),
        (
            "# [Foo]\n[foo]: /url\n> bar\n",
            '<h1><a href="/url">Foo</a></h1>\n<blockquote>\n<p>bar</p>\n'
            '</blockquote>\n',
        ),
        (
            "[foo]: /url\nbar\n===\n[foo]\n",
            '<h1>bar</h1>\n<p><a href="/url">foo</a></p>\n',
        ),
        ("[foo]: /url\n===\n[foo]\n", '<p>===\n<a href="/url">foo</a></p>\n'),
        (
            '[foo]: /foo-url "foo"\n[bar]: /bar-url\n  "bar"\n[baz]: /baz-url\n\n'
            "[foo],\n[bar],\n[baz]\n",
            '<p><a href="/foo-url" title="foo">foo</a>,\n'
            '<a href="/bar-url" title="bar">bar</a>,\n<a href="/baz-url">baz</a></p>\n',
        ),
        (
            "[foo]\n\n> [foo]: /url\n",
            '<p><a href="/url">foo</a></p>\n<blockquote>\n</blockquote>\n',
        ),
    ],
)
def test_link_reference_definitions(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("aaa\n\nbbb\n", "<p>aaa</p>\n<p>bbb</p>\n"),
        ("aaa\nbbb\n\nccc\nddd\n", "<p>aaa\nbbb</p>\n<p>ccc\nddd</p>\n"),
        ("aaa\n\n\nbbb\n", "<p>aaa</p>\n<p>bbb</p>\n"),
        ("  aaa\n bbb\n", "<p>aaa\nbbb</p>\n"),
        (
            "aaa\n             bbb\n                                       ccc\n",
            "<p>aaa\nbbb\nccc</p>\n",
        ),
        ("   aaa\nbbb\n", "<p>aaa\nbbb</p>\n"),
        ("    aaa\nbbb\n", "<pre><code>aaa\n</code></pre>\n<p>bbb</p>\n"),
        ("aaa     \nbbb     \n", "<p>aaa<br />\nbbb</p>\n"),
        ("  \n\naaa\n  \n\n# aaa\n\n  \n", "<p>aaa</p>\n<h1>aaa</h1>\n"),
    ],
)
def test_paragraphs_and_blank_lines(source, expected):
    assert to_html(source) == expected


_QUOTE = "<blockquote>\n<h1>Foo</h1>\n<p>bar\nbaz</p>\n</blockquote>\n"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("> # Foo\n> bar\n> baz\n", _QUOTE),
        ("># Foo\n>bar\n> baz\n", _QUOTE),
        ("   > # Foo\n   > bar\n > baz\n", _QUOTE),
        (
            "    > # Foo\n    > bar\n    > baz\n",
            "<pre><code>&gt; # Foo\n&gt; bar\n&gt; baz\n</code></pre>\n",
        ),
        ("> # Foo\n> bar\nbaz\n", _QUOTE),
        ("> bar\nbaz\n> foo\n", "<blockquote>\n<p>bar\nbaz\nfoo</p>\n</blockquote>\n"),
        ("> foo\n---\n", "<blockquote>\n<p>foo</p>\n</blockquote>\n<hr />\n"),
        (
            "> - foo\n- bar\n",
            "<blockquote>\n<ul>\n<li>foo</li>\n</ul>\n</blockquote>\n"
            "<ul>\n<li>bar</li>\n</ul>\n",
        ),
        (
            ">     foo\n    bar\n",
            "<blockquote>\n<pre><code>foo\n</code></pre>\n</blockquote>\n"
            "<pre><code>bar\n</code></pre>\n",
        ),
        (
            "> ```\nfoo\n```\n",
            "<blockquote>\n<pre><code></code></pre>\n</blockquote>\n<p>foo</p>\n"
            "<pre><code></code></pre>\n",
        ),
        ("> foo\n    - bar\n", "<blockquote>\n<p>foo\n- bar</p>\n</blockquote>\n"),
        (">\n", "<blockquote>\n</blockquote>\n"),
        (">\n>  \n> \n", "<blockquote>\n</blockquote>\n"),
        (">\n> foo\n>  \n", "<blockquote>\n<p>foo</p>\n</blockquote>\n"),
        (
            "> foo\n\n> bar\n",
            "<blockquote>\n<p>foo</p>\n</blockquote>\n<blockquote>\n<p>bar</p>\n"
            "</blockquote>\n",
        ),
        ("> foo\n> bar\n", "<blockquote>\n<p>foo\nbar</p>\n</blockquote>\n"),
        ("> foo\n>\n> bar\n", "<blockquote>\n<p>foo</p>\n<p>bar</p>\n</blockquote>\n"),
        ("foo\n> bar\n", "<p>foo</p>\n<blockquote>\n<p>bar</p>\n</blockquote>\n"),
        (
            "> aaa\n***\n> bbb\n",
            "<blockquote>\n<p>aaa</p>\n</blockquote>\n<hr />\n<blockquote>\n"
            "<p>bbb</p>\n"
            "</blockquote>\n",
        ),
        ("> bar\nbaz\n", "<blockquote>\n<p>bar\nbaz</p>\n</blockquote>\n"),
        ("> bar\n\nbaz\n", "<blockquote>\n<p>bar</p>\n</blockquote>\n<p>baz</p>\n"),
        ("> bar\n>\nbaz\n", "<blockquote>\n<p>bar</p>\n</blockquote>\n<p>baz</p>\n"),
        (
            "> > > foo\nbar\n",
            "<blockquote>\n<blockquote>\n<blockquote>\n<p>foo\nbar</p>\n</blockquote>\n"
            "</blockquote>\n</blockquote>\n",
        ),
        (
            ">>> foo\n> bar\n>>baz\n",
            "<blockquote>\n<blockquote>\n<blockquote>\n<p>foo\nbar\nbaz</p>\n"
            "</blockquote>\n</blockquote>\n</blockquote>\n",
        ),
        (
            ">     code\n\n>    not code\n",
            "<blockquote>\n<pre><code>code\n</code></pre>\n</blockquote>\n"
            "<blockquote>\n<p>not code</p>\n</blockquote>\n",
        ),
    ],
)
def test_block_quotes(source, expected):
    assert to_html(source) == expected


_ITEM = (
    "<ol>\n<li>\n<p>A paragraph\nwith two lines.</p>\n"
    "<pre><code>indented code\n</code></pre>\n"
    "<blockquote>\n<p>A block quote.</p>\n</blockquote>\n</li>\n</ol>\n"
)


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "1.  A paragraph\n    with two lines.\n\n        indented code\n\n"
            "    > A block quote.\n",
            _ITEM,
        ),
        ("- one\n\n two\n", "<ul>\n<li>one</li>\n</ul>\n<p>two</p>\n"),
        ("- one\n\n  two\n", "<ul>\n<li>\n<p>one</p>\n<p>two</p>\n</li>\n</ul>\n"),
        (
            " -    one\n\n     two\n",
            "<ul>\n<li>one</li>\n</ul>\n<pre><code> two\n</code></pre>\n",
        ),
        (
            " -    one\n\n      two\n",
            "<ul>\n<li>\n<p>one</p>\n<p>two</p>\n</li>\n</ul>\n",
        ),
        (
            "   > > 1.  one\n>>\n>>     two\n",
            "<blockquote>\n<blockquote>\n<ol>\n<li>\n<p>one</p>\n<p>two</p>\n</li>\n"
            "</ol>\n"
            "</blockquote>\n</blockquote>\n",
        ),
        (
            ">>- one\n>>\n  >  > two\n",
            "<blockquote>\n<blockquote>\n<ul>\n<li>one</li>\n</ul>\n<p>two</p>\n"
            "</blockquote>\n</blockquote>\n",
        ),
        ("-one\n\n2.two\n", "<p>-one</p>\n<p>2.two</p>\n"),
        ("- foo\n\n\n  bar\n", "<ul>\n<li>\n<p>foo</p>\n<p>bar</p>\n</li>\n</ul>\n"),
        (
            "1.  foo\n\n    ```\n    bar\n    ```\n\n    baz\n\n    > bam\n",
            "<ol>\n<li>\n<p>foo</p>\n<pre><code>bar\n</code></pre>\n<p>baz</p>\n"
            "<blockquote>\n<p>bam</p>\n</blockquote>\n</li>\n</ol>\n",
        ),
        (
            "- Foo\n\n      bar\n\n\n      baz\n",
            "<ul>\n<li>\n<p>Foo</p>\n<pre><code>bar\n\n\nbaz\n</code></pre>\n</li>\n"
            "</ul>\n",
        ),
        ("123456789. ok\n", '<ol start="123456789">\n<li>ok</li>\n</ol>\n'),
        ("1234567890. not ok\n", "<p>1234567890. not ok</p>\n"),
        ("0. ok\n", '<ol start="0">\n<li>ok</li>\n</ol>\n'),
        ("003. ok\n", '<ol start="3">\n<li>ok</li>\n</ol>\n'),
        ("-1. not ok\n", "<p>-1. not ok</p>\n"),
        (
            "- foo\n\n      bar\n",
            "<ul>\n<li>\n<p>foo</p>\n<pre><code>bar\n</code></pre>\n</li>\n</ul>\n",
        ),
        (
            "  10.  foo\n\n           bar\n",
            '<ol start="10">\n<li>\n<p>foo</p>\n<pre><code>bar\n</code></pre>\n</li>\n'
            "</ol>\n",
        ),
        (
            "1.     indented code\n\n   paragraph\n\n       more code\n",
            "<ol>\n<li>\n<pre><code>indented code\n</code></pre>\n<p>paragraph</p>\n"
            "<pre><code>more code\n</code></pre>\n</li>\n</ol>\n",
        ),
        (
            "1.      indented code\n\n   paragraph\n\n       more code\n",
            "<ol>\n<li>\n<pre><code> indented code\n</code></pre>\n<p>paragraph</p>\n"
            "<pre><code>more code\n</code></pre>\n</li>\n</ol>\n",
        ),
        ("-    foo\n\n  bar\n", "<ul>\n<li>foo</li>\n</ul>\n<p>bar</p>\n"),
        ("-  foo\n\n   bar\n", "<ul>\n<li>\n<p>foo</p>\n<p>bar</p>\n</li>\n</ul>\n"),
        (
            "-\n  foo\n-\n  ```\n  bar\n  ```\n-\n      baz\n",
            "<ul>\n<li>foo</li>\n<li>\n<pre><code>bar\n</code></pre>\n</li>\n<li>\n"
            "<pre><code>baz\n</code></pre>\n</li>\n</ul>\n",
        ),
        ("-   \n  foo\n", "<ul>\n<li>foo</li>\n</ul>\n"),
        ("-\n\n  foo\n", "<ul>\n<li></li>\n</ul>\n<p>foo</p>\n"),
        ("- foo\n-\n- bar\n", "<ul>\n<li>foo</li>\n<li></li>\n<li>bar</li>\n</ul>\n"),
        (
            "- foo\n-   \n- bar\n",
            "<ul>\n<li>foo</li>\n<li></li>\n<li>bar</li>\n</ul>\n",
        ),
        (
            "1. foo\n2.\n3. bar\n",
            "<ol>\n<li>foo</li>\n<li></li>\n<li>bar</li>\n</ol>\n",
        ),
        ("*\n", "<ul>\n<li></li>\n</ul>\n"),
        ("foo\n*\n\nfoo\n1.\n", "<p>foo\n*</p>\n<p>foo\n1.</p>\n"),
        (
            " 1.  A paragraph\n     with two lines.\n\n         indented code\n\n"
            "     > A block quote.\n",
            _ITEM,
        ),
        (
            "    1.  A paragraph\n        with two lines.\n\n"
            "            indented code\n\n"
            "        > A block quote.\n",
            "<pre><code>1.  A paragraph\n    with two lines.\n\n        indented code\n"
            "\n    &gt; A block quote.\n</code></pre>\n",
        ),
        (
            "  1.  A paragraph\nwith two lines.\n\n          indented code\n\n"
            "      > A block quote.\n",
            _ITEM,
        ),
        (
            "  1.  A paragraph\n    with two lines.\n",
            "<ol>\n<li>A paragraph\nwith two lines.</li>\n</ol>\n",
        ),
        (
            "> 1. > Blockquote\ncontinued here.\n",
            "<blockquote>\n<ol>\n<li>\n<blockquote>\n<p>Blockquote\n"
            "continued here.</p>\n"
            "</blockquote>\n</li>\n</ol>\n</blockquote>\n",
        ),
        (
            "- foo\n  - bar\n    - baz\n      - boo\n",
            "<ul>\n<li>foo\n<ul>\n<li>bar\n<ul>\n<li>baz\n<ul>\n<li>boo</li>\n</ul>\n"
            "</li>\n</ul>\n</li>\n</ul>\n</li>\n</ul>\n",
        ),
        (
            "- foo\n - bar\n  - baz\n   - boo\n",
            "<ul>\n<li>foo</li>\n<li>bar</li>\n<li>baz</li>\n<li>boo</li>\n</ul>\n",
        ),
        (
            "10) foo\n    - bar\n",
            '<ol start="10">\n<li>foo\n<ul>\n<li>bar</li>\n</ul>\n</li>\n</ol>\n',
        ),
        (
            "10) foo\n   - bar\n",
            '<ol start="10">\n<li>foo</li>\n</ol>\n<ul>\n<li>bar</li>\n</ul>\n',
        ),
        ("- - foo\n", "<ul>\n<li>\n<ul>\n<li>foo</li>\n</ul>\n</li>\n</ul>\n"),
        (
            "1. - 2. foo\n",
            '<ol>\n<li>\n<ul>\n<li>\n<ol start="2">\n<li>foo</li>\n</ol>\n</li>\n'
            '</ul>\n'
            "</li>\n</ol>\n",
        ),
        (
            "- # Foo\n- Bar\n  ---\n  baz\n",
            "<ul>\n<li>\n<h1>Foo</h1>\n</li>\n<li>\n<h2>Bar</h2>\nbaz</li>\n</ul>\n",
        ),
    ],
)
def test_list_items(source, expected):
    assert to_html(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "- foo\n- bar\n+ baz\n",
            "<ul>\n<li>foo</li>\n<li>bar</li>\n</ul>\n<ul>\n<li>baz</li>\n</ul>\n",
        ),
        (
            "1. foo\n2. bar\n3) baz\n",
            '<ol>\n<li>foo</li>\n<li>bar</li>\n</ol>\n<ol start="3">\n<li>baz</li>\n'
            "</ol>\n",
        ),
        (
            "Foo\n- bar\n- baz\n",
            "<p>Foo</p>\n<ul>\n<li>bar</li>\n<li>baz</li>\n</ul>\n",
        ),
        (
            "The number of windows in my house is\n14.  The number of doors is 6.\n",
            "<p>The number of windows in my house is\n"
            "14.  The number of doors is 6.</p>\n",
        ),
        (
            "The number of windows in my house is\n1.  The number of doors is 6.\n",
            "<p>The number of windows in my house is</p>\n<ol>\n"
            "<li>The number of doors is 6.</li>\n</ol>\n",
        ),
        (
            "- foo\n\n- bar\n\n\n- baz\n",
            "<ul>\n<li>\n<p>foo</p>\n</li>\n<li>\n<p>bar</p>\n</li>\n<li>\n<p>baz</p>\n"
            "</li>\n</ul>\n",
        ),
        (
            "- foo\n  - bar\n    - baz\n\n\n      bim\n",
            "<ul>\n<li>foo\n<ul>\n<li>bar\n<ul>\n<li>\n<p>baz</p>\n<p>bim</p>\n</li>\n"
            "</ul>\n</li>\n</ul>\n</li>\n</ul>\n",
        ),
        (
            "- foo\n- bar\n\n<!-- -->\n\n- baz\n- bim\n",
            "<ul>\n<li>foo</li>\n<li>bar</li>\n</ul>\n<!-- -->\n<ul>\n<li>baz</li>\n"
            "<li>bim</li>\n</ul>\n",
        ),
        (
            "-   foo\n\n    notcode\n\n-   foo\n\n<!-- -->\n\n    code\n",
            "<ul>\n<li>\n<p>foo</p>\n<p>notcode</p>\n</li>\n<li>\n<p>foo</p>\n</li>\n"
            "</ul>\n<!-- -->\n<pre><code>code\n</code></pre>\n",
        ),
        (
            "- a\n - b\n  - c\n   - d\n  - e\n - f\n- g\n",
            "<ul>\n<li>a</li>\n<li>b</li>\n<li>c</li>\n<li>d</li>\n<li>e</li>\n"
            "<li>f</li>\n<li>g</li>\n</ul>\n",
        ),
        (
            "1. a\n\n  2. b\n\n   3. c\n",
            "<ol>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n</li>\n<li>\n<p>c</p>\n"
            "</li>\n"
            "</ol>\n",
        ),
        (
            "- a\n - b\n  - c\n   - d\n    - e\n",
            "<ul>\n<li>a</li>\n<li>b</li>\n<li>c</li>\n<li>d\n- e</li>\n</ul>\n",
        ),
        (
            "1. a\n\n  2. b\n\n    3. c\n",
            "<ol>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n</li>\n</ol>\n"
            "<pre><code>3. c\n</code></pre>\n",
        ),
        (
            "- a\n- b\n\n- c\n",
            "<ul>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n</li>\n<li>\n<p>c</p>\n"
            "</li>\n"
            "</ul>\n",
        ),
        (
            "* a\n*\n\n* c\n",
            "<ul>\n<li>\n<p>a</p>\n</li>\n<li></li>\n<li>\n<p>c</p>\n</li>\n</ul>\n",
        ),
        (
            "- a\n- b\n\n  c\n- d\n",
            "<ul>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n<p>c</p>\n</li>\n<li>\n"
            "<p>d</p>\n</li>\n</ul>\n",
        ),
        (
            "- a\n- b\n\n  [ref]: /url\n- d\n",
            "<ul>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n</li>\n<li>\n<p>d</p>\n"
            "</li>\n"
            "</ul>\n",
        ),
        (
            "- a\n- ```\n  b\n\n\n  ```\n- c\n",
            "<ul>\n<li>a</li>\n<li>\n<pre><code>b\n\n\n</code></pre>\n</li>\n"
            "<li>c</li>\n</ul>\n",
        ),
        (
            "- a\n  - b\n\n    c\n- d\n",
            "<ul>\n<li>a\n<ul>\n<li>\n<p>b</p>\n<p>c</p>\n</li>\n</ul>\n</li>\n"
            "<li>d</li>\n</ul>\n",
        ),
        (
            "* a\n  > b\n  >\n* c\n",
            "<ul>\n<li>a\n<blockquote>\n<p>b</p>\n</blockquote>\n</li>\n<li>c</li>\n"
            "</ul>\n",
        ),
        (
            "- a\n  > b\n  ```\n  c\n  ```\n- d\n",
            "<ul>\n<li>a\n<blockquote>\n<p>b</p>\n</blockquote>\n"
            "<pre><code>c\n</code></pre>\n</li>\n<li>d</li>\n</ul>\n",
        ),
        ("- a\n", "<ul>\n<li>a</li>\n</ul>\n"),
        ("- a\n  - b\n", "<ul>\n<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>\n</ul>\n"),
        (
            "1. ```\n   foo\n   ```\n\n   bar\n",
            "<ol>\n<li>\n<pre><code>foo\n</code></pre>\n<p>bar</p>\n</li>\n</ol>\n",
        ),
        (
            "* foo\n  * bar\n\n  baz\n",
            "<ul>\n<li>\n<p>foo</p>\n<ul>\n<li>bar</li>\n</ul>\n<p>baz</p>\n</li>\n"
            "</ul>\n",
        ),
        (
            "- a\n  - b\n  - c\n\n- d\n  - e\n  - f\n",
            "<ul>\n<li>\n<p>a</p>\n<ul>\n<li>b</li>\n<li>c</li>\n</ul>\n</li>\n<li>\n"
            "<p>d</p>\n<ul>\n<li>e</li>\n<li>f</li>\n</ul>\n</li>\n</ul>\n",
        ),
    ],
)
def test_lists(source, expected):
    assert to_html(source) == expected
