from __future__ import annotations

import argparse
import difflib
import re
import sys

from .. import __version__

_INVALID_CHOICE = re.compile(r"invalid choice: '([^']*)'")


class Parser(argparse.ArgumentParser):
    """argparse, with errors that are one line and a guess at what was meant."""

    def error(self, message: str):
        match = _INVALID_CHOICE.search(message)
        choices = self._command_names()
        if match and choices:
            word = match.group(1)
            message = f"'{word}' is not a command"
            close = difflib.get_close_matches(word, choices, n=1)
            if close:
                message += f", did you mean '{close[0]}'?"
        sys.stderr.write(f"{self.prog}: {message}\n")
        sys.stderr.write(f"Try '{self.prog} --help' for more information.\n")
        raise SystemExit(2)

    def _command_names(self) -> list[str]:
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                return list(action.choices)
        return []


def global_options(defaults: bool) -> argparse.ArgumentParser:
    """The options every command takes.

    They are accepted before and after the command name. The second copy
    must not have defaults, or it would wipe out what the first one parsed.
    """

    def default(value):
        return value if defaults else argparse.SUPPRESS

    parent = argparse.ArgumentParser(add_help=False)
    group = parent.add_argument_group("global options")
    group.add_argument(
        "-C",
        "--root",
        metavar="DIR",
        default=default(None),
        help="site directory (default: found by walking up from here)",
    )
    group.add_argument(
        "-c",
        "--config",
        metavar="FILE",
        default=default(None),
        help="config file to use instead of inkstone.toml",
    )
    group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=default(False),
        help="only print warnings and errors",
    )
    group.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=default(False),
        help="say what is being done",
    )
    group.add_argument(
        "--debug",
        action="store_true",
        default=default(False),
        help="show tracebacks and debug output",
    )
    group.add_argument(
        "--no-color",
        action="store_true",
        default=default(False),
        help="plain output, also when writing to a terminal",
    )
    return parent


def build_parser() -> Parser:
    # imported here so that `import inkstone.cli.parser` stays cheap
    from . import (
        build,
        clean,
        serve,
        version,
    )

    parser = Parser(
        prog="inkstone",
        description="A small static site generator.",
        parents=[global_options(defaults=True)],
        epilog="Run 'inkstone COMMAND --help' for the options of a command.",
    )
    parser.add_argument(
        "--version", action="version", version=f"inkstone {__version__}"
    )
    commands = parser.add_subparsers(
        title="commands", dest="command", metavar="COMMAND", parser_class=Parser
    )
    shared = global_options(defaults=False)
    # the order they are listed in by --help
    for module in (
        build,
        serve,
        clean,
        version,
    ):
        module.add_parser(commands, shared)
    return parser
