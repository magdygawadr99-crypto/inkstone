from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, this, using
from ..registry import register
from ..token import (
    Comment,
    Error,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Whitespace,
)


@register
class JsonLexer(RegexLexer):
    name = "json"
    aliases = ("jsonc", "jsonl", "ndjson", "geojson")
    extensions = (".json", ".jsonc", ".jsonl", ".geojson", ".webmanifest")
    filenames = (".babelrc", ".eslintrc", ".prettierrc", "*.code-workspace")

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            # not JSON proper, but tsconfig and VS Code settings are full of them
            (r"//.*$", Comment.Single),
            (r"/\*(?:.|\n)*?\*/", Comment.Multiline),
            (r'"(?:\\.|[^"\\\n])*"(?=\s*:)', Name.Tag),
            (r'"', String, "string"),
            (
                r"-?(?:0|[1-9]\d*)(?:\.\d+(?:[eE][+-]?\d+)?|[eE][+-]?\d+)",
                Number.Float,
            ),
            (r"-?(?:0|[1-9]\d*)", Number.Integer),
            (r"(?:true|false|null)\b", Keyword.Constant),
            (r"[{}\[\],:]", Punctuation),
            # anything else isn't JSON; flag the whole word at once
            (r"[^\s{}\[\],:\"/\d-]+", Error),
        ],
        "string": [
            (r'"', String, "#pop"),
            (r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})', String.Escape),
            (r'[^"\\\n]+', String),
            (r"\n", Whitespace, "#pop"),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        stripped = re.sub(r"\A(?:\s*//.*\n)+", "", code).strip()
        if not stripped or stripped[0] not in "{[" or stripped[-1] not in "}]":
            return 0.0
        if re.search(r'"(?:\\.|[^"\\\n])*"\s*:', stripped):
            return 0.75
        # an array of scalars; could just as well be Python or JavaScript
        return 0.2


_TOML_DIGITS = r"\d(?:_?\d)*"
_TOML_ESCAPE = r'\\(?:[btnfre"\\]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})'
_TOML_BARE_KEY = r"[A-Za-z0-9_-]+"
_TOML_QUOTED_KEY = r'"(?:\\.|[^"\\\n])*"|' + r"'[^'\n]*'"


