from __future__ import annotations

import re
from typing import Iterable, Iterator

from .errors import HighlightError
from .styles import DEFAULT_STYLE, Style, get_style
from .token import Text, Token, TokenType, css_class, styled_types

_ESCAPES = str.maketrans(
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}
)
_LINE_RANGE = re.compile(r"(\d+)(?:-(\d+))?\Z")


def escape_html(text: str) -> str:
    return text.translate(_ESCAPES)


def _lineno_mode(value: bool | str | None) -> str | None:
    if value is True:
        return "table"
    if value is False or value is None:
        return None
    if value in ("table", "inline"):
        return value
    raise HighlightError(
        f"linenos must be True, False, 'table' or 'inline', not {value!r}"
    )


def parse_line_numbers(spec: str | Iterable[int] | None) -> frozenset[int]:
    """Turn ``"1,3-5 8"`` (or any iterable of ints) into a set of line numbers."""
    if not spec:
        return frozenset()
    if not isinstance(spec, str):
        try:
            return frozenset(int(n) for n in spec)
        except (TypeError, ValueError):
            raise HighlightError(f"bad line numbers: {spec!r}") from None
    lines: set[int] = set()
    # "3 - 5" is one range, not three items
    spec = re.sub(r"\s*-\s*", "-", spec)
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        match = _LINE_RANGE.match(part)
        if match is None:
            raise HighlightError(f"bad line range {part!r} in {spec!r}")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        lines.update(range(first, last + 1))
    return frozenset(lines)


