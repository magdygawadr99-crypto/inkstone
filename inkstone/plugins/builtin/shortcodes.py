"""Shortcodes: small named snippets called from Markdown.

    {{< figure src="harbour.jpg" alt="Boats" caption="Six in the morning." >}}

Expansion happens in two steps. Before Markdown runs, every shortcode is
replaced by a placeholder (a few private-use characters Markdown has no
opinion about) and its HTML is put aside; once the page is rendered the
placeholders are swapped for the HTML. Handing the HTML to the Markdown
parser directly mostly works too, right up to the first shortcode that
prints a blank line.

A shortcode is a function taking a Call and returning HTML, registered with
register(), or a template in ``templates/shortcodes/<name>.html``. Templates
win over functions, so a site can replace the built-in ones.
"""

from __future__ import annotations

import difflib
import html
import posixpath
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from ... import frontmatter
from ...errors import ContentError, InkstoneError
from ...tmpl import (
    Environment,
    FileSystemLoader,
    Markup,
    TemplateError,
    TemplateNotFound,
    select_autoescape,
)
from ...utils import fs, log, paths
from ...utils.hashing import hash_text
from ..base import Plugin
from . import _html
from ._common import display_path, lookup, setting, source_file, url_for
from ._shortcode_parser import Shortcode, parse

_NAME = re.compile(r"[A-Za-z_][\w-]*")

# Private-use characters: valid text everywhere, nothing Markdown reacts to,
# and dropped by slugify, so a shortcode in a heading stays out of its id.
_START = "\ue000"
_END = "\ue001"
_DIGITS = "".join(chr(0xE010 + digit) for digit in range(10))
_ENCODE = str.maketrans("0123456789", _DIGITS)
_DECODE = str.maketrans(_DIGITS, "0123456789")
_PLACEHOLDER = re.compile(f"{_START}([{_DIGITS}]+){_END}")
# what the Markdown renderer turns a placeholder into inside a link target
_QUOTED_START = quote(_START)
_QUOTED_PLACEHOLDER = re.compile(
    re.escape(_QUOTED_START)
    + "((?:"
    + "|".join(re.escape(quote(char)) for char in _DIGITS)
    + ")+)"
    + re.escape(quote(_END))
)

_PARAGRAPH = re.compile(r"<p>(.*?)</p>", re.S)
_EDGE_BREAKS = re.compile(r"\A(?:\s|<br\s*/?>)+|(?:\s|<br\s*/?>)+\Z")
_BLOCK = re.compile(
    r"\s*<(?:address|article|aside|blockquote|details|div|dl|fieldset|figure"
    r"|footer|form|h[1-6]|header|hr|main|nav|ol|p|pre|section|table|ul)\b",
    re.I,
)

# how deep {{< include >}} may nest before we assume a loop
_MAX_INCLUDES = 10
_MARKDOWN_SUFFIXES = (".md", ".markdown")
# see Shortcodes._inputs()
_INPUTS_NOTE = re.compile(r"\n<!-- shortcodes:[0-9a-f]+ -->\Z")


@dataclass
class _Handler:
    fn: Callable
    # the result goes into the Markdown source instead of being held as HTML
    text: bool = False
    # for shortcodes that are templates: a hash of the template's source
    stamp: str = ""


@dataclass
class _Held:
    html: str
    # the shortcode as written, for when it turns out to sit in a code block
    source: str
    block: bool


_registry: dict[str, _Handler] = {}


def register(name: str, fn: Callable | None = None, *, text: bool = False):
    """Make ``fn(call)`` available as the shortcode ``name``.

    The function returns HTML. With ``text=True`` what it returns is put
    into the Markdown source instead, for shortcodes that produce a URL or
    more Markdown. Without ``fn`` this is a decorator.
    """
    if not _NAME.fullmatch(name):
        raise ValueError(f"{name!r} cannot be used as a shortcode name")

    def add(func: Callable) -> Callable:
        _registry[name] = _Handler(func, text)
        return func

    return add if fn is None else add(fn)


def unregister(name: str) -> None:
    _registry.pop(name, None)


def registered() -> list[str]:
    return sorted(_registry)


def _placeholder(index: int) -> str:
    return _START + str(index).translate(_ENCODE) + _END


