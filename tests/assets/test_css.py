from __future__ import annotations

import pytest

from inkstone.assets import AssetError
from inkstone.assets.css import (
    inline_imports,
    minify_css,
    minify_declarations,
    rebase_urls,
    rewrite_urls,
    tokenize,
    unescape,
)


def types(css):
    return [tok.type for tok in tokenize(css)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12", "number"),
        ("-1.5e3", "number"),
        ("+.5", "number"),
        ("1e3", "number"),
        ("50%", "percentage"),
        ("1.5em", "dimension"),
        ("1e3px", "dimension"),
        ("#fff", "hash"),
        ("#", "delim"),
        ("@media", "at"),
        ("@", "delim"),
        ("--main-color", "ident"),
        ("-webkit-box", "ident"),
        ("\u00e9t\u00e9", "ident"),
        ("\\31 23", "ident"),
        ("a\\:b", "ident"),
        ("rgb(", "function"),
        ("url(a.png)", "url"),
        ("url(  a.png  )", "url"),
        ("URL(a.png)", "url"),
        ("url(a b)", "bad-url"),
        ('"a\\"b"', "string"),
        ("'a\\\nb'", "string"),
        ("/* x */", "comment"),
        ("<!--", "cdo"),
        ("-->", "cdc"),
        (" \t\n", "ws"),
    ],
)
def test_single_token(text, expected):
    tokens = tokenize(text)
    assert [tok.type for tok in tokens] == [expected]
    assert tokens[0].value == text


def test_token_sequence():
    assert types("a{b:1px}") == ["ident", "{", "ident", ":", "dimension", "}"]
    assert types("a>b") == ["ident", "delim", "ident"]
    assert types("-") == ["delim"]
    assert types("1-2") == ["number", "number"]
    assert types("1 - 2") == ["number", "ws", "delim", "ws", "number"]


def test_quoted_url_is_a_function_holding_a_string():
    assert types('url( "a.png" )') == ["function", "ws", "string", "ws", ")"]


def test_tokens_cover_the_source_exactly():
    css = (
        "@charset 'x'; /* c */ a:not(.b)>c[d~=\"e\"]{f:url( g.png ) -1.5e3px;"
        "--h:{i};j:calc(1px + 2%)}\r\n@media (k){l{m:n!important}}"
    )
    tokens = tokenize(css)
    assert "".join(tok.value for tok in tokens) == css
    assert all(css[tok.pos : tok.end] == tok.value for tok in tokens)
    assert tokens[-1].end == len(css)


@pytest.mark.parametrize(
    "css, line",
    [
        ("a{}\nb{c:'oops\n}", 2),
        ('a{b:"never closed', 1),
        ("a{}\n\n/* never closed", 3),
        ("a{}\r\nb{c:url(d", 2),
    ],
)
def test_unterminated_constructs_report_the_line(css, line):
    with pytest.raises(AssetError) as info:
        tokenize(css, "site.css")
    assert info.value.line == line
    assert info.value.path == "site.css"
    assert str(info.value).startswith(f"site.css:{line}: unterminated")


def test_escaped_newline_does_not_end_a_string():
    assert types("'a\\\r\nb'") == ["string"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("plain", "plain"),
        ("\\41", "A"),
        ("\\000041 b", "Ab"),
        ("\\41  b", "A b"),
        ("a\\:b", "a:b"),
        ("a\\\nb", "ab"),
        ("\\0", "\ufffd"),
    ],
)
def test_unescape(text, expected):
    assert unescape(text) == expected