class HtmlFormatter:
    """Turns a token stream into HTML.

    ``linenos`` is False, ``"table"`` (also what True means; the numbers sit
    in their own table cell, so selecting the code doesn't pick them up) or
    ``"inline"``. ``hl_lines`` counts from 1 at the top of the block whatever
    ``line_start`` says. With ``nowrap`` only the highlighted lines come
    back, without the div/pre/code around them, for callers that bring their
    own wrapper; the filename caption and the table layout need the wrapper
    and are dropped. ``inline_styles`` writes ``style=""`` attributes instead
    of classes, for feeds and e-mail where our stylesheet isn't around.
    """

    def __init__(
        self,
        *,
        style: str | Style = DEFAULT_STYLE,
        linenos: bool | str = False,
        hl_lines: str | Iterable[int] = (),
        css_class: str = "highlight",
        filename: str | None = None,
        line_start: int = 1,
        nowrap: bool = False,
        inline_styles: bool = False,
        class_prefix: str = "",
        line_anchors: str | None = None,
    ):
        self.style = get_style(style)
        self.linenos = _lineno_mode(linenos)
        self.hl_lines = parse_line_numbers(hl_lines)
        self.css_class = css_class
        self.filename = filename
        self.line_start = int(line_start)
        self.nowrap = nowrap
        self.inline_styles = inline_styles
        self.class_prefix = class_prefix
        # id prefix: with "L" every line gets id="L-<number>" to link to
        self.line_anchors = line_anchors
        self._attrs: dict[TokenType, str] = {}

    def format(self, tokens: Iterable[tuple[TokenType, str]]) -> str:
        lines = [self._render_line(line) for line in self._split_lines(tokens)]
        numbers = range(self.line_start, self.line_start + len(lines))
        width = len(str(numbers[-1])) if lines else 1

        body = []
        for index, (number, line) in enumerate(zip(numbers, lines), 1):
            if self.linenos == "inline":
                line = self._lineno_span(number, width) + line
            if self.line_anchors:
                anchor = escape_html(f"{self.line_anchors}-{number}")
                line = f'<span id="{anchor}">{line}</span>'
            if index in self.hl_lines:
                # the newline goes inside so the span can be display:block
                # without doubling the line spacing
                body.append(f"<span{self._hl_attr()}>{line}\n</span>")
            else:
                body.append(line + "\n")
        code = "".join(body)
        if self.nowrap:
            return code
        return self._wrap(code, numbers, width)

    def _wrap(self, code: str, numbers: range, width: int) -> str:
        pre = "<pre>"
        if self.inline_styles:
            style = self.style
            pre = (
                f'<pre style="background-color: {style.background}; '
                f'color: {style.foreground}">'
            )
        block = f"{pre}<code>{code}</code></pre>"
        if self.linenos == "table":
            gutter = "\n".join(str(n).rjust(width) for n in numbers)
            lineno_attr = self._lineno_attr()
            block = (
                f'<table class="{self.class_prefix}linenotable"><tr>'
                f'<td class="{self.class_prefix}linenos">'
                f"<pre{lineno_attr}>{gutter}</pre></td>"
                f'<td class="{self.class_prefix}code">{block}</td></tr></table>'
            )
        caption = ""
        if self.filename:
            caption = (
                f'<div class="{self.class_prefix}filename">'
                f"{escape_html(self.filename)}</div>"
            )
        return f'<div class="{escape_html(self.css_class)}">{caption}{block}</div>'

    def _split_lines(
        self, tokens: Iterable[tuple[TokenType, str]]
    ) -> Iterator[list[tuple[str, str]]]:
        """Regroup the stream into lines of (span attributes, text).

        Tokens are cut at newlines so no span ever straddles two lines, and
        neighbours that would get identical markup are merged.
        """
        line: list[tuple[str, str]] = []
        for ttype, value in tokens:
            attr = self._attr(ttype)
            for index, part in enumerate(value.split("\n")):
                if index:
                    yield line
                    line = []
                if not part:
                    continue
                if line and line[-1][0] == attr:
                    line[-1] = (attr, line[-1][1] + part)
                else:
                    line.append((attr, part))
        if line:
            yield line

    def _render_line(self, parts: list[tuple[str, str]]) -> str:
        out = []
        for attr, text in parts:
            # browsers treat a stray CR in <pre> as another line break
            text = escape_html(text.replace("\r", ""))
            out.append(f"<span{attr}>{text}</span>" if attr else text)
        return "".join(out)

    def _attr(self, ttype: TokenType) -> str:
        try:
            return self._attrs[ttype]
        except KeyError:
            pass
        # Plain text and whitespace go out bare. Wrapping every run of
        # spaces in a span doubles the size of the page for nothing.
        if ttype in Text or ttype is Token:
            attr = ""
        elif self.inline_styles:
            css = self.style.style_for(ttype).css()
            attr = f' style="{css}"' if css else ""
        else:
            name = css_class(ttype)
            attr = f' class="{self.class_prefix}{name}"' if name else ""
        self._attrs[ttype] = attr
        return attr

    def _hl_attr(self) -> str:
        if self.inline_styles:
            return f' style="display: block; background-color: {self.style.highlight}"'
        return f' class="{self.class_prefix}hll"'

    def _lineno_attr(self) -> str:
        if self.inline_styles:
            return f' style="color: {self.style.line_numbers}; user-select: none"'
        return ""

    def _lineno_span(self, number: int, width: int) -> str:
        attr = self._lineno_attr() or f' class="{self.class_prefix}lineno"'
        return f"<span{attr}>{str(number).rjust(width)} </span>"

    def get_css(self, selector: str = ".highlight", *, media: str | None = None) -> str:
        """The stylesheet for this formatter's style.

        ``selector`` scopes every rule and may be a comma-separated list.
        ``media`` wraps the lot in a media query, which is how a site ships
        a second style for ``(prefers-color-scheme: dark)``.
        """
        style = self.style
        prefix = self.class_prefix
        scopes = [s.strip() for s in selector.split(",") if s.strip()] or [""]

        def scoped(*suffixes: str) -> str:
            return ", ".join(
                f"{scope} {suffix}".strip() for scope in scopes for suffix in suffixes
            )

        rules = []
        if scopes != [""]:
            # without a wrapper to hang it on there is no block rule to write
            rules.append(
                f"{scoped('')} {{ background-color: {style.background}; "
                f"color: {style.foreground} }}"
            )
        rules += [
            f"{scoped('pre')} {{ margin: 0; background-color: transparent; "
            "color: inherit }",
            f"{scoped('.' + prefix + 'hll')} {{ display: block; "
            f"background-color: {style.highlight} }}",
            f"{scoped('.' + prefix + 'lineno', '.' + prefix + 'linenos pre')} "
            f"{{ color: {style.line_numbers}; user-select: none }}",
            f"{scoped('.' + prefix + 'linenotable')} "
            "{ border-spacing: 0; width: 100% }",
            f"{scoped('.' + prefix + 'linenos')} "
            "{ padding: 0 0.8em 0 0; text-align: right; vertical-align: top; "
            "width: 1% }",
            f"{scoped('.' + prefix + 'code')} {{ padding: 0; vertical-align: top }}",
            f"{scoped('.' + prefix + 'filename')} "
            f"{{ color: {style.line_numbers}; font-size: 0.85em; padding: 0.3em 0 }}",
        ]
        for ttype in styled_types():
            css = style.style_for(ttype).css()
            if css:
                selector_text = scoped("." + prefix + css_class(ttype))
                rules.append(f"{selector_text} {{ {css} }} /* {_short_name(ttype)} */")
        if media:
            body = "\n".join("  " + rule for rule in rules)
            return f"@media {media} {{\n{body}\n}}\n"
        return "\n".join(rules) + "\n"


def _short_name(ttype: TokenType) -> str:
    return ".".join(ttype) or "Token"
