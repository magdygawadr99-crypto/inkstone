from __future__ import annotations

import difflib
import json

from ..utils import log, term
from ..utils.text import natural_sort_key, pluralize, slugify, truncate_chars

FORMATS = ("table", "json", "paths")
_TITLE_WIDTH = 48


def add_parser(commands, shared) -> None:
    parser = commands.add_parser(
        "list",
        parents=[shared],
        help="list the pages of the site",
        description="List content: one line per page, newest first.",
    )
    parser.add_argument("--section", metavar="S", help="only pages of this section")
    parser.add_argument("--tag", metavar="T", help="only pages with this tag")
    parser.add_argument("--drafts", action="store_true", help="include drafts")
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default="table",
        help="table (default), json, or paths: one source file per line",
    )
    parser.add_argument(
        "--sort", choices=("date", "title"), default="date", help="default: date"
    )
    parser.set_defaults(run=run)


def _same_tag(wanted: str, tags) -> bool:
    key = slugify(wanted) or wanted.lower()
    return any((slugify(tag) or tag.lower()) == key for tag in tags)


def _in_section(page, name: str) -> bool:
    section = page.section
    while section is not None:
        if section.name == name:
            return True
        section = section.parent
    return False


def select(site, *, section=None, tag=None, sort="date") -> list:
    pages = list(site.pages)
    if section:
        name = section.strip("/")
        if name not in site.sections:
            message = f"no section called {name!r}"
            close = difflib.get_close_matches(name, list(site.sections), n=1)
            if close:
                message += f", did you mean {close[0]!r}?"
            log.warning(message)
        pages = [page for page in pages if _in_section(page, name)]
    if tag:
        pages = [page for page in pages if _same_tag(tag, page.tags)]
    if sort == "title":
        pages.sort(key=lambda page: (natural_sort_key(page.title), page.url))
    else:
        pages.sort(
            key=lambda page: (
                page.date is None,
                -(page.date.timestamp() if page.date else 0),
                natural_sort_key(page.title),
                page.url,
            )
        )
    return pages


def as_record(page) -> dict:
    return {
        "title": page.title,
        "url": page.url,
        "date": page.date.isoformat() if page.date else None,
        "updated": page.updated.isoformat() if page.updated else None,
        "section": page.section.name if page.section is not None else None,
        "tags": list(page.tags),
        "draft": bool(page.draft),
        "source": page.source_path,
        "words": page.word_count,
    }


def as_table(pages: list) -> str:
    rows = []
    for page in pages:
        title = truncate_chars(page.title, _TITLE_WIDTH)
        if page.draft:
            title += " " + term.style("(draft)", "yellow")
        rows.append(
            (
                page.date.date().isoformat() if page.date else "-",
                title,
                page.section.name if page.section is not None else "-",
                page.url,
            )
        )
    return term.format_table(rows, headers=("date", "title", "section", "url"))


def run(app, args) -> int:
    from ..content import load_site

    config = app.config()
    site = load_site(config, drafts=True if args.drafts else None)
    pages = select(site, section=args.section, tag=args.tag, sort=args.sort)

    if args.format == "json":
        records = [as_record(page) for page in pages]
        app.out(json.dumps(records, indent=2, ensure_ascii=False))
    elif args.format == "paths":
        for page in pages:
            app.out(app.shown(config.content_path / page.source_path))
    elif pages:
        app.out(as_table(pages))
    if args.format == "table":
        drafts = sum(1 for page in pages if page.draft)
        note = f" ({pluralize(drafts, 'draft')})" if drafts else ""
        log.info("%s%s", pluralize(len(pages), "page"), note)
    return 0
