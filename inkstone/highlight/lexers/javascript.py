from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, default, include, inherit, words
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

# TODO: JSX. It lexes without errors but the tags come out as operators and
# plain names.

_KEYWORDS = """
    as async await break case catch continue debugger default delete do else
    export extends finally for if import in instanceof new of return switch
    throw try typeof void while with yield
""".split()

_BUILTINS = """
    Array ArrayBuffer BigInt Boolean DataView Date Function Intl JSON Map Math
    Number Object Promise Proxy Reflect RegExp Set String Symbol WeakMap
    WeakSet arguments clearInterval clearTimeout console decodeURIComponent
    document encodeURIComponent exports fetch globalThis isFinite isNaN
    localStorage module navigator parseFloat parseInt process queueMicrotask
    require setInterval setTimeout structuredClone window
""".split()

_ERRORS = """
    AggregateError Error EvalError RangeError ReferenceError SyntaxError
    TypeError URIError
""".split()

_TS_KEYWORDS = """
    abstract accessor asserts declare implements infer is keyof out override
    private protected public readonly satisfies unique
""".split()

_TS_TYPES = """
    any bigint boolean never number object string symbol unknown void
""".split()

_NAME = r"(?:[^\W\d]|\$)[\w$]*"
# Not after a single dot: promise.catch() and obj.default are plain property
# names. Three dots are spread, where a keyword may well follow (...this.args).
_NOT_PROPERTY = r"(?<![^.]\.)"
_DIGITS = r"\d(?:_?\d)*"

_MODIFIERS = "abstract|async|get|override|private|protected|public|readonly|set|static"
# Things that look like "name(...) {" at the start of a line but aren't methods.
_NOT_METHOD = "catch|do|else|for|function|if|return|switch|while|with"
# What follows a method name: optional generics, a flat parameter list, an
# optional return type and then the body. Nested parentheses in default
# values defeat it, which only costs the colour.
_METHOD_TAIL = (
    r"(?=[^\S\n]*(?:<[^<>()\n]*>[^\S\n]*)?\([^()\n]*\)[^\S\n]*(?::[^{};=\n]+)?\{)"
)


def _modifiers(lexer, match):
    pos = match.start()
    for part in re.split(r"(\s+)", match.group()):
        if part:
            yield pos, Whitespace if part.isspace() else Keyword, part
            pos += len(part)


