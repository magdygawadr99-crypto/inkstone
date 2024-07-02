from __future__ import annotations

import re

from ..lexer import RegexLexer, bygroups, default, include, words
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
    as assert async await break continue del elif else except finally for
    global if lambda nonlocal pass raise return try while with yield
""".split()

_BUILTINS = """
    abs aiter all anext any ascii bin bool breakpoint bytearray bytes callable
    chr classmethod compile complex delattr dict dir divmod enumerate eval exec
    filter float format frozenset getattr globals hasattr hash help hex id
    input int isinstance issubclass iter len list locals map max memoryview
    min next object oct open ord pow print property range repr reversed round
    set setattr slice sorted staticmethod str sum super tuple type vars zip
    __import__
""".split()

_EXCEPTIONS = """
    ArithmeticError AssertionError AttributeError BaseException
    BaseExceptionGroup BlockingIOError BrokenPipeError BufferError
    ConnectionError DeprecationWarning EOFError Exception ExceptionGroup
    FileExistsError FileNotFoundError FloatingPointError FutureWarning
    GeneratorExit ImportError IndentationError IndexError InterruptedError
    IsADirectoryError KeyError KeyboardInterrupt LookupError MemoryError
    ModuleNotFoundError NameError NotADirectoryError NotImplementedError
    OSError OverflowError PermissionError RecursionError ReferenceError
    ResourceWarning RuntimeError RuntimeWarning StopAsyncIteration
    StopIteration SyntaxError SystemError SystemExit TabError TimeoutError
    TypeError UnicodeDecodeError UnicodeEncodeError UnicodeError UserWarning
    ValueError Warning ZeroDivisionError
""".split()

_NAME = r"[^\W\d]\w*"
_DOTTED = rf"{_NAME}(?:\.{_NAME})*"
_DIGITS = r"\d(?:_?\d)*"

_ESCAPE = (
    r"\\(?:[\\abfnrtv\"']|\n|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8}"
    r"|N\{[^}\n]+\}|[0-7]{1,3})"
)
# %-style and str.format placeholders: %5.2f, %(name)s, {}, {0!r:>8}.
# The space flag is left out on purpose, "100% sure" is far more common
# than "% d".
_PRINTF = (
    r"%(?:\([^)\n]*\))?[-#0+]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?[diouxXeEfFgGcrsa%]"
)
_FORMAT_FIELD = r"\{(?:\w[\w.\[\]]*)?(?:![rsa])?(?::[^{}\n]*)?\}"

_QUOTES = {"tdq": '"""', "tsq": "'''", "dq": '"', "sq": "'"}

# kind -> (prefix pattern, has escapes, has {} interpolation)
_STRING_KINDS = {
    "rf": (r"(?i:rf|fr|rt|tr)", False, True),
    "f": (r"(?i:f|t)", True, True),
    "r": (r"(?i:rb|br|r)", False, False),
    "s": (r"(?i:u|b)?", True, False),
}


def _string_states() -> tuple[list, dict[str, list]]:
    """Opening rules for root plus one state per quote/prefix combination."""
    openers = []
    states = {}
    for quote_key, quote in _QUOTES.items():
        triple = len(quote) == 3
        char = quote[0]
        for kind, (prefix, escapes, interpolated) in _STRING_KINDS.items():
            state = f"{quote_key}-{kind}"
            openers.append(
                (f"({prefix})({quote})", bygroups(String.Affix, String), state)
            )
            rules: list = [(quote, String, "#pop")]
            if escapes:
                rules.append((_ESCAPE, String.Escape))
            else:
                # a backslash still protects the quote, it just stays literal
                rules.append((r"\\(?:.|\n)", String))
            if interpolated:
                rules += [
                    (r"\{\{|\}\}", String.Escape),
                    (r"\{", String.Interpol, "fexpr"),
                ]
            else:
                rules += [(_PRINTF, String.Interpol), (_FORMAT_FIELD, String.Interpol)]
            if triple:
                rules.append((rf"[^\\%{{}}{char}]+", String))
                rules.append((char, String))
            else:
                rules.append((rf"[^\\%{{}}{char}\n]+", String))
                rules.append((r"\n", Whitespace, "#pop"))
            rules.append((r"[\\%{}]", String))
            states[state] = rules
    return openers, states


_STRING_OPENERS, _STRING_STATES = _string_states()