def _item(held: list[_Held], encoded: str) -> _Held | None:
    index = int(encoded.translate(_DECODE))
    # out of range: somebody typed these characters into the text themselves
    return held[index] if index < len(held) else None


def _trim(inner: str) -> str:
    if "\n" not in inner:
        return inner.strip()
    return textwrap.dedent(inner).strip("\n")


def restore(markup: str, held: list[_Held]) -> str:
    """Put the HTML that was held back into rendered Markdown."""
    if _START not in markup and _QUOTED_START not in markup:
        return markup

    def item(encoded: str) -> _Held | None:
        return _item(held, encoded)

    def is_block(encoded: str) -> bool:
        found = item(encoded)
        return found is not None and found.block

    def paragraph(match: re.Match) -> str:
        # Markdown wraps a shortcode on a line of its own in <p>. Block-level
        # output cannot stay in there: it goes between paragraphs instead.
        parts = _PLACEHOLDER.split(match.group(1))
        blocks = {i for i in range(1, len(parts), 2) if is_block(parts[i])}
        if not blocks:
            return match.group()
        out = []
        run = ""
        for index, part in enumerate(parts + [""]):
            if index in blocks or index == len(parts):
                run = _EDGE_BREAKS.sub("", run)
                if run:
                    out.append(f"<p>{run}</p>")
                run = ""
                if index in blocks:
                    out.append(_START + part + _END)
            elif index % 2:
                run += _START + part + _END
            else:
                run += part
        return "\n".join(out)

    def as_html(match: re.Match) -> str:
        found = item(match.group(1))
        return match.group() if found is None else found.html

    def as_written(match: re.Match) -> str:
        found = item(match.group(1))
        if found is None:
            return match.group()
        return html.escape(found.source, quote=False)

    def as_text(match: re.Match) -> str:
        found = item(unquote(match.group(1)))
        if found is None:
            return match.group()
        return _html.escape(_html.text_content(found.html))

    markup = _PARAGRAPH.sub(paragraph, markup)
    out = []
    for token in _html.tokenize(markup):
        source = token.source
        if _START in source:
            # In a code block it can only be an indented one, which we did
            # not recognise as code: show what was written there, not what
            # it expands to.
            in_code = token.protected and token.kind == "text"
            source = _PLACEHOLDER.sub(as_written if in_code else as_html, source)
        if _QUOTED_START in source:
            source = _QUOTED_PLACEHOLDER.sub(as_text, source)
        out.append(source)
    return "".join(out)


class Call:
    """One use of a shortcode, as handed to the function behind it."""

    def __init__(self, expansion: _Expansion, node: Shortcode, inner: str | None):
        self.name = node.name
        self.args = list(node.args)
        self.kwargs = dict(node.kwargs)
        # written as {{% name %}}
        self.markdown = node.markdown
        self.line = node.line
        self.page = expansion.page
        self.site = expansion.site
        self.config = expansion.config
        self._expansion = expansion
        # inner text with nested shortcodes still as placeholders
        self._held = inner
        self._rendered: str | None = None

    def __repr__(self) -> str:
        return f"<Call {self.name} line {self.line}>"

    @property
    def paired(self) -> bool:
        return self._held is not None

    @property
    def inner(self) -> str | None:
        """What is between the tags; None for a shortcode standing alone.

        HTML for the ``{{% %}}`` form, the text as written for ``{{< >}}``.
        """
        if self._held is None:
            return None
        if self.markdown:
            return self.inner_html
        return self._expansion.substitute(self._held)

    @property
    def inner_html(self) -> str:
        """The inner text rendered as Markdown, whichever form was used."""
        if self._held is None:
            return ""
        if self._rendered is None:
            self._rendered = self._expansion.render(self._held)
        return self._rendered

    @property
    def inner_inline(self) -> str:
        """The inner text as one line of Markdown, without a ``<p>`` around it."""
        if self._held is None:
            return ""
        return self._expansion.render_inline(self._held)

    def get(self, key: str, position: int | None = None, default=None):
        """A named argument, or failing that the positional one at ``position``."""
        if key in self.kwargs:
            return self.kwargs[key]
        if position is not None and position < len(self.args):
            return self.args[position]
        return default

    def require(self, key: str, position: int | None = None) -> str:
        value = self.get(key, position)
        if value is None or value == "":
            raise self.error(f"'{key}' is missing")
        return value

    def flag(self, key: str, default: bool = False) -> bool:
        """``key=true``, or just the bare word ``key``."""
        if key in self.kwargs:
            return self.kwargs[key].strip().lower() in ("", "1", "true", "yes", "on")
        return key in self.args or default

    def render(self, text: str) -> str:
        return self._expansion.render(text)

    def render_inline(self, text: str) -> str:
        return self._expansion.render_inline(text)

    def expand(self, text: str, path: Path, skipped: int = 0) -> str:
        """Expand the shortcodes in text taken from another file.

        ``skipped`` is how many lines of that file come before ``text``.
        """
        return self._expansion.nested(text, path, self, skipped)

    def locate(self, name: str) -> Path | None:
        return self._expansion.locate(name)

    def url_for(self, url: str) -> str:
        return url_for(self.config, url)

    def error(self, message: str) -> ContentError:
        return ContentError(f"shortcode '{self.name}': {message}", line=self.line)


