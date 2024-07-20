from __future__ import annotations

from pathlib import Path

from ..utils import term
from ..utils.text import humanize_duration


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "build",
        parents=[shared],
        help="build the site",
        description="Build the site into the output directory (public/ by default).",
    )
    add_content_options(parser)
    parser.add_argument("--output", metavar="DIR", help="write the site to DIR")
    parser.add_argument("--base-url", metavar="URL", help="override base_url")
    parser.add_argument(
        "--clean", action="store_true", help="delete output and cache first"
    )
    parser.add_argument(
        "--no-incremental",
        action="store_true",
        help="render every page, whatever the cache says",
    )
    parser.add_argument("--minify", action="store_true", help="minify HTML, CSS and JS")
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        help="put a content hash into the names of static files",
    )
    parser.add_argument(
        "--profile", action="store_true", help="show how long each phase took"
    )
    parser.set_defaults(run=run)


def add_content_options(parser) -> None:
    parser.add_argument(
        "--drafts", action="store_true", help="include pages marked draft: true"
    )
    parser.add_argument(
        "--future", action="store_true", help="include pages dated in the future"
    )


def content_overrides(args) -> dict:
    """Config overrides for --drafts and --future; absent flags change nothing."""
    return {
        "build.drafts": True if args.drafts else None,
        "build.future": True if args.future else None,
    }


def overrides(args) -> dict:
    found = content_overrides(args)
    found.update(
        {
            # a relative DIR means relative to where the command was typed
            "output_dir": str(Path(args.output).resolve()) if args.output else None,
            "base_url": args.base_url,
            "build.incremental": False if args.no_incremental else None,
            "build.minify": True if args.minify else None,
            "build.fingerprint": True if args.fingerprint else None,
        }
    )
    return found


def profile(phases: dict) -> str:
    """The build phases as a table: name, time, share of the total."""
    total = sum(phases.values()) or 1.0
    rows = [
        (name, humanize_duration(seconds), f"{seconds / total:.0%}")
        for name, seconds in phases.items()
    ]
    rows.append(("total", humanize_duration(sum(phases.values())), ""))
    return term.format_table(rows, headers=("phase", "time", "share"), align="lrr")


def run(app, args) -> int:
    from ..build import Builder

    config = app.config(overrides(args))
    builder = Builder(config)
    if args.clean:
        builder.clean()
    report = builder.build()
    app.say(report.summary())
    if args.profile:
        app.out(profile(report.phases))
    return 0
