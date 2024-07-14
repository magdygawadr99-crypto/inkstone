from __future__ import annotations

import platform
import sys
from pathlib import Path

from .. import __version__


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "version",
        parents=[shared],
        help="print the version",
        description="Print the version; with -v also where it runs.",
    )
    parser.set_defaults(run=run)


def run(app, args) -> int:
    app.out(f"inkstone {__version__}")
    if args.verbose:
        app.out(f"python {platform.python_version()} ({sys.executable})")
        app.out(f"platform {platform.platform()}")
        app.out(f"installed in {Path(__file__).resolve().parent.parent}")
    return 0
