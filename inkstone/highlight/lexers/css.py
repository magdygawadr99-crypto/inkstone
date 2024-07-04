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
    Text,
    Whitespace,
)

# Nowhere near the full list of value keywords, just the ones that actually
# show up in stylesheets people paste into posts.
_VALUE_KEYWORDS = """
    absolute all alternate auto backwards baseline block bold bolder border-box
    both bottom break-word capitalize center collapse column column-reverse
    contain content-box cover currentcolor dashed default dotted double ease
    ease-in ease-in-out ease-out ellipsis fixed flex flex-end flex-start
    forwards grid hidden infinite inherit initial inline inline-block
    inline-flex inset italic justify left lighter linear lowercase middle
    monospace no-repeat none normal nowrap oblique outside pointer pre
    pre-wrap relative repeat revert reverse right row row-reverse sans-serif
    scroll serif small-caps solid space-around space-between space-evenly
    start end static sticky stretch table thin top transparent underline unset
    uppercase visible wrap
""".split()

_COLORS = """
    aqua beige black blue brown chocolate coral crimson cyan firebrick fuchsia
    gainsboro gold gray green grey indigo ivory khaki lavender lime linen
    magenta maroon navy olive orange orchid pink plum purple rebeccapurple red
    salmon sienna silver tan teal tomato turquoise violet wheat white yellow
""".split()

_UNITS = (
    "ch|cm|deg|dpi|dppx|dvh|dvw|em|ex|fr|grad|hz|in|khz|lh|mm|ms|pc|pt|px|q"
    "|rad|rem|rlh|svh|svw|s|turn|vh|vmax|vmin|vw|x|%"
)
_IDENT = r"-?[_a-zA-Z][\w-]*"
_NOT_IDENT = r"(?![\w-])"
_STRING = r'"(?:\\.|\\\n|[^"\\\n])*"|' + r"'(?:\\.|\\\n|[^'\\\n])*'"
# "a:hover {" starts with a word and a colon just like "color: red;" does.
# It's a declaration only if the statement ends before any brace opens;
# strings are skipped so content: "{" doesn't confuse things.
_ENDS_AS_DECLARATION = rf"(?=(?:[^{{}};\"']|{_STRING})*(?:[;}}]|\Z))"


