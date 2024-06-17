from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import css as _css
from . import js as _js
from .errors import AssetError, line_at


@dataclass
class Attr:
    name: str
    # raw source text with entities left as written; None for a bare attribute
    value: str | None
    quote: str = '"'
    # where the value sits in the source, quotes excluded
    start: int = 0
    end: int = 0


@dataclass
class Token:
    # type is one of: text raw start end comment doctype decl cdata pi
    # "raw" is the body of script/style/textarea/title.
    type: str
    data: str
    pos: int
    name: str = ""
    attrs: list[Attr] = field(default_factory=list)
    self_closing: bool = False

    def get(self, name: str) -> str | None:
        """Raw value of the named attribute (first wins, like browsers)."""
        for attr in self.attrs:
            if attr.name.lower() == name:
                return attr.value or ""
        return None


_RAW_TEXT = frozenset(
    "script style textarea title xmp iframe noembed noframes plaintext".split()
)
_VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
_TAG_NAME_RE = re.compile(r"[a-zA-Z][^\s/>]*")
_TAG_SPACE_RE = re.compile(r"[\s/]*")
_ATTR_NAME_RE = re.compile(r"[^\s/>][^\s/>=]*")
_ATTR_EQUALS_RE = re.compile(r"\s*=\s*")
_UNQUOTED_RE = re.compile(r"[^\s>]*")


def tokenize(html: str, path=None) -> list[Token]:
    """Split a document into tags, text and friends.

    The tokens cover the input exactly, so joining their `data` gives the
    source back.
    """
    tokens: list[Token] = []
    pos = 0
    end = len(html)

    def fail(message: str, at: int):
        raise AssetError(message, path=path, line=line_at(html, at))

    def flush_text(upto: int) -> None:
        if upto > pos:
            tokens.append(Token("text", html[pos:upto], pos))

    search = 0
    while pos < end:
        lt = html.find("<", search)
        if lt < 0:
            flush_text(end)
            break
        nxt = html[lt + 1 : lt + 2]
        if html.startswith("<!--", lt):
            # <!--> and <!---> are complete (empty) comments
            if html.startswith(">", lt + 4) or html.startswith("->", lt + 4):
                stop = html.index(">", lt + 4) + 1
            else:
                close = html.find("-->", lt + 4)
                if close < 0:
                    fail("unterminated comment", lt)
                stop = close + 3
            tok = Token("comment", html[lt:stop], lt)
        elif html.startswith("<![CDATA[", lt):
            close = html.find("]]>", lt)
            stop = close + 3 if close >= 0 else end
            tok = Token("cdata", html[lt:stop], lt)
        elif nxt in ("!", "?"):
            close = html.find(">", lt)
            stop = close + 1 if close >= 0 else end
            kind = "pi" if nxt == "?" else "decl"
            if html[lt + 2 : lt + 9].lower() == "doctype":
                kind = "doctype"
            tok = Token(kind, html[lt:stop], lt)
        elif nxt == "/" and html[lt + 2 : lt + 3].isalpha():
            name = _TAG_NAME_RE.match(html, lt + 2).group()
            close = html.find(">", lt)
            if close < 0:
                fail(f"unterminated </{name}> tag", lt)
            stop = close + 1
            tok = Token("end", html[lt:stop], lt, name.lower())
        elif nxt.isalpha() and nxt.isascii():
            tok = _start_tag(html, lt, fail)
            stop = tok.pos + len(tok.data)
        else:
            # a stray "<" is just text
            search = lt + 1
            continue

        flush_text(lt)
        tokens.append(tok)
        pos = search = stop
        if tok.type == "start" and tok.name in _RAW_TEXT:
            stop = _raw_text_end(html, pos, tok.name)
            if stop > pos:
                tokens.append(Token("raw", html[pos:stop], pos))
            pos = search = stop
    return tokens


def _raw_text_end(html: str, pos: int, name: str) -> int:
    if name == "plaintext":
        return len(html)
    match = re.compile("</" + name + r"(?=[\s/>])", re.I).search(html, pos)
    return match.start() if match else len(html)


