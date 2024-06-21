from __future__ import annotations

import pytest

from inkstone.assets import AssetError, minify_html
from inkstone.assets.html import tokenize


def types(html):
    return [tok.type for tok in tokenize(html)]


def test_token_sequence():
    html = "<!DOCTYPE html><p class=a>Hi<br/></p><!-- c --><?php x ?><![CDATA[y]]>"
    tokens = tokenize(html)
    assert [tok.type for tok in tokens] == [
        "doctype",
        "start",
        "text",
        "start",
        "end",
        "comment",
        "pi",
        "cdata",
    ]
    assert [tok.name for tok in tokens if tok.name] == ["p", "br", "p"]
    assert "".join(tok.data for tok in tokens) == html


def test_attributes():
    html = "<A HREF=\"x.html\" title='say \"hi\"' data-n=1 hidden class = \"a b\">"
    (tok,) = tokenize(html)
    assert tok.name == "a"
    assert [(a.name, a.value, a.quote) for a in tok.attrs] == [
        ("HREF", "x.html", '"'),
        ("title", 'say "hi"', "'"),
        ("data-n", "1", ""),
        ("hidden", None, ""),
        ("class", "a b", '"'),
    ]
    for attr in tok.attrs:
        if attr.value is not None:
            assert html[attr.start : attr.end] == attr.value
    assert tok.get("href") == "x.html"
    assert tok.get("hidden") == ""
    assert tok.get("nope") is None


@pytest.mark.parametrize(
    "html, self_closing, last_value",
    [
        ("<br>", False, None),
        ("<br/>", True, None),
        ("<br />", True, None),
        ('<img src="a.png"/>', True, "a.png"),
        ("<a href=x/>", False, "x/"),
        ("<a href=x />", True, "x"),
        ("<a href=>", False, ""),
    ],
)
def test_self_closing_slash(html, self_closing, last_value):
    (tok,) = tokenize(html)
    assert tok.self_closing is self_closing
    assert (tok.attrs[-1].value if tok.attrs else None) == last_value


@pytest.mark.parametrize(
    "html, body",
    [
        ('<script>if (a < b) { x = "</p>" }</script>', 'if (a < b) { x = "</p>" }'),
        ("<script>a = '<!--' + '<script>'</script>", "a = '<!--' + '<script>'"),
        ("<style>a > b { }</style>", "a > b { }"),
        ("<textarea><b>not a tag</b></textarea>", "<b>not a tag</b>"),
        ("<title>a < b</title>", "a < b"),
        ("<SCRIPT>x</SCRIPT >", "x"),
        ("<script>x</scripty>y</script>", "x</scripty>y"),
        ("<script>never closed", "never closed"),
    ],
)
def test_raw_text_elements(html, body):
    tokens = tokenize(html)
    assert tokens[1].type == "raw"
    assert tokens[1].data == body


def test_stray_angle_brackets_are_text():
    assert types("a < b and 1 <2 or <> </ >") == ["text"]
    assert types("x<3<p>") == ["text", "start"]


def test_empty_comments():
    assert types("<!-->a<!--->b<!---->") == [
        "comment",
        "text",
        "comment",
        "text",
        "comment",
    ]


@pytest.mark.parametrize(
    "html, line, what",
    [
        ("<p>\n<!-- never closed", 2, "comment"),
        ("<p>\n\n<a href='x", 3, "value for attribute 'href'"),
        ("<p>\n<a href=x", 2, "<a> tag"),
        ("</p", 1, "</p> tag"),
    ],
)
def test_unterminated_constructs_report_the_line(html, line, what):
    with pytest.raises(AssetError) as info:
        tokenize(html, "page.html")
    assert info.value.line == line
    assert info.value.path == "page.html"
    assert info.value.message == f"unterminated {what}"