class _Expansion:
    """Expanding the shortcodes of one page."""

    def __init__(self, plugin: Shortcodes, page):
        self.plugin = plugin
        self.page = page
        self.config = plugin.config
        self.site = getattr(page, "site", None) or plugin.site
        self.held: list[_Held] = []
        # files being included, outermost first
        self._files: list[Path] = []

    def expand(self, text: str) -> str:
        return self._join(parse(text))

    def _join(self, nodes: list) -> str:
        return "".join(
            node if isinstance(node, str) else self._run(node) for node in nodes
        )

    def _run(self, node: Shortcode) -> str:
        handler = self.plugin.find(node.name)
        if handler is None:
            if self.plugin.strict:
                raise ContentError(self.plugin.unknown(node.name), line=node.line)
            log.once("unknown shortcode %r left as it is", node.name)
            return node.source
        inner = None if node.inner is None else _trim(self._join(node.inner))
        call = Call(self, node, inner)
        try:
            result = handler.fn(call)
        except ContentError as exc:
            if exc.line is None and exc.path is None:
                exc.line = node.line
            raise
        result = "" if result is None else str(result)
        if handler.text:
            return result
        return self.hold(result, node.source)

    def hold(self, markup: str, source: str) -> str:
        self.held.append(_Held(markup, source, _BLOCK.match(markup) is not None))
        return _placeholder(len(self.held) - 1)

    def substitute(self, text: str) -> str:
        """Placeholders to HTML in text that never went through Markdown."""

        def fill(match: re.Match) -> str:
            found = _item(self.held, match.group(1))
            return match.group() if found is None else found.html

        return _PLACEHOLDER.sub(fill, text)

    def render(self, text: str) -> str:
        # XXX rendered on its own, so link references and footnotes defined
        # elsewhere on the page are not visible in here, and headings inside
        # can repeat an id used outside.
        markup = self.plugin.render_markdown(text, self.page)
        return restore(markup, self.held).strip()

    def render_inline(self, text: str) -> str:
        markup = self.plugin.converter(self.page).convert_inline(text)
        return restore(markup, self.held)

    @property
    def directory(self) -> Path | None:
        """Directory of the file whose text is being expanded right now."""
        if self._files:
            return self._files[-1].parent
        path = source_file(self.page, self.config)
        return Path(path).parent if path is not None else None

    def locate(self, name: str) -> Path | None:
        """Find a file named in a shortcode, without leaving the site."""
        root = lookup(self.config, "root")
        bases = []
        if name.startswith("/"):
            bases.append(root)
        else:
            bases += [self.directory, lookup(self.config, "content_path"), root]
        for base in bases:
            if base is None:
                continue
            path = (Path(base) / name.lstrip("/")).resolve()
            limit = Path(root if root is not None else base).resolve()
            if path.is_file() and (limit == path or limit in path.parents):
                return path
        return None

    def nested(self, text: str, path: Path, call: Call, skipped: int = 0) -> str:
        if path in self._files or path == source_file(self.page, self.config):
            raise call.error(f"{path.name} ends up including itself")
        if len(self._files) >= _MAX_INCLUDES:
            raise call.error(f"more than {_MAX_INCLUDES} levels of nesting")
        self._files.append(path)
        try:
            return self._join(parse(text))
        except ContentError as exc:
            if exc.path is None:
                exc.path = self.plugin.label(path)
                if exc.line is not None:
                    exc.line += skipped
            raise
        finally:
            self._files.pop()