MINIFY_CASES = [
    # whitespace and selectors
    ("a { color: red; }", "a{color:red}"),
    ("a{color:red;;}", "a{color:red}"),
    ("a , b > c + d ~ e { top: 0 }", "a,b>c+d~e{top:0}"),
    ("a   b\n\t.c{top:0}", "a b .c{top:0}"),
    ("a :hover{top:0}", "a :hover{top:0}"),
    ("a:not( .b , .c ){top:0}", "a:not(.b,.c){top:0}"),
    ("li:nth-child( 2n + 1 ){top:0}", "li:nth-child(2n+1){top:0}"),
    ("a[ href ^= 'http' ]{top:0}", "a[href^='http']{top:0}"),
    ("* + *{top:0}", "*+*{top:0}"),
    ("a *{top:0}", "a *{top:0}"),
    (".a\\:b , #Main{top:0}", ".a\\:b,#Main{top:0}"),
    ("a/**/b{top:0}", "a/**/b{top:0}"),
    ("a{color:red;&:hover{color:blue}.b &{top:0}}", None),
    ("a{top:0}\n<!-- b{top:0} -->", "a{top:0}b{top:0}"),
    # comments
    ("/* c */ a /* c */ { /* c */ top: 0 /* c */ }", "a{top:0}"),
    ("/*! keep */a{top:0}", None),
    ("a{top:0}/*! keep */", None),
    ("a{content:'  /* not a comment */  '}", None),
    # empty rules
    ("a{}", ""),
    ("a{ /* nothing */ }", ""),
    ("a{} b{top:0} c{;}", "b{top:0}"),
    ("@media print{a{}}", ""),
    ("@media print { a { top: 0 } b{} }", "@media print{a{top:0}}"),
    ("@keyframes x{}", None),
    ("@layer base{}", None),
    # colours
    ("a{color:#FFFFFF}", "a{color:#fff}"),
    ("a{color:#AABBCC}", "a{color:#abc}"),
    ("a{color:#A1B2C3}", "a{color:#a1b2c3}"),
    ("a{color:#ff0000}", "a{color:red}"),
    ("a{color:#FFFFFFFF}", "a{color:#fff}"),
    ("a{color:#11223344}", "a{color:#1234}"),
    ("a{color:rgb(255,0,0)}", "a{color:red}"),
    ("a{color:rgb(255, 255, 255)}", "a{color:#fff}"),
    ("a{color:rgb( 18 52 86 )}", "a{color:#123456}"),
    ("a{color:rgb(100%,0%,0%)}", "a{color:red}"),
    ("a{color:rgba(0,0,0,1)}", "a{color:#000}"),
    ("a{color:rgb(0 0 0 / 100%)}", "a{color:#000}"),
    ("a{color:rgba(0,0,0,0.5)}", "a{color:rgba(0,0,0,.5)}"),
    ("a{color:rgb(var(--r),0,0)}", None),
    ("a{color:rgb(127.5,0,0)}", None),
    ("a{color:hsl(0,100%,50%)}", "a{color:red}"),
    ("a{color:hsl(240deg 100% 50%)}", "a{color:#00f}"),
    ("a{color:hsl(120,100%,25%)}", None),
    ("a{color:white}", "a{color:#fff}"),
    ("a{color:BLACK}", "a{color:#000}"),
    ("a{color:red}", None),
    ("a{border:1px solid fuchsia}", "a{border:1px solid #f0f}"),
    ("a{font-family:White}", None),
    ("#FFF{color:#FFF}", "#FFF{color:#fff}"),
    (
        "a{background:linear-gradient(to right, white, #000000)}",
        "a{background:linear-gradient(to right,#fff,#000)}",
    ),
    # numbers and units
    ("a{margin:0px}", "a{margin:0}"),
    ("a{margin:0.0em}", "a{margin:0}"),
    ("a{margin:-0px}", "a{margin:0}"),
    ("a{width:0%}", None),
    ("a{transition:all 0s}", None),
    ("a{transform:rotate(0deg)}", None),
    ("a{transform:translate(0px, 0px)}", "a{transform:translate(0,0)}"),
    ("a{opacity:0.5}", "a{opacity:.5}"),
    ("a{margin:-0.5em}", "a{margin:-.5em}"),
    ("a{width:1.50px}", "a{width:1.5px}"),
    ("a{width:1.0px}", "a{width:1px}"),
    ("a{width:010px}", "a{width:10px}"),
    ("a{width:1e3px}", None),
    ("a{flex:1 1 0px}", None),
    ("a{width:calc(0px + 1em)}", None),
    ("a{width:calc( 100% - ( 2 * 10px ) )}", "a{width:calc(100% - (2*10px))}"),
    ("a{width:calc(1px / 2)}", "a{width:calc(1px/2)}"),
    ("a{width:var(--w, 0px)}", "a{width:var(--w,0px)}"),
    ("a{width:min(0.5em, 10px)}", "a{width:min(.5em,10px)}"),
    # shorthands
    ("a{margin:0 0 0 0}", "a{margin:0}"),
    ("a{margin:1px 2px 1px 2px}", "a{margin:1px 2px}"),
    ("a{margin:1px 2px 3px 2px}", "a{margin:1px 2px 3px}"),
    ("a{margin:1px 2px 3px 4px}", None),
    ("a{margin:1px 1px 2px}", None),
    ("a{padding:0px 0px}", "a{padding:0}"),
    ("a{margin:0 auto 0 auto}", "a{margin:0 auto}"),
    ("a{margin:0 0 0 0!important}", "a{margin:0!important}"),
    ("a{margin:0 0 0 0 ! important}", "a{margin:0!important}"),
    ("a{border-radius:1px 1px/2px 2px}", None),
    ("a{border-color:red red RED}", "a{border-color:red}"),
    ("a{gap:1em 1em}", "a{gap:1em}"),
    ("a{gap:1em 2em}", None),
    # keywords
    ("a{font-weight:bold}", "a{font-weight:700}"),
    ("a{font-weight:normal}", "a{font-weight:400}"),
    ("a{font-weight:bolder}", None),
    ("a{border:none}", None),
    ("a{outline:none !important}", "a{outline:none!important}"),
    ("a{COLOR:Red}", "a{color:Red}"),
    # values in general
    ("a{font:12px / 1.5 serif}", "a{font:12px/1.5 serif}"),
    ("a{font-family:'A B' , serif}", "a{font-family:'A B',serif}"),
    ("a{background:url( 'a.png' )}", "a{background:url(a.png)}"),
    ('a{background:url("a b.png")}', None),
    ("a{background:url( a.png )}", "a{background:url(a.png)}"),
    ("a{background:url(data:image/png;base64,AAAA==)}", None),
    ("a{grid-area:1 / 2 / 3}", "a{grid-area:1/2/3}"),
    (":root{--x: 0px ;--y:#FFFFFF;--z: }", ":root{--x:0px;--y:#FFFFFF;--z: }"),
    (":root{--j:{ a: b }}", None),
    ("a{*zoom:1}", None),
    ("@font-face{unicode-range:U+0025-00FF}", None),
    ("a{filter:progid:DXImageTransform.Microsoft.Shadow(color=#FF0000)}", None),
    # at-rules
    ('@charset "utf-8";', None),
    ("@import url(a.css)  screen;", "@import url(a.css) screen;"),
    ("@import 'a.css';a{top:0}", None),
    (
        "@media (min-width : 100px) and (max-width:200px){a{top:0}}",
        "@media (min-width:100px) and (max-width:200px){a{top:0}}",
    ),
    ("@media screen , print{a{top:0}}", "@media screen,print{a{top:0}}"),
    (
        "@media ( 400px <= width <= 700px ){a{top:0}}",
        "@media (400px<=width<=700px){a{top:0}}",
    ),
    (
        "@supports not ( display : grid ){a{top:0}}",
        "@supports not (display:grid){a{top:0}}",
    ),
    ("@MEDIA print{a{top:0}}", "@media print{a{top:0}}"),
    (
        "@font-face { font-family: X; src: url(x.woff2) format('woff2') }",
        "@font-face{font-family:X;src:url(x.woff2) format('woff2')}",
    ),
    (
        "@keyframes spin { from { top: 0 } 50% { top: 2px } 100% { top: 1px } }",
        "@keyframes spin{0%{top:0}50%{top:2px}to{top:1px}}",
    ),
    ("@layer a , b;", "@layer a,b;"),
    ("@page :first { margin: 1in }", "@page :first{margin:1in}"),
]


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify(before, after):
    assert minify_css(before) == (before if after is None else after)


