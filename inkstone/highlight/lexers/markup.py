from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, default, include, using
from ..registry import register
from ..token import (
    Comment,
    Name,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)

_TAG_NAME = r"[^\W\d][\w:.-]*"
_ENTITY = r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][\w.-]*);"

_CLOSE_TAG = bygroups(
    Punctuation, Punctuation, Whitespace, Name.Tag, Whitespace, Punctuation
)

_ATTRIBUTE_VALUE = [
    (r'"[^"]*"', String, "#pop"),
    (r"'[^']*'", String, "#pop"),
    (r"[^\s>]+", String, "#pop"),
    default("#pop"),
]


def _embedded(tag: str, language: str) -> list:
    """Rules for the body of a <script> or <style> element."""
    # XXX: the type attribute is ignored, so JSON-LD and import maps are lexed
    # as JavaScript. Close enough that nobody has complained.
    closing = rf"</\s*{tag}\s*>"
    return [
        (rf"(<)(/)(\s*)({tag})(\s*)(>)", _CLOSE_TAG, "#pop"),
        (rf".+?(?={closing})", using(language)),
        # never closed: the rest of the document belongs to it
        (r".+", using(language), "#pop"),
    ]


def _delegated_attribute(name: str, quote: str, action) -> tuple:
    return (
        rf"({name})(\s*)(=)(\s*)({quote})([^{quote}]*)({quote})",
        bygroups(
            Name.Attribute, Whitespace, Operator, Whitespace, String, action, String
        ),
    )


@register
class HtmlLexer(RegexLexer):
    name = "html"
    aliases = ("htm", "xhtml", "html5")
    extensions = (".html", ".htm", ".xhtml")

    flags = re.MULTILINE | re.IGNORECASE | re.DOTALL

    tokens = {
        "root": [
            (r"[^<&]+", Text),
            (_ENTITY, Name.Entity),
            (r"<!--.*?-->", Comment.Multiline),
            (r"<!\[CDATA\[.*?\]\]>", Comment.Preproc),
            (r"<![^>]*>", Comment.Preproc),
            (r"<\?.*?\?>", Comment.Preproc),
            (
                r"(<)(script)\b",
                bygroups(Punctuation, Name.Tag),
                ("script", "tag"),
            ),
            (
                r"(<)(style)\b",
                bygroups(Punctuation, Name.Tag),
                ("style", "tag"),
            ),
            (rf"(<)({_TAG_NAME})", bygroups(Punctuation, Name.Tag), "tag"),
            (rf"(<)(/)(\s*)({_TAG_NAME})(\s*)(>)", _CLOSE_TAG),
            # a stray < or & in running text; browsers shrug and so do we
            (r"[<&]", Text),
        ],
        "tag": [
            (r"\s+", Whitespace),
            _delegated_attribute("style", '"', using("css", state="inline")),
            _delegated_attribute("style", "'", using("css", state="inline")),
            _delegated_attribute(r"on[a-z]+", '"', using("javascript")),
            _delegated_attribute(r"on[a-z]+", "'", using("javascript")),
            (
                r"([\w:@.#-]+)(\s*)(=)(\s*)",
                bygroups(Name.Attribute, Whitespace, Operator, Whitespace),
                "attribute-value",
            ),
            (r"[\w:@.#-]+", Name.Attribute),
            (r"(/?)(\s*)(>)", bygroups(Punctuation, Whitespace, Punctuation), "#pop"),
        ],
        "attribute-value": _ATTRIBUTE_VALUE,
        "script": _embedded("script", "javascript"),
        "style": _embedded("style", "css"),
    }

    @staticmethod
    def analyse(code: str) -> float:
        if re.match(r"\s*<!DOCTYPE\s+html\b", code, re.I):
            return 0.95
        if re.search(r"<html\b|<body\b|<head\b", code, re.I):
            return 0.8
        tags = re.findall(r"</(?:div|p|span|a|ul|ol|li|h[1-6]|table|section)>", code)
        return 0.5 if tags else 0.0


@register
class XmlLexer(RegexLexer):
    name = "xml"
    aliases = ("svg", "rss", "atom", "xsl", "xslt", "plist")
    extensions = (".xml", ".svg", ".rss", ".atom", ".xsl", ".xslt", ".xsd", ".plist")

    flags = re.MULTILINE | re.DOTALL

    tokens = {
        "root": [
            (r"[^<&]+", Text),
            (_ENTITY, Name.Entity),
            (r"<!--.*?-->", Comment.Multiline),
            (
                r"(<!\[CDATA\[)(.*?)(\]\]>)",
                bygroups(Comment.Preproc, String, Comment.Preproc),
            ),
            (r"<\?[\w:.-]+", Comment.Preproc, "instruction"),
            # a DOCTYPE may carry an internal subset in square brackets
            (r"<!DOCTYPE\b[^>\[]*(?:\[.*?\][^>]*)?>", Comment.Preproc),
            (r"<![^>]*>", Comment.Preproc),
            (
                r"(<)(?:([^\W\d][\w.-]*)(:))?([^\W\d][\w.-]*)",
                bygroups(Punctuation, Name.Namespace, Punctuation, Name.Tag),
                "tag",
            ),
            (
                r"(<)(/)(\s*)(?:([^\W\d][\w.-]*)(:))?([^\W\d][\w.-]*)(\s*)(>)",
                bygroups(
                    Punctuation,
                    Punctuation,
                    Whitespace,
                    Name.Namespace,
                    Punctuation,
                    Name.Tag,
                    Whitespace,
                    Punctuation,
                ),
            ),
            (r"[<&]", Text),
        ],
        "attributes": [
            (r"\s+", Whitespace),
            (
                rf"({_TAG_NAME})(\s*)(=)(\s*)",
                bygroups(Name.Attribute, Whitespace, Operator, Whitespace),
                "attribute-value",
            ),
            (_TAG_NAME, Name.Attribute),
        ],
        "tag": [
            include("attributes"),
            (r"(/?)(\s*)(>)", bygroups(Punctuation, Whitespace, Punctuation), "#pop"),
        ],
        "instruction": [
            include("attributes"),
            (r"\?>", Comment.Preproc, "#pop"),
            (r"[^?\s]+|\?", Comment.Preproc),
        ],
        "attribute-value": _ATTRIBUTE_VALUE,
    }

    @staticmethod
    def analyse(code: str) -> float:
        if re.match(r"\s*<\?xml\b", code):
            return 0.95
        if re.match(r"\s*<(?:svg|rss|feed|urlset)\b[^>]*\bxmlns", code):
            return 0.85
        return 0.0