MINIFY_CASES = [
    # whitespace in text
    ("<p>  a   b  </p>", "<p>a b</p>"),
    ("<p>a</p>\n\n<p>b</p>\n", "<p>a</p><p>b</p>"),
    ("<p>a <b>b</b> c</p>", None),
    ("<p>a<b> b </b>c</p>", None),
    ("<span>a</span> <span>b</span>", None),
    ("<span>a</span>\n    <span>b</span>", "<span>a</span> <span>b</span>"),
    ("<div> <span>a</span> </div>", "<div><span>a</span></div>"),
    ("<ul>\n  <li>a</li>\n  <li>b</li>\n</ul>", "<ul><li>a</li><li>b</li></ul>"),
    ("<p>a <br> b</p>", "<p>a<br>b</p>"),
    ("<p>a\u00a0 \u00a0b</p>", None),
    ("  just text  ", "just text"),
    ("<label>a</label> <input> <button>b</button>", None),
    # elements that keep their whitespace
    ("<pre>  a\n  b  </pre>", None),
    ("<pre><code> a\n</code></pre>\n<p>x</p>", "<pre><code> a\n</code></pre><p>x</p>"),
    ("<pre>\n<b> a </b>\n</pre>", None),
    ("<textarea>\n  a  </textarea>", None),
    ("<title>\n  A   B\n</title>", "<title>A B</title>"),
    # comments
    ("<p>a<!-- c -->b</p>", "<p>ab</p>"),
    ("<p>a <!-- c --> b</p>", "<p>a b</p>"),
    ("<div><!-- c --> <!-- d --></div>", "<div></div>"),
    ("<!--[if IE]><p>x</p><![endif]-->", None),
    ("<!--[if !IE]><!--><p>x</p><!--<![endif]-->", None),
    ("<!--! keep --><p>x</p>", None),
    ('<!--#include virtual="x.html" -->', None),
    # doctype
    ("<!DOCTYPE html>\n<html></html>", "<!doctype html><html></html>"),
    (
        '<!DOCTYPE html PUBLIC\n  "-//W3C//DTD XHTML 1.0 Strict//EN">',
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">',
    ),
    # tags and attributes
    ('<P CLASS="a"  ID=b >x</P >', '<p class="a" id="b">x</p>'),
    ('<p class="  a   b ">x</p>', '<p class="a b">x</p>'),
    ("<a title='say \"hi\"'>x</a>", None),
    (
        '<input disabled="disabled" checked="" required>',
        "<input disabled checked required>",
    ),
    ('<input DISABLED="Disabled">', "<input disabled>"),
    ('<input value="">', None),
    ('<div hidden="until-found">x</div>', None),
    ('<img src="a.png" />', '<img src="a.png">'),
    ("<br/>", "<br>"),
    ('<input type="text">', None),
    (
        '<script type="text/javascript" src="a.js"></script>',
        '<script src="a.js"></script>',
    ),
    (
        '<script language="JavaScript" src="a.js"></script>',
        '<script src="a.js"></script>',
    ),
    ('<script type="module" src="a.js"></script>', None),
    (
        '<link rel="stylesheet" type="text/css" href="a.css">',
        '<link rel="stylesheet" href="a.css">',
    ),
    ('<link rel="alternate" type="text/css" href="a.css">', None),
    ('<form method="GET" action="/s"></form>', '<form action="/s"></form>'),
    ('<form method="post"></form>', None),
    ('<p style="color: red; margin: 0px">x</p>', '<p style="color:red;margin:0">x</p>'),
    ('<p style="font-family: &quot;A B&quot;">x</p>', None),
    # inline styles and scripts
    (
        '<style type="text/css">\n a { color: #FFFFFF }\n</style>',
        "<style>a{color:#fff}</style>",
    ),
    ("<script>\n  var a = 1; // c\n</script>", "<script>var a=1;</script>"),
    (
        '<script type="application/ld+json">\n{ "a": [1, 2] }\n</script>',
        '<script type="application/ld+json">{"a":[1,2]}</script>',
    ),
    ('<script type="text/x-template">\n <p> a </p>\n</script>', None),
    ("<script>var a = 'oops\n</script>", None),
    ("<script><!--\nalert(1)\n//--></script>", None),
    ("<style>a{top:0}}</style>", None),
    ('<script type="application/json">{not json}</script>', None),
    # head and other invisible elements
    (
        "<head>\n  <meta charset=utf-8>\n  <title>x</title>\n</head>",
        '<head><meta charset="utf-8"><title>x</title></head>',
    ),
    (
        "<p>x</p>\n<script src=a.js></script>\n<script src=b.js></script>\n",
        '<p>x</p><script src="a.js"></script><script src="b.js"></script>',
    ),
    ("a <script>x()</script> b", None),
    # svg
    (
        '<svg viewBox="0 0 1 1">\n  <linearGradient id="g" />\n'
        '  <path d="M0 0" />\n</svg>',
        '<svg viewBox="0 0 1 1"><linearGradient id="g"/><path d="M0 0"/></svg>',
    ),
    ("<svg><text>  a  b </text></svg>", None),
    ("<p>a <svg></svg> b</p>", None),
    ('<svg><a xlink:href="#x" preserveAspectRatio="none"/></svg>', None),
]


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify(before, after):
    assert minify_html(before) == (before if after is None else after)


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify_is_idempotent(before, after):
    once = minify_html(before)
    assert minify_html(once) == once


