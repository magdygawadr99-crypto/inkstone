from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, words
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    TokenType,
    Whitespace,
)

_KEYWORDS = """
    as async await break continue dyn else for if in loop match move mut pub
    ref return unsafe where while yield
""".split()

_DECLARATIONS = "const enum fn impl let static struct trait type".split()

_TYPES = """
    bool char f32 f64 i8 i16 i32 i64 i128 isize str u8 u16 u32 u64 u128 usize
""".split()

# prelude items, more or less
_BUILTINS = """
    Box Clone Copy Default Drop Eq Err From Into Iterator None Ok Option Ord
    PartialEq PartialOrd Result Send Sized Some String Sync ToString Vec
""".split()

_NAME = r"[^\W\d]\w*"
_INT_SUFFIX = r"(?:[iu](?:8|16|32|64|128|size))?"
_FLOAT_SUFFIX = r"(?:_?f(?:32|64))"
_EXPONENT = r"[eE][+-]?[\d_]+"
_ESCAPE = r"\\(?:[nrt0\\'\"]|x[0-9a-fA-F]{2}|u\{[0-9a-fA-F_]{1,6}\})"


def _nested_comment(ttype: TokenType) -> list:
    # block comments nest in Rust, so count the openers
    return [
        (r"[^*/]+", ttype),
        (r"/\*", ttype, "#push"),
        (r"\*/", ttype, "#pop"),
        (r"[*/]", ttype),
    ]


@register
class RustLexer(RegexLexer):
    name = "rust"
    aliases = ("rs",)
    extensions = (".rs",)

    tokens = {
        "root": [
            (r"\A#!(?!\[).*$", Comment.Hashbang),
            (r"\s+", Whitespace),
            (r"//[/!].*$", Comment.Doc),
            (r"//.*$", Comment.Single),
            (r"/\*[*!](?![*/])", Comment.Doc, "doc-comment"),
            (r"/\*", Comment.Multiline, "comment"),
            (r"#!?\[", Comment.Preproc, "attribute"),
            (
                rf"(fn)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Function),
            ),
            (
                rf"(struct|enum|trait|type)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            # "union" is only a keyword in front of a definition
            (
                rf"(union)(\s+)({_NAME})(?=\s*[{{<])",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            (
                rf"(mod)(\s+)({_NAME})",
                bygroups(Keyword.Namespace, Whitespace, Name.Namespace),
            ),
            (
                rf"(macro_rules!)(\s+)({_NAME})",
                bygroups(Name.Function.Magic, Whitespace, Name.Function),
            ),
            (r"(?:use|mod|extern)\b", Keyword.Namespace),
            (r"(?:self|Self|crate|super)\b", Name.Builtin.Pseudo),
            (r"(?:true|false)\b", Keyword.Constant),
            (words(_DECLARATIONS, suffix=r"\b"), Keyword.Declaration),
            (words(_KEYWORDS, suffix=r"\b"), Keyword),
            (words(_TYPES, suffix=r"\b"), Keyword.Type),
            (r"b?'(?:" + _ESCAPE + r"|[^\\'\n])'", String.Char),
            (rf"'{_NAME}", Name.Label),
            (r'(?:b|c)?r(#*)"(?:.|\n)*?"\1', String),
            (r'(?:b|c)?"', String, "string"),
            (rf"0b[01_]+{_INT_SUFFIX}", Number.Bin),
            (rf"0o[0-7_]+{_INT_SUFFIX}", Number.Oct),
            (rf"0x[0-9a-fA-F_]+{_INT_SUFFIX}", Number.Hex),
            # not after a dot: in t.0.1 those are tuple fields, not "0.1"
            (
                rf"(?<!\.)\d[\d_]*\.\d[\d_]*(?:{_EXPONENT})?{_FLOAT_SUFFIX}?"
                rf"|\d[\d_]*{_EXPONENT}{_FLOAT_SUFFIX}?|\d[\d_]*{_FLOAT_SUFFIX}"
                rf"|(?<!\.)\d[\d_]*\.(?![\w.])",
                Number.Float,
            ),
            (rf"\d[\d_]*{_INT_SUFFIX}", Number.Integer),
            (rf"{_NAME}!(?=\s*[(\[{{])", Name.Function.Magic),
            (rf"r#{_NAME}", Name),
            (rf"\${_NAME}", Name.Variable),
            (words(_BUILTINS, suffix=r"\b"), Name.Builtin),
            (r"[A-Z][A-Z0-9_]+\b", Name.Constant),
            (r"[A-Z]\w*", Name.Class),
            (rf"{_NAME}(?=::)", Name.Namespace),
            (rf"{_NAME}(?=\s*\()", Name.Function),
            (_NAME, Name),
            (
                r"->|=>|\.\.=|\.\.\.?|&&|\|\||<<=?|>>=?|[-+*/%&|^!=<>]=?|[?~@$]",
                Operator,
            ),
            (r"::|[()\[\]{}:;,.#]", Punctuation),
        ],
        "comment": _nested_comment(Comment.Multiline),
        "doc-comment": _nested_comment(Comment.Doc),
        "attribute": [
            (r"\]", Comment.Preproc, "#pop"),
            (r"\[", Comment.Preproc, "#push"),
            (r'"(?:\\.|[^"\\])*"', String),
            (r'[^\[\]"]+', Comment.Preproc),
            (r'"', Comment.Preproc),
        ],
        "string": [
            (r'"', String, "#pop"),
            (_ESCAPE, String.Escape),
            (r"\\\n\s*", String.Escape),
            (r"\{\{|\}\}", String.Escape),
            # format placeholders: {}, {0}, {name}, {:>8.3}, {x:?}
            (r"\{[\w.]*(?::[^{}\n\"]*)?\}", String.Interpol),
            (r'[^"\\{}]+', String),
            (r"[\\{}]", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"\bfn\s+\w+\s*(?:<[^>]*>)?\s*\(", code):
            score += 0.4
        if re.search(r"\blet\s+mut\b|\bimpl\b.*\bfor\b|^\s*use\s+\w+::", code, re.M):
            score += 0.3
        if re.search(r"\bprintln!\(|#\[derive\(|\bpub\s+(?:fn|struct|enum)\b", code):
            score += 0.2
        return score
