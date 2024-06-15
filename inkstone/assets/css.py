from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, NamedTuple, Optional

from . import _colors
from .errors import AssetError, line_at


class Token(NamedTuple):
    # type is one of: ws comment string url bad-url function ident at hash
    # number percentage dimension delim cdo cdc, or the character itself
    # for { } ( ) [ ] : ; ,
    type: str
    value: str
    pos: int

    @property
    def end(self) -> int:
        return self.pos + len(self.value)


_WS = " \t\n\r\f"
_ESCAPE = r"\\(?:[0-9a-fA-F]{1,6}[ \t\n\r\f]?|[^\n\r\f0-9a-fA-F])"
_NAME_START = r"(?:[a-zA-Z_\u0080-\U0010ffff]|" + _ESCAPE + ")"
_NAME_CHAR = r"(?:[a-zA-Z0-9_\-\u0080-\U0010ffff]|" + _ESCAPE + ")"

_WS_RE = re.compile(r"[ \t\n\r\f]+")
_IDENT_RE = re.compile("(?:--|-?" + _NAME_START + ")" + _NAME_CHAR + "*")
_NAME_RE = re.compile(_NAME_CHAR + "+")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")
_URL_BODY_RE = re.compile(
    r"[ \t\n\r\f]*(?:[^\"'()\\\s\x00-\x08\x0b\x0e-\x1f\x7f]|" + _ESCAPE + r")*"
    r"[ \t\n\r\f]*\)"
)
_ESCAPE_RE = re.compile(
    r"\\(?:([0-9a-fA-F]{1,6})[ \t\n\r\f]?|(\r\n|[\n\r\f])|(.))", re.S
)
_PUNCT = "{}()[]:;,"


def tokenize(css: str, path=None) -> list[Token]:
    """Split a stylesheet into tokens.

    Every character of the input ends up in exactly one token, so joining the
    values gives the source back.
    """
    tokens: list[Token] = []
    pos = 0
    end = len(css)
    while pos < end:
        ch = css[pos]
        if ch in _WS:
            stop = _WS_RE.match(css, pos).end()
            kind = "ws"
        elif ch == "/" and css.startswith("/*", pos):
            stop = css.find("*/", pos + 2)
            if stop < 0:
                raise AssetError(
                    "unterminated comment", path=path, line=line_at(css, pos)
                )
            stop += 2
            kind = "comment"
        elif ch in "\"'":
            stop = _string_end(css, pos, path)
            kind = "string"
        elif ch == "#":
            match = _NAME_RE.match(css, pos + 1)
            stop = match.end() if match else pos + 1
            kind = "hash" if match else "delim"
        elif ch == "@":
            match = _IDENT_RE.match(css, pos + 1)
            stop = match.end() if match else pos + 1
            kind = "at" if match else "delim"
        elif ch in _PUNCT:
            stop = pos + 1
            kind = ch
        elif css.startswith("<!--", pos):
            stop = pos + 4
            kind = "cdo"
        elif css.startswith("-->", pos):
            stop = pos + 3
            kind = "cdc"
        else:
            kind, stop = _number_or_name(css, pos, path)
        tokens.append(Token(kind, css[pos:stop], pos))
        pos = stop
    return tokens


def _number_or_name(css: str, pos: int, path) -> tuple[str, int]:
    match = _NUMBER_RE.match(css, pos)
    if match:
        stop = match.end()
        unit = _IDENT_RE.match(css, stop)
        if unit:
            return "dimension", unit.end()
        if css.startswith("%", stop):
            return "percentage", stop + 1
        return "number", stop
    match = _IDENT_RE.match(css, pos)
    if match is None:
        return "delim", pos + 1
    stop = match.end()
    if not css.startswith("(", stop):
        return "ident", stop
    stop += 1
    if match.group().lower() != "url":
        return "function", stop
    # url( followed by a quote is an ordinary function holding a string;
    # the unquoted form is a single token of its own.
    space = _WS_RE.match(css, stop)
    arg = space.end() if space else stop
    if css[arg : arg + 1] in ('"', "'"):
        return "function", stop
    body = _URL_BODY_RE.match(css, stop)
    if body:
        return "url", body.end()
    close = css.find(")", stop)
    if close < 0:
        raise AssetError("unterminated url()", path=path, line=line_at(css, pos))
    return "bad-url", close + 1


