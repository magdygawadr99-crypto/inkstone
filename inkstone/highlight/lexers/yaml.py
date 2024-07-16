from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, this, using
from ..registry import register
from ..token import (
    Comment,
    Keyword,
    Literal,
    Name,
    Number,
    Punctuation,
    String,
    Whitespace,
)

# This is a line-oriented approximation, not a YAML parser. It knows nothing
# about indentation except for block scalars, which is enough for config
# files and front matter but will mis-colour the stranger corners of the spec.

# One non-blank character of a plain scalar. A colon only ends the scalar
# when whitespace follows, and a hash only starts a comment after whitespace.
_BLOCK_CHAR = r"(?:[^\s#:]|:(?=\S)|(?<=\S)#)"
_FLOW_CHAR = r"(?:[^\s,\[\]{}#:]|:(?=[^\s,\[\]{}])|(?<=\S)#)"
# Characters a plain scalar can't start with.
_NOT_INDICATOR = r"(?![\[\]{},'\"&*!|>%@`])"


def _plain(char: str) -> str:
    # first and last character are non-blank, so trailing spaces stay out
    return rf"{_NOT_INDICATOR}{char}(?:(?:{char}|[^\S\n])*{char})?"


_BLOCK_PLAIN = _plain(_BLOCK_CHAR)
_FLOW_PLAIN = _plain(_FLOW_CHAR)
_QUOTED = r'"(?:\\.|[^"\\\n])*"|' + r"'(?:''|[^'\n])*'"
_KEY_FOLLOWS = r"(?=[^\S\n]*:(?:\s|$))"

# What may come after a scalar for it to count as a number, boolean or date
# rather than the start of a longer plain string.
_BLOCK_END = r"(?=[^\S\n]*(?:#.*)?$)"
_FLOW_END = r"(?=[^\S\n]*(?:[,\]}]|#.*$|$))"

_NODE_PROPERTY = r"[^\s,\[\]{}]+"


def _typed_scalars(end: str) -> list:
    return [
        (rf"(?i:true|false|yes|no|on|off|null|~){end}", Keyword.Constant),
        (
            r"\d{4}-\d{2}-\d{2}(?:[Tt ]\d{1,2}:\d{2}:\d{2}(?:\.\d+)?"
            rf"(?:[^\S\n]*(?:Z|[-+]\d{{1,2}}(?::\d{{2}})?))?)?{end}",
            Literal.Date,
        ),
        (rf"[-+]?0x[0-9a-fA-F_]+{end}", Number.Hex),
        (rf"[-+]?0o[0-7_]+{end}", Number.Oct),
        (
            rf"[-+]?(?:\d[\d_]*\.\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?"
            rf"|\d[\d_]*[eE][-+]?\d+|\.(?i:inf|nan)){end}",
            Number.Float,
        ),
        (rf"[-+]?\d[\d_]*{end}", Number.Integer),
    ]


@register
class YamlLexer(RegexLexer):
    name = "yaml"
    aliases = ("yml",)
    extensions = (".yaml", ".yml")
    filenames = (".clang-format", ".yamllint")

    tokens = {
        "root": [
            (r"\n", Whitespace),
            (r"^(?:---|\.\.\.)(?=\s|$)", Name.Namespace),
            (r"^%.*$", Comment.Preproc),
            # A block scalar: "key: |" (or "- >-" and so on) followed by
            # every line indented deeper than the line it started on. The
            # (?! ) stops the indent group from backtracking, which gets
            # quadratic on long runs of spaces.
            (
                r"^([ ]*)(?! )((?:[^\n#'\"]*?[:-][ ]+)?(?:[!&]\S*[ ]+)*)"
                r"([|>][+-]?\d?[+-]?)([ ]*)(#.*)?(\n|\Z)"
                r"((?:(?:\1[ ]+.*|[ ]*)(?:\n|\Z))*)",
                bygroups(
                    Whitespace,
                    using(this),
                    Punctuation,
                    Whitespace,
                    Comment.Single,
                    Whitespace,
                    String,
                ),
            ),
            (r"[^\S\n]+", Whitespace),
            (r"(?:^|(?<=\s))#.*$", Comment.Single),
            (r"-(?=\s|$)", Punctuation),
            (r"\?(?=\s|$)", Punctuation),
            include("properties"),
            (rf"(?:{_QUOTED}){_KEY_FOLLOWS}", Name.Tag),
            (rf"{_BLOCK_PLAIN}{_KEY_FOLLOWS}", Name.Tag),
            (r":(?=\s|$)", Punctuation),
            include("quoted"),
            (r"[\[{]", Punctuation, "flow"),
            *_typed_scalars(_BLOCK_END),
            (_BLOCK_PLAIN, String),
            # leftovers of a malformed line; not worth an error each
            (r"[|>][+-]?\d?[+-]?|[\]},:]", Punctuation),
        ],
        "properties": [
            (rf"&{_NODE_PROPERTY}", Name.Label),
            (rf"\*{_NODE_PROPERTY}", Name.Variable),
            (rf"!(?:<[^>\n]*>|{_NODE_PROPERTY})?", Keyword.Type),
        ],
        "quoted": [
            (r'"', String, "double"),
            (r"'", String, "single"),
        ],
        "flow": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (r"[\[{]", Punctuation, "#push"),
            (r"[\]}]", Punctuation, "#pop"),
            (r",", Punctuation),
            include("properties"),
            (rf"(?:{_QUOTED}|{_FLOW_PLAIN}){_KEY_FOLLOWS}", Name.Tag),
            (r"[:?](?=\s|$)", Punctuation),
            include("quoted"),
            *_typed_scalars(_FLOW_END),
            (_FLOW_PLAIN, String),
        ],
        "double": [
            (r'"', String, "#pop"),
            (
                r"\\(?:x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}|.|\n)",
                String.Escape,
            ),
            (r'[^"\\]+', String),
        ],
        "single": [
            (r"''", String.Escape),
            (r"'", String, "#pop"),
            (r"[^']+", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        keys = re.findall(r"^[ ]*(?:- )?[\w.-]+:(?:[ ]|$)", code, re.M)
        if re.match(r"(?:\s*#.*\n)*---[ ]*\n", code) and keys:
            return 0.7
        # lines ending in ; or { mean CSS or a C-like language, whose
        # "case x:" and "label:" lines would otherwise pass for keys
        if len(keys) < 2 or re.search(r"[;{]\s*$", code, re.M):
            return 0.0
        return 0.45 if re.search(r"^[ ]*- \S", code, re.M) else 0.35
