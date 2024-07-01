from __future__ import annotations

import os
import re
import sys
import unicodedata
from typing import Iterable, Sequence

_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}
# CSI sequences (colours, cursor movement) and OSC ones (hyperlinks, titles)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")

_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

_vt_mode: bool | None = None
_forced: bool | None = None


def enable_vt_mode() -> bool:
    """Make the Windows console interpret ANSI escapes.

    Returns whether escapes can be expected to work. Does nothing (and says
    yes) on other systems; the result is cached either way.
    """
    global _vt_mode
    if _vt_mode is None:
        _vt_mode = _enable_windows_vt() if os.name == "nt" else True
    return _vt_mode


def _enable_windows_vt() -> bool:
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        enabled = False
        for std_handle in (-11, -12):  # stdout, stderr
            handle = ctypes.c_void_p(kernel32.GetStdHandle(std_handle))
            mode = ctypes.c_uint32()
            # fails for handles that are not consoles (pipes, files)
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            wanted = mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
            if kernel32.SetConsoleMode(handle, ctypes.c_uint32(wanted)):
                enabled = True
        return enabled
    except (AttributeError, OSError, ImportError):
        return False


def set_color(enabled: bool | None) -> None:
    """Force colours on or off (the --color/--no-color flags); None = auto."""
    global _forced
    _forced = enabled


def supports_color(stream=None) -> bool:
    """Should ANSI colours be written to ``stream`` (stdout by default)?

    An explicit set_color() wins, then NO_COLOR, then FORCE_COLOR, and
    otherwise it depends on whether the stream is a terminal.
    """
    if _forced is not None:
        return _forced
    if os.environ.get("NO_COLOR"):
        return False
    force = os.environ.get("FORCE_COLOR")
    if force:
        return force.lower() not in ("0", "false", "no")
    if stream is None:
        stream = sys.stdout
    try:
        if not stream.isatty():
            return False
    except (AttributeError, ValueError):
        # no isatty at all, or a closed file
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return enable_vt_mode()


def _color_code(name: str) -> int:
    key = name.lower().replace("-", "_")
    if key in ("gray", "grey"):
        key = "bright_black"
    bright = key.startswith("bright_")
    base = _COLORS.get(key[7:] if bright else key)
    if base is None:
        raise ValueError(f"unknown colour: {name!r}")
    return base + 60 if bright else base


def style(
    text: str,
    fg: str | None = None,
    bg: str | None = None,
    *,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    enabled: bool | None = None,
) -> str:
    """Wrap ``text`` in ANSI codes, or return it untouched if colour is off.

    ``enabled=None`` asks supports_color() about stdout; pass a bool when
    writing somewhere else.
    """
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    if underline:
        codes.append("4")
    if fg:
        codes.append(str(_color_code(fg)))
    if bg:
        codes.append(str(_color_code(bg) + 10))
    if enabled is None:
        enabled = supports_color()
    if not codes or not enabled or not text:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def visible_len(text: str) -> int:
    """Width of ``text`` in terminal cells, escape sequences not counted."""
    width = 0
    for char in strip_ansi(text):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def _pad(text: str, width: int, align: str) -> str:
    gap = max(width - visible_len(text), 0)
    if align == "r":
        return " " * gap + text
    if align == "c":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


def format_table(
    rows: Iterable[Sequence],
    *,
    headers: Sequence | None = None,
    align: str = "",
    padding: int = 2,
) -> str:
    """Lay out rows in aligned columns.

    ``align`` holds one letter per column (l, r or c); columns it does not
    cover are left-aligned. Cells may contain colour codes.
    """
    table = [[str(cell) for cell in row] for row in rows]
    head = [str(cell) for cell in headers] if headers else []
    columns = max((len(row) for row in [head, *table]), default=0)
    widths = [0] * columns
    for row in [head, *table]:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], visible_len(cell))
    aligns = (align.lower() + "l" * columns)[:columns]
    gap = " " * padding

    def render(row: list[str]) -> str:
        row = row + [""] * (columns - len(row))
        cells = [_pad(cell, widths[i], aligns[i]) for i, cell in enumerate(row)]
        return gap.join(cells).rstrip()

    lines = []
    if head:
        lines.append(render(head))
        lines.append(gap.join("-" * width for width in widths))
    lines.extend(render(row) for row in table)
    return "\n".join(lines)