@pytest.mark.parametrize("before, after", MINIFY_CASES)
def test_minify_is_idempotent(before, after):
    once = minify_css(before)
    assert minify_css(once) == once


def test_minify_normalises_line_endings_and_bom():
    assert minify_css("\ufeffa {\r\n  top: 0;\r\n}\r\n") == "a{top:0}"


def test_minify_closes_blocks_left_open_at_eof():
    assert minify_css("@media print{a{top:0") == "@media print{a{top:0}}"


def test_minify_rejects_stray_closing_brace():
    with pytest.raises(AssetError) as info:
        minify_css("a{top:0}\n}\nb{top:0}", path="x.css")
    assert info.value.line == 2
    assert "unexpected" in info.value.message


def test_minify_declarations():
    assert minify_declarations(" color : #FFFFFF ; margin : 0px 0px ; ") == (
        "color:#fff;margin:0"
    )
    assert minify_declarations("") == ""


def test_rewrite_urls_handles_every_form():
    css = (
        "@import 'base.css';\n"
        "a { background: url(a.png), url( \"b.png\" ), image-set('c.png' 1x) }\n"
        "b { content: 'd.png' }\n"
    )
    seen = []

    def fn(url):
        seen.append(url)
        return "x/" + url

    assert rewrite_urls(css, fn) == (
        "@import 'x/base.css';\n"
        "a { background: url(x/a.png), url( \"x/b.png\" ), image-set('x/c.png' 1x) }\n"
        "b { content: 'd.png' }\n"
    )
    assert seen == ["base.css", "a.png", "b.png", "c.png"]


