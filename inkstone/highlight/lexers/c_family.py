from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, inherit, words
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
    Whitespace,
)

_C_KEYWORDS = """
    _Alignas _Alignof _Atomic _Generic _Noreturn _Static_assert _Thread_local
    alignas alignof auto break case const constexpr continue default do else
    enum extern for goto if inline register restrict return sizeof static
    static_assert struct switch thread_local typedef typeof union volatile
    while
""".split()

_C_TYPES = """
    FILE _Bool _Complex bool char char16_t char32_t double float int int8_t
    int16_t int32_t int64_t intmax_t intptr_t long ptrdiff_t short signed
    size_t ssize_t uint8_t uint16_t uint32_t uint64_t uintmax_t uintptr_t
    unsigned va_list void wchar_t
""".split()

_CPP_KEYWORDS = """
    and and_eq asm bitand bitor catch class co_await co_return co_yield compl
    concept const_cast consteval constinit decltype delete dynamic_cast
    explicit export final friend mutable namespace new noexcept not not_eq
    operator or or_eq override private protected public reinterpret_cast
    requires static_cast template this throw try typeid typename using virtual
    xor xor_eq
""".split()

_NAME = r"[a-zA-Z_]\w*"
# C++14 and C23 allow ' as a digit separator, but only between digits
_DEC = r"\d(?:'?\d)*"
_HEX = r"[0-9a-fA-F](?:'?[0-9a-fA-F])*"
_INT_SUFFIX = r"(?:[uU](?:ll|LL|[lLzZ])?|(?:ll|LL|[lLzZ])[uU]?)?"

_ESCAPE = (
    r"\\(?:[\\abefnrtv\"'?]|x[0-9a-fA-F]+|[0-7]{1,3}|u[0-9a-fA-F]{4}"
    r"|U[0-9a-fA-F]{8})"
)
_PRINTF = (
    r"%[-+ #0]*(?:\*|\d+)?(?:\.(?:\*|\d+))?(?:hh|ll|[hlLjzt])?[diouxXeEfFgGaAcspn%]"
)
# Keywords that can be followed by a colon at the start of a line without
# being a goto label.
_NOT_LABEL = "default|case|public|private|protected|signals|slots"


class _CFamilyLexer(RegexLexer):
    tokens = {
        "root": [
            (
                r"^([^\S\n]*)(#[^\S\n]*(?:include|import))([^\S\n]*)"
                r"(<[^>\n]*>|\"[^\"\n]*\")",
                bygroups(Whitespace, Comment.Preproc, Whitespace, Comment.PreprocFile),
            ),
            (r"^([^\S\n]*)(#)", bygroups(Whitespace, Comment.Preproc), "macro"),
            (
                rf"^([^\S\n]*)((?!(?:{_NOT_LABEL})\b){_NAME})([^\S\n]*)(:)(?![:=])",
                bygroups(Whitespace, Name.Label, Whitespace, Punctuation),
            ),
            include("whitespace"),
            include("statements"),
        ],
        "whitespace": [
            (r"\n", Whitespace),
            (r"[^\S\n]+", Whitespace),
            (r"\\\n", Text),
            (r"//[/!](?:[^\\\n]|\\.|\\\n)*", Comment.Doc),
            (r"//(?:[^\\\n]|\\.|\\\n)*", Comment.Single),
            (r"/\*[*!](?!/)(?:.|\n)*?\*/", Comment.Doc),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
        ],
        # The rest of a preprocessor line, continuation lines included.
        "macro": [
            (r"[^/\\\n]+", Comment.Preproc),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
            (r"//.*$", Comment.Single),
            (r"\\\n", Comment.Preproc),
            (r"[/\\]", Comment.Preproc),
            (r"\n", Whitespace, "#pop"),
        ],
        "statements": [
            include("literals"),
            (
                rf"(struct|union|enum)(\s+)({_NAME})",
                bygroups(Keyword, Whitespace, Name.Class),
            ),
            (r"(?:true|false|nullptr)\b", Keyword.Constant),
            (r"(?:NULL|EOF|stdin|stdout|stderr|errno)\b", Name.Builtin),
            (words(_C_KEYWORDS, suffix=r"\b"), Keyword),
            (words(_C_TYPES, suffix=r"\b"), Keyword.Type),
            include("names"),
            (
                r"->\*?|\+\+|--|<=>|<<=?|>>=?|&&|\|\||\.\.\.|[-+*/%&|^!=<>]=?|[~?]",
                Operator,
            ),
            (r"::?", Punctuation),
            (r"[()\[\]{};,.]", Punctuation),
        ],
        "names": [
            (rf"{_NAME}(?=\s*\()", Name.Function),
            (r"[A-Z][A-Z0-9_]+\b", Name.Constant),
            (_NAME, Name),
        ],
        "literals": [
            (r'(u8|[LuU])?(")', bygroups(String.Affix, String), "string"),
            (
                r"(u8|[LuU])?('(?:\\(?:x[0-9a-fA-F]+|[0-7]{1,3}|.)|[^\\'\n])')",
                bygroups(String.Affix, String.Char),
            ),
            (rf"0[xX](?:{_HEX})?\.?(?:{_HEX})?[pP][+-]?\d+[fFlL]?", Number.Float),
            (
                rf"(?:{_DEC}\.(?:{_DEC})?|\.{_DEC})(?:[eE][+-]?\d+)?[fFlL]?"
                rf"|{_DEC}[eE][+-]?\d+[fFlL]?|{_DEC}[fF]\b",
                Number.Float,
            ),
            (rf"0[xX]{_HEX}{_INT_SUFFIX}", Number.Hex),
            (rf"0[bB][01](?:'?[01])*{_INT_SUFFIX}", Number.Bin),
            (rf"0(?:'?[0-7])+{_INT_SUFFIX}", Number.Oct),
            (rf"{_DEC}{_INT_SUFFIX}", Number.Integer),
        ],
        "string": [
            (r'"', String, "#pop"),
            (_ESCAPE, String.Escape),
            (_PRINTF, String.Interpol),
            (r'[^\\"%\n]+', String),
            (r"\\\n", String),
            (r"[\\%]", String),
        ],
    }


