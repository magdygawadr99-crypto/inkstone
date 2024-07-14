from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from ..config import CONFIG_NAMES, load_config
from ..errors import ConfigError, InkstoneError
from ..utils import log, term
from .parser import build_parser

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

_UNICODE = ("utf-8", "utf8", "utf-16", "utf-16-le", "utf-32")


class NoSiteError(ConfigError):
    """There is no site where the command was run."""


def find_site_root(start=None) -> Path | None:
    """The closest directory at or above ``start`` that has a config file."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in (here, *here.parents):
        if any((candidate / name).is_file() for name in CONFIG_NAMES):
            return candidate
    return None


class App:
    """What a command gets to work with: the options and the site they select."""

    def __init__(self, args):
        self.args = args
        self._root: Path | None = None

    @property
    def root(self) -> Path:
        if self._root is None:
            self._root = self._find_root()
        return self._root

    def _find_root(self) -> Path:
        args = self.args
        if args.root:
            root = Path(args.root)
            if not root.is_dir():
                raise NoSiteError(f"{args.root}: no such directory")
            has_config = any((root / name).is_file() for name in CONFIG_NAMES)
            if not has_config and not args.config:
                raise NoSiteError(
                    f"{args.root} is not an inkstone site (no {CONFIG_NAMES[0]} in it)"
                )
            return root.resolve()
        root = find_site_root()
        if root is not None:
            return root
        if args.config:
            # no site around, but we were told which file describes one
            return Path(args.config).resolve().parent
        raise NoSiteError(
            f"no inkstone site here: there is no {CONFIG_NAMES[0]} in "
            f"{Path.cwd()} or any directory above it.\n"
            "Run 'inkstone new site NAME' to make one, or point at one with -C DIR."
        )

    def in_site(self) -> bool:
        try:
            self.root
        except NoSiteError:
            return False
        return True

    def config(self, overrides: dict | None = None):
        """Load the site's configuration with command line ``overrides`` on top."""
        path = self.args.config
        if path is not None:
            # relative to where the command was typed; failing that, to the
            # site, so `-C site -c production.toml` works from anywhere
            path = Path(path)
            if not path.is_file() and (self.root / path).is_file():
                path = self.root / path
            path = path.resolve()
        overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
        return load_config(self.root, path=path, overrides=overrides)

    def out(self, text: str = "") -> None:
        """Print a command's actual output; the chatter goes through log."""
        sys.stdout.write(text + "\n")

    def say(self, text: str = "") -> None:
        """Like out(), but silent with --quiet."""
        if not self.args.quiet:
            self.out(text)

    def shown(self, path) -> str:
        """A path the way the user would type it from where they are."""
        path = Path(path).resolve()
        try:
            return str(path.relative_to(Path.cwd().resolve()))
        except ValueError:
            # not below the working directory: ../../.. helps nobody
            return str(path)


def setup_output(args) -> None:
    # Redirected output on Windows is in a legacy code page. A title in a
    # script that page lacks should come out mangled, not end the run.
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if encoding and encoding not in _UNICODE and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    log.reset()
    if args.debug:
        log.set_level(log.DEBUG)
    elif args.verbose:
        log.set_level(log.VERBOSE)
    elif args.quiet:
        log.set_level(log.QUIET)
    else:
        log.set_level(log.NORMAL)
    term.set_color(False if args.no_color else None)


def main(argv=None) -> int:
    """Run the command line; returns the exit status instead of exiting."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse exits by itself for --help, --version and usage errors
        if exc.code is None:
            return EXIT_OK
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    if not getattr(args, "run", None):
        parser.print_help(sys.stderr)
        return EXIT_USAGE

    setup_output(args)
    app = App(args)
    try:
        return args.run(app, args) or EXIT_OK
    except InkstoneError as exc:
        if args.debug:
            traceback.print_exc()
        log.error("%s", exc)
        return EXIT_ERROR
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        # `inkstone list | head`: the reader went away, nothing to report
        try:
            sys.stdout.close()
        except OSError:
            pass
        return EXIT_ERROR
    except Exception as exc:
        if args.debug:
            traceback.print_exc()
        log.error(
            "%s: %s (this is a bug; --debug shows where)", type(exc).__name__, exc
        )
        return EXIT_ERROR