class Shortcodes(Plugin):
    name = "shortcodes"
    # early, in both directions: other plugins should see neither the tags
    # in the Markdown nor the placeholders in the HTML
    priority = 10

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.strict = setting(self, "strict", True)
        self.template_dir = setting(self, "templates", "shortcodes").strip("/")
        self.site = None
        self._builder = None
        self._env = None
        self._markdown = None
        self._local: dict[str, _Handler] = {}
        self._templates: dict[str, _Handler | None] = {}
        self._held: dict[int, list[_Held]] = {}

    def register(self, name: str, fn: Callable, *, text: bool = False) -> None:
        """Add a shortcode for this site only (from another plugin's setup)."""
        if not _NAME.fullmatch(name):
            raise ValueError(f"{name!r} cannot be used as a shortcode name")
        self._local[name] = _Handler(fn, text)

    def setup(self, builder) -> None:
        self._builder = builder
        self._templates.clear()

    def content_loaded(self, site) -> None:
        self.site = site
        # templates may have come or gone since the last build (serve)
        self._templates.clear()
        self._held.clear()
        for page in getattr(site, "all_pages", None) or site.pages:
            raw = _INPUTS_NOTE.sub("", getattr(page, "raw", None) or "")
            if "{{" in raw and getattr(page, "source_path", None):
                stamp = self._inputs(page, raw)
                if stamp:
                    page.raw = f"{raw}\n<!-- shortcodes:{stamp} -->"

    def _inputs(self, page, raw: str) -> str:
        """A hash of what the shortcodes of a page take from outside it.

        The build cache renders a page again when its text has changed. A
        page that includes a file, refers to another page or uses a
        shortcode template depends on more than its own text, and nobody
        would think of touching the page after editing the template. So the
        state of those things is noted at the end of the text, where the
        cache sees it; page_markdown() takes the note off again.
        """
        try:
            todo = parse(raw)
        except ContentError:
            # rendering will say what is wrong, and with the file name
            return ""
        expansion = _Expansion(self, page)
        found = []
        while todo:
            node = todo.pop()
            if isinstance(node, str):
                continue
            todo.extend(node.inner or ())
            handler = self.find(node.name)
            if handler is None:
                continue
            first = node.args[0] if node.args else ""
            if handler.stamp:
                found.append(f"template {node.name} {handler.stamp}")
            elif handler.fn is include:
                # XXX one level only: what an included file includes in
                # turn is not followed
                name = node.kwargs.get("file", first)
                path = expansion.locate(name) if name else None
                try:
                    digest = fs.file_hash(path) if path is not None else "missing"
                except OSError:
                    digest = "unreadable"
                found.append(f"include {name} {digest}")
            elif handler.fn is ref:
                target = node.kwargs.get("path", first).partition("#")[0]
                other = _find_page(expansion.site, page, target) if target else None
                url = other.url if other is not None else "missing"
                found.append(f"ref {target} {url}")
        return hash_text("\n".join(sorted(found)))[:12] if found else ""

    def page_markdown(self, page, text):
        text = _INPUTS_NOTE.sub("", text)
        if "{{" not in text:
            return text
        expansion = _Expansion(self, page)
        try:
            out = expansion.expand(text)
        except ContentError as exc:
            if exc.path is None:
                exc.path = display_path(page, self.config)
                if exc.line is not None:
                    exc.line += _line_offset(page, text, self.config)
            raise
        if expansion.held:
            self._held[id(page)] = expansion.held
        return out

    def page_html(self, page, html):
        held = self._held.pop(id(page), None)
        if not held:
            return html
        _clean_toc(page, held)
        return restore(str(html), held)

    def find(self, name: str) -> _Handler | None:
        template = self._template(name)
        if template is not None:
            return template
        return self._local.get(name) or _registry.get(name)

    def names(self) -> list[str]:
        found = set(_registry) | set(self._local)
        env = self._environment()
        if env is not None:
            prefix = self.template_dir + "/"
            for name in env.list_templates():
                if name.startswith(prefix) and name.endswith(".html"):
                    found.add(name[len(prefix) : -len(".html")])
        return sorted(found)

    def unknown(self, name: str) -> str:
        message = f"unknown shortcode '{name}'"
        close = difflib.get_close_matches(name, self.names(), n=1)
        if close:
            message += f", did you mean '{close[0]}'?"
        return message

    def label(self, path: Path) -> str:
        root = lookup(self.config, "root")
        if root is not None:
            try:
                return Path(path).relative_to(root).as_posix()
            except ValueError:
                pass
        return str(path)

    def converter(self, page):
        """The Markdown converter of the site; a plain one outside a build."""
        if self._builder is not None:
            return self._builder.markdown_for(page)
        if self._markdown is None:
            from ...markdown import Markdown

            options = lookup(self.config, "markdown") or {}
            self._markdown = Markdown(
                extensions=lookup(options, "extensions") or None,
                smart=bool(lookup(options, "smart", True)),
                heading_ids=bool(lookup(options, "heading_ids", True)),
                hard_wraps=bool(lookup(options, "hard_wraps", False)),
            )
        return self._markdown

    def render_markdown(self, text: str, page) -> str:
        if self._builder is not None:
            # also fixes up links to other .md files
            return str(self._builder.render_markdown(text, page))
        return self.converter(page).convert(text)

    def _environment(self):
        if self._builder is not None:
            return self._builder.env
        if self._env is None:
            directory = lookup(self.config, "templates_path")
            if directory is None:
                return None
            self._env = Environment(
                loader=FileSystemLoader([str(directory)]),
                autoescape=select_autoescape(),
            )
        return self._env

    def _template(self, name: str) -> _Handler | None:
        try:
            return self._templates[name]
        except KeyError:
            pass
        handler = None
        env = self._environment()
        if env is not None:
            try:
                template = env.get_template(f"{self.template_dir}/{name}.html")
            except TemplateNotFound:
                pass
            else:
                stamp = _template_stamp(env, template)
                handler = _Handler(_from_template(template), stamp=stamp)
        self._templates[name] = handler
        return handler


