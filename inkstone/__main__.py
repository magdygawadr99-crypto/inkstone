import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .errors import InkstoneError
from .site import build


def main(argv=None):
    parser = argparse.ArgumentParser(prog="inkstone")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("build", help="build the site")
    p.add_argument("source", nargs="?", default=".")
    p.add_argument("-o", "--output", help="output directory (default: SOURCE/public)")
    p.add_argument("--drafts", action="store_true", help="include drafts")
    args = parser.parse_args(argv)

    if args.command != "build":
        parser.print_help()
        return 2

    src = Path(args.source)
    out = Path(args.output) if args.output else src / "public"
    started = time.perf_counter()
    try:
        count = build(src, out, drafts=args.drafts)
    except InkstoneError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{count} pages in {time.perf_counter() - started:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
