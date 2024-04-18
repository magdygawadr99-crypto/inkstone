from __future__ import annotations

from inkstone.markdown import (
    FootnoteBackref,
    FootnoteDef,
    FootnoteList,
    FootnoteRef,
    Markdown,
    plain_text,
)

md = Markdown(extensions=["footnotes"], heading_ids=False)

BACK = "&#8617;&#xFE0E;"


def ref(number: int, ref_id: str | None = None) -> str:
    ref_id = ref_id or f"fnref-{number}"
    return (
        f'<sup class="footnote-ref"><a href="#fn-{number}" id="{ref_id}">{number}</a>'
        "</sup>"
    )


def backref(ref_id: str, label: str = BACK) -> str:
    return f' <a href="#{ref_id}" class="footnote-backref">{label}</a>'


def test_basic_footnote():
    html = md.convert("Here is a note[^1].\n\n[^1]: The note text.\n")
    assert html == (
        f"<p>Here is a note{ref(1)}.</p>\n"
        '<section class="footnotes">\n<ol>\n'
        f'<li id="fn-1">\n<p>The note text.{backref("fnref-1")}</p>\n</li>\n'
        "</ol>\n</section>\n"
    )


def test_footnotes_are_numbered_by_first_reference():
    html = md.convert(
        "B[^b] then A[^a].\n\n[^a]: Note A.\n[^b]: Note B.\n"
    )
    assert html.index("Note B.") < html.index("Note A.")
    assert f"B{ref(1)} then A{ref(2)}." in html
    assert [d.label for d in md.footnotes] == ["b", "a"]
    assert [d.number for d in md.footnotes] == [1, 2]


def test_labels_can_be_words_and_match_case_insensitively():
    html = md.convert("See[^Some-Note].\n\n[^some-note]: Text.\n")
    assert ref(1) in html
    assert '<li id="fn-1">' in html


def test_repeated_references_share_one_footnote():
    html = md.convert("One[^n] two[^n] three[^n].\n\n[^n]: Shared.\n")
    assert html.count('<li id="fn-') == 1
    assert ref(1) in html
    assert ref(1, "fnref-1-2") in html
    assert ref(1, "fnref-1-3") in html
    assert backref("fnref-1") in html
    assert backref("fnref-1-2", BACK + "<sup>2</sup>") in html
    assert backref("fnref-1-3", BACK + "<sup>3</sup>") in html


def test_unused_definitions_are_dropped():
    html = md.convert("Text.\n\n[^unused]: Nobody points here.\n")
    assert html == "<p>Text.</p>\n"
    assert md.footnotes == []


def test_reference_without_definition_is_literal_text():
    assert md.convert("Missing[^nope].\n") == "<p>Missing[^nope].</p>\n"


def test_first_definition_wins():
    html = md.convert("X[^1]\n\n[^1]: first\n\n[^1]: second\n")
    assert "first" in html and "second" not in html


def test_multi_paragraph_footnote():
    html = md.convert(
        "Text[^long].\n\n"
        "[^long]: First paragraph.\n\n"
        "    Second paragraph with `code`.\n\n"
        "    > and a quote\n\n"
        "Back in the body.\n"
    )
    assert html == (
        f"<p>Text{ref(1)}.</p>\n<p>Back in the body.</p>\n"
        '<section class="footnotes">\n<ol>\n<li id="fn-1">\n'
        "<p>First paragraph.</p>\n<p>Second paragraph with <code>code</code>.</p>\n"
        "<blockquote>\n<p>and a quote</p>\n</blockquote>\n"
        f'<p>{backref("fnref-1").strip()}</p>\n</li>\n</ol>\n</section>\n'
    )


def test_backref_goes_into_the_last_paragraph():
    html = md.convert("T[^1]\n\n[^1]: One.\n\n    Two.\n")
    assert f"<p>One.</p>\n<p>Two.{backref('fnref-1')}</p>" in html


def test_footnote_definition_continues_lazily():
    html = md.convert("T[^1]\n\n[^1]: starts here\nand goes on\n")
    assert "<p>starts here\nand goes on" in html


def test_footnote_inside_a_footnote():
    html = md.convert("A[^1].\n\n[^1]: Outer, see also[^2].\n[^2]: Inner.\n")
    assert html.index('<li id="fn-1">') < html.index('<li id="fn-2">')
    assert f"see also{ref(2)}." in html
    assert [d.number for d in md.footnotes] == [1, 2]


def test_footnote_only_referenced_from_an_unused_footnote_is_dropped():
    html = md.convert("Body.\n\n[^a]: refers to[^b]\n[^b]: other\n")
    assert html == "<p>Body.</p>\n"


def test_references_work_inside_other_inline_markup():
    html = md.convert("*emphasis[^1]* and [link[^1]](/u)\n\n[^1]: N\n")
    assert f"<em>emphasis{ref(1)}</em>" in html
    assert f'<a href="/u">link{ref(1, "fnref-1-2")}</a>' in html


def test_footnote_reference_in_heading_table_and_list():
    full = Markdown(heading_ids=False)
    html = full.convert(
        "# Title[^h]\n\n- item[^l]\n\n| a[^t] |\n|---|\n\n"
        "[^h]: H\n[^l]: L\n[^t]: T\n"
    )
    assert f"<h1>Title{ref(1)}</h1>" in html
    assert f"<li>item{ref(2)}</li>" in html
    assert f"<th>a{ref(3)}</th>" in html


def test_definition_takes_precedence_over_link_reference_syntax():
    doc = md.parse("[^note]: /not-a-url\n\n[^note]\n")
    assert doc.references == {}
    assert isinstance(doc.children[-1], FootnoteList)


def test_code_spans_and_escapes_protect_reference_syntax():
    html = md.convert("`[^1]` and \\[^1]\n\n[^1]: N\n")
    assert html == "<p><code>[^1]</code> and [^1]</p>\n"


def test_tree_shape():
    doc = md.parse("Text[^x].\n\n[^x]: Note.\n")
    paragraph, notes = doc.children
    reference = paragraph.children[1]
    assert isinstance(reference, FootnoteRef)
    assert (reference.label, reference.number, reference.ref_id) == ("x", 1, "fnref-1")
    assert isinstance(notes, FootnoteList)
    (definition,) = notes.children
    assert isinstance(definition, FootnoteDef)
    assert definition.ref_ids == ["fnref-1"]
    assert isinstance(definition.children[-1].children[-1], FootnoteBackref)
    assert definition.line == 3


def test_definitions_are_removed_from_where_they_were_written():
    doc = md.parse("> quote[^q]\n>\n> [^q]: defined inside the quote\n\nafter\n")
    quote = doc.children[0]
    assert not list(quote.find_all(FootnoteDef))
    assert isinstance(doc.children[-1], FootnoteList)


def test_plain_text_skips_footnotes_unless_asked():
    doc = md.parse("Body[^1] text.\n\n[^1]: The note.\n")
    assert plain_text(doc) == "Body text."
    assert plain_text(doc, footnotes=True) == "Body text.\n\nThe note."


def test_footnotes_can_be_switched_off():
    core = Markdown(extensions=[], heading_ids=False)
    html = core.convert("Text[^1].\n\n[^1]: /url\n")
    # without the extension that is an ordinary link reference labelled "^1"
    assert html == '<p>Text<a href="/url">^1</a>.</p>\n'


def test_state_does_not_leak_between_documents():
    md.convert("A[^1]\n\n[^1]: one\n")
    html = md.convert("B[^1]\n")
    assert html == "<p>B[^1]</p>\n"
    assert md.footnotes == []