def _template_stamp(env, template) -> str:
    """Hash of a template's source and of everything it pulls in."""
    sources = []
    for name in sorted({template.name, *template.all_dependencies()}):
        try:
            sources.append(env.loader.get_source(name)[0])
        except TemplateNotFound:
            sources.append("")
    return hash_text("\0".join(sources))


def _from_template(template) -> Callable:
    def render(call: Call) -> str:
        inner = call.inner
        try:
            return template.render(
                name=call.name,
                args=call.args,
                kwargs=call.kwargs,
                inner=Markup(inner if inner is not None else ""),
                page=call.page,
                site=call.site,
                config=call.config,
            )
        except TemplateError as exc:
            raise call.error(f"template failed: {exc}") from exc

    return render


def _line_offset(page, body: str, config) -> int:
    """How many lines of the source file come before the Markdown body."""
    path = source_file(page, config)
    if path is None:
        return 0
    try:
        full = fs.read_text(path)
    except (OSError, InkstoneError):
        return 0
    full, body = full.rstrip(), body.rstrip()
    if not full.endswith(body):
        # another plugin rewrote the text; lines within the body will do
        return 0
    return full.count("\n") - body.count("\n")


def _clean_toc(page, held: list[_Held]) -> None:
    """Take placeholders out of a table of contents made before we ran."""

    def text(match: re.Match) -> str:
        found = _item(held, match.group(1))
        return match.group() if found is None else _html.text_content(found.html)

    toc_html = getattr(page, "toc_html", "")
    if toc_html and _START in toc_html:
        cleaned = _PLACEHOLDER.sub(lambda m: _html.escape(text(m)), str(toc_html))
        page.toc_html = Markup(cleaned)
    todo = list(getattr(page, "toc", None) or ())
    while todo:
        entry = todo.pop()
        if _START in entry.title:
            entry.title = _PLACEHOLDER.sub(text, entry.title)
        todo.extend(entry.children)


def _attributes(pairs) -> str:
    out = []
    for name, value in pairs:
        if value is None or value is False:
            continue
        out.append(f" {name}" if value is True else f' {name}="{_html.escape(value)}"')
    return "".join(out)


