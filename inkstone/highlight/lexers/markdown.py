from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, using
from ..registry import find_lexer, register
from ..token import (
    Comment,
    Generic,
    Keyword,
    Name,
    Punctuation,
    String,
    Text,
    Whitespace,
)

# The text of an inline span, lazily, within one paragraph. The length caps
# are there because an opener that is never closed makes the regex scan
# ahead from every such opener, and a page of stray asterisks or brackets
# would otherwise take seconds.
_SPAN = r"(?:[^\n]|\n(?!\n)){1,600}?"
_LINK_CHAR = r"(?:\\.|[^\]\\\n])"


# The closing fence has to repeat the opening one (longer is fine); a block
# that is never closed runs to the end of the document.
_FENCED_CODE = (
    r"^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})(?P<gap>[ \t]*)(?P<lang>[^\s`{]*)"
    r"(?P<gap2>[ \t]*)(?P<info>[^\n`]*)(?P<eol>\n|\Z)"
    r"(?P<body>(?:.*(?:\n|\Z))*?)"
    r"(?:(?P<indent2>[ ]{0,3})(?P<closing>(?P=fence)[`~]*)(?=[ \t]*$)|\Z)"
)
_FENCE_PARTS = (
    ("indent", Whitespace),
    ("fence", String.Backtick),
    ("gap", Whitespace),
    ("lang", Name.Label),
    ("gap2", Whitespace),
    ("info", Name.Attribute),
    ("eol", Whitespace),
    ("body", None),
    ("indent2", Whitespace),
    ("closing", String.Backtick),
)


def _fenced_code(lexer, match):
    """A ``` block: lex the body as whatever language the info string names."""
    language = match.group("lang")
    sub = find_lexer(language.lower()) if language else None
    for group, ttype in _FENCE_PARTS:
        text = match.group(group)
        if not text:
            continue
        start = match.start(group)
        if ttype is not None:
            yield start, ttype, text
        elif sub is None or sub.name == "text":
            yield start, String, text
        else:
            for offset, sub_type, value in sub.scan(text):
                yield start + offset, sub_type, value


def _front_matter(fence: str, closing: str, language: str) -> tuple:
    """Rule for a metadata block at the very top of the file."""
    return (
        rf"\A({fence}[ \t]*\n)((?:.*\n)*?)({closing})(?=[ \t]*$)",
        bygroups(Name.Namespace, using(language), Name.Namespace),
    )


@register
class MarkdownLexer(RegexLexer):
    name = "markdown"
    aliases = ("md", "mkd", "mdown")
    extensions = (".md", ".markdown", ".mdown", ".mkd")

    tokens = {
        "root": [
            _front_matter(r"---", r"---|\.\.\.", "yaml"),
            _front_matter(r"\+\+\+", r"\+\+\+", "toml"),
            (r"\n", Whitespace),
            (_FENCED_CODE, _fenced_code),
            (r"^#[ \t]+.*$", Generic.Heading),
            (r"^#{2,6}[ \t]+.*$", Generic.Subheading),
            # setext headings: a line of text underlined with === or ---
            (
                r"^([^\s#>*+`|\d-].*)(\n)(=+)(?=[ \t]*$)",
                bygroups(Generic.Heading, Whitespace, Generic.Heading),
            ),
            (
                r"^([^\s#>*+`|\d-].*)(\n)(-+)(?=[ \t]*$)",
                bygroups(Generic.Subheading, Whitespace, Generic.Subheading),
            ),
            # thematic breaks, then the |---|:-:| row under a table header
            (
                r"^[ ]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$",
                Punctuation,
            ),
            (
                r"^[ ]{0,3}\|?(?:[ \t]*:?-+:?[ \t]*\|)+(?:[ \t]*:?-+:?[ \t]*)?$",
                Punctuation,
            ),
            (r"^([ ]{0,3})((?:>[ ]?)+)", bygroups(Whitespace, Keyword)),
            (
                r"^([ \t]*)([*+-]|\d{1,9}[.)])([ \t]+)(\[[ xX]\](?=[ \t]))?",
                bygroups(Whitespace, Keyword, Whitespace, Keyword),
            ),
            # A footnote's text is prose; a link definition's is a target.
            (
                r"^([ ]{0,3})(\[\^[^\]\s]+\])(:)",
                bygroups(Whitespace, Name.Label, Punctuation),
            ),
            (
                r"^([ ]{0,3})(\[[^\]\n]+\])(:)([ \t]*)(\S+)?([ \t]*)(.*)$",
                bygroups(
                    Whitespace,
                    Name.Label,
                    Punctuation,
                    Whitespace,
                    Name.Attribute,
                    Whitespace,
                    String,
                ),
            ),
            include("inline"),
        ],
        "inline": [
            (r"\\[\\`*_{}\[\]()#+.!|<>~-]", String.Escape),
            (r"&(?:#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z]\w*);", Name.Entity),
            (r"(?<!`)(`+)(?!`)(?:.|\n(?!\n))+?(?<!`)\1(?!`)", String.Backtick),
            (r"<!--(?:.|\n)*?-->", Comment.Multiline),
            (
                r"(<)((?:https?|ftp|mailto):[^>\s]+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)(>)",
                bygroups(Punctuation, Name.Attribute, Punctuation),
            ),
            (r"</?[a-zA-Z][\w:-]*(?:\s[^<>]*)?/?>", using("html")),
            # [text](url "title") and ![alt](src)
            (
                rf"(!?\[)({_LINK_CHAR}{{0,300}})(\])(\()([^)\s]*)"
                r"([ \t]*)(\"[^\"\n]*\"|'[^'\n]*')?(\))",
                bygroups(
                    Punctuation,
                    Name.Tag,
                    Punctuation,
                    Punctuation,
                    Name.Attribute,
                    Whitespace,
                    String,
                    Punctuation,
                ),
            ),
            (r"\[\^[^\]\s]+\]", Name.Label),
            # [text][ref]
            (
                rf"(!?\[)({_LINK_CHAR}{{1,300}})(\])(\[)([^\]\n]*)(\])",
                bygroups(
                    Punctuation,
                    Name.Tag,
                    Punctuation,
                    Punctuation,
                    Name.Label,
                    Punctuation,
                ),
            ),
            (r"https?://[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"]", Name.Attribute),
            # Emphasis has to hug its text, and underscores inside a word
            # (snake_case) don't count.
            (rf"(\*\*\*|\*\*)(?=\S){_SPAN}(?<=\S)\1", Generic.Strong),
            (rf"(?<!\w)__(?=\S){_SPAN}(?<=\S)__(?!\w)", Generic.Strong),
            (r"\*[^\s*](?:[^*\n]*[^\s*])?\*(?!\*)", Generic.Emph),
            (r"(?<!\w)_[^\s_](?:[^_\n]*[^\s_])?_(?!\w)", Generic.Emph),
            (rf"~~(?=\S){_SPAN}(?<=\S)~~", Generic.Deleted),
            (r"[^\s\\`*_~\[\]!<&]+", Text),
            (r"[ \t]+", Whitespace),
            (r"[\\`*_~\[\]!<&]", Text),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^#{1,6} \S", code, re.M):
            score += 0.25
        if re.search(r"^(?:```|~~~)", code, re.M):
            score += 0.2
        if re.search(r"\[[^\]\n]+\]\([^)\s]+\)", code):
            score += 0.2
        if re.search(r"^\s*[-*] \S.*\n\s*[-*] \S", code, re.M):
            score += 0.1
        return score
