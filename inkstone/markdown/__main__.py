from __future__ import annotations

import argparse
import sys

from .core import Markdown
from .errors import MarkdownError
from .nodes import dump
from .text import plain_text


def main(argv: list[str] | None = None) -> int:
    """``python -m inkstone.markdown``: convert a file without the rest of inkstone."""
    parser = argparse.ArgumentParser(
        prog="python -m inkstone.markdown",
        description="Convert Markdown to HTML and print it.",
    )
    parser.add_argument("file", nargs="?", help="source file (default: stdin)")
    parser.add_argument("-x", "--extensions", help="comma separated extension names")
    parser.add_argument("--smart", action="store_true", help="smart punctuation")
    parser.add_argument("--safe", action="store_true", help="escape raw HTML")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--ast", action="store_true", help="print the tree instead")
    output.add_argument("--text", action="store_true", help="print plain text instead")
    args = parser.parse_args(argv)

    extensions = None
    if args.extensions is not None:
        extensions = [name for name in args.extensions.split(",") if name]
    try:
        md = Markdown(extensions=extensions, smart=args.smart, safe=args.safe)
        if args.file:
            with open(args.file, encoding="utf-8-sig") as f:
                source = f.read()
        else:
            # not sys.stdin.read(): on Windows that decodes with the ANSI
            # code page, which is never what a piped Markdown file is in
            source = sys.stdin.buffer.read().decode("utf-8-sig")
        doc = md.parse(source)
        if args.ast:
            result = dump(doc) + "\n"
        elif args.text:
            result = plain_text(doc) + "\n"
        else:
            result = md.render(doc)
    except (MarkdownError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
