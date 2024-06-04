from __future__ import annotations

import pytest

import inkstone.markdown as markdown
from inkstone.errors import InkstoneError
from inkstone.markdown import (
    DEFAULT_EXTENSIONS,
    CodeBlock,
    Document,
    Extension,
    HtmlRenderer,
    Markdown,
    MarkdownError,
    Paragraph,
    Reference,
    Text,
    available_extensions,
    render,
)
from inkstone.markdown.__main__ import main
from inkstone.markdown.blocks import parse_info

ALL_EXTENSIONS = [
    "tables",
    "strikethrough",
    "tasklists",
    "autolink",
    "footnotes",
    "deflists",
    "admonitions",
    "attrs",
    "smart",
    "toc",
    "abbr",
    "mark",
    "sub",
    "sup",
]


def test_convert_returns_html():
    assert Markdown().convert("Hello *world*") == "<p>Hello <em>world</em></p>\n"


def test_render_helper_takes_the_same_options():
    assert render("# Hi") == '<h1 id="hi">Hi</h1>\n'
    assert render("# Hi", heading_ids=False) == "<h1>Hi</h1>\n"
    assert render("a -- b", smart=True) == "<p>a \u2013 b</p>\n"
    assert render("~~a~~", extensions=[]) == "<p>~~a~~</p>\n"


@pytest.mark.parametrize("source", ["", "\n", "   \n\n  \n", "\ufeff"])
def test_empty_input_gives_empty_output(source):
    md = Markdown()
    assert md.convert(source) == ""
    assert md.parse(source).children == []


def test_parse_returns_a_document_and_render_accepts_it():
    md = Markdown()
    doc = md.parse("para")
    assert isinstance(doc, Document)
    assert isinstance(doc.children[0], Paragraph)
    assert md.render(doc) == "<p>para</p>\n"


def test_instance_can_be_reused():
    md = Markdown()
    first = md.convert("[a]\n\n[a]: /one\n")
    second = md.convert("[a]\n")
    assert 'href="/one"' in first
    assert second == "<p>[a]</p>\n"
    assert md.references == {}


@pytest.mark.parametrize("source", [None, b"bytes", 42, ["list"]])
def test_non_string_source_is_a_type_error(source):
    with pytest.raises(TypeError, match="must be str"):
        Markdown().convert(source)
    with pytest.raises(TypeError, match="must be str"):
        Markdown().convert_inline(source)


def test_default_extension_set():
    md = Markdown()
    assert md.extension_names == list(DEFAULT_EXTENSIONS)
    assert "smart" not in md.extension_names
    assert Markdown(extensions=None).extension_names == md.extension_names


def test_every_extension_is_registered():
    assert available_extensions() == ALL_EXTENSIONS
    assert set(DEFAULT_EXTENSIONS) < set(ALL_EXTENSIONS)
    md = Markdown(extensions=ALL_EXTENSIONS)
    assert md.extension_names == ALL_EXTENSIONS


def test_extensions_accepts_any_iterable_and_ignores_order_and_duplicates():
    md = Markdown(extensions=("toc", "tables", "tables"))
    assert md.extension_names == ["tables", "toc"]
    md = Markdown(extensions=iter(["footnotes"]))
    assert md.extension_names == ["footnotes"]
    assert Markdown(extensions="tables").extension_names == ["tables"]


def test_unknown_extension_is_a_markdown_error():
    with pytest.raises(MarkdownError, match="extension 'table'") as info:
        Markdown(extensions=["table"])
    assert "did you mean 'tables'" in str(info.value)
    assert isinstance(info.value, InkstoneError)


@pytest.mark.parametrize("bad", ["nonsense-xyz", "", 42, None])
def test_unknown_extension_without_a_close_match(bad):
    with pytest.raises(MarkdownError) as info:
        Markdown(extensions=[bad])
    assert "did you mean" not in str(info.value)


