from __future__ import annotations

import pytest

from inkstone.markdown import (
    BlockQuote,
    Code,
    CodeBlock,
    Document,
    Emphasis,
    Heading,
    HtmlBlock,
    HtmlInline,
    Image,
    LineBreak,
    Link,
    List,
    ListItem,
    Markdown,
    NodeVisitor,
    Paragraph,
    SoftBreak,
    Strong,
    Text,
    ThematicBreak,
    dump,
    walk,
)

md = Markdown(extensions=[])

SAMPLE = """\
# Title

First *paragraph*
with two lines.

> A quote
> - with a list
>   item

1. one
2. two

```
code
```

<div>html</div>

---
"""


def test_block_structure():
    doc = md.parse(SAMPLE)
    assert [type(node) for node in doc.children] == [
        Heading,
        Paragraph,
        BlockQuote,
        List,
        CodeBlock,
        HtmlBlock,
        ThematicBreak,
    ]
    quote = doc.children[2]
    assert [type(node) for node in quote.children] == [Paragraph, List]
    assert [type(node) for node in doc.children[3].children] == [ListItem, ListItem]


def test_node_type_names():
    doc = md.parse(SAMPLE)
    assert [node.type for node in doc.children] == [
        "heading",
        "paragraph",
        "block_quote",
        "list",
        "code_block",
        "html_block",
        "thematic_break",
    ]
    assert doc.type == "document"
    assert doc.children[3].children[0].type == "list_item"
    assert (SoftBreak().type, LineBreak().type) == ("soft_break", "line_break")
    assert HtmlInline().type == "html_inline"


def test_blocks_know_their_source_lines():
    doc = md.parse(SAMPLE)
    spans = [(node.type, node.line, node.end_line) for node in doc.children]
    assert spans == [
        ("heading", 1, 1),
        ("paragraph", 3, 4),
        ("block_quote", 6, 8),
        ("list", 10, 11),
        ("code_block", 13, 15),
        ("html_block", 17, 17),
        ("thematic_break", 19, 19),
    ]
    quote = doc.children[2]
    assert [(n.line, n.end_line) for n in quote.children] == [(6, 6), (7, 8)]
    items = doc.children[3].children
    assert [item.line for item in items] == [10, 11]
    assert (doc.line, doc.end_line) == (1, 19)


def test_setext_heading_starts_on_its_text_line():
    doc = md.parse("intro\n\nTitle\nmore\n=====\n")
    heading = doc.children[1]
    assert isinstance(heading, Heading) and heading.setext
    assert (heading.line, heading.end_line) == (3, 5)


def test_inline_nodes_have_no_line():
    doc = md.parse("some *text*")
    assert all(node.line is None for node in doc.children[0].children)


def test_inline_structure():
    doc = md.parse("a *b **c*** `d` [e](/f 'g') ![h](/i)  \nj\nk <br>")
    kinds = [type(node) for node in doc.children[0].children]
    assert kinds == [
        Text,
        Emphasis,
        Text,
        Code,
        Text,
        Link,
        Text,
        Image,
        LineBreak,
        Text,
        SoftBreak,
        Text,
        HtmlInline,
    ]
    emphasis = doc.children[0].children[1]
    assert [type(node) for node in emphasis.children] == [Text, Strong]
    link = doc.children[0].children[5]
    assert (link.dest, link.title) == ("/f", "g")
    image = doc.children[0].children[7]
    assert (image.dest, image.title) == ("/i", "")


def test_adjacent_text_is_merged():
    doc = md.parse("a_b*c [d] !e \\* &amp; f")
    (text,) = doc.children[0].children
    assert text.literal == "a_b*c [d] !e * & f"


def test_list_attributes():
    doc = md.parse("- a\n- b\n\n3) c\n\n4) d\n")
    bullets, ordered = doc.children
    assert (bullets.ordered, bullets.tight, bullets.bullet) == (False, True, "-")
    assert bullets.start is None
    assert (ordered.ordered, ordered.tight, ordered.start) == (True, False, 3)
    assert ordered.delimiter == ")"


def test_heading_attributes():
    doc = md.parse("### Three\n\nOne\n===\n")
    atx, setext = doc.children
    assert (atx.level, atx.setext, atx.id) == (3, False, "three")
    assert (setext.level, setext.setext) == (1, True)


def test_parents_and_siblings():
    doc = md.parse("one\n\ntwo *x*\n\nthree\n")
    first, second, third = doc.children
    assert first.parent is doc and doc.parent is None
    assert first.previous is None and first.next is second
    assert third.previous is second and third.next is None
    emphasis = second.children[1]
    assert emphasis.parent is second
    assert emphasis.children[0].parent is emphasis
    assert list(emphasis.children[0].ancestors()) == [emphasis, second, doc]


def test_walk_is_depth_first_in_document_order():
    doc = md.parse("# T\n\n- a *b*\n- c\n")
    assert [node.type for node in walk(doc)] == [
        "document",
        "heading",
        "text",
        "list",
        "list_item",
        "paragraph",
        "text",
        "emphasis",
        "text",
        "list_item",
        "paragraph",
        "text",
    ]
    assert [n.type for n in doc.walk()] == [n.type for n in walk(doc)]