def test_rewrite_urls_leaves_text_alone_when_fn_declines():
    css = "a{b:url( a.png )}  /* url(c.png) */"
    assert rewrite_urls(css, lambda url: None) == css
    assert rewrite_urls(css, lambda url: url) == css


def test_rewrite_urls_quotes_when_needed():
    assert rewrite_urls("a{b:url(a.png)}", lambda url: "a b(1).png") == (
        'a{b:url("a b(1).png")}'
    )
    assert rewrite_urls("a{b:url('a.png')}", lambda url: "it's.png") == (
        "a{b:url('it\\'s.png')}"
    )


def test_rewrite_urls_unescapes_before_calling_fn():
    seen = []
    rewrite_urls("a{b:url(a\\ b.png)}", seen.append)
    assert seen == ["a b.png"]


@pytest.mark.parametrize(
    "url, expected",
    [
        ("img/a.png", "vendor/img/a.png"),
        ("../img/a.png", "img/a.png"),
        ("a.png?v=2#x", "vendor/a.png?v=2#x"),
        ("/img/a.png", "/img/a.png"),
        ("https://example.com/a.png", "https://example.com/a.png"),
        ("//cdn.example.com/a.png", "//cdn.example.com/a.png"),
        ("data:image/png;base64,AAAA", "data:image/png;base64,AAAA"),
        ("#gradient", "#gradient"),
    ],
)
def test_rebase_urls(url, expected):
    css = f"a{{b:url({url})}}"
    assert rebase_urls(css, "css/vendor", "css") == f"a{{b:url({expected})}}"


def test_rebase_urls_upwards():
    assert rebase_urls("a{b:url(a.png)}", "css", "css/pages") == "a{b:url(../a.png)}"
    assert rebase_urls("a{b:url(a.png)}", "", "css") == "a{b:url(../a.png)}"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_inline_imports_nested(tmp_path):
    main = write(tmp_path / "main.css", '@import "a.css";\nbody{top:0}\n')
    write(tmp_path / "a.css", "@import url(b.css);\na{top:0}\n")
    write(tmp_path / "b.css", "b{top:0}\n")
    deps = []
    assert minify_css(inline_imports(main, deps=deps)) == "b{top:0}a{top:0}body{top:0}"
    assert deps == ["a.css", "b.css"]