def test_each_default_extension_can_be_dropped_on_its_own():
    source = (
        "| a |\n|---|\n\n~~s~~\n\n- [ ] t\n\nwww.example.com\n\nF[^1]\n\n[^1]: n\n\n"
        "Term\n: Def\n\n!!! note\n    box\n\n## H {#custom}\n\n[TOC]\n"
    )
    markers = {
        "tables": "<table>",
        "strikethrough": "<del>",
        "tasklists": "checkbox",
        "autolink": 'href="http://www.example.com"',
        "footnotes": 'class="footnotes"',
        "deflists": "<dl>",
        "admonitions": 'class="admonition note"',
        "attrs": 'id="custom"',
        "toc": '<nav class="toc">',
    }
    full = Markdown().convert(source)
    for marker in markers.values():
        assert marker in full
    for name, marker in markers.items():
        others = [ext for ext in DEFAULT_EXTENSIONS if ext != name]
        html = Markdown(extensions=others).convert(source)
        assert marker not in html, name
        for other in others:
            assert markers[other] in html, (name, other)


def test_hard_wraps():
    assert render("a\nb", hard_wraps=True) == "<p>a<br />\nb</p>\n"
    assert render("a\nb") == "<p>a\nb</p>\n"
    assert render("# a\n\n- x\n  y\n", hard_wraps=True) == (
        '<h1 id="a">a</h1>\n<ul>\n<li>x<br />\ny</li>\n</ul>\n'
    )


def test_references_property():
    md = Markdown()
    md.convert('[Foo Bar]: /url "Title"\n[b]: <x y>\n\n[foo bar]\n')
    assert md.references == {
        "foo bar": Reference("Foo Bar", "/url", "Title"),
        "b": Reference("b", "x%20y", ""),
    }
    assert md.references["foo bar"].dest == "/url"


def test_reset_forgets_the_last_document():
    md = Markdown()
    md.convert("# T\n\n[a]: /b\n\nx[^1]\n\n[^1]: n\n")
    assert md.toc and md.references and md.footnotes
    md.reset()
    assert md.toc == [] and md.references == {} and md.footnotes == []


def test_highlight_callback_gets_code_and_language():
    calls = []

    def highlight(code, lang):
        calls.append((code, lang))
        return f'<pre class="hl">{code.upper()}</pre>'

    html = render("```py\nx = 1\n```\n\n    indented\n", highlight=highlight)
    assert calls == [("x = 1\n", "py"), ("indented\n", None)]
    assert html == '<pre class="hl">X = 1\n</pre>\n<pre class="hl">INDENTED\n</pre>\n'


def test_highlight_returning_none_falls_back():
    def highlight(code, lang):
        return "<pre>custom</pre>\n" if lang == "known" else None

    html = render("```known\na\n```\n\n```other\n<b>\n```\n", highlight=highlight)
    assert html == (
        '<pre>custom</pre>\n<pre><code class="language-other">&lt;b&gt;\n'
        '</code></pre>\n'
    )


def test_highlight_callback_may_ask_for_the_fence_attributes():
    seen = {}

    def highlight(code, lang, attrs=None):
        seen.update(attrs)
        return "<pre></pre>"

    render('```py {hl_lines="2" linenos}\na\nb\n```\n', highlight=highlight)
    assert seen == {"hl_lines": "2", "linenos": True}

    def with_kwargs(code, lang=None, **options):
        return "<pre>" + ",".join(sorted(options)) + "</pre>"

    # a catch-all is not a request for attrs
    assert render("```py {x=1}\na\n```\n", highlight=with_kwargs) == "<pre></pre>\n"


def test_highlight_can_be_a_builtin_or_bound_method():
    class Highlighter:
        def run(self, code, lang):
            return f"<pre>{lang}</pre>"

    assert render("```x\n```\n", highlight=Highlighter().run) == "<pre>x</pre>\n"