def _string_end(css: str, pos: int, path) -> int:
    quote = css[pos]
    i = pos + 1
    end = len(css)
    while i < end:
        ch = css[i]
        if ch == quote:
            return i + 1
        if ch == "\\":
            i += 3 if css.startswith("\r\n", i + 1) else 2
            continue
        if ch in "\n\r\f":
            break
        i += 1
    raise AssetError("unterminated string", path=path, line=line_at(css, pos))


def unescape(text: str) -> str:
    """Resolve CSS backslash escapes in an identifier, string body or url."""

    def repl(match: re.Match) -> str:
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        if match.group(2):
            return ""
        return match.group(3)

    return _ESCAPE_RE.sub(repl, text) if "\\" in text else text


def string_value(token_text: str) -> str:
    """Contents of a string token (quotes stripped, escapes resolved)."""
    return unescape(token_text[1:-1])


def quote_string(value: str, quote: str = '"') -> str:
    out = value.replace("\\", "\\\\").replace(quote, "\\" + quote)
    out = out.replace("\n", "\\a ").replace("\r", "\\d ").replace("\f", "\\c ")
    return quote + out + quote


_URL_NEEDS_QUOTES_RE = re.compile(r"[\s\"'()\\\x00-\x1f\x7f]")


def format_url(url: str) -> str:
    """Write a url() using the unquoted form whenever that is legal."""
    if url and not _URL_NEEDS_QUOTES_RE.search(url):
        return "url(" + url + ")"
    return "url(" + quote_string(url) + ")"


def _significant(tokens: list[Token], i: int) -> int:
    """Index of the first token at or after `i` that is not space or comment."""
    while i < len(tokens) and tokens[i].type in ("ws", "comment"):
        i += 1
    return i


def _url_refs(tokens: list[Token]) -> Iterator[tuple[Token, str]]:
    """Yield (token, url) for every token that holds a URL reference.

    That is unquoted url() tokens, the string inside url("...") and
    image-set("..."), and the string form of @import.
    """
    stack: list[str] = []
    for i, tok in enumerate(tokens):
        kind = tok.type
        if kind == "url":
            yield tok, unescape(tok.value[4:-1].strip(_WS))
        elif kind == "function":
            stack.append(tok.value[:-1].lower())
        elif kind == "(":
            stack.append("")
        elif kind == ")":
            if stack:
                stack.pop()
        elif kind == "string":
            if stack and stack[-1] in ("url", "image-set", "-webkit-image-set"):
                yield tok, string_value(tok.value)
            elif not stack and _follows_import(tokens, i):
                yield tok, string_value(tok.value)


def _follows_import(tokens: list[Token], i: int) -> bool:
    i -= 1
    while i >= 0 and tokens[i].type in ("ws", "comment"):
        i -= 1
    return i >= 0 and tokens[i].type == "at" and tokens[i].value.lower() == "@import"


def rewrite_urls(css: str, fn: Callable[[str], str | None], *, path=None) -> str:
    """Pass every URL in `css` through `fn` and splice the results back in.

    `fn` returns the replacement, or None to leave that reference alone.
    Nothing else in the stylesheet is touched.
    """
    out: list[str] = []
    last = 0
    for tok, url in _url_refs(tokenize(css, path)):
        new = fn(url)
        if new is None or new == url:
            continue
        out.append(css[last : tok.pos])
        if tok.type == "url":
            out.append(format_url(new))
        else:
            out.append(quote_string(new, tok.value[0]))
        last = tok.end
    out.append(css[last:])
    return "".join(out)


_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*:")


def is_relative_url(url: str) -> bool:
    """True for references that depend on where the stylesheet lives."""
    url = url.strip()
    return bool(url) and not (
        url.startswith(("/", "#", "?")) or _SCHEME_RE.match(url)
    )


def split_suffix(url: str) -> tuple[str, str]:
    """Split off the ?query and #fragment."""
    cut = len(url)
    for mark in "?#":
        found = url.find(mark)
        if found >= 0:
            cut = min(cut, found)
    return url[:cut], url[cut:]