def test_inline_imports_rebases_urls(tmp_path):
    main = write(tmp_path / "css" / "main.css", "@import 'vendor/lib.css';")
    write(
        tmp_path / "css" / "vendor" / "lib.css",
        "a{b:url(img/a.png);c:url(/abs.png);d:url(../up.png)}",
    )
    assert inline_imports(main) == (
        "a{b:url(vendor/img/a.png);c:url(/abs.png);d:url(up.png)}"
    )


def test_inline_imports_wraps_conditions(tmp_path):
    main = write(
        tmp_path / "main.css",
        "@import 'print.css' print and (orientation: landscape);\n"
        "@import url(grid.css) layer(layout) supports(display: grid) screen;\n"
        "@import 'anon.css' layer;\n",
    )
    write(tmp_path / "print.css", "a{top:0}")
    write(tmp_path / "grid.css", "b{top:0}")
    write(tmp_path / "anon.css", "c{top:0}")
    assert minify_css(inline_imports(main)) == (
        "@media print and (orientation:landscape){a{top:0}}"
        "@media screen{@supports (display:grid){@layer layout{b{top:0}}}}"
        "@layer{c{top:0}}"
    )


def test_inline_imports_leaves_external_imports(tmp_path):
    css = (
        "@import url(https://fonts.example.com/css?family=X);\n"
        "@import '//cdn.example.com/x.css';\n"
        "a{top:0}\n"
    )
    assert inline_imports(write(tmp_path / "main.css", css)) == css


def test_inline_imports_ignores_imports_after_rules(tmp_path):
    css = "a{top:0}\n@import 'missing.css';\n"
    assert inline_imports(write(tmp_path / "main.css", css)) == css


def test_inline_imports_drops_charset_of_imported_file(tmp_path):
    main = write(tmp_path / "main.css", '@charset "utf-8";\n@import "a.css";\n')
    write(tmp_path / "a.css", '@charset "utf-8";\na{top:0}\n')
    assert inline_imports(main) == '@charset "utf-8";\na{top:0}\n'


def test_inline_imports_detects_cycles(tmp_path):
    main = write(tmp_path / "main.css", "@import 'a.css';")
    write(tmp_path / "a.css", "/* hi */\n@import 'b.css';")
    write(tmp_path / "b.css", "@import 'a.css';")
    with pytest.raises(AssetError) as info:
        inline_imports(main)
    assert "circular @import: a.css -> b.css -> a.css" in str(info.value)
    assert info.value.path == "b.css"
    assert info.value.line == 1


def test_inline_imports_same_file_twice_is_not_a_cycle(tmp_path):
    main = write(tmp_path / "main.css", "@import 'a.css';@import 'b.css';")
    write(tmp_path / "a.css", "@import 'shared.css';")
    write(tmp_path / "b.css", "@import 'shared.css';")
    write(tmp_path / "shared.css", "s{top:0}")
    assert inline_imports(main) == "s{top:0}s{top:0}"


def test_inline_imports_missing_file(tmp_path):
    main = write(tmp_path / "main.css", "/* x */\n@import 'nope.css';")
    with pytest.raises(AssetError) as info:
        inline_imports(main)
    assert "nope.css" in info.value.message
    assert info.value.line == 2
    with pytest.raises(AssetError):
        inline_imports(tmp_path / "does-not-exist.css")


def test_inline_imports_root_relative(tmp_path):
    main = write(tmp_path / "css" / "pages" / "main.css", "@import '/css/base.css';")
    write(tmp_path / "css" / "base.css", "a{b:url(a.png)}")
    assert inline_imports(main, root=tmp_path) == "a{b:url(../a.png)}"
