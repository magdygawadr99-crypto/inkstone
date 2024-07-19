from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, include, this, using, words
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

_KEYWORDS = """
    case coproc do done elif else esac fi for function if in select then time
    until while
""".split()

_BUILTINS = """
    alias bg bind break builtin cd command compgen complete continue declare
    dirs disown echo enable eval exec exit export false fc fg getopts hash help
    history jobs kill let local logout mapfile popd printf pushd pwd read
    readarray readonly return set shift shopt source suspend test times trap
    true type typeset ulimit umask unalias unset wait
""".split()

# A word is "whole" when it isn't glued to more of a path or an option:
# the "for" in --for, do.sh or in/out is not a keyword.
_WORD_START = r"(?<![\w./=-])"
_WORD_END = r"(?![\w./=-])"

# Builtins are only coloured where a command can start, so that the "test"
# in "git checkout test" stays plain. Lookbehinds have to be fixed-width,
# hence the list of alternatives.
_COMMAND_START = (
    r"(?:(?<=[;|&(`{])|(?<=[;|&(`{]\s)|(?<=\bthen\s)|(?<=\bdo\s)|(?<=\belse\s)"
    r"|(?<=\bsudo\s)|(?<=\bexec\s)|(?<=\bif\s)|(?<=\bwhile\s)|(?<=!\s))"
)


@register
class BashLexer(RegexLexer):
    name = "bash"
    aliases = ("sh", "shell", "zsh", "ksh")
    extensions = (".sh", ".bash", ".zsh", ".ksh")
    filenames = (".bashrc", ".bash_profile", ".zshrc", ".profile", "PKGBUILD")
    shebangs = (r"(?:ba|da|a|k|z)?sh",)

    tokens = {
        "root": [
            (r"\A#!.*$", Comment.Hashbang),
            # Heredoc: the operator and delimiter, whatever else is on that
            # line, the body, and the closing delimiter.
            (
                r"(<<-?)([ \t]*)((['\"]?)([A-Za-z_]\w*)\4)(.*\n)"
                r"((?:.*\n)*?)([ \t]*\5)(?=\n|\Z)",
                bygroups(
                    Operator,
                    Whitespace,
                    String.Delimiter,
                    None,
                    None,
                    using(this),
                    String.Heredoc,
                    String.Delimiter,
                ),
            ),
            (
                r"^([ \t]*)(function)([ \t]+)([\w:.-]+)",
                bygroups(Whitespace, Keyword, Whitespace, Name.Function),
            ),
            (
                r"^([ \t]*)([\w:.-]+)([ \t]*)(\(\))",
                bygroups(Whitespace, Name.Function, Whitespace, Punctuation),
            ),
            (
                rf"^([ \t]*){words(_BUILTINS, prefix='(', suffix=')')}{_WORD_END}",
                bygroups(Whitespace, Name.Builtin),
            ),
            (r"[ \t]+", Whitespace),
            (r"\n", Whitespace),
            (r"(?:^|(?<=[\s;(]))#.*$", Comment.Single),
            (rf"{_COMMAND_START}{words(_BUILTINS)}{_WORD_END}", Name.Builtin),
            (words(_KEYWORDS, prefix=_WORD_START, suffix=_WORD_END), Keyword),
            (
                rf"{_WORD_START}([a-zA-Z_]\w*)(\[[^\]\n]*\])?(\+?=)",
                bygroups(Name.Variable, using(this), Operator),
            ),
            (r"\\[\w\W]", String.Escape),
            (r"\[\[(?=\s)|(?<=\s)\]\]|\[(?=\s)|(?<=\s)\]", Keyword),
            (r"\(\(", Keyword, "math"),
            (r"\(", Punctuation, "group"),
            (r"&&|\|\||;;&?|;&|\|&?|&>>?|[<>]&\d*-?|<<<|>>|<>|>\||[<>&;]", Operator),
            (r"[{})=!]", Punctuation),
            include("data"),
            include("interpolation"),
            (r"\$", Text),
        ],
        "interpolation": [
            (r"\$\(\(", Keyword, "math"),
            (r"\$\(", Keyword, "substitution"),
            (r"\$\{[#!]?", String.Interpol, "parameter"),
            (r"\$(?:[a-zA-Z_]\w*|\d+|[#$?!_*@-])", Name.Variable),
            (r"`", String.Backtick, "backticks"),
        ],
        "data": [
            (r'\$?"', String.Double, "double"),
            (r"\$'(?:\\[\w\W]|[^'\\])*'", String.Single),
            (r"'[^']*'", String.Single),
            (rf"(?<![\w./-])\d+{_WORD_END}", Number),
            (r"[^\s=$`'\"\\|&;(){}<>#\[\]!]+", Text),
            (r"[#\[\]]", Text),
        ],
        "double": [
            (r'"', String.Double, "#pop"),
            (r'\\[\\"$`\n]', String.Escape),
            include("interpolation"),
            (r'[^"\\$`]+', String.Double),
            (r"[\\$]", String.Double),
        ],
        # ${name:-default}, ${#array[@]}, ${path##*/}
        "parameter": [
            (r"\}", String.Interpol, "#pop"),
            (r"[a-zA-Z_]\w*|\d+|[@*?$-]", Name.Variable, "parameter-rest"),
            include("root"),
        ],
        "parameter-rest": [
            (r"\}", String.Interpol, "#pop:2"),
            (r"[@\[\]*]", Operator),
            (r":?[-=+?]|##?|%%?|//?|\^\^?|,,?|:", Operator, "parameter-word"),
            include("root"),
        ],
        # after the operator comes a default or a pattern: ordinary words,
        # in which / and - mean nothing special
        "parameter-word": [
            (r"\}", String.Interpol, "#pop:3"),
            include("root"),
        ],
        # FIXME: the unbalanced ")" of a case pattern inside $(...) or a
        # subshell closes it early. The rest still lexes, just one level off.
        "substitution": [
            (r"\)", Keyword, "#pop"),
            include("root"),
        ],
        "group": [
            (r"\)", Punctuation, "#pop"),
            include("root"),
        ],
        "backticks": [
            (r"`", String.Backtick, "#pop"),
            include("root"),
        ],
        "math": [
            (r"\)\)", Keyword, "#pop"),
            (r"\s+", Whitespace),
            (r"\d+#[\da-zA-Z@_]+|0[xX][\da-fA-F]+|\d+", Number),
            (r"[a-zA-Z_]\w*", Name.Variable),
            (r"\*\*|\+\+|--|<<=?|>>=?|&&|\|\||[-+*/%&|^<>=!]=?|[~?:,]", Operator),
            (r"\(", Punctuation, "math-group"),
            include("interpolation"),
            # "((" can also open two nested subshells; don't litter those
            # with error tokens
            (r"[^\s()]", Text),
        ],
        "math-group": [
            (r"\)", Punctuation, "#pop"),
            include("math"),
        ],
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^\s*(?:fi|done|esac)\s*$", code, re.M):
            score += 0.4
        if re.search(r"^\s*(?:if|while|elif) \[\[? ", code, re.M):
            score += 0.2
        if re.search(r"^(?:sudo |apt(?:-get)? |cd |echo |export \w+=)", code, re.M):
            score += 0.2
        return score