def test_walk_tolerates_changes_to_children_of_the_current_node():
    doc = md.parse("a *b* c\n\nd *e*\n")
    for node in walk(doc):
        if isinstance(node, Emphasis):
            node.replace_with(*node.children)
    assert not list(doc.find_all(Emphasis))
    assert md.render(doc) == "<p>a b c</p>\n<p>d e</p>\n"


def test_find_all():
    doc = md.parse("*a* **b** *c*\n\n> *d*\n")
    assert len(list(doc.find_all(Emphasis))) == 3
    assert len(list(doc.find_all(Emphasis, Strong))) == 4
    assert list(doc.find_all(Link)) == []


def test_append_unlink_and_insert():
    doc = Document()
    first = doc.append(Paragraph())
    last = doc.append(Paragraph())
    middle = Paragraph()
    first.insert_after(middle)
    assert doc.children == [first, middle, last]
    assert middle.parent is doc
    rule = ThematicBreak()
    first.insert_before(rule)
    assert doc.children[0] is rule
    middle.unlink()
    assert middle.parent is None and doc.children == [rule, first, last]
    middle.unlink()


def test_replace_with():
    doc = md.parse("keep\n\nswap\n\nkeep\n")
    target = doc.children[1]
    a, b = ThematicBreak(), ThematicBreak()
    target.replace_with(a, b)
    assert doc.children[1:3] == [a, b] and a.parent is doc
    assert target.parent is None
    a.replace_with()
    assert len(doc.children) == 3
    with pytest.raises(ValueError):
        target.replace_with(ThematicBreak())
    with pytest.raises(ValueError):
        target.insert_after(ThematicBreak())


def test_set_children_reparents():
    paragraph = Paragraph()
    paragraph.set_children([Text("a"), Text("b")])
    assert [child.parent for child in paragraph.children] == [paragraph, paragraph]


def test_tree_built_by_hand_renders():
    doc = Document()
    heading = doc.append(Heading(level=2))
    heading.append(Text("Made by hand"))
    paragraph = doc.append(Paragraph())
    paragraph.append(Text("a < b "))
    link = paragraph.append(Link("/x?a=1&b=2", "t"))
    link.append(Text("link"))
    assert md.render(doc) == (
        "<h2>Made by hand</h2>\n"
        '<p>a &lt; b <a href="/x?a=1&amp;b=2" title="t">link</a></p>\n'
    )


def test_visitor_dispatches_on_type():
    class Counter(NodeVisitor):
        def __init__(self):
            self.headings = []
            self.words = 0

        def visit_heading(self, node):
            self.headings.append(node.level)
            self.generic_visit(node)

        def visit_text(self, node):
            self.words += len(node.literal.split())

    counter = Counter()
    counter.visit(md.parse("# One two\n\nthree *four* five\n\n## Six\n"))
    assert counter.headings == [1, 2]
    assert counter.words == 6


def test_visitor_return_values_pass_through():
    class Depth(NodeVisitor):
        def generic_visit(self, node):
            return 1 + max((self.visit(child) for child in node.children), default=0)

    assert Depth().visit(md.parse("> - a *b*\n")) == 7


def test_dump():
    doc = md.parse("# T\n\n- a `b`\n")
    assert dump(doc) == (
        "document\n"
        "  heading level=1 id='t'\n"
        "    text literal='T'\n"
        "  list ordered=False tight=True\n"
        "    list_item\n"
        "      paragraph\n"
        "        text literal='a '\n"
        "        code literal='b'"
    )


def test_repr():
    doc = md.parse("## Sub\n\n[x](/y)\n")
    assert repr(doc.children[0]) == "<Heading level=2 id='sub' line=1>"
    assert repr(doc.children[1].children[0]) == "<Link dest='/y'>"
    assert repr(doc.children[1]) == "<Paragraph line=3>"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("a\r\nb\r\n\r\n# h\r\n", "<p>a\nb</p>\n<h1>h</h1>\n"),
        ("a\rb\r\r- x\r", "<p>a\nb</p>\n<ul>\n<li>x</li>\n</ul>\n"),
        ("```\r\ncode\r\n```\r\n", "<pre><code>code\n</code></pre>\n"),
        ("a  \r\nb", "<p>a<br />\nb</p>\n"),
        ("\ufeff# bom", "<h1>bom</h1>\n"),
        ("nul\0char", "<p>nul\ufffdchar</p>\n"),
        ("no trailing newline", "<p>no trailing newline</p>\n"),
        ("trailing blank lines\n\n\n\n", "<p>trailing blank lines</p>\n"),
        ("\n\n\nleading blank lines", "<p>leading blank lines</p>\n"),
        ("a\u2028b", "<p>a\u2028b</p>\n"),
    ],
)
def test_line_endings_and_odd_characters(source, expected):
    assert Markdown(extensions=[], heading_ids=False).convert(source) == expected


def test_line_numbers_with_crlf_input():
    doc = md.parse("a\r\n\r\nb\r\n\r\n\r\nc\r\n")
    assert [node.line for node in doc.children] == [1, 3, 6]


def test_parser_bookkeeping_does_not_leak_into_the_result():
    doc = md.parse("- a\n\n    code\n\n> q\n")
    for node in walk(doc):
        if node.is_block:
            assert not node._open
            assert node._lines == []
