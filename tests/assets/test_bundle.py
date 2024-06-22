from __future__ import annotations

import pytest

from inkstone.assets import AssetError, Bundle
from inkstone.assets.bundle import concat_css, concat_js

FILES = [
    "css/main.css",
    "css/reset.css",
    "js/app.js",
    "js/vendor/b.js",
    "js/vendor/a.js",
    "js/vendor/c.min.js",
]


def test_bundle_normalises_its_paths():
    bundle = Bundle("/css\\site.css", ["./css/reset.css", "css\\main.css"])
    assert bundle.output == "css/site.css"
    assert bundle.inputs == ["css/reset.css", "css/main.css"]
    assert bundle.minify is None


def test_bundle_accepts_a_single_input_string():
    assert Bundle("js/all.js", "js/app.js").inputs == ["js/app.js"]


def test_bundle_needs_inputs():
    with pytest.raises(AssetError, match="no inputs") as info:
        Bundle("js/all.js", [])
    assert info.value.path == "js/all.js"


@pytest.mark.parametrize(
    "output, kind",
    [
        ("css/site.css", "css"),
        ("SITE.CSS", "css"),
        ("js/app.js", "js"),
        ("js/app.mjs", "js"),
        ("data/all.json", ""),
        ("README", ""),
    ],
)
def test_bundle_kind(output, kind):
    assert Bundle(output, ["x"]).kind == kind


def test_expand_keeps_the_given_order():
    bundle = Bundle("css/site.css", ["css/reset.css", "css/main.css"])
    assert bundle.expand(FILES) == ["css/reset.css", "css/main.css"]
    bundle = Bundle("css/site.css", ["css/main.css", "css/reset.css"])
    assert bundle.expand(FILES) == ["css/main.css", "css/reset.css"]


def test_expand_globs_in_sorted_order():
    bundle = Bundle("js/all.js", ["js/vendor/*.js", "js/app.js"])
    assert bundle.expand(FILES) == [
        "js/vendor/a.js",
        "js/vendor/b.js",
        "js/vendor/c.min.js",
        "js/app.js",
    ]


def test_expand_includes_each_file_once():
    bundle = Bundle("js/all.js", ["js/vendor/b.js", "js/vendor/*.js", "js/vendor/b.js"])
    assert bundle.expand(FILES) == [
        "js/vendor/b.js",
        "js/vendor/a.js",
        "js/vendor/c.min.js",
    ]


def test_expand_may_include_a_source_named_like_the_output():
    bundle = Bundle("js/app.js", ["js/vendor/a.js", "js/*.js"])
    assert bundle.expand(FILES) == [
        "js/vendor/a.js",
        "js/app.js",
        "js/vendor/b.js",
        "js/vendor/c.min.js",
    ]


@pytest.mark.parametrize("name", ["js/missing.js", "fonts/*.woff2", "JS/app.js"])
def test_expand_missing_input(name):
    with pytest.raises(AssetError, match="does not match any file") as info:
        Bundle("js/all.js", ["js/app.js", name]).expand(FILES)
    assert info.value.path == "js/all.js"


@pytest.mark.parametrize(
    "sources, expected",
    [
        (["var a = 1", "(function () {})()"], "var a = 1;\n(function () {})();\n"),
        (["var a = 1;", "var b = 2;\n\n"], "var a = 1;\nvar b = 2;\n"),
        (["var a = 1 // one", "var b = 2"], "var a = 1 // one\n;\nvar b = 2;\n"),
        (["var a = 1; // one", "var b = 2"], "var a = 1; // one\nvar b = 2;\n"),
        (["var a = 1 /* one */", "var b"], "var a = 1 /* one */;\nvar b;\n"),
        (["function f() {}", "f()"], "function f() {};\nf();\n"),
        (["", "  \n", "var a"], "var a;\n"),
        (["// just a comment", "var a"], "// just a comment\nvar a;\n"),
        (["a = `x`", "b = /y/"], "a = `x`;\nb = /y/;\n"),
        ([], ""),
    ],
)
def test_concat_js(sources, expected):
    parts = [(f"{i}.js", source) for i, source in enumerate(sources)]
    assert concat_js(parts) == expected


def test_concat_js_reports_the_broken_file():
    with pytest.raises(AssetError) as info:
        concat_js([("a.js", "var a"), ("b.js", "var b = 'oops")])
    assert info.value.path == "b.js"


def test_concat_css_hoists_charset_and_imports():
    parts = [
        (
            "a.css",
            '@charset "utf-8";\n@import url(https://example.com/a.css);\na{top:0}\n',
        ),
        (
            "b.css",
            '@charset "latin1";\n/* b */\n@import "https://example.com/b.css" print;\n'
            "@import url(https://example.com/a.css);\nb{top:0}\n",
        ),
        ("c.css", "c{top:0}\n@import 'too-late.css';\n"),
    ]
    assert concat_css(parts) == (
        '@charset "utf-8";\n'
        "@import url(https://example.com/a.css);\n"
        '@import "https://example.com/b.css" print;\n'
        "a{top:0}\n"
        "/* b */\n\n\nb{top:0}\n"
        "c{top:0}\n@import 'too-late.css';\n"
    )


def test_concat_css_plain_files():
    parts = [("a.css", "a{top:0}"), ("b.css", "\n"), ("c.css", "c{top:0}\n")]
    assert concat_css(parts) == "a{top:0}\nc{top:0}\n"
    assert concat_css([]) == ""


def test_concat_css_leaves_layer_statements_in_place():
    parts = [("a.css", "@layer base, theme;\n@import 'x.css';\na{top:0}")]
    assert concat_css(parts) == "@import 'x.css';\n@layer base, theme;\n\na{top:0}\n"


def test_concat_dispatches_on_the_output_type():
    parts = [("a", "one"), ("b", "two")]
    assert Bundle("x.js", ["a", "b"]).concat(parts) == "one;\ntwo;\n"
    assert Bundle("x.css", ["a", "b"]).concat(parts) == "one\ntwo\n"
    assert Bundle("x.txt", ["a", "b"]).concat(parts) == "one\ntwo"