def rebase_urls(css: str, from_dir: str, to_dir: str, *, path=None) -> str:
    """Adjust relative URLs for a stylesheet moving between directories.

    Both directories are slash-separated and relative to the same root.
    """
    if posixpath.normpath(from_dir or ".") == posixpath.normpath(to_dir or "."):
        return css

    def rebase(url: str) -> str | None:
        if not is_relative_url(url):
            return None
        target, suffix = split_suffix(url)
        target = posixpath.normpath(posixpath.join(from_dir or ".", target))
        return posixpath.relpath(target, to_dir or ".") + suffix

    return rewrite_urls(css, rebase, path=path)


@dataclass
class _Import:
    start: int
    end: int
    url: str
    # None means no layer at all, "" an anonymous one
    layer: str | None
    supports: str
    media: str

    def wrap(self, body: str) -> str:
        if self.layer is not None:
            name = " " + self.layer if self.layer else ""
            body = "@layer" + name + " {\n" + body + "\n}"
        if self.supports:
            body = "@supports " + self.supports + " {\n" + body + "\n}"
        if self.media:
            body = "@media " + self.media + " {\n" + body + "\n}"
        return body


def _statement_end(tokens: list[Token], i: int) -> int:
    """Index of the `;` that ends the at-rule starting at `i` (or len)."""
    depth = 0
    while i < len(tokens):
        kind = tokens[i].type
        if kind in ("(", "[", "function"):
            depth += 1
        elif kind in (")", "]"):
            depth = max(depth - 1, 0)
        elif depth == 0 and kind in (";", "{", "}"):
            break
        i += 1
    return i


def _text(tokens: list[Token]) -> str:
    return "".join(t.value for t in tokens if t.type != "comment").strip(_WS)


def _closing_paren(tokens: list[Token], i: int) -> int:
    """Index of the `)` matching the opener at `i`."""
    depth = 0
    for j in range(i, len(tokens)):
        kind = tokens[j].type
        if kind in ("(", "function"):
            depth += 1
        elif kind == ")":
            depth -= 1
            if depth == 0:
                return j
    return len(tokens) - 1


def _parse_import(tokens: list[Token], start: int, stop: int) -> _Import | None:
    i = _significant(tokens, start + 1)
    if i >= stop:
        return None
    tok = tokens[i]
    if tok.type == "string":
        url = string_value(tok.value)
        i += 1
    elif tok.type == "url":
        url = unescape(tok.value[4:-1].strip(_WS))
        i += 1
    elif tok.type == "function" and tok.value.lower() == "url(":
        close = _closing_paren(tokens, i)
        inner = [t for t in tokens[i + 1 : close] if t.type == "string"]
        if not inner:
            return None
        url = string_value(inner[0].value)
        i = close + 1
    else:
        return None

    layer = None
    supports = ""
    i = _significant(tokens, i)
    if i < stop and tokens[i].value.lower() == "layer":
        layer = ""
        i = _significant(tokens, i + 1)
    elif i < stop and tokens[i].value.lower() == "layer(":
        close = _closing_paren(tokens, i)
        layer = _text(tokens[i + 1 : close])
        i = _significant(tokens, close + 1)
    if i < stop and tokens[i].value.lower() == "supports(":
        close = _closing_paren(tokens, i)
        supports = _text(tokens[i + 1 : close])
        # supports(display: grid) takes a bare declaration, @supports wants
        # it parenthesised
        if not supports.startswith(("(", "not ", "not(")):
            supports = "(" + supports + ")"
        i = close + 1
    end = tokens[stop].end if stop < len(tokens) else tokens[-1].end
    return _Import(
        tokens[start].pos, end, url, layer, supports, _text(tokens[i:stop])
    )


def leading_statements(tokens: list[Token]) -> Iterator[tuple[str, int, int]]:
    """Yield (name, start, stop) for the @charset/@import/@layer statements
    that open a stylesheet; `stop` is the index of the closing `;`.

    @import only counts up here; one that appears after an ordinary rule is
    ignored by browsers.
    """
    i = 0
    while True:
        i = _significant(tokens, i)
        if i >= len(tokens) or tokens[i].type != "at":
            return
        name = tokens[i].value.lower()
        stop = _statement_end(tokens, i)
        ended = stop >= len(tokens) or tokens[stop].type == ";"
        if name not in ("@charset", "@import", "@layer") or not ended:
            return
        yield name, i, stop
        i = stop + 1


# takes a root-relative name, returns the stylesheet text or None
Loader = Callable[[str], Optional[str]]