@register
class TomlLexer(RegexLexer):
    name = "toml"
    aliases = ()
    extensions = (".toml",)
    filenames = ("Pipfile", "poetry.lock", "Cargo.lock", "uv.lock")

    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (
                r"(\[\[?)([^\[\]\n#]*)(\]\]?)",
                bygroups(Punctuation, Name.Namespace, Punctuation),
            ),
            (_TOML_BARE_KEY, Name.Attribute),
            (_TOML_QUOTED_KEY, Name.Attribute),
            (r"\.", Punctuation),
            (r"=", Operator, "value"),
        ],
        # Everything after "=" up to the end of the line. Arrays and
        # multi-line strings have their own states and so can run on.
        "value": [
            (r"[^\S\n]+", Whitespace),
            (r"#.*$", Comment.Single),
            (r"\n", Whitespace, "#pop"),
            include("values"),
        ],
        "values": [
            (r'"""', String, "multiline-basic"),
            (r"'''(?:.|\n)*?'''", String),
            (r'"', String, "basic"),
            (r"'[^'\n]*'", String),
            (
                r"\d{4}-\d{2}-\d{2}"
                r"(?:[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:\d{2})?)?",
                Literal.Date,
            ),
            (r"\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?", Literal.Date),
            (r"0x[0-9a-fA-F](?:_?[0-9a-fA-F])*", Number.Hex),
            (r"0o[0-7](?:_?[0-7])*", Number.Oct),
            (r"0b[01](?:_?[01])*", Number.Bin),
            (
                rf"[+-]?{_TOML_DIGITS}(?:\.{_TOML_DIGITS}(?:[eE][+-]?{_TOML_DIGITS})?"
                rf"|[eE][+-]?{_TOML_DIGITS})|[+-]?(?:inf|nan)\b",
                Number.Float,
            ),
            (rf"[+-]?{_TOML_DIGITS}", Number.Integer),
            (r"(?:true|false)\b", Keyword.Constant),
            (r"\[", Punctuation, "array"),
            (r"\{", Punctuation, "inline-table"),
        ],
        "array": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (r",", Punctuation),
            (r"\]", Punctuation, "#pop"),
            include("values"),
        ],
        "inline-table": [
            (r"\s+", Whitespace),
            (r"#.*$", Comment.Single),
            (r"[,.]", Punctuation),
            (r"=", Operator),
            (r"\}", Punctuation, "#pop"),
            (rf"(?:{_TOML_QUOTED_KEY})(?=\s*[=.])", Name.Attribute),
            # Values before bare keys: a bare key is allowed to look like
            # "1" and would otherwise claim the integer part of every float.
            include("values"),
            (_TOML_BARE_KEY, Name.Attribute),
            (_TOML_QUOTED_KEY, Name.Attribute),
        ],
        # No rule for a newline here: an unterminated string then falls out
        # to root via the lexer's recovery instead of back into "value".
        "basic": [
            (r'"', String, "#pop"),
            (_TOML_ESCAPE, String.Escape),
            (r'[^"\\\n]+', String),
        ],
        "multiline-basic": [
            (r'"""', String, "#pop"),
            (_TOML_ESCAPE, String.Escape),
            # a trailing backslash swallows the newline and following indent
            (r"\\[^\S\n]*\n\s*", String.Escape),
            (r'[^"\\]+', String),
            (r'"', String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        tables = re.search(r"^\[\[?[\w.\"-]+\]\]?\s*$", code, re.M)
        pairs = re.findall(r"^[\w.-]+ = \S", code, re.M)
        # TOML has no bare-word values; "key = some text" is an ini file
        if re.search(
            r"^[\w.-]+ = (?![\"'\[{\d+-]|(?:true|false|inf|nan)\b)", code, re.M
        ):
            return 0.0
        # Without a table header it's indistinguishable from assignments in
        # half a dozen programming languages.
        if not (tables and pairs):
            return 0.0
        typed = re.search(r"^[\w.-]+ = [\"'\[{]", code, re.M)
        return 0.7 if typed else 0.5


# Keys may contain spaces ("log file = x") but don't end in one. Spelled
# out like this rather than with a lazy quantifier, which goes quadratic
# on a key followed by a long run of blanks.
_INI_KEY = r"[^=:\s\[;#](?:[^=:\n]*[^=:\s])?"
# A value that is nothing but a number or a switch word.
_INI_WHOLE = r"(?=[^\S\n]*\Z)"


@register
class IniLexer(RegexLexer):
    name = "ini"
    aliases = ("cfg", "dosini", "properties", "editorconfig", "systemd")
    # .conf is deliberately missing: half of those are nginx or apache
    extensions = (".ini", ".cfg", ".properties", ".desktop", ".service")
    filenames = (".editorconfig", ".gitconfig", ".npmrc", ".flake8", ".pylintrc")

    tokens = {
        "root": [
            (r"\n", Whitespace),
            (r"^[^\S\n]*[;#].*$", Comment.Single),
            (
                r"^([^\S\n]*)(\[)([^\]\n]*)(\])",
                bygroups(Whitespace, Punctuation, Name.Namespace, Punctuation),
            ),
            # The value runs on over any following lines indented deeper
            # than the key (configparser's rule), so those lines aren't
            # mistaken for keys of their own.
            (
                rf"^([^\S\n]*)({_INI_KEY})([^\S\n]*)([=:])"
                r"(.*(?:\n\1[^\S\n]+\S.*)*)",
                bygroups(
                    Whitespace,
                    Name.Attribute,
                    Whitespace,
                    Operator,
                    using(this, state="value"),
                ),
            ),
            # a bare flag, as in my.cnf's "skip-networking"
            (
                rf"^([^\S\n]*)({_INI_KEY})([^\S\n]*)$",
                bygroups(Whitespace, Name.Attribute, Whitespace),
            ),
            (r"[^\S\n]+", Whitespace),
        ],
        "value": [
            (
                rf"\A([^\S\n]*)((?i:true|false|yes|no|on|off|none|null)){_INI_WHOLE}",
                bygroups(Whitespace, Keyword.Constant),
            ),
            (
                rf"\A([^\S\n]*)([-+]?\d+\.\d+){_INI_WHOLE}",
                bygroups(Whitespace, Number.Float),
            ),
            (
                rf"\A([^\S\n]*)([-+]?\d+){_INI_WHOLE}",
                bygroups(Whitespace, Number.Integer),
            ),
            (r"\s+", Whitespace),
            # Only with a space on both sides: "#fff" and "a;b" are values.
            (r"(?<=\s)[;#]\s.*$", Comment.Single),
            (r"%\([\w.-]+\)[sd]|\$\{[^}\n]+\}", String.Interpol),
            (r"[^\s%$;#]+", String),
            (r"[%$;#]", String),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        sections = re.search(r"^\[[^\]\n]+\]\s*$", code, re.M)
        pairs = re.findall(r"^\s*[\w.-]+\s*=", code, re.M)
        return 0.4 if sections and pairs else 0.0