@register
class JavaScriptLexer(RegexLexer):
    name = "javascript"
    aliases = ("js", "jsx", "node", "ecmascript", "mjs", "cjs")
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    shebangs = (r"node(js)?", "deno", "bun")

    tokens = {
        "root": [
            (r"\A#!.*$", Comment.Hashbang),
            (
                rf"^([^\S\n]*)((?:(?:{_MODIFIERS})[^\S\n]+)*)(\*?)"
                rf"((?!(?:{_NOT_METHOD})\b)#?{_NAME}){_METHOD_TAIL}",
                bygroups(Whitespace, _modifiers, Operator, Name.Function),
            ),
            # a slash that begins a line is a regex, not a division
            (r"^(?=[^\S\n]*/)", Text, "slashstartsregex"),
            include("whitespace"),
            include("literals"),
            include("declarations"),
            include("names"),
            (r"\+\+|--", Operator),
            (
                r"\?\?=?|\?\.|&&=?|\|\|=?|\*\*=?|>>>=?|<<=?|>>=?|=>|[!=]==?"
                r"|\.\.\.|[-+*/%&|^<>=!]=?|[~?:]",
                Operator,
                "slashstartsregex",
            ),
            (r"\{", Punctuation, "slashstartsregex"),
            (r"[(\[;,]", Punctuation, "slashstartsregex"),
            (r"[)\]}.]", Punctuation),
        ],
        "whitespace": [
            (r"\n", Whitespace),
            include("blanks"),
        ],
        "blanks": [
            (r"[^\S\n]+", Whitespace),
            (r"/\*\*(?!/)(?:.|\n)*?\*/", Comment.Doc),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
            (r"//.*$", Comment.Single),
        ],
        # Entered after anything that can't end an expression. Newlines are
        # left for root, whose line-anchored rules need to see them.
        "slashstartsregex": [
            include("blanks"),
            (
                r"/(?:\\.|[^\[/\\\n]|\[(?:\\.|[^\]\\\n])*\])+/[dgimsuvy]*",
                String.Regex,
                "#pop",
            ),
            default("#pop"),
        ],
        "literals": [
            (r"0[bB][01](?:_?[01])*n?", Number.Bin),
            (r"0[oO][0-7](?:_?[0-7])*n?", Number.Oct),
            (r"0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*n?", Number.Hex),
            (
                rf"(?:{_DIGITS})?\.{_DIGITS}(?:[eE][+-]?\d+)?"
                rf"|{_DIGITS}[eE][+-]?\d+",
                Number.Float,
            ),
            (rf"{_DIGITS}n?", Number.Integer),
            (r'"', String, "dqs"),
            (r"'", String, "sqs"),
            (r"`", String.Backtick, "template"),
        ],
        "declarations": [
            (
                rf"(function)\b(\s*)(\*?)(\s*)({_NAME})?",
                bygroups(
                    Keyword.Declaration, Whitespace, Operator, Whitespace, Name.Function
                ),
            ),
            (
                rf"(class)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            # const add = (a, b) => ...   and   handler = function () {}
            (
                rf"({_NAME})(\s*)(=)(\s*)"
                rf"(?=(?:async\s*)?(?:function\b|\([^()\n]*\)\s*(?::[^=\n]+)?=>"
                rf"|{_NAME}\s*=>))",
                bygroups(Name.Function, Whitespace, Operator, Whitespace),
            ),
            (rf"{_NOT_PROPERTY}(?:var|let|const|class)\b", Keyword.Declaration),
        ],
        "names": [
            (rf"@{_NAME}(?:\.{_NAME})*", Name.Decorator),
            (
                rf"{_NOT_PROPERTY}(?:true|false|null|undefined|NaN|Infinity)\b",
                Keyword.Constant,
            ),
            (rf"{_NOT_PROPERTY}(?:this|super)\b", Name.Builtin.Pseudo),
            # contextual keywords: only where they can't be an identifier
            (r"from(?=\s*[\"'])", Keyword),
            (rf"(?:get|set|static)(?=\s+[#\[]?{_NAME})", Keyword),
            (
                words(_KEYWORDS, prefix=_NOT_PROPERTY, suffix=r"\b"),
                Keyword,
                "slashstartsregex",
            ),
            (words(_ERRORS, prefix=_NOT_PROPERTY, suffix=r"\b"), Name.Exception),
            (words(_BUILTINS, prefix=_NOT_PROPERTY, suffix=r"\b"), Name.Builtin),
            (rf"#?{_NAME}", Name),
        ],
        "escapes": [
            (
                r"\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|u\{[0-9a-fA-F]+\}|[^\n])",
                String.Escape,
            ),
            (r"\\\n", String),
        ],
        "dqs": [
            (r'"', String, "#pop"),
            include("escapes"),
            (r'[^"\\\n]+', String),
            (r"\n", Whitespace, "#pop"),
        ],
        "sqs": [
            (r"'", String, "#pop"),
            include("escapes"),
            (r"[^'\\\n]+", String),
            (r"\n", Whitespace, "#pop"),
        ],
        "template": [
            (r"`", String.Backtick, "#pop"),
            include("escapes"),
            (r"\$\{", String.Interpol, ("interp", "slashstartsregex")),
            (r"[^`\\$]+", String.Backtick),
            (r"\$", String.Backtick),
        ],
        "interp": [
            (r"\}", String.Interpol, "#pop"),
            (r"\{", Punctuation, ("braces", "slashstartsregex")),
            include("root"),
        ],
        # object literals and blocks inside ${...}; without this their
        # closing brace would end the interpolation early
        "braces": [
            (r"\}", Punctuation, "#pop"),
            (r"\{", Punctuation, ("#push", "slashstartsregex")),
            include("root"),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"\b(?:const|let|var)\s+[\w$]+\s*=", code):
            score += 0.25
        if re.search(r"\bfunction\s*[\w$]*\s*\(|=>\s*[{(]", code):
            score += 0.2
        if re.search(r"\bconsole\.log\(|\brequire\(['\"]|\bdocument\.", code):
            score += 0.2
        if re.search(r"^(?:import|export)\b.*\bfrom\s+['\"]", code, re.M):
            score += 0.2
        return min(score, 0.8)


# Positions where a type is expected, so "string" and friends used as
# ordinary identifiers elsewhere stay plain.
_TYPE_CONTEXT = (
    r"(?:(?<=[:<|&(,\[])|(?<=[:|&,=<>]\s)|(?<=\bas\s)|(?<=\bis\s)"
    r"|(?<=\bkeyof\s)|(?<=\bextends\s))"
)


@register
class TypeScriptLexer(JavaScriptLexer):
    name = "typescript"
    aliases = ("ts", "tsx", "mts", "cts")
    extensions = (".ts", ".tsx", ".mts", ".cts")
    shebangs = ("ts-node", "tsx")

    tokens = {
        "declarations": [
            (
                rf"(interface|enum)(\s+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            # "type" is far too common as a property name to be a keyword
            # anywhere but in front of an alias declaration
            (
                rf"(type)(\s+)({_NAME})(?=\s*(?:=|<))",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            (
                rf"(namespace|module)(\s+)({_NAME}(?:\.{_NAME})*)",
                bygroups(Keyword.Declaration, Whitespace, Name.Namespace),
            ),
            # import type { A } / export type { A }, but not "export type A ="
            (
                r"(import|export)(\s+)(type)(?=\s*[{*]|\s+[\w$]+\s*(?:,|from\b))",
                bygroups(Keyword, Whitespace, Keyword),
            ),
            (
                r"(declare)(\s+)(module|global)\b",
                bygroups(Keyword, Whitespace, Keyword.Declaration),
            ),
            inherit,
        ],
        "names": [
            # the lookahead keeps parameters that happen to be called
            # "object" or "symbol" out of it
            (rf"{_TYPE_CONTEXT}{words(_TS_TYPES)}\b(?!\s*\??:)", Keyword.Type),
            (words(_TS_KEYWORDS, prefix=_NOT_PROPERTY, suffix=r"\b"), Keyword),
            inherit,
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        # Python has "type X = ..." statements too, hence the fussy ending
        if re.search(
            r"^\s*(?:export\s+)?(?:interface\s+\w+[^\n]*\{|type\s+\w+[^\n]*=.*[;{|]$)",
            code,
            re.M,
        ):
            score += 0.4
        if re.search(r"[\w)\]]\??:\s*(?:string|number|boolean|void)\b", code):
            score += 0.35
        if re.search(r"\b(?:private|public|readonly)\s+\w+\s*[:(]", code):
            score += 0.15
        return min(score, 0.85)
