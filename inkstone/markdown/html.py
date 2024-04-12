from __future__ import annotations

import inspect
from typing import Callable

from .nodes import (
    CodeBlock,
    DefinitionDescription,
    Document,
    Heading,
    List,
    ListItem,
    Node,
    NodeVisitor,
    Paragraph,
)
from .text import PlainTextRenderer
from .toc import render_toc
from .utils import escape_html, is_unsafe_url, parse_line_numbers

Highlighter = Callable[..., "str | None"]

_FALSEY = ("false", "no", "off", "0")


def _wants_attrs(func: Callable) -> bool:
    """Does the highlight callback take the fence attributes as well?"""
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    # Has to be asked for by name. A catch-all **kwargs doesn't count, it
    # usually just forwards options to something that never heard of attrs.
    return "attrs" in params


class HtmlRenderer(NodeVisitor):
    """Render a tree as HTML.

    highlight, if given, is called as ``highlight(code, lang)`` for every
    code block and returns finished markup (including the ``<pre>``), or
    None to get the plain rendering. A callback with an ``attrs`` parameter
    also receives the fence attributes (``hl_lines`` and friends) by keyword.
    """

    def __init__(
        self,
        *,
        highlight: Highlighter | None = None,
        safe: bool = False,
        hard_wraps: bool = False,
    ) -> None:
        self.highlight = highlight
        self.safe = safe
        self.hard_wraps = hard_wraps
        self._highlight_attrs = highlight is not None and _wants_attrs(highlight)
        self._alt_text = PlainTextRenderer()
        self._out: list[str] = []
        self._last = "\n"
        self._toc: list = []

    def render(self, node: Node) -> str:
        self._out = []
        self._last = "\n"
        root = node
        while root.parent is not None:
            root = root.parent
        self._toc = root.toc if isinstance(root, Document) else []
        self.visit(node)
        result = "".join(self._out)
        self._out = []
        return result

    def write(self, text: str) -> None:
        if text:
            self._out.append(text)
            self._last = text[-1]

    def newline(self) -> None:
        """Start a new line unless we are at the start of one already."""
        if self._last != "\n":
            self._out.append("\n")
            self._last = "\n"

    def children(self, node: Node) -> None:
        for child in node.children:
            self.visit(child)

    def attributes(self, attrs: dict) -> str:
        parts = []
        for name, value in attrs.items():
            if value is None or value is False:
                continue
            if self.safe and (name.lower().startswith("on") or name.lower() == "style"):
                continue
            if value is True:
                parts.append(f" {escape_html(name)}")
            else:
                parts.append(f' {escape_html(name)}="{escape_html(str(value))}"')
        return "".join(parts)

    def _container(self, node: Node, tag: str, attrs: dict | None = None) -> None:
        self.newline()
        self.write(f"<{tag}{self.attributes(attrs or {})}>")
        self.newline()
        self.children(node)
        self.newline()
        self.write(f"</{tag}>")
        self.newline()

    def _wrapped(self, node: Node, tag: str) -> None:
        self.write(f"<{tag}>")
        self.children(node)
        self.write(f"</{tag}>")

    def visit_document(self, node) -> None:
        self.children(node)
        self.newline()

    def visit_paragraph(self, node: Paragraph) -> None:
        parent = node.parent
        tight = (
            isinstance(parent, ListItem)
            and isinstance(parent.parent, List)
            and parent.parent.tight
        ) or (isinstance(parent, DefinitionDescription) and parent.tight)
        if not tight:
            self.newline()
            self.write("<p>")
        if isinstance(parent, ListItem) and parent.checked is not None:
            if parent.children[0] is node:
                self._checkbox(parent.checked)
        self.children(node)
        if not tight:
            self.write("</p>")
            self.newline()

    def _checkbox(self, checked: bool) -> None:
        state = ' checked=""' if checked else ""
        self.write(f'<input type="checkbox"{state} disabled="" /> ')

    def visit_heading(self, node: Heading) -> None:
        attrs = {}
        if node.id:
            attrs["id"] = node.id
        attrs.update((k, v) for k, v in node.attrs.items() if k != "id")
        tag = f"h{node.level}"
        self.newline()
        self.write(f"<{tag}{self.attributes(attrs)}>")
        self.children(node)
        self.write(f"</{tag}>")
        self.newline()

    def visit_block_quote(self, node) -> None:
        self._container(node, "blockquote")

    def visit_list(self, node: List) -> None:
        attrs = {}
        if node.ordered and node.start is not None and node.start != 1:
            attrs["start"] = node.start
        if any(item.checked is not None for item in node.children):
            attrs["class"] = "task-list"
        self._container(node, "ol" if node.ordered else "ul", attrs)

    def visit_list_item(self, node: ListItem) -> None:
        if node.checked is not None:
            self.write('<li class="task-list-item">')
        else:
            self.write("<li>")
        self.children(node)
        self.write("</li>")
        self.newline()

    def visit_thematic_break(self, node) -> None:
        self.newline()
        self.write("<hr />")
        self.newline()

    def visit_html_block(self, node) -> None:
        self.newline()
        self.write(escape_html(node.literal) if self.safe else node.literal)
        self.newline()

    def visit_code_block(self, node: CodeBlock) -> None:
        self.newline()
        markup = None
        if self.highlight is not None:
            if self._highlight_attrs:
                markup = self.highlight(node.literal, node.lang, attrs=dict(node.attrs))
            else:
                markup = self.highlight(node.literal, node.lang)
        if markup is None:
            markup = self._plain_code_block(node)
        self.write(markup)
        self.newline()

    def _plain_code_block(self, node: CodeBlock) -> str:
        attrs = dict(node.attrs)
        highlighted = parse_line_numbers(attrs.pop("hl_lines", None))
        linenos = attrs.pop("linenos", False)
        if isinstance(linenos, str) and linenos.lower() in _FALSEY:
            linenos = False
        try:
            first = int(attrs.pop("linenostart", 1))
        except (TypeError, ValueError):
            first = 1

        code_attrs = {}
        if node.lang:
            lang = node.lang
            if not lang.startswith(("language-", "lang-")):
                lang = "language-" + lang
            code_attrs["class"] = lang

        if highlighted or linenos:
            body = self._code_lines(node.literal, highlighted, bool(linenos), first)
        else:
            body = escape_html(node.literal)
        pre = self.attributes(attrs)
        return f"<pre{pre}><code{self.attributes(code_attrs)}>{body}</code></pre>"

    def _code_lines(
        self, code: str, highlighted: set[int], numbers: bool, first: int
    ) -> str:
        # One span per line, so a stylesheet can mark some and number all.
        out = []
        lines = code.split("\n")
        if lines and not lines[-1]:
            lines.pop()
        for offset, line in enumerate(lines):
            classes = "line hl" if offset + 1 in highlighted else "line"
            number = f'<span class="lineno">{first + offset}</span>' if numbers else ""
            out.append(f'<span class="{classes}">{number}{escape_html(line)}</span>\n')
        return "".join(out)

    def visit_table(self, node) -> None:
        self.newline()
        self.write("<table>\n")
        head = [row for row in node.children if row.header]
        body = [row for row in node.children if not row.header]
        for tag, rows in (("thead", head), ("tbody", body)):
            if not rows:
                continue
            self.write(f"<{tag}>\n")
            for row in rows:
                self.visit(row)
            self.write(f"</{tag}>\n")
        self.write("</table>")
        self.newline()

    def visit_table_row(self, node) -> None:
        self.write("<tr>\n")
        self.children(node)
        self.write("</tr>\n")

    def visit_table_cell(self, node) -> None:
        tag = "th" if node.header else "td"
        style = f' style="text-align: {node.align}"' if node.align else ""
        self.write(f"<{tag}{style}>")
        self.children(node)
        self.write(f"</{tag}>\n")

    def visit_definition_list(self, node) -> None:
        self._container(node, "dl")

    def visit_definition_term(self, node) -> None:
        self.write("<dt>")
        self.children(node)
        self.write("</dt>")
        self.newline()

    def visit_definition_description(self, node) -> None:
        self.write("<dd>")
        self.children(node)
        self.write("</dd>")
        self.newline()

    def visit_admonition(self, node) -> None:
        classes = ["admonition", node.kind] + list(node.classes)
        attrs: dict = {"class": " ".join(classes)}
        self.newline()
        if node.collapsible:
            if node.open:
                attrs["open"] = True
            self.write(f"<details{self.attributes(attrs)}>\n")
            if node.title:
                self.write(f"<summary>{escape_html(node.title)}</summary>\n")
        else:
            self.write(f"<div{self.attributes(attrs)}>\n")
            if node.title:
                title = escape_html(node.title)
                self.write(f'<p class="admonition-title">{title}</p>\n')
        self.children(node)
        self.newline()
        self.write("</details>" if node.collapsible else "</div>")
        self.newline()

    def visit_footnote_list(self, node) -> None:
        self.newline()
        self.write('<section class="footnotes">\n<ol>\n')
        self.children(node)
        self.write("</ol>\n</section>")
        self.newline()

    def visit_footnote_def(self, node) -> None:
        self.write(f'<li id="fn-{node.number}">')
        self.children(node)
        self.newline()
        self.write("</li>")
        self.newline()

    def visit_footnote_ref(self, node) -> None:
        n = node.number
        link = f'<a href="#fn-{n}" id="{node.ref_id}">{n}</a>'
        self.write(f'<sup class="footnote-ref">{link}</sup>')

    def visit_footnote_backref(self, node) -> None:
        links = []
        for i, ref_id in enumerate(node.ref_ids):
            # U+FE0E keeps phones from turning the arrow into an emoji
            label = "&#8617;&#xFE0E;"
            if i:
                label += f"<sup>{i + 1}</sup>"
            links.append(f'<a href="#{ref_id}" class="footnote-backref">{label}</a>')
        if node.previous is not None:
            self.write(" ")
        self.write(" ".join(links))

    def visit_toc_marker(self, node) -> None:
        self.newline()
        if self._toc:
            self.write('<nav class="toc">\n' + render_toc(self._toc) + "</nav>")
        self.newline()

    def visit_text(self, node) -> None:
        self.write(escape_html(node.literal))

    def visit_soft_break(self, node) -> None:
        self.write("<br />\n" if self.hard_wraps else "\n")

    def visit_line_break(self, node) -> None:
        self.write("<br />\n")

    def visit_code(self, node) -> None:
        self.write(f"<code>{escape_html(node.literal)}</code>")

    def visit_emphasis(self, node) -> None:
        self._wrapped(node, "em")

    def visit_strong(self, node) -> None:
        self._wrapped(node, "strong")

    def visit_strikethrough(self, node) -> None:
        self._wrapped(node, "del")

    def visit_mark(self, node) -> None:
        self._wrapped(node, "mark")

    def visit_subscript(self, node) -> None:
        self._wrapped(node, "sub")

    def visit_superscript(self, node) -> None:
        self._wrapped(node, "sup")

    def visit_link(self, node) -> None:
        dest = node.dest
        if self.safe and is_unsafe_url(dest):
            dest = ""
        title = f' title="{escape_html(node.title)}"' if node.title else ""
        self.write(f'<a href="{escape_html(dest)}"{title}>')
        self.children(node)
        self.write("</a>")

    def visit_image(self, node) -> None:
        dest = node.dest
        if self.safe and is_unsafe_url(dest, image=True):
            dest = ""
        alt = escape_html(self._alt_text.render(node))
        title = f' title="{escape_html(node.title)}"' if node.title else ""
        self.write(f'<img src="{escape_html(dest)}" alt="{alt}"{title} />')

    def visit_html_inline(self, node) -> None:
        self.write(escape_html(node.literal) if self.safe else node.literal)

    def visit_abbreviation(self, node) -> None:
        self.write(f'<abbr title="{escape_html(node.title)}">')
        self.children(node)
        self.write("</abbr>")
