from __future__ import annotations

from ..nodes import Document, Paragraph, TocMarker
from . import Extension


class TocExtension(Extension):
    """A paragraph consisting of ``[TOC]`` becomes the table of contents."""

    name = "toc"

    def before_inlines(self, doc: Document) -> None:
        for paragraph in list(doc.find_all(Paragraph)):
            if paragraph.raw in ("[TOC]", "[toc]"):
                marker = TocMarker()
                marker.line = paragraph.line
                marker.end_line = paragraph.end_line
                marker._open = False
                paragraph.replace_with(marker)
