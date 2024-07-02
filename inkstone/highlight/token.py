from __future__ import annotations

from typing import Iterator


class TokenType(tuple):
    """One node of the token tree, e.g. ``Token.Name.Function``.

    Children spring into existence on attribute access, so a lexer can use
    ``Name.Function.Magic`` without declaring it anywhere. Every node is a
    singleton: compare with ``is``, or use ``in`` for ancestry
    (``Keyword.Type in Keyword`` is true).
    """

    parent: TokenType | None = None

    def __init__(self, *args):
        self.subtypes: set[TokenType] = set()

    def __getattr__(self, name: str) -> TokenType:
        if not name[:1].isupper():
            raise AttributeError(name)
        child = TokenType(self + (name,))
        child.parent = self
        setattr(self, name, child)
        self.subtypes.add(child)
        return child

    def __contains__(self, other: object) -> bool:
        return self is other or (
            type(other) is TokenType and other[: len(self)] == self
        )

    def __repr__(self) -> str:
        return "Token" + "".join("." + part for part in self)

    def ancestors(self) -> Iterator[TokenType]:
        """This type, then its parent, and so on up to ``Token``."""
        node: TokenType | None = self
        while node is not None:
            yield node
            node = node.parent

    # Nodes are singletons; copying or unpickling must hand back the same
    # object or identity checks in lexers and styles silently stop working.
    def __copy__(self) -> TokenType:
        return self

    def __deepcopy__(self, memo) -> TokenType:
        return self

    def __reduce__(self):
        return (_from_parts, (tuple(self),))


def _from_parts(parts: tuple[str, ...]) -> TokenType:
    node = Token
    for part in parts:
        node = getattr(node, part)
    return node


Token = TokenType()

Text = Token.Text
Whitespace = Text.Whitespace
Error = Token.Error
Other = Token.Other

Keyword = Token.Keyword
Name = Token.Name
Literal = Token.Literal
String = Literal.String
Number = Literal.Number
Operator = Token.Operator
Punctuation = Token.Punctuation
Comment = Token.Comment
Generic = Token.Generic

# Shortcuts, so Token.String.Escape and Token.Literal.String.Escape are the
# same object.
Token.String = String
Token.Number = Number


def parse_token(name: str) -> TokenType:
    """Turn ``"Name.Function"`` (or ``"Token.Name.Function"``) into the type."""
    parts = [part for part in name.split(".") if part]
    if parts and parts[0] == "Token":
        parts = parts[1:]
    for part in parts:
        if not part[0].isupper() or not part.isidentifier():
            raise ValueError(f"not a token type: {name!r}")
    return _from_parts(tuple(parts))


# The class names are the ones Pygments uses, on purpose: it means any
# Pygments-compatible stylesheet lying around works with our markup too.
# Text and Whitespace get no class at all, see HtmlFormatter.
_CSS_CLASSES: dict[TokenType, str] = {
    Token: "",
    Text: "",
    Whitespace: "",
    Error: "err",
    Other: "x",
    Keyword: "k",
    Keyword.Constant: "kc",
    Keyword.Declaration: "kd",
    Keyword.Namespace: "kn",
    Keyword.Pseudo: "kp",
    Keyword.Reserved: "kr",
    Keyword.Type: "kt",
    Name: "n",
    Name.Attribute: "na",
    Name.Builtin: "nb",
    Name.Builtin.Pseudo: "bp",
    Name.Class: "nc",
    Name.Constant: "no",
    Name.Decorator: "nd",
    Name.Entity: "ni",
    Name.Exception: "ne",
    Name.Function: "nf",
    Name.Function.Magic: "fm",
    Name.Property: "py",
    Name.Label: "nl",
    Name.Namespace: "nn",
    Name.Other: "nx",
    Name.Tag: "nt",
    Name.Variable: "nv",
    Name.Variable.Magic: "vm",
    Literal: "l",
    Literal.Date: "ld",
    String: "s",
    String.Affix: "sa",
    String.Backtick: "sb",
    String.Char: "sc",
    String.Delimiter: "dl",
    String.Doc: "sd",
    String.Double: "s2",
    String.Escape: "se",
    String.Heredoc: "sh",
    String.Interpol: "si",
    String.Other: "sx",
    String.Regex: "sr",
    String.Single: "s1",
    String.Symbol: "ss",
    Number: "m",
    Number.Bin: "mb",
    Number.Float: "mf",
    Number.Hex: "mh",
    Number.Integer: "mi",
    Number.Oct: "mo",
    Operator: "o",
    Operator.Word: "ow",
    Punctuation: "p",
    Comment: "c",
    Comment.Doc: "cd",
    Comment.Hashbang: "ch",
    Comment.Multiline: "cm",
    Comment.Preproc: "cp",
    Comment.PreprocFile: "cpf",
    Comment.Single: "c1",
    Comment.Special: "cs",
    Generic: "g",
    Generic.Deleted: "gd",
    Generic.Emph: "ge",
    Generic.Error: "gr",
    Generic.Heading: "gh",
    Generic.Inserted: "gi",
    Generic.Output: "go",
    Generic.Prompt: "gp",
    Generic.Strong: "gs",
    Generic.Subheading: "gu",
    Generic.Traceback: "gt",
}


def css_class(ttype: TokenType) -> str:
    """Short class name for a token type, falling back to its nearest ancestor."""
    try:
        return _CSS_CLASSES[ttype]
    except KeyError:
        pass
    for node in ttype.ancestors():
        if node in _CSS_CLASSES:
            # remember it so odd one-off subtypes only walk the tree once
            _CSS_CLASSES[ttype] = _CSS_CLASSES[node]
            return _CSS_CLASSES[node]
    return ""


def styled_types() -> list[TokenType]:
    """Token types that have a class of their own, in a stable order."""
    seen: set[str] = set()
    result = []
    for ttype, name in _CSS_CLASSES.items():
        if name and name not in seen:
            seen.add(name)
            result.append(ttype)
    return result