def _start_tag(html: str, lt: int, fail) -> Token:
    name = _TAG_NAME_RE.match(html, lt + 1)
    tok = Token("start", "", lt, name.group().lower())
    pos = name.end()
    end = len(html)
    while True:
        gap = _TAG_SPACE_RE.match(html, pos)
        pos = gap.end()
        if pos >= end:
            fail(f"unterminated <{tok.name}> tag", lt)
        if html[pos] == ">":
            tok.self_closing = "/" in gap.group()
            tok.data = html[lt : pos + 1]
            return tok
        attr_name = _ATTR_NAME_RE.match(html, pos)
        pos = attr_name.end()
        equals = _ATTR_EQUALS_RE.match(html, pos)
        if equals is None:
            tok.attrs.append(Attr(attr_name.group(), None, "", pos, pos))
            continue
        pos = equals.end()
        quote = html[pos : pos + 1]
        if quote in ('"', "'"):
            close = html.find(quote, pos + 1)
            if close < 0:
                fail(f"unterminated value for attribute {attr_name.group()!r}", pos)
            attr = Attr(attr_name.group(), html[pos + 1 : close], quote, pos + 1, close)
            pos = close + 1
        else:
            value = _UNQUOTED_RE.match(html, pos)
            attr = Attr(attr_name.group(), value.group(), "", pos, value.end())
            pos = value.end()
        tok.attrs.append(attr)


# Elements whose edges swallow whitespace when rendered. Anything not listed
# is treated as inline, where a space between tags is visible.
_BLOCK = frozenset(
    "html head body address article aside blockquote br caption col colgroup dd "
    "details dialog div dl dt fieldset figcaption figure footer form h1 h2 h3 h4 "
    "h5 h6 header hgroup hr legend li main menu nav ol optgroup option p pre "
    "section summary table tbody td tfoot th thead tr ul".split()
)
# Take up no room themselves; whitespace between two of them is noise.
_INVISIBLE = frozenset("script style link meta base title template".split())
_BOOLEAN_ATTRS = frozenset(
    "allowfullscreen async autofocus autoplay checked controls default defer "
    "disabled formnovalidate hidden inert ismap itemscope loop multiple muted "
    "nomodule novalidate open playsinline readonly required reversed "
    "selected".split()
)
_JS_TYPES = frozenset(
    "text/javascript application/javascript text/ecmascript "
    "application/ecmascript application/x-javascript text/jscript".split()
)
_JSON_TYPES = frozenset(
    ["application/json", "application/ld+json", "importmap", "speculationrules"]
)
# inside <svg>: text in these is rendered as written
_FOREIGN_TEXT = frozenset(["text", "foreignobject", "desc"])
_WS_RUN_RE = re.compile(r"[ \t\n\r\f]+")
_NO_QUOTES_RE = re.compile(r"[^\s\"'=<>`]+")
_HTML5_DOCTYPE_RE = re.compile(r"<!doctype\s+html\s*>", re.I)


def _keep_comment(data: str) -> bool:
    body = data[4:-3]
    # conditional comments (both flavours), <!--! keep me -->, and SSI
    return body.startswith(("[if ", "!", "#")) or body.endswith("<![endif]")


def _script_kind(tok: Token) -> str | None:
    kind = (tok.get("type") or "").strip().lower()
    if kind in _JSON_TYPES:
        return "json"
    if not kind or kind == "module" or kind in _JS_TYPES:
        return "js"
    # templates, shaders, whatever else people park in script tags
    return None


