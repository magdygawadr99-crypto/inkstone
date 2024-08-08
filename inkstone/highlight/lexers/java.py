from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, words
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Whitespace,
)

_KEYWORDS = """
    abstract assert break case catch continue default do else extends final
    finally for goto if implements instanceof native new permits private
    protected public return sealed static strictfp switch synchronized throw
    throws transient try var volatile while yield
""".split()

_TYPES = "boolean byte char double float int long short void".split()

_NAME = r"[^\W\d][\w$]*"
_DEC = r"\d(?:_*\d)*"
_HEX = r"[0-9a-fA-F](?:_*[0-9a-fA-F])*"
_ESCAPE = r"\\(?:[btnfrs\"'\\]|u+[0-9a-fA-F]{4}|[0-7]{1,3})"
# java.util.Formatter: %s, %-10.2f, %1$d, %n
_FORMAT = r"%(?:\d+\$)?[-#+ 0,(]*\d*(?:\.\d+)?[bBhHsScCdoxXeEfgGaAn%]"


@register
class JavaLexer(RegexLexer):
    name = "java"
    aliases = ()
    extensions = (".java",)

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"/\*\*(?!/)(?:.|\n)*?\*/", Comment.Doc),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
            (r"//.*$", Comment.Single),
            (
                r"(package|import)(\s+)(?:(static)(\s+))?(\w+(?:\.\w+)*(?:\.\*)?)",
                bygroups(
                    Keyword.Namespace,
                    Whitespace,
                    Keyword,
                    Whitespace,
                    Name.Namespace,
                ),
            ),
            (r"@interface\b", Keyword.Declaration),
            (rf"@{_NAME}(?:\.{_NAME})*", Name.Decorator),
            (
                rf"(class|interface|enum)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            # "record" is a perfectly good variable name everywhere else
            (
                rf"(record)(\s+)({_NAME})(?=\s*[(<])",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            (r"(?:class|interface|enum)\b", Keyword.Declaration),
            (r"non-sealed\b", Keyword),
            (words(_KEYWORDS, suffix=r"\b"), Keyword),
            (words(_TYPES, suffix=r"\b"), Keyword.Type),
            (r"(?:true|false|null)\b", Keyword.Constant),
            (r"(?:this|super)\b", Name.Builtin.Pseudo),
            include("literals"),
            (r"[A-Z][A-Z0-9_]+\b", Name.Constant),
            # the naming convention is reliable enough to lean on
            (r"[A-Z][\w$]*", Name.Class),
            (rf"{_NAME}(?=\s*\()", Name.Function),
            (_NAME, Name),
            (
                r"->|>>>=?|<<=?|>>=?|\+\+|--|&&|\|\||[-+*/%&|^!=<>]=?|[~?]",
                Operator,
            ),
            (r"::|\.\.\.|[()\[\]{}:;,.@]", Punctuation),
        ],
        "literals": [
            (r'"""', String, "text-block"),
            (r'"', String, "string"),
            (rf"'(?:{_ESCAPE}|[^\\'\n])'", String.Char),
            (rf"0[xX]{_HEX}[lL]?", Number.Hex),
            (r"0[bB][01](?:_*[01])*[lL]?", Number.Bin),
            (
                rf"(?:{_DEC}\.(?:{_DEC})?|\.{_DEC})(?:[eE][+-]?{_DEC})?[fFdD]?"
                rf"|{_DEC}[eE][+-]?{_DEC}[fFdD]?|{_DEC}[fFdD]",
                Number.Float,
            ),
            (r"0(?:_*[0-7])+[lL]?", Number.Oct),
            (rf"{_DEC}[lL]?", Number.Integer),
        ],
        "string": [
            (r'"', String, "#pop"),
            (_ESCAPE, String.Escape),
            (_FORMAT, String.Interpol),
            (r'[^"\\%\n]+', String),
            (r"[\\%]", String),
        ],
        "text-block": [
            (r'"""', String, "#pop"),
            (_ESCAPE, String.Escape),
            # a backslash at the end of a line joins it to the next
            (r"\\\n", String.Escape),
            (_FORMAT, String.Interpol),
            (r'[^"\\%]+', String),
            (r'["\\%]', String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^\s*import\s+java[\w.]*\.[\w*]+\s*;", code, re.M):
            score += 0.5
        if re.search(r"\bpublic\s+(?:final\s+|abstract\s+)?class\s+\w+", code):
            score += 0.35
        if re.search(r"\bpublic\s+static\s+void\s+main\b|System\.out\.", code):
            score += 0.3
        return min(score, 0.9)