@register
class CLexer(_CFamilyLexer):
    name = "c"
    aliases = ("h",)
    extensions = (".c", ".h")

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^\s*#\s*include\s*[<\"][\w/.]+\.h[>\"]", code, re.M):
            score += 0.45
        if re.search(r"\bint\s+main\s*\(", code):
            score += 0.2
        if re.search(r"\b(?:printf|malloc|sizeof)\s*\(|\bstruct\s+\w+\s*\{", code):
            score += 0.15
        return score


@register
class CppLexer(_CFamilyLexer):
    name = "cpp"
    aliases = ("c++", "cxx", "cc", "hpp", "hxx")
    extensions = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".ino")

    tokens = {
        "statements": [
            # R"delim( ... )delim"
            (
                r'((?:u8|[LuU])?R)("([^\\()\s]{0,16})\((?:.|\n)*?\)\3")',
                bygroups(String.Affix, String),
            ),
            (r"\[\[[\w:,\s()\"]+\]\]", Name.Decorator),
            (
                rf"(enum)(\s+)(class|struct)(\s+)({_NAME})",
                bygroups(Keyword, Whitespace, Keyword, Whitespace, Name.Class),
            ),
            (
                rf"(class|struct|concept)(\s+)({_NAME})",
                bygroups(Keyword, Whitespace, Name.Class),
            ),
            (
                rf"(namespace)(\s+)({_NAME}(?:::{_NAME})*)",
                bygroups(Keyword, Whitespace, Name.Namespace),
            ),
            (words(_CPP_KEYWORDS, suffix=r"\b"), Keyword),
            (r"(?:char8_t|string|string_view|wstring)\b", Keyword.Type),
            inherit,
        ],
        "names": [
            (rf"{_NAME}(?=::)", Name.Namespace),
            # foo<int>(x): still a call, as long as the brackets are simple
            (rf"{_NAME}(?=<[\w\s:,*&]*>\()", Name.Function),
            inherit,
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^\s*#\s*include\s*<[a-z_]+>", code, re.M):
            score += 0.45
        if re.search(r"\bstd::\w+|\busing\s+namespace\b", code):
            score += 0.3
        if re.search(r"\btemplate\s*<|\bclass\s+\w+\s*(?::\s*public\b|\{)", code):
            score += 0.2
        return min(score, 0.9)