def inline_imports_from(name: str, load: Loader, *, deps: list | None = None) -> str:
    """Expand local @import rules, reading files through `load`.

    Names are slash-separated paths relative to some root that `load` knows
    about; it returns the stylesheet text, or None if there is no such file.
    Every file pulled in is appended to `deps`.
    """
    css = load(name)
    if css is None:
        raise AssetError("stylesheet not found", path=name)
    return _inline(name, css, load, deps, ())


def _inline(
    name: str, css: str, load: Loader, deps: list | None, parents: tuple
) -> str:
    tokens = tokenize(css, name)
    chain = parents + (name,)
    here = posixpath.dirname(name)
    out: list[str] = []
    last = 0
    for kind, start, stop in leading_statements(tokens):
        if kind == "@charset" and parents:
            # only meaningful as the first bytes of a file, which this no
            # longer is
            out.append(css[last : tokens[start].pos])
            last = tokens[stop].end if stop < len(tokens) else len(css)
            continue
        if kind != "@import":
            continue
        imp = _parse_import(tokens, start, stop)
        if imp is None or not _is_local(imp.url):
            continue
        line = line_at(css, imp.start)
        target, _ = split_suffix(imp.url)
        if target.startswith("/"):
            target = posixpath.normpath(target.lstrip("/"))
        else:
            target = posixpath.normpath(posixpath.join(here, target))
        if target in chain:
            loop = " -> ".join(chain[chain.index(target) :] + (target,))
            raise AssetError(f"circular @import: {loop}", path=name, line=line)
        imported = load(target)
        if imported is None:
            raise AssetError(
                f"cannot find imported file {imp.url!r}", path=name, line=line
            )
        if deps is not None and target not in deps:
            deps.append(target)
        body = _inline(target, imported, load, deps, chain)
        body = rebase_urls(body, posixpath.dirname(target), here, path=target)
        # XXX an external @import inside a file that gets wrapped in @media
        # ends up nested, where browsers ignore it.
        out.append(css[last : imp.start])
        out.append(imp.wrap(body.strip(_WS)))
        last = imp.end
    out.append(css[last:])
    return "".join(out)


def _is_local(url: str) -> bool:
    url = url.strip()
    return bool(url) and not url.startswith("//") and not _SCHEME_RE.match(url)