def _local_url(call: Call, src: str) -> str:
    """Resolve an image or link target the way the page itself would see it."""
    if paths.is_external(src) or src.startswith("#"):
        return src
    if src.startswith("/"):
        return call.url_for(src)
    for resource in getattr(call.page, "resources", None) or ():
        if resource.name == src:
            return call.url_for(resource.url)
    return src


@register("figure")
def figure(call: Call) -> str:
    attrs = [
        ("src", _local_url(call, call.require("src", 0))),
        ("alt", call.get("alt", 1, "")),
        ("width", call.get("width")),
        ("height", call.get("height")),
        ("loading", call.get("loading", default="lazy")),
    ]
    image = f"<img{_attributes(attrs)}>"
    link = call.get("link")
    if link:
        image = f'<a href="{_html.escape(_local_url(call, link))}">{image}</a>'
    caption = call.get("caption", 2)
    if caption:
        caption = call.render_inline(caption)
    elif call.paired:
        caption = call.inner_inline
    out = ["<figure" + _attributes([("class", call.get("class"))]) + ">", image]
    if caption:
        out.append(f"<figcaption>{caption}</figcaption>")
    out.append("</figure>")
    return "\n".join(out)


_NOTE_TYPES = {
    "info": "info",
    "note": "info",
    "warning": "warning",
    "caution": "warning",
    "tip": "tip",
    "hint": "tip",
}


@register("note")
def note(call: Call) -> str:
    kind = call.get("type", 0, "info").lower()
    if kind not in _NOTE_TYPES:
        raise call.error(f"unknown type '{kind}' (use info, warning or tip)")
    if not call.paired:
        raise call.error("needs a body; close it with {{< /note >}}")
    kind = _NOTE_TYPES[kind]
    classes = f"note note--{kind}"
    if kind != "info":
        # the default theme colours these through its admonition rules
        classes += f" admonition {kind}"
    out = [f'<div class="{classes}" role="note">']
    title = call.get("title")
    if title:
        out.append(f'<p class="note__title">{call.render_inline(title)}</p>')
    out.append(call.inner_html)
    out.append("</div>")
    return "\n".join(out)


@register("details")
def details(call: Call) -> str:
    if not call.paired:
        raise call.error("needs a body; close it with {{< /details >}}")
    summary = call.render_inline(call.get("summary", 0, "Details"))
    opening = "<details open>" if call.flag("open") else "<details>"
    return f"{opening}\n<summary>{summary}</summary>\n{call.inner_html}\n</details>"


_YOUTUBE_ID = re.compile(r"[A-Za-z0-9_-]{6,}")
_YOUTUBE_URL = re.compile(
    r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/"
    r"(?:watch\?(?:[^#\s]*&)?v=|embed/|shorts/|live/))([A-Za-z0-9_-]{6,})"
)


@register("youtube")
def youtube(call: Call) -> str:
    video = call.require("id", 0)
    pasted = _YOUTUBE_URL.search(video)
    if pasted is not None:
        video = pasted.group(1)
    elif not _YOUTUBE_ID.fullmatch(video):
        raise call.error(f"'{video}' does not look like a video id")
    # the nocookie host does not set cookies until the visitor presses play
    src = f"https://www.youtube-nocookie.com/embed/{video}"
    start = call.get("start")
    if start:
        if not start.isdigit():
            raise call.error(f"start must be a number of seconds, got '{start}'")
        src += f"?start={start}"
    attrs = [
        ("src", src),
        ("title", call.get("title", 1, "YouTube video")),
        ("loading", "lazy"),
        ("allow", "accelerometer; encrypted-media; gyroscope; picture-in-picture"),
        ("referrerpolicy", "strict-origin-when-cross-origin"),
        ("allowfullscreen", True),
    ]
    return f'<div class="video">\n<iframe{_attributes(attrs)}></iframe>\n</div>'


