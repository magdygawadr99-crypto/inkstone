from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .nodes import Document, Heading
from .text import PlainTextRenderer
from .utils import escape_html, slugify, unique_id


@dataclass
class TocEntry:
    level: int
    id: str
    title: str
    children: list[TocEntry] = field(default_factory=list)

    def walk(self) -> Iterator[TocEntry]:
        """This entry and everything nested below it, in document order."""
        yield self
        for child in self.children:
            yield from child.walk()


def assign_heading_ids(doc: Document, generate: bool = True) -> None:
    """Give headings their id attribute.

    Ids written out by hand (``## Title {#custom}``) always win. The rest
    are slugs of the heading text, numbered when they would repeat.
    """
    headings = list(doc.find_all(Heading))
    seen: dict[str, int] = {}
    for heading in headings:
        explicit = heading.attrs.get("id")
        if explicit:
            heading.id = explicit
            seen.setdefault(explicit, 0)
    if not generate:
        return
    text = PlainTextRenderer()
    for heading in headings:
        if heading.id is None:
            heading.id = unique_id(slugify(text.render(heading)), seen)


def build_toc(headings: Iterable[Heading]) -> list[TocEntry]:
    """Nest headings by level.

    Each heading goes under the closest earlier heading with a lower level,
    so a document that jumps from h1 to h3 still gets a sensible tree.
    """
    text = PlainTextRenderer()
    roots: list[TocEntry] = []
    stack: list[TocEntry] = []
    for heading in headings:
        entry = TocEntry(heading.level, heading.id or "", text.render(heading))
        while stack and stack[-1].level >= entry.level:
            stack.pop()
        if stack:
            stack[-1].children.append(entry)
        else:
            roots.append(entry)
        stack.append(entry)
    return roots


def render_toc(entries: list[TocEntry]) -> str:
    """Nested ``<ul>`` markup for a list of entries; "" if there are none."""
    if not entries:
        return ""
    out = ["<ul>\n"]
    for entry in entries:
        title = escape_html(entry.title)
        if entry.id:
            href = escape_html("#" + entry.id)
            out.append(f'<li><a href="{href}">{title}</a>')
        else:
            out.append(f"<li>{title}")
        if entry.children:
            out.append("\n" + render_toc(entry.children))
        out.append("</li>\n")
    out.append("</ul>\n")
    return "".join(out)
