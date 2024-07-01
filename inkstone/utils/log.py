"""A very small logger for the command line.

Everything goes to stderr so that stdout stays usable for real output.
Used through the module-level functions:

    from inkstone.utils import log

    log.info("building %d pages", count)
    log.once("template %r uses the deprecated 'page.url_path'", name)
"""

from __future__ import annotations

import sys

from . import term

QUIET = 0
NORMAL = 1
VERBOSE = 2
DEBUG = 3

_LEVELS = {"quiet": QUIET, "normal": NORMAL, "verbose": VERBOSE, "debug": DEBUG}


def _level(value) -> int:
    if isinstance(value, str):
        try:
            return _LEVELS[value.lower()]
        except KeyError:
            raise ValueError(f"unknown log level: {value!r}") from None
    return max(QUIET, min(int(value), DEBUG))


class Logger:
    def __init__(self, level=NORMAL, stream=None):
        self.level = _level(level)
        self._stream = stream
        self.warnings = 0
        self.errors = 0
        self._seen: set = set()

    @property
    def stream(self):
        # Looked up on every write rather than captured once: pytest's
        # capsys (and anything else that swaps sys.stderr) keeps working.
        return self._stream if self._stream is not None else sys.stderr

    @stream.setter
    def stream(self, stream) -> None:
        self._stream = stream

    def set_level(self, level) -> None:
        self.level = _level(level)

    def error(self, message, *args) -> None:
        self.errors += 1
        self._write(message, args, "error", fg="red", bold=True)

    def warning(self, message, *args) -> None:
        # shown even in quiet mode; quiet only silences the chatter
        self.warnings += 1
        self._write(message, args, "warning", fg="yellow")

    def info(self, message, *args) -> None:
        if self.level >= NORMAL:
            self._write(message, args)

    def verbose(self, message, *args) -> None:
        if self.level >= VERBOSE:
            self._write(message, args)

    def debug(self, message, *args) -> None:
        if self.level >= DEBUG:
            self._write(message, args, "debug", fg="bright_black")

    def once(self, message, *args, key=None) -> bool:
        """Warn, but only the first time this message (or ``key``) comes up.

        Returns whether the warning was shown. Repeats are not counted.
        """
        text = _format(message, args)
        if key is None:
            key = text
        if key in self._seen:
            return False
        self._seen.add(key)
        self.warning(text)
        return True

    def reset(self) -> None:
        """Forget the counters and what once() has already seen."""
        self.warnings = 0
        self.errors = 0
        self._seen.clear()

    def _write(self, message, args, prefix: str = "", **look) -> None:
        text = _format(message, args)
        stream = self.stream
        if prefix:
            colour = term.supports_color(stream)
            text = term.style(prefix + ":", enabled=colour, **look) + " " + text
        stream.write(text + "\n")
        stream.flush()


def _format(message, args) -> str:
    text = str(message)
    # only interpolate when there is something to put in, so a stray "%"
    # in a plain message is harmless
    return text % args if args else text


_default = Logger()

error = _default.error
warning = _default.warning
info = _default.info
verbose = _default.verbose
debug = _default.debug
once = _default.once
reset = _default.reset
set_level = _default.set_level


def get_level() -> int:
    return _default.level


def set_stream(stream) -> None:
    """Send output somewhere else; None goes back to stderr."""
    _default.stream = stream


def warning_count() -> int:
    return _default.warnings


def error_count() -> int:
    return _default.errors
