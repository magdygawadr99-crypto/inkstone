from __future__ import annotations

from ..config import default_config
from ..highlight import HtmlFormatter, list_styles


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "highlight-css",
        parents=[shared],
        help="print the stylesheet of a highlighting style",
        description=(
            "Print the CSS for highlighted code blocks. The build writes this "
            "to css/highlight.css by itself; the command is for themes that "
            "want it somewhere else."
        ),
    )
    parser.add_argument(
        "--style",
        metavar="NAME",
        help="style to print (default: markdown.highlight_style of the site)",
    )
    parser.add_argument(
        "--selector",
        default=".highlight",
        help="CSS selector the rules are scoped to (default: %(default)s)",
    )
    parser.add_argument("--list", action="store_true", help="list the styles and exit")
    parser.set_defaults(run=run)


def run(app, args) -> int:
    if args.list:
        for name in list_styles():
            app.out(name)
        return 0
    style = args.style
    if style is None:
        if app.in_site():
            style = app.config().markdown.highlight_style
        else:
            style = default_config()["markdown"]["highlight_style"]
    # an unknown name raises HighlightError, which lists the ones there are
    css = HtmlFormatter(style=style).get_css(args.selector)
    app.out(css.rstrip("\n"))
    return 0
