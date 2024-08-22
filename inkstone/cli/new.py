from __future__ import annotations

from pathlib import Path

from .. import scaffold
from ..utils import log


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "new",
        parents=[shared],
        help="create a site, a post or a page",
        description="Create a new site, or a post or page in the current one.",
    )
    kinds = parser.add_subparsers(
        dest="kind", metavar="WHAT", required=True, parser_class=type(parser)
    )

    site = kinds.add_parser(
        "site",
        parents=[shared],
        help="scaffold a new site in PATH",
        description="Write a starter site: config, home page, a first post, about.",
    )
    site.add_argument("path", metavar="PATH", help="directory to create the site in")
    site.add_argument("--theme", default="default", help="theme to start with")
    site.add_argument("--title", metavar="T", help="title of the site")
    site.add_argument(
        "--force",
        action="store_true",
        help="write into a directory that is not empty (existing files are kept)",
    )
    site.set_defaults(run=new_site)

    post = kinds.add_parser(
        "post",
        parents=[shared],
        help="create a post dated today",
        description=(
            "Create content/<section>/<date>-<slug>.md with the front matter "
            "filled in, and print its path."
        ),
    )
    post.add_argument("title", metavar="TITLE", nargs="+", help="title of the post")
    post.add_argument(
        "--section", metavar="S", default="posts", help="section to put it in"
    )
    post.add_argument("--draft", action="store_true", help="mark it draft: true")
    post.add_argument("--date", metavar="D", help="date instead of today")
    post.add_argument("--slug", metavar="S", help="slug instead of one from the title")
    post.add_argument("--tags", metavar="a,b", help="comma separated tags")
    post.set_defaults(run=new_post)

    page = kinds.add_parser(
        "page",
        parents=[shared],
        help="create a page at PATH",
        description=(
            "Create a page below the content directory: 'about.md', "
            "'projects/widget.md', or 'trip/' for a page bundle."
        ),
    )
    page.add_argument("path", metavar="PATH", help="path below the content directory")
    page.add_argument("--title", metavar="T", help="title instead of one from the name")
    page.set_defaults(run=new_page)


def new_site(app, args) -> int:
    target = Path(args.path)
    created = scaffold.create_site(
        target,
        title=args.title or "My Site",
        theme=args.theme,
        force=args.force,
    )
    for path in created:
        log.verbose("wrote %s", app.shown(path))
    shown = app.shown(target)
    if not created:
        app.say(f"{shown}: everything was there already, nothing written")
        return 0
    app.say(f"Created a site in {shown} ({len(created)} files). Next:")
    app.say("")
    if target.resolve() != Path.cwd().resolve():
        app.say(f"  cd {shown}")
    app.say("  inkstone serve")
    return 0


def new_post(app, args) -> int:
    config = app.config()
    tags = args.tags.split(",") if args.tags else []
    path = scaffold.new_post(
        config,
        " ".join(args.title),
        section=args.section,
        date=args.date,
        slug=args.slug,
        tags=tags,
        draft=args.draft,
    )
    app.out(app.shown(path))
    return 0


def new_page(app, args) -> int:
    path = scaffold.new_page(app.config(), args.path, title=args.title)
    app.out(app.shown(path))
    return 0