class _Minifier:
    def __init__(self, tokens: list[Token], options: dict, path=None):
        self.tokens = tokens
        self.path = path
        self.collapse = options["collapse_whitespace"]
        self.unquote = options["remove_attribute_quotes"]
        self.drop_defaults = options["remove_default_attributes"]
        self.shorten_booleans = options["collapse_boolean_attributes"]
        self.inline_css = options["minify_css"]
        self.inline_js = options["minify_js"]
        self.pre = 0
        self.foreign = 0
        self.foreign_text = 0
        self.in_head = False
        self.opener: Token | None = None

    def run(self) -> str:
        out: list[str] = []
        for i, tok in enumerate(self.tokens):
            kind = tok.type
            if kind == "text":
                out.append(self.text(i))
            elif kind == "start":
                out.append(self.start_tag(tok))
                self.opener = tok
            elif kind == "end":
                out.append(self.end_tag(tok))
            elif kind == "raw":
                out.append(self.raw(tok))
            elif kind == "doctype":
                if _HTML5_DOCTYPE_RE.fullmatch(tok.data):
                    out.append("<!doctype html>")
                else:
                    out.append(_WS_RUN_RE.sub(" ", tok.data))
            else:
                out.append(tok.data)
        return "".join(out)

    def edge(self, i: int) -> str:
        """How the token at `i` treats whitespace next to it."""
        if i < 0 or i >= len(self.tokens):
            return "block"
        tok = self.tokens[i]
        if tok.type in ("start", "end"):
            if self.foreign or tok.name in _BLOCK:
                return "block"
            return "invisible" if tok.name in _INVISIBLE else "inline"
        if tok.type in ("doctype", "decl", "comment"):
            return "block"
        return "inline"

    def text(self, i: int) -> str:
        data = self.tokens[i].data
        if not self.collapse or self.pre or self.foreign_text:
            return data
        data = _WS_RUN_RE.sub(" ", data)
        before = self.edge(i - 1)
        after = self.edge(i + 1)
        if data == " ":
            if self.in_head or "block" in (before, after):
                return ""
            return "" if before == after == "invisible" else " "
        if before == "block":
            data = data.lstrip(" ")
        if after == "block":
            data = data.rstrip(" ")
        return data

    def start_tag(self, tok: Token) -> str:
        name = tok.name
        foreign = self.foreign > 0 or name in ("svg", "math")
        if not tok.self_closing or not foreign:
            self.enter(name)
        # foreign elements and their attributes are case-sensitive
        out = ["<", tok.data[1 : 1 + len(name)] if foreign else name]
        bare_tail = False
        for attr in tok.attrs:
            text = self.attribute(tok, attr, foreign)
            if text:
                out.append(" " + text)
                bare_tail = "=" in text and text[-1] not in "\"'"
        if tok.self_closing and (foreign or name not in _VOID):
            # after an unquoted value the slash would join the value
            out.append(" /" if bare_tail else "/")
        out.append(">")
        return "".join(out)

    def enter(self, name: str) -> None:
        if name in ("pre", "listing"):
            self.pre += 1
        elif name == "head":
            self.in_head = True
        elif name == "body":
            self.in_head = False
        elif name in ("svg", "math"):
            self.foreign += 1
        elif self.foreign and name in _FOREIGN_TEXT:
            self.foreign_text += 1

    def end_tag(self, tok: Token) -> str:
        name = tok.name
        foreign = self.foreign > 0
        if name in ("pre", "listing"):
            self.pre = max(self.pre - 1, 0)
        elif name == "head":
            self.in_head = False
        elif name in ("svg", "math"):
            self.foreign = max(self.foreign - 1, 0)
            if not self.foreign:
                self.foreign_text = 0
        elif foreign and name in _FOREIGN_TEXT:
            self.foreign_text = max(self.foreign_text - 1, 0)
        if foreign:
            return "</" + tok.data[2 : 2 + len(name)] + ">"
        return "</" + name + ">"

    def attribute(self, tok: Token, attr: Attr, foreign: bool) -> str:
        name = attr.name if foreign else attr.name.lower()
        value = attr.value
        if value is None:
            return name
        if not foreign:
            lowered = value.strip().lower()
            if self.drop_defaults and self.is_default(tok, name, lowered):
                return ""
            if self.shorten_booleans and name in _BOOLEAN_ATTRS:
                if lowered in ("", name):
                    return name
            if name == "class":
                value = _WS_RUN_RE.sub(" ", value).strip(" ")
            elif name == "style" and self.inline_css and "&" not in value:
                # entities would need decoding first; not worth the trouble
                try:
                    value = _css.minify_declarations(value)
                except AssetError:
                    pass
        if self.unquote and _NO_QUOTES_RE.fullmatch(value):
            return name + "=" + value
        if '"' not in value:
            return name + '="' + value + '"'
        if "'" not in value:
            return name + "='" + value + "'"
        return name + '="' + value.replace('"', "&quot;") + '"'

    def is_default(self, tok: Token, name: str, value: str) -> bool:
        tag = tok.name
        if tag == "script":
            if name == "type":
                return value in _JS_TYPES
            return name == "language" and value == "javascript"
        if name == "type" and value == "text/css":
            if tag == "style":
                return True
            rel = (tok.get("rel") or "").lower().split()
            return tag == "link" and "stylesheet" in rel
        return tag == "form" and name == "method" and value == "get"

    def raw(self, tok: Token) -> str:
        opener = self.opener
        data = tok.data
        if opener is None or self.pre:
            return data
        if opener.name == "title":
            return _WS_RUN_RE.sub(" ", data).strip(" ")
        try:
            if opener.name == "style" and self.inline_css:
                return _css.minify_css(data)
            if opener.name == "script":
                return self.script(opener, data)
        except AssetError:
            # A page with a dodgy inline snippet should still build; the
            # snippet goes out the way it came in.
            pass
        return data

    def script(self, opener: Token, data: str) -> str:
        kind = _script_kind(opener)
        if kind == "json":
            try:
                compact = json.dumps(
                    json.loads(data), separators=(",", ":"), ensure_ascii=False
                )
            except ValueError:
                return data
            # the JSON parser unescaped any <\/script> that was in there
            return compact.replace("</", "<\\/").replace("<!--", "<\\u0021--")
        if kind != "js" or not self.inline_js:
            return data
        if "<!--" in data:
            # the old hide-from-Netscape-2 wrapper; our lexer does not speak it
            return data
        return _js.minify_js(data)


