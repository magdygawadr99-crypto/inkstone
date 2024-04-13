from __future__ import annotations

from typing import Callable, Iterable

from .blocks import BlockParser
from .errors import MarkdownError
from .extensions import Extension, load
from .html import HtmlRenderer
from .inlines import InlineParser
from .nodes import (
    Document,
    FootnoteDef,
    FootnoteList,
    Heading,
    Paragraph,
    Reference,
    walk,
)
from .toc import TocEntry, assign_heading_ids, build_toc, render_toc


class Markdown:
    """A configured Markdown converter.

    Setting one up costs a little (extensions hook themselves into the
    parsers, patterns get compiled), so build one and reuse it for every
    page::

        md = Markdown(smart=True)
        html = md.convert(text)
        md.toc          # headings of the document just converted

    extensions is a list of names (see ``extensions.available()``) or None
    for the default set. highlight is called as ``highlight(code, lang)``
    for each code block and returns ready HTML, or None to decline.
    """

    def __init__(
        self,
        extensions: Iterable[str | Extension] | None = None,
        highlight: Callable[..., str | None] | None = None,
        heading_ids: bool = True,
        smart: bool = False,
        safe: bool = False,
        hard_wraps: bool = False,
    ) -> None:
        self.extensions = load(extensions)
        if smart and not any(ext.name == "smart" for ext in self.extensions):
            self.extensions += load(["smart"])
        self.highlight = highlight
        self.heading_ids = heading_ids
        self.safe = safe
        self.hard_wraps = hard_wraps

        self._blocks = BlockParser()
        self._inlines = InlineParser()
        for ext in self.extensions:
            ext.setup_blocks(self._blocks)
            ext.setup_inlines(self._inlines)
        self.smart = self._inlines.smart
        self._renderer = HtmlRenderer(
            highlight=highlight, safe=safe, hard_wraps=hard_wraps
        )
        self._doc = Document()

    @property
    def extension_names(self) -> list[str]:
        return [ext.name for ext in self.extensions]

    def parse(self, text: str) -> Document:
        """Parse text into a tree, without rendering it."""
        if not isinstance(text, str):
            raise TypeError(f"markdown source must be str, not {type(text).__name__}")
        try:
            doc = self._blocks.parse(text)
            for ext in self.extensions:
                ext.before_inlines(doc)
            self._parse_inlines(doc)
            for ext in self.extensions:
                ext.after_inlines(doc)
            assign_heading_ids(doc, generate=self.heading_ids)
            doc.toc = build_toc(doc.find_all(Heading))
        except RecursionError:
            # Only inline nesting can get this deep (blocks are capped by the
            # parser): thousands of emphasis markers inside one another.
            raise MarkdownError("document is nested too deeply to parse") from None
        self._doc = doc
        return doc

    def _parse_inlines(self, doc: Document) -> None:
        parser = self._inlines
        for node in walk(doc):
            if node.raw is not None and not node.children:
                node.set_children(parser.parse(node.raw, doc))

    def render(self, doc: Document) -> str:
        """Render a tree from parse() as HTML."""
        try:
            return self._renderer.render(doc)
        except RecursionError:
            raise MarkdownError("document is nested too deeply to render") from None

    def convert(self, text: str) -> str:
        return self.render(self.parse(text))

    def convert_inline(self, text: str) -> str:
        """Convert a single line of Markdown without wrapping it in ``<p>``.

        For page titles and the like, where emphasis and code spans should
        work but block structure makes no sense. Does not touch ``toc`` and
        friends, and cannot see link references of any document.
        """
        if not isinstance(text, str):
            raise TypeError(f"markdown source must be str, not {type(text).__name__}")
        holder = Paragraph()
        holder.set_children(self._inlines.parse(" ".join(text.split()), Document()))
        return "".join(self._renderer.render(child) for child in holder.children)

    @property
    def toc(self) -> list[TocEntry]:
        """Table of contents of the last document, nested by heading level."""
        return self._doc.toc

    def render_toc(self) -> str:
        return render_toc(self._doc.toc)

    @property
    def references(self) -> dict[str, Reference]:
        """Link reference definitions of the last document, by normalised label."""
        return self._doc.references

    @property
    def footnotes(self) -> list[FootnoteDef]:
        """Footnotes of the last document that were used, in numbered order."""
        last = self._doc.children[-1] if self._doc.children else None
        if isinstance(last, FootnoteList):
            return list(last.children)
        return []

    def reset(self) -> None:
        """Forget the last document."""
        self._doc = Document()


def render(text: str, **options) -> str:
    """Convert text to HTML in one go. Options are those of Markdown()."""
    return Markdown(**options).convert(text)
