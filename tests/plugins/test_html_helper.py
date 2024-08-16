from __future__ import annotations

import pytest

from inkstone.plugins.builtin import _html

DOCUMENT = """<p>One <a href="/a/" class="x">link</a> and <img src='b.png' alt=B></p>
<!-- <a href="/commented/">no</a> -->
<pre><code class="language-html">&lt;a href="/c/"&gt;<span>code</span></code></pre>
<p>Inline <code><a href="/d/">d</a></code> and a <br /> break.</p>
<script>if (a < b) { document.write("<a href='/e/'>e</a>"); }</script>
<style>a > b { color: red }</style>
<textarea><a href="/f/">f</a></textarea>
<p>Last <A HREF="/g/">one</A></p>
"""


def links(markup):
    found = []
    _html.rewrite(markup, lambda tag: found.append(tag.get("href")), ("a",))
    return found


def test_tokens_cover_the_input_exactly():
    tokens = list(_html.tokenize(DOCUMENT))
    assert "".join(token.source for token in tokens) == DOCUMENT
    assert [token.pos for token in tokens] == sorted(token.pos for token in tokens)
    assert all(DOCUMENT[token.pos : token.end] == token.source for token in tokens)


def test_token_kinds():
    kinds = [(t.kind, t.name) for t in _html.tokenize('<p id="a">x<br/></p><!--c-->')]
    assert kinds == [
        ("start", "p"),
        ("text", ""),
        ("start", "br"),
        ("end", "p"),
        ("comment", ""),
    ]


def test_rewrite_skips_code_scripts_styles_and_comments():
    assert links(DOCUMENT) == ["/a/", "/g/"]


def test_rewrite_without_changes_returns_the_input():
    assert _html.rewrite(DOCUMENT, lambda tag: None) == DOCUMENT


def test_rewrite_only_touches_the_tags_it_changed():
    def mark(tag):
        if tag.get("href") == "/g/":
            tag.set("rel", "nofollow")

    out = _html.rewrite(DOCUMENT, mark, ("a",))
    # attribute names stay as written, only the tag name is normalised
    assert '<a HREF="/g/" rel="nofollow">one</A>' in out
    assert out.replace('<a HREF="/g/" rel="nofollow">', '<A HREF="/g/">') == DOCUMENT


def test_text_after_code_is_not_protected():
    tokens = list(_html.tokenize("<pre>a</pre>b<code>c</code>d"))
    protected = {t.source: t.protected for t in tokens if t.kind == "text"}
    assert protected == {"a": True, "b": False, "c": True, "d": False}


def test_unclosed_script_protects_the_rest():
    tokens = list(_html.tokenize("<p>a</p><script>var x = '<p>';"))
    assert tokens[-1].kind == "text" and tokens[-1].protected
    assert tokens[-1].source == "var x = '<p>';"


@pytest.mark.parametrize(
    "source, name, expected",
    [
        ('<a href="/x/">', "href", "/x/"),
        ("<a href='/x/'>", "href", "/x/"),
        ("<a href=/x/>", "href", "/x/"),
        ('<a HREF="/x/">', "href", "/x/"),
        ('<a title="a &amp; b &quot;c&quot;">', "title", 'a & b "c"'),
        ("<input disabled>", "disabled", ""),
        ('<a href="/x/">', "rel", None),
        ('<a data-x="1 > 0" href="/y/">', "href", "/y/"),
    ],
)
def test_reading_attributes(source, name, expected):
    tag = next(_html.tokenize(source)).tag
    assert tag.get(name) == expected
    assert tag.has(name) is (expected is not None)


def test_setting_attributes_escapes_and_keeps_order():
    tag = next(_html.tokenize('<a class="a" href="/x/">')).tag
    tag.set("title", 'Tom & "Jerry" <3')
    tag.set("href", "/y/")
    assert str(tag) == (
        '<a class="a" href="/y/" title="Tom &amp; &quot;Jerry&quot; &lt;3">'
    )
    assert tag.get("title") == 'Tom & "Jerry" <3'


def test_setting_the_same_value_changes_nothing():
    source = "<img src='a.png' alt=A>"
    tag = next(_html.tokenize(source)).tag
    tag.set("alt", "A")
    tag.setdefault("src", "other.png")
    assert not tag.changed
    assert str(tag) == source


def test_bare_attributes_and_self_closing_survive_a_rewrite():
    tag = next(_html.tokenize('<img src="a.png" hidden />')).tag
    tag.set("width", "10")
    assert str(tag) == '<img src="a.png" hidden width="10" />'
    tag.set("async", None)
    assert str(tag).endswith("async />")


@pytest.mark.parametrize(
    "source, self_closing",
    [
        ("<br/>", True),
        ("<br />", True),
        ('<img src="a.png"/>', True),
        ("<img src='a.png' / >", True),
        ("<p>", False),
        ('<a href="/x/">', False),
        # an unquoted value may end in a slash; that does not close the tag
        ("<a href=/x/>", False),
    ],
)
def test_self_closing(source, self_closing):
    tag = next(_html.tokenize(source)).tag
    assert tag.self_closing is self_closing


def test_unquoted_value_ending_in_a_slash_is_rewritten_properly():
    out = _html.rewrite("<a href=/x/>y</a>", lambda tag: tag.set("rel", "me"))
    assert out == '<a href="/x/" rel="me">y</a>'


def test_remove_and_classes():
    tag = next(_html.tokenize('<a class="one two" rel="me" href="#">')).tag
    tag.remove("rel")
    tag.remove("nothing")
    tag.add_class("two", "three")
    assert tag.classes == ["one", "two", "three"]
    assert str(tag) == '<a class="one two three" href="#">'


def test_find_elements_returns_offsets():
    markup = '<h2 id="a">One</h2>\n<p>x</p>\n<h3 id="b">Two <em>b</em></h3>'
    first, second = _html.find_elements(markup, ("h2", "h3"))
    assert first.tag.get("id") == "a"
    assert markup[first.start : first.end] == '<h2 id="a">One</h2>'
    assert first.inner(markup) == "One"
    assert second.inner(markup) == "Two <em>b</em>"


def test_find_elements_handles_nesting_of_the_same_tag():
    markup = "<ul><li>a<ul><li>inner</li></ul></li><li>b</li></ul>"
    items = _html.find_elements(markup, ("li",))
    assert [item.inner(markup) for item in items] == ["a<ul><li>inner</li></ul>", "b"]


def test_find_elements_ignores_code_and_unclosed_tags():
    markup = "<pre><h2>not</h2></pre><h2>yes</h2><h2>never closed"
    assert [el.inner(markup) for el in _html.find_elements(markup, ("h2",))] == ["yes"]


@pytest.mark.parametrize(
    "markup, text",
    [
        ("<p>Hello <em>there</em></p>", "Hello there"),
        ("a &amp; b &lt;c&gt;", "a & b <c>"),
        ("<p>one</p>\n\n<p>two</p>", "one two"),
        ("x<!-- gone -->y", "xy"),
        ("", ""),
    ],
)
def test_text_content(markup, text):
    assert _html.text_content(markup) == text
