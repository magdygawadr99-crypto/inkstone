from __future__ import annotations

import re

from ..blocks import CONTAINER, CONTINUE, NO_MATCH, STOP, BlockParser, ContainerRule
from ..inlines import InlineParser
from ..nodes import (
    Block,
    Document,
    FootnoteBackref,
    FootnoteDef,
    FootnoteList,
    FootnoteRef,
    Node,
    Paragraph,
    walk,
)
from ..utils import normalize_label
from . import Extension

_DEFINITION = re.compile(r"\[\^([^\]\s]+)\]:")
_REFERENCE = re.compile(r"\[\^([^\]\s]+)\]")

# Continuation lines of a definition are indented this much.
_INDENT = 4


class _FootnoteDefRule(ContainerRule):
    def continue_(self, parser: BlockParser, block: FootnoteDef) -> int:
        if parser.blank:
            if not block.children:
                return STOP
            parser.advance_next_nonspace()
        elif parser.indent >= _INDENT:
            parser.advance_offset(_INDENT, columns=True)
        else:
            return STOP
        return CONTINUE


def _definition_start(parser: BlockParser, container: Block) -> int:
    if parser.indented or parser.next_char() != "[":
        return NO_MATCH
    m = _DEFINITION.match(parser.current_line, parser.next_nonspace)
    if m is None:
        return NO_MATCH
    parser.advance_next_nonspace()
    parser.advance_offset(len(m.group()))
    if parser.char_at_offset() in (" ", "\t"):
        parser.advance_offset(1, columns=True)
    parser.close_unmatched_blocks()
    definition = parser.add_child(FootnoteDef(m.group(1)))
    # as with link references, the first definition of a label wins
    parser.doc.footnotes.setdefault(normalize_label(m.group(1)), definition)
    return CONTAINER


def _reference(parser: InlineParser) -> bool:
    if parser.peek(1) != "^" or parser.doc is None:
        return False
    m = _REFERENCE.match(parser.subject, parser.pos)
    if m is None or normalize_label(m.group(1)) not in parser.doc.footnotes:
        return False
    parser.add(FootnoteRef(m.group(1)))
    parser.pos = m.end()
    return True


def _references_in(node: Node, skip_definitions: bool) -> list[FootnoteRef]:
    found = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, FootnoteRef):
            found.append(current)
        for child in reversed(current.children):
            if not (skip_definitions and isinstance(child, FootnoteDef)):
                stack.append(child)
    return found


class FootnotesExtension(Extension):
    """``[^1]`` references with ``[^1]: text`` definitions.

    Footnotes are numbered in the order they are first referred to, and
    definitions nothing refers to are dropped.
    """

    name = "footnotes"

    def setup_blocks(self, parser: BlockParser) -> None:
        parser.add_rule(FootnoteDef, _FootnoteDefRule())
        parser.add_start("footnote_def", _definition_start)

    def setup_inlines(self, parser: InlineParser) -> None:
        parser.add_hook("[", _reference)

    def after_inlines(self, doc: Document) -> None:
        definitions = [node for node in walk(doc) if isinstance(node, FootnoteDef)]
        if not definitions:
            return

        used: list[FootnoteDef] = []
        # References in the body come first; the ones inside footnotes are
        # looked at as their footnote comes up, which may pull in more.
        pending = _references_in(doc, skip_definitions=True)
        position = 0
        while True:
            for ref in pending:
                definition = doc.footnotes[normalize_label(ref.label)]
                if definition.number is None:
                    used.append(definition)
                    definition.number = len(used)
                ref.number = definition.number
                ref.ref_id = f"fnref-{ref.number}"
                if definition.ref_ids:
                    ref.ref_id += f"-{len(definition.ref_ids) + 1}"
                definition.ref_ids.append(ref.ref_id)
            if position >= len(used):
                break
            pending = _references_in(used[position], skip_definitions=False)
            position += 1

        for definition in definitions:
            definition.unlink()
        if not used:
            return
        # XXX the ids are only unique within one document. Two posts shown in
        # full on the same index page will both have a fn-1.
        footnotes = FootnoteList()
        footnotes.line = used[0].line
        for definition in used:
            _add_backref(definition)
            footnotes.append(definition)
        doc.append(footnotes)


def _add_backref(definition: FootnoteDef) -> None:
    backref = FootnoteBackref(definition.ref_ids)
    last = definition.children[-1] if definition.children else None
    if not isinstance(last, Paragraph):
        last = definition.append(Paragraph())
    last.append(backref)