@register
class PythonLexer(RegexLexer):
    name = "python"
    aliases = ("py", "python3", "py3")
    extensions = (".py", ".pyw", ".pyi")
    filenames = ("SConstruct", "SConscript")
    shebangs = (r"pythonw?(\d+(\.\d+)*)?",)

    tokens = {
        "root": [
            (r"\A#!.*$", Comment.Hashbang),
            (r"\n", Whitespace),
            # a triple-quoted string that starts a line is (close enough to)
            # a docstring
            (
                r'^([^\S\n]*)((?i:r|u)?)("""(?:[^\\]|\\.|\\\n)*?""")',
                bygroups(Whitespace, String.Affix, String.Doc),
            ),
            (
                r"^([^\S\n]*)((?i:r|u)?)('''(?:[^\\]|\\.|\\\n)*?''')",
                bygroups(Whitespace, String.Affix, String.Doc),
            ),
            (
                rf"^([^\S\n]*)(@{_DOTTED})",
                bygroups(Whitespace, Name.Decorator),
            ),
            # match, case and type are only keywords where a statement starts
            (
                r"^([^\S\n]*)(match|case)\b(?![^\S\n]*[=.,)\]:])"
                r"(?=.*:[^\S\n]*(?:#.*)?$)",
                bygroups(Whitespace, Keyword),
            ),
            (
                rf"^([^\S\n]*)(type)([^\S\n]+)(?={_NAME}[^\S\n]*[=\[])",
                bygroups(Whitespace, Keyword.Declaration, Whitespace),
            ),
            (r"[^\S\n]+", Whitespace),
            (r"\\\n", Text),
            (r"#.*$", Comment.Single),
            include("keywords"),
            include("numbers"),
            *_STRING_OPENERS,
            include("names"),
            (r"->|:=|\*\*=?|//=?|<<=?|>>=?|[-+*/%@&|^=!<>]=?|~", Operator),
            (r"\.\.\.", Keyword.Constant),
            (r"[()\[\]{}:,;.]", Punctuation),
        ],
        "keywords": [
            (
                r"(def)([^\S\n]+)(__\w+__)\b",
                bygroups(Keyword.Declaration, Whitespace, Name.Function.Magic),
            ),
            (
                rf"(def)([^\S\n]+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Function),
            ),
            (
                rf"(class)([^\S\n]+)({_NAME})",
                bygroups(Keyword.Declaration, Whitespace, Name.Class),
            ),
            # "from" also turns up in "yield from" and "raise ... from", so
            # only the full "from x import" form counts as an import
            (
                rf"(from)([^\S\n]+)(\.*(?:{_DOTTED})?)([^\S\n]+)(import)\b",
                bygroups(
                    Keyword.Namespace,
                    Whitespace,
                    Name.Namespace,
                    Whitespace,
                    Keyword.Namespace,
                ),
            ),
            (r"import\b", Keyword.Namespace, "import"),
            (
                r"(?:True|False|None|NotImplemented|Ellipsis|__debug__)\b",
                Keyword.Constant,
            ),
            (r"(?:and|or|not|in|is)\b", Operator.Word),
            (r"(?:def|class)\b", Keyword.Declaration),
            (words(_KEYWORDS + ["from"], suffix=r"\b"), Keyword),
        ],
        "import": [
            (r"[^\S\n]+", Whitespace),
            (r"\\\n", Text),
            (
                rf"(as)([^\S\n]+)({_NAME})",
                bygroups(Keyword.Namespace, Whitespace, Name),
            ),
            (r",", Punctuation),
            (_DOTTED, Name.Namespace),
            default("#pop"),
        ],
        "numbers": [
            (r"0[bB](?:_?[01])+", Number.Bin),
            (r"0[oO](?:_?[0-7])+", Number.Oct),
            (r"0[xX](?:_?[0-9a-fA-F])+", Number.Hex),
            (
                rf"(?:{_DIGITS})?\.{_DIGITS}(?:[eE][+-]?{_DIGITS})?[jJ]?"
                rf"|{_DIGITS}\.(?:[eE][+-]?{_DIGITS})?[jJ]?(?![\w.])"
                rf"|{_DIGITS}[eE][+-]?{_DIGITS}[jJ]?",
                Number.Float,
            ),
            (rf"{_DIGITS}[jJ]", Number.Float),
            (_DIGITS, Number.Integer),
        ],
        "names": [
            (r"(?:self|cls)\b", Name.Builtin.Pseudo),
            (
                r"__(?:name|file|doc|all|dict|class|module|slots|path|package"
                r"|spec|annotations|qualname)__\b",
                Name.Variable.Magic,
            ),
            (words(_EXCEPTIONS, prefix=r"(?<!\.)", suffix=r"\b"), Name.Exception),
            (words(_BUILTINS, prefix=r"(?<!\.)", suffix=r"\b"), Name.Builtin),
            (r"[A-Z][A-Z0-9_]+\b", Name.Constant),
            (_NAME, Name),
        ],
        # the expression part of an f-string field, up to its closing brace
        "fexpr": [
            (r"\}", String.Interpol, "#pop"),
            (r"![rsa](?=[:}])", String.Interpol),
            (r"=(?=[!:}])", String.Interpol),
            (r":(?!=)", String.Interpol, "fspec"),
            (r"[(\[{]", Punctuation, "fnested"),
            include("root"),
        ],
        "fnested": [
            (r"[)\]}]", Punctuation, "#pop"),
            (r"[(\[{]", Punctuation, "#push"),
            include("root"),
        ],
        "fspec": [
            (r"\{", String.Interpol, "fexpr"),
            (r"\}", String.Interpol, "#pop:2"),
            (r"[^{}\n]+", String),
            default("#pop:2"),
        ],
        **_STRING_STATES,
    }

    @staticmethod
    def analyse(code: str) -> float:
        score = 0.0
        if re.search(r"^\s*(?:def|class)\s+\w+.*:\s*(?:#.*)?$", code, re.M):
            score += 0.4
        if re.search(r"^(?:import \w+|from [\w.]+ import )", code, re.M):
            score += 0.3
        if re.search(r"^\s*(?:elif\b.*:|if __name__ ==|print\()", code, re.M):
            score += 0.2
        return min(score, 0.9)