@register
class CssLexer(RegexLexer):
    name = "css"
    aliases = ("css3", "stylesheet")
    extensions = (".css",)

    flags = re.MULTILINE | re.IGNORECASE

    tokens = {
        "root": [
            include("basics"),
            (r"\}", Punctuation),
            include("at-rules"),
            include("selector"),
            (r"\{", Punctuation, "block"),
        ],
        "basics": [
            (r"\s+", Whitespace),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
        ],
        "at-rules": [
            (r"@(?:charset|import|namespace)\b", Keyword, "at-statement"),
            (r"@[\w-]+", Keyword, "at-prelude"),
        ],
        "selector": [
            (r"[>+~|]", Operator),
            (r",", Punctuation),
            (r"[*&]", Name.Tag),
            (rf"\.{_IDENT}", Name.Class),
            (rf"#{_IDENT}", Name.Constant),
            (r"(::?[\w-]+)(\()", bygroups(Name.Decorator, Punctuation), "pseudo-args"),
            (r"::?[\w-]+", Name.Decorator),
            (r"\[", Punctuation, "attribute"),
            # keyframe stops
            (r"\d+(?:\.\d+)?%", Number),
            (_IDENT, Name.Tag),
        ],
        "pseudo-args": [
            (r"\s+", Whitespace),
            (r"\)", Punctuation, "#pop"),
            # :nth-child(2n+1), :nth-of-type(odd)
            (r"[+-]?\d*n(?:\s*[+-]\s*\d+)?|[+-]?\d+|(?:odd|even)\b", Number),
            (_STRING, String),
            include("selector"),
        ],
        "attribute": [
            (r"\s+", Whitespace),
            (r"\]", Punctuation, "#pop"),
            (r"[~|^$*]?=", Operator),
            (_STRING, String),
            (rf"(?<==){_IDENT}", String),
            (r"[is](?=\s*\])", Keyword),
            (r"[\w:-]+", Name.Attribute),
        ],
        "at-statement": [
            include("basics"),
            (r";", Punctuation, "#pop"),
            include("values"),
        ],
        # everything between "@media" (or friends) and the opening brace
        "at-prelude": [
            include("basics"),
            (r"\{", Punctuation, ("#pop", "block")),
            (r";", Punctuation, "#pop"),
            (r"(?:and|not|only|or|from|to|through)\b", Operator.Word),
            # @page :first
            (r":[\w-]+", Name.Decorator),
            (r"\(", Punctuation, "at-condition"),
            (r"[<>]=?|=", Operator),
            include("values"),
        ],
        "at-condition": [
            include("basics"),
            (r"\)", Punctuation, "#pop"),
            (r"\(", Punctuation, "#push"),
            (r"(?:and|not|or)\b", Operator.Word),
            (r"([\w-]+)(\s*)(:)", bygroups(Name.Property, Whitespace, Punctuation)),
            (r"[<>]=?|=", Operator),
            include("values"),
        ],
        # A declaration block. With nesting, rules can also live in here, so
        # anything that isn't "property: value" is treated as a selector.
        "block": [
            include("basics"),
            (r"\}", Punctuation, "#pop"),
            (r";", Punctuation),
            include("at-rules"),
            include("declaration"),
            include("selector"),
            (r"\{", Punctuation, "#push"),
        ],
        "declaration": [
            (
                r"(--[\w-]+)(\s*)(:)",
                bygroups(Name.Variable, Whitespace, Punctuation),
                "value",
            ),
            (
                rf"([\w-]+)(\s*)(:){_ENDS_AS_DECLARATION}",
                bygroups(Name.Property, Whitespace, Punctuation),
                "value",
            ),
        ],
        "value": [
            include("basics"),
            (r";", Punctuation, "#pop"),
            (r"(?=\})", Text, "#pop"),
            include("values"),
        ],
        "values": [
            (r"!\s*important\b", Keyword),
            (r"#[0-9a-f]{3,8}\b", Number.Hex),
            (
                rf"([+-]?(?:\d*\.\d+)(?:e[+-]?\d+)?)({_UNITS})?{_NOT_IDENT}",
                bygroups(Number.Float, Keyword.Type),
            ),
            (
                rf"([+-]?\d+(?:e[+-]?\d+)?)({_UNITS})?{_NOT_IDENT}",
                bygroups(Number.Integer, Keyword.Type),
            ),
            (r"u\+[0-9a-f?]{1,6}(?:-[0-9a-f]{1,6})?", Number.Hex),
            (
                r"(url)(\()(\s*)([^\s)\"']+)(\s*)(\))",
                bygroups(
                    Name.Function,
                    Punctuation,
                    Whitespace,
                    String.Other,
                    Whitespace,
                    Punctuation,
                ),
            ),
            (
                r"(--[\w-]+|[\w-]+)(\()",
                bygroups(Name.Function, Punctuation),
                "function",
            ),
            (r"--[\w-]+", Name.Variable),
            (_STRING, String),
            (words(_VALUE_KEYWORDS, suffix=_NOT_IDENT), Keyword.Constant),
            (words(_COLORS, suffix=_NOT_IDENT), Name.Constant),
            (_IDENT, Name),
            (r"[,/]", Punctuation),
            (r"[*+-]", Operator),
            (r"\(", Punctuation, "function"),
        ],
        "function": [
            include("basics"),
            (r"\)", Punctuation, "#pop"),
            include("values"),
        ],
        # the contents of a style="..." attribute
        "inline": [
            include("basics"),
            (r";", Punctuation),
            (
                r"(--[\w-]+|[\w-]+)(\s*)(:)",
                bygroups(Name.Property, Whitespace, Punctuation),
                "value",
            ),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        rules = re.findall(r"[\w\])*]\s*\{\s*(?:--)?[\w-]+\s*:[^{}]*\}", code)
        if not rules:
            return 0.0
        if re.search(r"@(?:media|import|font-face|keyframes)\b", code):
            return 0.6
        return 0.45 if len(rules) > 1 else 0.3