@pytest.mark.parametrize(
    "info, lang, attrs",
    [
        ("python", "python", {}),
        ("python {linenos}", "python", {"linenos": True}),
        ('py {hl_lines="1 3" linenos}', "py", {"hl_lines": "1 3", "linenos": True}),
        ("{.python linenos}", "python", {"linenos": True}),
        ("{.python .extra}", "python", {"class": "extra"}),
        ("{#a}", None, {"id": "a"}),
        ("", None, {}),
        ("ruby startline=3", "ruby", {}),
        ("py {x=1} trailing", "py", {}),
        ("py {.c1 .c2 k='v w'}", "py", {"class": "c1 c2", "k": "v w"}),
    ],
)
def test_parse_info(info, lang, attrs):
    assert parse_info(info) == (lang, attrs)


def test_code_block_node_keeps_info_language_and_attributes():
    doc = Markdown().parse("```py {a=1}\nx\n```\n\n    plain\n")
    fenced, indented = doc.find_all(CodeBlock)
    assert (fenced.info, fenced.lang, fenced.attrs) == ("py {a=1}", "py", {"a": "1"})
    assert fenced.fenced and fenced.literal == "x\n"
    assert (indented.info, indented.lang, indented.attrs) == ("", None, {})
    assert not indented.fenced and indented.literal == "plain\n"


def test_highlighted_lines_and_line_numbers_without_a_highlighter():
    html = render('```python {hl_lines="1 3" linenos}\na\nb\nc\n```\n')
    assert html == (
        '<pre><code class="language-python">'
        '<span class="line hl"><span class="lineno">1</span>a</span>\n'
        '<span class="line"><span class="lineno">2</span>b</span>\n'
        '<span class="line hl"><span class="lineno">3</span>c</span>\n'
        "</code></pre>\n"
    )


def test_line_number_options():
    html = render("```py {linenos=true linenostart=10}\na\nb\n```\n")
    assert '<span class="lineno">10</span>a' in html
    assert '<span class="lineno">11</span>b' in html
    assert "lineno" not in render("```py {linenos=false}\na\n```\n")
    assert "lineno" not in render('```py {hl_lines="1"}\na\n```\n')
    html = render('``` {hl_lines="2-3,5 x"}\n1\n2\n3\n4\n5\n```\n')
    assert html.count('class="line hl"') == 3
    assert '<span class="line hl">5</span>' in html


def test_other_fence_attributes_go_on_the_pre_element():
    html = render('```{.python .extra #snippet title="x.py"}\na\n```\n')
    assert html == (
        '<pre id="snippet" class="extra" title="x.py">'
        '<code class="language-python">a\n</code></pre>\n'
    )


def test_code_in_line_spans_is_escaped():
    html = render("```html {linenos}\n<a href=\"x\">&</a>\n```\n")
    assert "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;" in html


def test_convert_inline():
    md = Markdown()
    assert md.convert_inline("Hello *world* & `code`") == (
        "Hello <em>world</em> &amp; <code>code</code>"
    )
    assert md.convert_inline("# not a heading") == "# not a heading"
    assert md.convert_inline("two\nlines  here") == "two lines here"
    assert md.convert_inline("") == ""


def test_convert_inline_leaves_document_state_alone():
    md = Markdown()
    md.convert("# Title\n\n[ref]: /url\n")
    assert md.convert_inline("[ref] and ~~x~~") == "[ref] and <del>x</del>"
    assert [entry.title for entry in md.toc] == ["Title"]
    assert md.convert("[ref]\n\n[ref]: /again\n") == '<p><a href="/again">ref</a></p>\n'


def test_html_renderer_can_be_used_directly_and_on_subtrees():
    doc = Markdown().parse("# Title\n\nSome *text*.\n")
    renderer = HtmlRenderer()
    assert renderer.render(doc) == (
        '<h1 id="title">Title</h1>\n<p>Some <em>text</em>.</p>\n'
    )
    assert renderer.render(doc.children[1]) == "<p>Some <em>text</em>.</p>\n"
    assert renderer.render(doc.children[1].children[1]) == "<em>text</em>"


def test_html_renderer_can_be_subclassed():
    class Shouting(HtmlRenderer):
        def visit_text(self, node):
            self.write(node.literal.upper())

        def visit_thematic_break(self, node):
            self.newline()
            self.write('<hr class="fancy" />')
            self.newline()

    doc = Markdown().parse("quiet *words*\n\n---\n")
    assert Shouting().render(doc) == (
        '<p>QUIET <em>WORDS</em></p>\n<hr class="fancy" />\n'
    )