@register("button")
def button(call: Call) -> str:
    href = call.get("href", 0) or call.get("url")
    if not href:
        raise call.error("'href' is missing")
    if call.paired:
        label = call.inner_inline
    else:
        label = call.render_inline(call.get("text", 1, href))
    classes = ["button"]
    style = call.get("style")
    if style:
        classes.append(f"button--{style}")
    classes += (call.get("class") or "").split()
    new_tab = call.flag("new_tab")
    attrs = [
        ("class", " ".join(classes)),
        ("href", _local_url(call, href)),
        ("target", "_blank" if new_tab else None),
        ("rel", "noopener" if new_tab else None),
    ]
    return f"<a{_attributes(attrs)}>{label}</a>"


def _keys(text: str) -> list[str]:
    """Split "Ctrl+Shift+P"; a doubled or trailing plus is the plus key."""
    keys = []
    parts = text.split("+")
    index = 0
    while index < len(parts):
        part = parts[index].strip()
        if part:
            keys.append(part)
            index += 1
        else:
            if len(parts) > 1:
                keys.append("+")
            index += 2
    return keys


@register("kbd")
def kbd(call: Call) -> str:
    keys: list[str] = []
    for arg in call.args:
        keys += _keys(arg)
    if not keys and call.paired:
        keys = _keys(call.inner or "")
    if not keys:
        raise call.error("no keys given")
    separator = _html.escape(call.get("sep", default="+"))
    return separator.join(f"<kbd>{_html.escape(key)}</kbd>" for key in keys)


@register("ref", text=True)
def ref(call: Call) -> str:
    """URL of another page, given its path below the content directory."""
    target = call.require("path", 0)
    path, hash_, fragment = target.partition("#")
    if call.site is None and path:
        raise call.error("there is no site to look pages up in")
    page = call.page if not path else _find_page(call.site, call.page, path)
    if page is None:
        raise call.error(f"no page found for '{path}'")
    if call.flag("absolute"):
        url = page.permalink
    else:
        url = call.url_for(page.url)
    return url + hash_ + fragment


def _find_page(site, page, path: str):
    """The page a path names, as seen from ``page``; None if there is none."""
    if site is None:
        return None
    candidates = [path]
    source = getattr(page, "source_path", None)
    if source and not path.startswith("/"):
        # relative to the page that uses it comes first
        here = posixpath.dirname(source)
        candidates.insert(0, posixpath.normpath(posixpath.join(here, path)))
    for candidate in candidates:
        if candidate.startswith(".."):
            continue
        found = site.get_page(candidate)
        if found is not None:
            return found
    return None


def _line_range(call: Call, spec: str, count: int) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d*)\s*(-?)\s*(\d*)\s*", spec)
    if match is None or not (match.group(1) or match.group(3)):
        raise call.error(f"cannot read lines='{spec}' (use 5-12, 5- or -12)")
    first = int(match.group(1) or 1)
    if match.group(2):
        last = int(match.group(3) or count)
    else:
        last = first
    if first < 1 or last < first:
        raise call.error(f"lines='{spec}' is not a range")
    return first, min(last, count)


@register("include", text=True)
def include(call: Call) -> str:
    """The content of another file, as if it had been typed here.

    Markdown files lose their front matter and have their own shortcodes
    expanded. ``code=LANG`` (or just ``code``) wraps the file in a fence.
    """
    name = call.require("file", 0)
    path = call.locate(name)
    if path is None:
        raise call.error(f"cannot find '{name}'")
    try:
        text = fs.read_text(path)
    except OSError as exc:
        raise call.error(f"cannot read '{name}': {exc.strerror or exc}") from None
    is_markdown = path.suffix.lower() in _MARKDOWN_SUFFIXES
    code = call.get("code")
    if code is None and "code" in call.args:
        code = path.suffix.lstrip(".")
    # lines of the file that come before what is used, for error messages
    skipped = 0
    if is_markdown and code is None:
        try:
            body = frontmatter.split(text)[1]
        except ContentError as exc:
            raise call.error(f"'{name}': {exc.message}") from None
        skipped = text.count("\n") - body.count("\n")
        text = body
    lines = call.get("lines")
    if lines:
        rows = text.split("\n")
        first, last = _line_range(call, lines, len(rows))
        text = "\n".join(rows[first - 1 : last])
        skipped += first - 1
    if code is not None:
        longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
        fence = "`" * max(3, longest + 1)
        return f"{fence}{code}\n{text.rstrip()}\n{fence}"
    if is_markdown:
        return call.expand(text, path, skipped).strip("\n")
    return text.strip("\n")