def test_json_script_cannot_break_out_of_its_element():
    html = '<script type="application/json">{"a": "<\\/script><!-- x"}</script>'
    assert minify_html(html) == (
        '<script type="application/json">{"a":"<\\/script><\\u0021-- x"}</script>'
    )


@pytest.mark.parametrize(
    "before, after",
    [
        ('<p class="a" id="b c" title="">x</p>', '<p class=a id="b c" title="">x</p>'),
        ('<a href="a/b.html?x=1">x</a>', '<a href="a/b.html?x=1">x</a>'),
        ('<a href="a/b.html">x</a>', "<a href=a/b.html>x</a>"),
        ('<img src="a.png" alt="it\'s">', '<img src=a.png alt="it\'s">'),
        ('<svg><path d="M0" /></svg>', "<svg><path d=M0 /></svg>"),
        ('<input value="a>b">', '<input value="a>b">'),
    ],
)
def test_remove_attribute_quotes(before, after):
    assert minify_html(before, remove_attribute_quotes=True) == after


def test_options_can_be_switched_off():
    html = (
        '<!-- c -->\n<p  class="a"> x  y </p>\n<input disabled="disabled">'
        '<script type="text/javascript"> a = 1; </script><style> a { top: 0 } </style>'
    )
    assert minify_html(html, remove_comments=False).startswith("<!-- c --><p")
    assert minify_html(html, collapse_whitespace=False).startswith(
        '\n<p class="a"> x  y </p>\n<input disabled>'
    )
    assert 'disabled="disabled"' in minify_html(html, collapse_boolean_attributes=False)
    assert "text/javascript" in minify_html(html, remove_default_attributes=False)
    assert "<script> a = 1; </script>" in minify_html(html, minify_js=False)
    assert "<style> a { top: 0 } </style>" in minify_html(html, minify_css=False)
    assert minify_html(html).endswith("<script>a=1;</script><style>a{top:0}</style>")


def test_minify_whole_document():
    html = (
        "\ufeff<!DOCTYPE html>\r\n"
        '<html lang="en">\r\n'
        "  <head>\r\n"
        '    <meta charset="utf-8">\r\n'
        "    <!-- build: 123 -->\r\n"
        '    <link rel="stylesheet" href="/css/site.css">\r\n'
        "  </head>\r\n"
        '  <body class="home">\r\n'
        "    <h1>  Hello,   <em>world</em>  !  </h1>\r\n"
        "    <p>\r\n      Some <b>bold</b> <i>text</i>.\r\n    </p>\r\n"
        "  </body>\r\n"
        "</html>\r\n"
    )
    assert minify_html(html) == (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<link rel="stylesheet" href="/css/site.css"></head>'
        '<body class="home"><h1>Hello, <em>world</em> !</h1>'
        "<p>Some <b>bold</b> <i>text</i>.</p></body></html>"
    )


def test_minify_reports_errors_with_path():
    with pytest.raises(AssetError) as info:
        minify_html("<p>\n<!-- oops", path="index.html")
    assert str(info.value) == "index.html:2: unterminated comment"
