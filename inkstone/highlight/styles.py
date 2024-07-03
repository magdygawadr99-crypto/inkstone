from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .errors import HighlightError
from .token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    TokenType,
)

DEFAULT_STYLE = "paper"

_HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")
_FLAGS = ("bold", "italic", "underline")


@dataclass(frozen=True)
class TokenStyle:
    color: str | None = None
    background: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False

    def __bool__(self) -> bool:
        return bool(
            self.color or self.background or self.bold or self.italic or self.underline
        )

    def css(self) -> str:
        """The declarations for this style, without braces."""
        parts = []
        if self.color:
            parts.append(f"color: {self.color}")
        if self.background:
            parts.append(f"background-color: {self.background}")
        if self.bold:
            parts.append("font-weight: bold")
        if self.italic:
            parts.append("font-style: italic")
        if self.underline:
            parts.append("text-decoration: underline")
        return "; ".join(parts)


def _colour(value: str, where: str) -> str:
    if not _HEX_COLOUR.match(value):
        raise HighlightError(f"{where}: {value!r} is not a hex colour")
    value = value.lower()
    if len(value) == 4:
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value


def _parse_rule(spec: str, inherited: TokenStyle, where: str) -> TokenStyle:
    changes: dict[str, object] = {}
    for word in spec.split():
        if word == "noinherit":
            inherited = TokenStyle()
        elif word in _FLAGS:
            changes[word] = True
        elif word[:2] == "no" and word[2:] in _FLAGS:
            changes[word[2:]] = False
        elif word.startswith("bg:"):
            changes["background"] = _colour(word[3:], where)
        else:
            changes["color"] = _colour(word, where)
    return replace(inherited, **changes)