def test_custom_extension_instance():
    class Shout(Extension):
        name = "shout"

        def after_inlines(self, doc):
            for node in doc.find_all(Text):
                node.literal = node.literal.upper()

    md = Markdown(extensions=["tables", Shout()])
    assert md.extension_names == ["tables", "shout"]
    assert md.convert("hello `code`") == "<p>HELLO <code>code</code></p>\n"
    # the class itself will do as well
    assert Markdown(extensions=[Shout]).convert("hi") == "<p>HI</p>\n"


def test_custom_extension_can_add_inline_syntax():
    class Kbd(Extension):
        name = "kbd"

        def setup_inlines(self, parser):
            parser.add_hook("{", self.parse)

        def parse(self, parser):
            end = parser.subject.find("}", parser.pos)
            if end == -1:
                return False
            parser.add(Text("<" + parser.subject[parser.pos + 1 : end] + ">"))
            parser.pos = end + 1
            return True

    md = Markdown(extensions=[Kbd()])
    assert md.convert("press {ctrl} now, not {this") == (
        "<p>press &lt;ctrl&gt; now, not {this</p>\n"
    )


def test_deeply_nested_blocks_are_capped_not_fatal():
    html = Markdown().convert(">" * 5000 + " deep")
    assert html.count("<blockquote>") == 100
    assert "deep" in html
    html = Markdown().convert("".join("  " * i + "- x\n" for i in range(200)))
    assert html.count("<ul>") <= 100


def test_deeply_nested_inlines_raise_a_markdown_error():
    md = Markdown()
    with pytest.raises(MarkdownError, match="nested too deeply"):
        md.convert("![" * 600 + "x" + "](y)" * 600)
    with pytest.raises(MarkdownError, match="nested too deeply"):
        md.convert("_a " * 3000 + "b_ " * 3000)
    # and the converter is still usable afterwards
    assert md.convert("fine") == "<p>fine</p>\n"


@pytest.mark.parametrize(
    "source",
    [
        "[" * 3000 + "a" + "]" * 3000,
        "*a " * 3000,
        "[a](b" * 2000,
        "`" * 1000 + " x",
        "<" * 2000,
        "&" * 2000 + ";",
        "a\n" * 3000,
        "- a\n" * 2000,
        "\\" * 3001,
    ],
)
def test_awkward_input_is_handled(source):
    assert Markdown().convert(source)


def test_public_names_are_importable():
    for name in markdown.__all__:
        assert hasattr(markdown, name), name
    for name in ("Markdown", "render", "TocEntry", "MarkdownError", "walk"):
        assert name in markdown.__all__


def test_command_line_converts_a_file(tmp_path, capsys):
    source = tmp_path / "page.md"
    source.write_text("# Héllo\n\n~~x~~ -- y\n", encoding="utf-8")
    assert main([str(source), "--smart"]) == 0
    out = capsys.readouterr().out
    assert out == '<h1 id="héllo">Héllo</h1>\n<p><del>x</del> \u2013 y</p>\n'


def test_command_line_output_modes_and_extensions(tmp_path, capsys):
    source = tmp_path / "page.md"
    source.write_text("# T\n\n~~x~~ *y*\n", encoding="utf-8")
    assert main([str(source), "--text", "-x", ""]) == 0
    assert capsys.readouterr().out == "T\n\n~~x~~ y\n"
    assert main([str(source), "--ast", "-x", "strikethrough"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[:2] == ["document", "  heading level=1 id='t'"]
    assert "strikethrough" in out


def test_command_line_reports_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.md")]) == 1
    assert "error:" in capsys.readouterr().err
    source = tmp_path / "page.md"
    source.write_text("x", encoding="utf-8")
    assert main([str(source), "-x", "tabels"]) == 1
    assert "did you mean 'tables'" in capsys.readouterr().err
