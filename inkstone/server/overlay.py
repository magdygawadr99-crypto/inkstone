from __future__ import annotations

import html
import re
import traceback

from inkstone.errors import InkstoneError

_CONTEXT_LINES = 3
_MAX_LINE_LENGTH = 240

# Shared by the overlay and the standalone page. The overlay lives in a
# shadow root, so none of this can collide with (or be restyled by) the
# site's own CSS; the ink- prefix is for browsers without shadow DOM.
_PANEL_CSS = """
.ink-panel {
  box-sizing: border-box;
  width: 100%;
  max-width: 62rem;
  margin: 0 auto;
  background: #1c1e26;
  color: #e4e4e7;
  border-top: 4px solid #e5484d;
  border-radius: 6px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  text-align: left;
}
.ink-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 1.25rem;
  border-bottom: 1px solid #2e313d;
}
.ink-badge {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #9a9cab;
}
.ink-title {
  flex: 1;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #ff8589;
}
.ink-dismiss {
  border: 0;
  background: none;
  color: #9a9cab;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.25rem;
}
.ink-dismiss:hover {
  color: #fff;
}
.ink-detail {
  margin: 0;
  padding: 1rem 1.25rem;
  overflow: auto;
  max-height: 65vh;
  font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre;
  tab-size: 4;
}
.ink-hit {
  background: rgba(229, 72, 77, 0.22);
  color: #fff;
}
.ink-dim {
  color: #8b8d9b;
}
.ink-foot {
  margin: 0;
  padding: 0.7rem 1.25rem;
  border-top: 1px solid #2e313d;
  color: #9a9cab;
  font-size: 12px;
}
"""

_OVERLAY_CSS = """
.ink-backdrop {
  position: fixed;
  inset: 0;
  box-sizing: border-box;
  padding: 6vh 1.5rem;
  overflow: auto;
  background: rgba(10, 11, 15, 0.72);
}
"""

_PAGE_CSS = """
html {
  background: #101116;
}
body {
  margin: 0;
  padding: 8vh 1.5rem;
}
"""

_MARKED_LINE = re.compile(r"> +\d+ \|")


def describe_error(exc: BaseException) -> tuple[str, str]:
    """Title and plain-text detail for a failed build.

    Errors inkstone raises on purpose get their message and, when they point
    at a line in a source file, a few lines around it. Anything else is a
    bug somewhere (ours or a plugin's), so it gets the whole traceback.
    """
    if isinstance(exc, InkstoneError):
        parts = [str(exc) or type(exc).__name__]
        excerpt = source_excerpt(exc.path, exc.line)
        if excerpt:
            parts.append(excerpt)
        cause = exc.__cause__
        if cause is not None:
            parts.append(f"Caused by {type(cause).__name__}: {cause}")
        return "Build failed", "\n\n".join(parts)

    name = type(exc).__name__
    message = str(exc)
    parts = [f"{name}: {message}" if message else name]
    if isinstance(exc, SyntaxError):
        excerpt = source_excerpt(exc.filename, exc.lineno)
        if excerpt:
            parts.append(excerpt)
    trace = traceback.format_exception(type(exc), exc, exc.__traceback__)
    parts.append("".join(trace).rstrip())
    return f"Build failed: {name}", "\n\n".join(parts)


def source_excerpt(path, line: int | None, context: int = _CONTEXT_LINES) -> str:
    """A few numbered lines around ``line``, the guilty one marked with ``>``.

    Empty when there's nothing useful to show: no location, an unreadable
    file, or a line number past the end of it.
    """
    if path is None or not isinstance(line, int) or line < 1:
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return ""
    if line > len(lines):
        return ""
    first = max(line - context, 1)
    last = min(line + context, len(lines))
    width = len(str(last))
    out = []
    for number in range(first, last + 1):
        text = lines[number - 1].expandtabs(4)
        if len(text) > _MAX_LINE_LENGTH:
            text = text[: _MAX_LINE_LENGTH - 3] + "..."
        marker = ">" if number == line else " "
        out.append(f"{marker} {number:>{width}} | {text}".rstrip())
    return "\n".join(out)


def render_overlay(title: str, detail: str = "") -> str:
    """HTML fragment for the in-page overlay.

    The live-reload client drops this into a shadow root; anything carrying
    ``data-inkstone-dismiss`` closes the overlay when clicked.
    """
    button = (
        '<button class="ink-dismiss" type="button" data-inkstone-dismiss'
        ' title="Dismiss (Esc)" aria-label="Dismiss">&times;</button>'
    )
    return (
        f"<style>{_PANEL_CSS}{_OVERLAY_CSS}</style>\n"
        '<div class="ink-backdrop" role="alertdialog" aria-label="Build error">\n'
        f"{_panel(title, detail, button)}"
        "</div>\n"
    )


def render_error_page(title: str, detail: str = "") -> str:
    """A complete page showing the error, for when there's no page to overlay.

    The ``data-inkstone-error`` attribute tells the live-reload client that
    it is looking at this page, so it reloads on the next successful build
    instead of drawing an overlay on top of the same message.
    """
    return (
        "<!doctype html>\n"
        '<html lang="en" data-inkstone-error>\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{_PANEL_CSS}{_PAGE_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{_panel(title, detail)}"
        "</body>\n"
        "</html>\n"
    )


def _panel(title: str, detail: str, button: str = "") -> str:
    return (
        '<div class="ink-panel">\n'
        '<div class="ink-head">'
        '<span class="ink-badge">inkstone</span>'
        f'<h1 class="ink-title">{html.escape(title)}</h1>'
        f"{button}"
        "</div>\n"
        f'<pre class="ink-detail">{_detail_html(detail)}</pre>\n'
        '<p class="ink-foot">Fix the problem and save again;'
        " this goes away once the site builds.</p>\n"
        "</div>\n"
    )


def _detail_html(detail: str) -> str:
    out = []
    for line in detail.splitlines():
        escaped = html.escape(line)
        if _MARKED_LINE.match(line):
            escaped = f'<span class="ink-hit">{escaped}</span>'
        elif line.startswith(("Traceback ", "  File ")):
            escaped = f'<span class="ink-dim">{escaped}</span>'
        out.append(escaped)
    return "\n".join(out)