def _luminance(colour: str) -> float:
    channels = []
    for i in (1, 3, 5):
        c = int(colour[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colours, from 1 to 21."""
    a = _luminance(_colour(first, "contrast_ratio"))
    b = _luminance(_colour(second, "contrast_ratio"))
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


class Style:
    """A named colour scheme: page colours plus a rule per token type.

    A rule is a short spec such as ``"bold #7a3e9d"``, ``"italic"``,
    ``"bg:#ffeef0"`` or ``"nobold"``. A token type without a rule uses its
    parent's; one with a rule still inherits whatever the rule leaves out,
    unless it says ``noinherit``.
    """

    def __init__(
        self,
        name: str,
        *,
        background: str,
        foreground: str,
        highlight: str,
        line_numbers: str,
        rules: dict[TokenType, str],
    ):
        self.name = name
        self.background = _colour(background, name)
        self.foreground = _colour(foreground, name)
        # background of lines picked out with hl_lines
        self.highlight = _colour(highlight, name)
        self.line_numbers = _colour(line_numbers, name)
        self._rules = dict(rules)
        self._resolved: dict[TokenType, TokenStyle] = {}
        # resolve everything now so a typo in a rule fails loudly at
        # definition time rather than on some unlucky token later
        for ttype in self._rules:
            self.style_for(ttype)

    def __repr__(self) -> str:
        return f"<Style {self.name!r}>"

    @property
    def dark(self) -> bool:
        return _luminance(self.background) < 0.2

    def style_for(self, ttype: TokenType) -> TokenStyle:
        try:
            return self._resolved[ttype]
        except KeyError:
            pass
        if ttype.parent is None:
            inherited = TokenStyle()
        else:
            inherited = self.style_for(ttype.parent)
        spec = self._rules.get(ttype)
        if spec is None:
            resolved = inherited
        else:
            resolved = _parse_rule(spec, inherited, f"style {self.name!r}, {ttype!r}")
        self._resolved[ttype] = resolved
        return resolved


_styles: dict[str, Style] = {}


def register_style(style: Style) -> Style:
    _styles[style.name.lower()] = style
    return style


def get_style(name: str | Style) -> Style:
    if isinstance(name, Style):
        return name
    try:
        return _styles[name.strip().lower()]
    except (KeyError, AttributeError):
        known = ", ".join(list_styles())
        raise HighlightError(f"no style called {name!r} (have: {known})") from None


def list_styles() -> list[str]:
    return sorted(_styles)


# Light, slightly warm white. The default.
register_style(
    Style(
        "paper",
        background="#fbfaf7",
        foreground="#2a2a2e",
        highlight="#fdf0b4",
        line_numbers="#8a8a93",
        rules={
            Comment: "italic #6f6f7a",
            Comment.Preproc: "noitalic #8a5a00",
            Comment.Doc: "#56705e",
            Comment.Special: "bold",
            Keyword: "bold #7a3e9d",
            Keyword.Constant: "nobold #a35200",
            Keyword.Type: "nobold #1b6a85",
            Operator: "#5c5c66",
            Operator.Word: "bold #7a3e9d",
            Punctuation: "#5c5c66",
            Name.Function: "#1d5fbf",
            Name.Class: "bold #1d5fbf",
            Name.Namespace: "#1b6a85",
            Name.Builtin: "#0b7567",
            Name.Builtin.Pseudo: "italic",
            Name.Exception: "#b02a37",
            Name.Decorator: "#8a5a00",
            Name.Tag: "#b02a37",
            Name.Attribute: "#8a5a00",
            Name.Property: "#1b6a85",
            Name.Variable: "#6f42c1",
            Name.Constant: "#a35200",
            Name.Label: "#8a5a00",
            Name.Entity: "#a35200",
            String: "#2c7530",
            String.Doc: "italic",
            String.Escape: "bold #a35200",
            String.Interpol: "#a35200",
            String.Regex: "#a8326e",
            String.Affix: "#7a3e9d",
            String.Delimiter: "bold",
            Number: "#a35200",
            Literal.Date: "#a35200",
            Generic.Heading: "bold #1d5fbf",
            Generic.Subheading: "bold #7a3e9d",
            Generic.Inserted: "#1a6e30 bg:#e2f8e6",
            Generic.Deleted: "#b3261e bg:#ffebe9",
            Generic.Emph: "italic",
            Generic.Strong: "bold",
            Generic.Error: "#b3261e",
            Generic.Prompt: "bold #6f6f7a",
            Generic.Output: "#5c5c66",
            Error: "#b3261e bg:#ffe3e3",
        },
    )
)

# Dark blue-grey with pastel accents.
register_style(
    Style(
        "dusk",
        background="#1e1f2b",
        foreground="#d7d9e4",
        highlight="#34364d",
        line_numbers="#7a7fa3",
        rules={
            Comment: "italic #6b7089",
            Comment.Preproc: "noitalic #e0a458",
            Comment.Doc: "#8fb0a8",
            Comment.Special: "bold",
            Keyword: "#c79bf2",
            Keyword.Constant: "#f2a65a",
            Keyword.Type: "#7fd1e0",
            Operator: "#a9b0d0",
            Operator.Word: "#c79bf2",
            Punctuation: "#a9b0d0",
            Name.Function: "#82aaff",
            Name.Class: "bold #82aaff",
            Name.Namespace: "#7fd1e0",
            Name.Builtin: "#5fd3bc",
            Name.Builtin.Pseudo: "italic",
            Name.Exception: "#ff8a80",
            Name.Decorator: "#e6c07b",
            Name.Tag: "#ff8a80",
            Name.Attribute: "#e6c07b",
            Name.Property: "#7fd1e0",
            Name.Variable: "#d4bfff",
            Name.Constant: "#f2a65a",
            Name.Label: "#e6c07b",
            Name.Entity: "#f2a65a",
            String: "#a5d68c",
            String.Doc: "italic",
            String.Escape: "bold #f2a65a",
            String.Interpol: "#f2a65a",
            String.Regex: "#f78fb3",
            String.Affix: "#c79bf2",
            String.Delimiter: "bold",
            Number: "#f2a65a",
            Literal.Date: "#f2a65a",
            Generic.Heading: "bold #82aaff",
            Generic.Subheading: "bold #c79bf2",
            Generic.Inserted: "#a5d68c bg:#1f3326",
            Generic.Deleted: "#ff8a80 bg:#3a2026",
            Generic.Emph: "italic",
            Generic.Strong: "bold",
            Generic.Error: "#ff8a80",
            Generic.Prompt: "bold #8a90b3",
            Generic.Output: "#a9b0d0",
            Error: "#ff8a80 bg:#3a2026",
        },
    )
)
