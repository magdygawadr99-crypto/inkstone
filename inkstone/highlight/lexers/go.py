from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, this, using, words
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
    break case continue default defer else fallthrough for go goto if range
    return select switch
""".split()

_DECLARATIONS = "chan const func interface map struct type var".split()

_TYPES = """
    any bool byte comparable complex64 complex128 error float32 float64 int
    int8 int16 int32 int64 rune string uint uint8 uint16 uint32 uint64 uintptr
""".split()

_BUILTINS = """
    append cap clear close complex copy delete imag len make max min new panic
    print println real recover
""".split()

_NAME = r"[^\W\d]\w*"
_DEC = r"\d(?:_?\d)*"
_ESCAPE = (
    r"\\(?:[abfnrtv\\'\"]|[0-7]{3}|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})"
)
# fmt verbs: %v, %+v, %-8.3f, %[1]d, %%
_VERB = r"%[-+# 0]*(?:\[\d+\])?(?:\*|\d+)?(?:\.(?:\*|\d+))?[vTtbcdoOqxXUeEfFgGsp%]"


@register
class GoLexer(RegexLexer):
    name = "go"
    aliases = ("golang",)
    extensions = (".go",)

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"//(?:go:\w+|\s*\+build\b).*$", Comment.Preproc),
            (r"//.*$", Comment.Single),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
            (
                rf"(package)(\s+)({_NAME})",
                bygroups(Keyword.Namespace, Whitespace, Name.Namespace),
            ),
            (r"import\b", Keyword.Namespace),
            # func (r *Receiver) Method(...); the lookahead keeps the result type
            # of an anonymous func(x int) error {...} from looking like a name
            (
                rf"(func)(\s*)(\([^()\n]*\))(\s*)({_NAME})(?=\s*\()",
                bygroups(
                    Keyword.Declaration,
                    Whitespace,
                    using(this),
                    Whitespace,
                    Name.Function,
                ),
            ),
            (
                rf"(func)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Function),
            ),
            (
                rf"(type)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            (words(_DECLARATIONS, suffix=r"\b"), Keyword.Declaration),
            (words(_KEYWORDS, suffix=r"\b"), Keyword),
            (r"(?:true|false|nil|iota)\b", Keyword.Constant),
            (words(_TYPES, suffix=r"\b"), Keyword.Type),
            (words(_BUILTINS, suffix=r"\b(?=\s*\()"), Name.Builtin),
            (r"0[xX]_?[0-9a-fA-F](?:_?[0-9a-fA-F])*i?", Number.Hex),
            (r"0[bB]_?[01](?:_?[01])*i?", Number.Bin),
            (r"0[oO]?_?[0-7](?:_?[0-7])*i?(?![\d.eE])", Number.Oct),
            (
                rf"(?:{_DEC}\.(?:{_DEC})?|\.{_DEC})(?:[eE][+-]?{_DEC})?i?"
                rf"|{_DEC}[eE][+-]?{_DEC}i?|{_DEC}i",
                Number.Float,
            ),
            (_DEC, Number.Integer),
            (rf"'(?:{_ESCAPE}|[^\\'\n])'", String.Char),
            (r"`[^`]*`", String.Backtick),
            (r'"', String, "string"),
            (rf"{_NAME}(?=\s*\()", Name.Function),
            (_NAME, Name),
            (
                r"<-|:=|\+\+|--|&&|\|\||&\^=?|<<=?|>>=?|\.\.\.|[-+*/%&|^<>=!]=?|~",
                Operator,
            ),
            (r"[()\[\]{}:;,.]", Punctuation),
        ],
        "string": [
            (r'"', String, "#pop"),
            (_ESCAPE, String.Escape),
            (_VERB, String.Interpol),
            (r'[^"\\%\n]+', String),
            (r"[\\%]", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^package \w+\s*$", code, re.M):
            score += 0.5
        if re.search(r"^func (?:\([^)]*\) )?\w+\(", code, re.M):
            score += 0.3
        if re.search(r"\b\w+ := |\bfmt\.Print", code):
            score += 0.15
        return score