def read_css(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise AssetError("not valid UTF-8", path=path) from None
    except OSError as exc:
        raise AssetError(f"cannot read file: {exc.strerror}", path=path) from None


def inline_imports(path, *, root=None, deps: list | None = None) -> str:
    """Return the stylesheet at `path` with its local @imports inlined.

    Relative imports are followed from each file's own directory. `root` is
    what a leading slash refers to; it defaults to the directory of `path`.
    Imports of other sites (http:, //cdn...) are left in place. A file that
    ends up importing itself raises AssetError.
    """
    path = Path(path)
    root = Path(root) if root is not None else path.parent
    try:
        name = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise AssetError(f"not inside {root}", path=path) from None

    def load(name: str) -> str | None:
        target = root / name
        return read_css(target) if target.is_file() else None

    if not path.is_file():
        raise AssetError("stylesheet not found", path=path)
    return inline_imports_from(name, load, deps=deps)


@dataclass
class _Decl:
    tokens: list[Token]


@dataclass
class _Rule:
    prelude: list[Token]
    # None for statements such as `@import "x";`
    block: list | None


class _Parser:
    """Groups a token list into rules and declarations.

    Just enough structure for the minifier: it knows where selectors, values
    and blocks begin and end, not what they mean.
    """

    def __init__(self, css: str, path=None):
        self.css = css
        self.path = path
        self.tokens = tokenize(css, path)

    def items(self, i: int, nested: bool) -> tuple[list, int]:
        tokens = self.tokens
        items: list = []
        while i < len(tokens):
            tok = tokens[i]
            kind = tok.type
            if kind in ("ws", ";", "cdo", "cdc"):
                i += 1
            elif kind == "comment":
                if tok.value.startswith("/*!"):
                    items.append(tok)
                i += 1
            elif kind == "}":
                if not nested:
                    raise AssetError(
                        "unexpected '}'",
                        path=self.path,
                        line=line_at(self.css, tok.pos),
                    )
                return items, i + 1
            else:
                item, i = self.item(i)
                items.append(item)
        # running off the end closes any open blocks, as browsers do
        return items, i

    def item(self, i: int):
        tokens = self.tokens
        start = i
        first = tokens[i]
        custom = first.type == "ident" and first.value.startswith("--")
        if custom:
            colon = _significant(tokens, i + 1)
            custom = colon < len(tokens) and tokens[colon].type == ":"
        depth = 0
        braces = 0
        while i < len(tokens):
            kind = tokens[i].type
            if kind in ("(", "[", "function"):
                depth += 1
            elif kind in (")", "]"):
                depth = max(depth - 1, 0)
            elif custom:
                # custom property values may contain balanced {} blocks
                if kind == "{":
                    braces += 1
                elif kind == "}":
                    if braces == 0:
                        break
                    braces -= 1
                elif kind == ";" and braces == 0 and depth == 0:
                    break
            elif depth == 0:
                if kind in (";", "}"):
                    break
                if kind == "{":
                    block, end = self.items(i + 1, nested=True)
                    return _Rule(tokens[start:i], block), end
            i += 1
        body = tokens[start:i]
        if i < len(tokens) and tokens[i].type == ";":
            i += 1
        if first.type == "at":
            return _Rule(body, None), i
        return _Decl(body), i


_SEPARATORS = frozenset(["ws", "comment", *_PUNCT])

_LENGTH_UNITS = frozenset(
    "px em rem ex ch cap ic lh rlh vw vh vi vb vmin vmax svw svh lvw lvh dvw dvh "
    "cqw cqh cqi cqb cqmin cqmax cm mm q in pt pc".split()
)
_MATH_FUNCTIONS = frozenset(
    "calc min max clamp round mod rem sin cos tan asin acos atan atan2 pow sqrt "
    "hypot log exp abs sign -webkit-calc -moz-calc".split()
)
# nothing inside these is rewritten: whatever comes out gets substituted
# somewhere we cannot see
_OPAQUE_FUNCTIONS = frozenset(["var", "env", "attr"])
_COLOUR_FUNCTIONS = frozenset(["rgb", "rgba", "hsl", "hsla"])
_COLOUR_SHORTHANDS = frozenset(
    "background background-image border border-top border-right border-bottom "
    "border-left border-block border-inline outline box-shadow text-shadow "
    "text-decoration column-rule fill stroke".split()
)
# `flex: 1 1 0` and `flex: 1 1 0px` are not the same thing
_KEEP_UNIT_PROPS = frozenset(["flex", "flex-basis", "-webkit-flex", "-ms-flex"])
_VERBATIM_PROPS = frozenset(["unicode-range", "-ms-filter"])
_BOX_PROPS = frozenset(
    "margin padding inset border-width border-style border-color border-radius "
    "scroll-margin scroll-padding".split()
)
_PAIR_PROPS = frozenset(
    "gap overflow overscroll-behavior place-items place-content place-self "
    "border-spacing margin-block margin-inline padding-block padding-inline "
    "inset-block inset-inline".split()
)
_FONT_WEIGHTS = {"normal": "400", "bold": "700"}
_KEYFRAME_STOPS = {"from": "0%", "100%": "to"}
_DROP_WHEN_EMPTY = frozenset(
    ["@media", "@supports", "@container", "@document", "@font-face", "@page"]
)
_NUMBER_PARTS_RE = re.compile(r"([+-]?)(\d*)(?:\.(\d+))?((?:[eE][+-]?\d+)?)")


def _clean(tokens: list[Token]) -> list[Token]:
    """Drop comments, squash whitespace runs to one space, trim both ends."""
    out: list[Token] = []
    for i, tok in enumerate(tokens):
        if tok.type == "comment":
            if tok.value.startswith("/*!"):
                out.append(tok)
                continue
            before = out[-1].type if out else "ws"
            after = tokens[i + 1].type if i + 1 < len(tokens) else "ws"
            if before in _SEPARATORS or (after in _SEPARATORS and after != "comment"):
                continue
            # a/**/b is two tokens; without the comment it would be one
            out.append(tok._replace(value="/**/"))
        elif tok.type == "ws":
            if out and out[-1].type != "ws":
                out.append(tok._replace(value=" "))
        else:
            out.append(tok)
    while out and out[-1].type == "ws":
        out.pop()
    return out


def _join(tokens: list[Token]) -> str:
    return "".join(t.value for t in tokens)


def _shorten_numeric(tok: Token, prop: str, in_math: bool) -> str:
    text = tok.value
    end = _NUMBER_RE.match(text).end()
    unit = text[end:]
    sign, whole, frac, exponent = _NUMBER_PARTS_RE.fullmatch(text[:end]).groups()
    if exponent:
        return text
    whole = whole.lstrip("0")
    frac = (frac or "").rstrip("0")
    if whole or frac:
        return sign + whole + ("." + frac if frac else "") + unit
    if in_math:
        # calc(0px + 1em) needs its unit, and -0 is a different number there
        return sign + "0" + unit
    droppable = tok.type == "dimension" and unit.lower() in _LENGTH_UNITS
    if droppable and prop not in _KEEP_UNIT_PROPS:
        return "0"
    return "0" + unit


def _colour_from_function(name: str, inner: list[Token]) -> str | None:
    """`#rrggbb` for an opaque rgb()/hsl() call with literal arguments."""
    args = [t for t in inner if t.type not in ("ws", ",", "comment")]
    alpha = None
    if len(args) == 5 and args[3].type == "delim" and args[3].value == "/":
        alpha = args[4]
        args = args[:3]
    elif len(args) == 4:
        alpha = args.pop()
    if len(args) != 3:
        return None
    if alpha is not None:
        if alpha.type not in ("number", "percentage"):
            return None
        opaque = 100.0 if alpha.type == "percentage" else 1.0
        if float(alpha.value.rstrip("%")) < opaque:
            return None

    if name.startswith("rgb"):
        kinds = {t.type for t in args}
        if kinds == {"number"}:
            return _colors.rgb_to_hex(*(float(t.value) for t in args))
        if kinds == {"percentage"}:
            return _colors.rgb_to_hex(*(float(t.value[:-1]) * 2.55 for t in args))
        return None

    hue, sat, light = args
    if hue.type == "dimension" and hue.value.lower().endswith("deg"):
        degrees = hue.value[:-3]
    elif hue.type == "number":
        degrees = hue.value
    else:
        return None
    if sat.type != "percentage" or light.type != "percentage":
        return None
    try:
        return _colors.hsl_to_hex(
            float(degrees), float(sat.value[:-1]), float(light.value[:-1])
        )
    except ValueError:
        return None


def _unquote_url(toks: list[Token], i: int) -> tuple[Token, int] | None:
    """Turn url("x") starting at `i` into a single unquoted url token."""
    j = i + 1
    if j < len(toks) and toks[j].type == "ws":
        j += 1
    if j >= len(toks) or toks[j].type != "string":
        return None
    k = j + 1
    if k < len(toks) and toks[k].type == "ws":
        k += 1
    if k >= len(toks) or toks[k].type != ")":
        return None
    body = toks[j].value[1:-1]
    if not body or _URL_NEEDS_QUOTES_RE.search(body):
        return None
    return Token("url", "url(" + body + ")", toks[i].pos), k + 1


def _can_follow_colour(toks: list[Token], i: int) -> bool:
    # rgb(0,0,0)solid is legal; blacksolid would be a different word
    if i >= len(toks):
        return True
    tok = toks[i]
    return tok.type in ("ws", ",", ")") or (tok.type == "delim" and tok.value in "/!")


def _optimise(prop: str, toks: list[Token]) -> list[Token]:
    colourish = prop.endswith("color") or prop in _COLOUR_SHORTHANDS
    out: list[Token] = []
    stack: list[str] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        kind = tok.type
        i += 1
        frozen = any(name in _OPAQUE_FUNCTIONS for name in stack)
        if kind == "function":
            name = tok.value[:-1].lower()
            if name == "url" and not frozen:
                merged = _unquote_url(toks, i - 1)
                if merged:
                    out.append(merged[0])
                    i = merged[1]
                    continue
            if name in _COLOUR_FUNCTIONS and not frozen:
                close = _closing_paren(toks, i - 1)
                colour = None
                if toks[close].type == ")" and _can_follow_colour(toks, close + 1):
                    colour = _colour_from_function(name, toks[i:close])
                if colour:
                    out.append(Token("hash", _colors.shorten_hex(colour), tok.pos))
                    i = close + 1
                    continue
            stack.append(name)
        elif kind == "(":
            stack.append("")
        elif kind == ")":
            if stack:
                stack.pop()
        elif frozen:
            pass
        elif kind in ("number", "percentage", "dimension"):
            in_math = any(name in _MATH_FUNCTIONS for name in stack)
            tok = tok._replace(value=_shorten_numeric(tok, prop, in_math))
        elif kind == "hash":
            if _colors.is_hex_colour(tok.value):
                tok = tok._replace(value=_colors.shorten_hex(tok.value))
        elif kind == "url":
            tok = tok._replace(value="url(" + tok.value[4:-1].strip(_WS) + ")")
        elif kind == "ident":
            if colourish:
                short = _colors.shorten_name(tok.value)
                if short:
                    tok = tok._replace(type="hash", value=short)
            elif prop == "font-weight" and not stack:
                weight = _FONT_WEIGHTS.get(tok.value.lower())
                if weight:
                    tok = tok._replace(type="number", value=weight)
        out.append(tok)
    return out


def _tighten(toks: list[Token]) -> list[Token]:
    """Remove the spaces in a value that do not separate anything."""
    out: list[Token] = []
    stack: list[str] = []
    for i, tok in enumerate(toks):
        kind = tok.type
        if kind == "ws":
            in_math = any(name in _MATH_FUNCTIONS for name in stack)
            glued = "/!*" if in_math else "/!"
            prev = toks[i - 1]
            nxt = toks[i + 1]
            if prev.type in (",", "(", "function") or nxt.type in (",", ")"):
                continue
            if prev.type == "delim" and prev.value in glued:
                continue
            if nxt.type == "delim" and nxt.value in glued:
                continue
        elif kind == "function":
            stack.append(tok.value[:-1].lower())
        elif kind == "(":
            stack.append("")
        elif kind == ")" and stack:
            stack.pop()
        out.append(tok)
    return out


def _split_groups(toks: list[Token]) -> list[str] | None:
    """Space-separated components of a value, or None if it is not that simple."""
    groups: list[list[str]] = [[]]
    depth = 0
    for tok in toks:
        if tok.type in ("function", "("):
            depth += 1
        elif tok.type == ")":
            depth -= 1
        elif depth == 0:
            if tok.type == "ws":
                groups.append([])
                continue
            if tok.type == "," or (tok.type == "delim" and tok.value == "/"):
                return None
        groups[-1].append(tok.value)
    return ["".join(group) for group in groups]


def _collapse_box(parts: list[str]) -> list[str]:
    """top right bottom left -> the shortest equivalent list."""
    lowered = [p.lower() for p in parts]
    if len(parts) == 4 and lowered[3] == lowered[1]:
        parts = parts[:3]
    if len(parts) == 3 and lowered[2] == lowered[0]:
        parts = parts[:2]
    if len(parts) == 2 and lowered[1] == lowered[0]:
        parts = parts[:1]
    return parts


def _value(prop: str, toks: list[Token]) -> str:
    if prop in _VERBATIM_PROPS:
        return _join(toks)
    if prop == "filter" and any(t.value.lower() == "progid" for t in toks):
        # old IE filters carry #AARRGGBB colours and their own syntax
        return _join(toks)
    toks = _tighten(_optimise(prop, toks))
    text = _join(toks)
    if prop in _BOX_PROPS or prop in _PAIR_PROPS:
        parts = _split_groups(toks)
        if parts and prop in _BOX_PROPS and len(parts) <= 4:
            text = " ".join(_collapse_box(parts))
        elif parts and len(parts) == 2 and parts[0].lower() == parts[1].lower():
            text = parts[0]
    # No `border:none` -> `border:0` here, tempting as it is: the two leave
    # different widths behind for a later `border-style: solid` to pick up.
    return text


def _declaration(tokens: list[Token]) -> str:
    toks = _clean(tokens)
    if not toks:
        return ""
    colon = next((i for i, t in enumerate(toks[:3]) if t.type == ":"), 0)
    if toks[0].type != "ident" or not colon:
        # *zoom:1 and friends; leave whatever this is alone
        return _join(toks)
    name = toks[0].value
    value = toks[colon + 1 :]
    if value and value[0].type == "ws":
        del value[0]
    if name.startswith("--"):
        # `--x: ;` (an empty value) is valid and different from no value
        return name + ":" + (_join(value) or " ")

    important = False
    if len(value) >= 2 and value[-1].value.lower() == "important":
        bang = len(value) - 2
        if value[bang].type == "ws" and bang:
            bang -= 1
        if value[bang].type == "delim" and value[bang].value == "!":
            important = True
            value = value[:bang]
            if value and value[-1].type == "ws":
                value.pop()
    prop = name.lower()
    return prop + ":" + _value(prop, value) + ("!important" if important else "")


def _selector(tokens: list[Token]) -> str:
    toks = _clean(tokens)
    out: list[str] = []
    brackets = 0

    def hugs(tok: Token, is_prev: bool) -> bool:
        if tok.type == ",":
            return True
        if tok.type == "delim":
            return tok.value in ("=~|^$*" if brackets else ">+~")
        if is_prev:
            return tok.type in ("(", "function", "[")
        return tok.type in (")", "]")

    for i, tok in enumerate(toks):
        if tok.type == "ws":
            if not hugs(toks[i - 1], True) and not hugs(toks[i + 1], False):
                out.append(" ")
            continue
        if tok.type == "[":
            brackets += 1
        elif tok.type == "]":
            brackets = max(brackets - 1, 0)
        out.append(tok.value)
    return "".join(out)


def _at_prelude(name: str, tokens: list[Token]) -> str:
    toks = _clean(tokens)
    if not toks:
        return name
    if name == "@charset":
        # browsers only recognise this exact byte sequence
        return name + " " + _join(toks)
    out = [name, " "]
    depth = 0

    def hugs(tok: Token, is_prev: bool) -> bool:
        if tok.type == ",":
            return True
        if not depth:
            return False
        if tok.type == ":" or (tok.type == "delim" and tok.value in "<>=/"):
            return True
        if is_prev:
            return tok.type in ("(", "function")
        return tok.type == ")"

    for i, tok in enumerate(toks):
        if tok.type == "ws":
            if not hugs(toks[i - 1], True) and not hugs(toks[i + 1], False):
                out.append(" ")
            continue
        if tok.type in ("(", "function"):
            depth += 1
        elif tok.type == ")":
            depth = max(depth - 1, 0)
        out.append(tok.value)
    return "".join(out)


def _rule(rule: _Rule, in_keyframes: bool) -> str:
    first = rule.prelude[0] if rule.prelude else None
    if first is not None and first.type == "at":
        name = first.value.lower()
        head = _at_prelude(name, rule.prelude[1:])
        if rule.block is None:
            return head
        body = _block(rule.block, top=False, in_keyframes=name.endswith("keyframes"))
        if not body and name in _DROP_WHEN_EMPTY:
            return ""
        return head + "{" + body + "}"

    body = _block(rule.block, top=False)
    if not body:
        return ""
    head = _selector(rule.prelude)
    if in_keyframes:
        stops = head.split(",")
        head = ",".join(_KEYFRAME_STOPS.get(s.lower(), s) for s in stops)
    return head + "{" + body + "}"


def _block(items: list, *, top: bool, in_keyframes: bool = False) -> str:
    out: list[str] = []
    unterminated = False
    for item in items:
        if isinstance(item, Token):
            text = item.value
        elif isinstance(item, _Decl):
            text = _declaration(item.tokens)
        else:
            text = _rule(item, in_keyframes)
        if not text:
            continue
        if unterminated:
            out.append(";")
        out.append(text)
        unterminated = isinstance(item, _Decl) or (
            isinstance(item, _Rule) and item.block is None
        )
    if unterminated and top:
        out.append(";")
    return "".join(out)


def _normalise(css: str) -> str:
    if css.startswith("\ufeff"):
        css = css[1:]
    return css.replace("\r\n", "\n").replace("\r", "\n")


def minify_css(css: str, *, path=None) -> str:
    """Minify a stylesheet. `path` is only used in error messages."""
    parser = _Parser(_normalise(css), path)
    items, _ = parser.items(0, nested=False)
    return _block(items, top=True)


def minify_declarations(css: str, *, path=None) -> str:
    """Minify a bare declaration list, as found in a style="" attribute."""
    parser = _Parser(_normalise(css), path)
    items, _ = parser.items(0, nested=False)
    return _block(items, top=False)