def _drop_comments(tokens: list[Token]) -> list[Token]:
    out: list[Token] = []
    for tok in tokens:
        if tok.type == "comment" and not _keep_comment(tok.data):
            continue
        if tok.type == "text" and out and out[-1].type == "text":
            # text on either side of a removed comment is one run again
            out[-1] = Token("text", out[-1].data + tok.data, out[-1].pos)
            continue
        out.append(tok)
    return out


def minify_html(
    html: str,
    *,
    collapse_whitespace: bool = True,
    remove_comments: bool = True,
    remove_attribute_quotes: bool = False,
    remove_default_attributes: bool = True,
    collapse_boolean_attributes: bool = True,
    minify_css: bool = True,
    minify_js: bool = True,
    path=None,
) -> str:
    """Minify an HTML document or fragment.

    Whitespace inside pre, textarea, script and style is left alone, and a
    space between inline elements is never removed entirely. Whitespace
    next to block-level tags (div, p, li...) does go, on the assumption that
    they are displayed as blocks; a stylesheet that turns list items into
    inline-blocks and relies on the gaps between them will notice.

    Quote removal is off by default: it saves little and upsets some
    XML-minded tools.
    """
    if html.startswith("\ufeff"):
        html = html[1:]
    html = html.replace("\r\n", "\n").replace("\r", "\n")
    tokens = tokenize(html, path)
    if remove_comments:
        tokens = _drop_comments(tokens)
    options = {
        "collapse_whitespace": collapse_whitespace,
        "remove_attribute_quotes": remove_attribute_quotes,
        "remove_default_attributes": remove_default_attributes,
        "collapse_boolean_attributes": collapse_boolean_attributes,
        "minify_css": minify_css,
        "minify_js": minify_js,
    }
    return _Minifier(tokens, options, path).run()
