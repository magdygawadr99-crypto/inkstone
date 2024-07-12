"""Cache keys: reducing pages and their surroundings to hashable descriptions.

An output is rebuilt when the hash of its description changes, so what goes
into a description decides how incremental a build is. Too little and stale
pages survive; too much and everything is rebuilt all the time.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import PurePath
from typing import Any

from ..content import Page, Paginator, Resource, Section, Taxonomy, Term
from ..content.menus import MenuEntry
from ..utils.hashing import hash_bytes, hash_text, stable_hash

# How deep to look into objects we know nothing about (plugin data mostly).
_MAX_DEPTH = 6

# Page attributes that are covered elsewhere in a fingerprint, or that are
# bookkeeping. Anything else found on a page was put there by a plugin.
_STANDARD_ATTRS = frozenset(
    {
        "kind",
        "url",
        "title",
        "slug",
        "description",
        "date",
        "updated",
        "draft",
        "weight",
        "source_path",
        "file_path",
        "meta",
        "params",
        "taxonomies",
        "raw",
        "content",
        "summary",
        "truncated",
        "toc",
        "toc_html",
        "template",
        "layout",
        "section",
        "site",
        "prev",
        "next",
        "aliases",
        "resources",
        "extra_context",
        "paginator",
        "paginate",
        "first_page",
    }
)

# Templates that look at the whole site depend on more than their own page.
# Spotting that in the source is crude, but it is right for every template I
# have seen, and the alternative is re-rendering everything on every change.
# TODO: note what a render actually touched instead of guessing; something
# like {% set s = site %}{{ s.pages }} gets past these.
_USES_PAGES = re.compile(
    r"\bsite\s*\.\s*(?:pages|all_pages|pages_by_date)\b"
    r"|\bget_(?:page|section)\s*\("
    r"|\bsection\s*\.\s*(?:pages|all_pages)\b"
    r"|\bsite\s*\.\s*sections\b[^}%]*\.\s*(?:pages|all_pages)\b"
)
_USES_TAXONOMIES = re.compile(
    r"\bsite\s*\.\s*taxonomies\b|\btaxonomy\s*\.\s*terms\b|\bin\s+taxonomy\b"
)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def page_ref(page: Page) -> list:
    """What a link to a page usually shows: enough for nav links and boxes."""
    return [
        "page",
        page.url,
        page.title,
        _iso(page.date),
        page.description,
        hash_text(str(page.summary)),
    ]


def describe(value: Any, depth: int = 0, *, refs_only: bool = False) -> Any:
    """Reduce any value to plain data that stable_hash() accepts.

    Pages near the top are described by their metadata, pages further down
    (and all of them with ``refs_only``) by a short reference, which also
    keeps two pages that point at each other from recursing forever.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, (bytes, bytearray)):
        return hash_bytes(bytes(value))
    if isinstance(value, Page):
        if refs_only or depth > 2:
            return page_ref(value)
        return ["page", metadata_hash(value)]
    if isinstance(value, Section):
        return ["section", value.name, value.title, value.url]
    if isinstance(value, Term):
        return ["term", value.slug, value.name, value.count]
    if isinstance(value, Taxonomy):
        return ["taxonomy", value.name, value.singular, value.url]
    if isinstance(value, Paginator):
        return [
            "paginator",
            value.page,
            value.pages,
            value.total,
            value.per_page,
            value.base_url,
            [describe(item, depth + 1, refs_only=refs_only) for item in value.items],
        ]
    if isinstance(value, Resource):
        return ["resource", value.name, value.url]
    if isinstance(value, MenuEntry):
        children = [describe(child, depth + 1) for child in value.children]
        return ["menu", value.name, value.url, value.weight, children]
    if depth >= _MAX_DEPTH:
        return f"<{type(value).__name__}>"
    deeper = {"depth": depth + 1, "refs_only": refs_only}
    if isinstance(value, dict):
        return {str(key): describe(item, **deeper) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [describe(item, **deeper) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(stable_hash(describe(item, **deeper)) for item in value)
    if callable(value):
        return f"<callable {getattr(value, '__name__', type(value).__name__)}>"
    attrs = getattr(value, "__dict__", None)
    if isinstance(attrs, dict):
        # what plugins hand to templates: an archive's years, a series...
        public = {
            name: describe(item, **deeper)
            for name, item in attrs.items()
            if not name.startswith("_")
        }
        return [type(value).__name__, public]
    return f"<{type(value).__name__}>"


def plugin_attrs(page: Page) -> dict:
    """Attributes plugins attached to a page (page.related, page.series...)."""
    found = {}
    for name, value in vars(page).items():
        if name.startswith("_") or name in _STANDARD_ATTRS:
            continue
        found[name] = describe(value, 1, refs_only=True)
    return found


def page_metadata(page: Page) -> dict:
    """What a list page or a feed can show of a page.

    Deliberately without the body: fixing a typo deep in a post should not
    re-render the front page.
    """
    return {
        "url": page.url,
        "kind": page.kind,
        "title": page.title,
        "description": page.description,
        "date": _iso(page.date),
        "updated": _iso(page.updated),
        "draft": page.draft,
        "weight": page.weight,
        "taxonomies": {name: list(terms) for name, terms in page.taxonomies.items()},
        "summary": hash_text(str(page.summary)),
        "truncated": page.truncated,
        # minutes, not the word count: that would change with every edit
        "reading_time": page.reading_time,
        "params": describe(dict(page.params), 1, refs_only=True),
        "section": page.section.name if page.section is not None else None,
        "plugins": plugin_attrs(page),
    }


def metadata_hash(page: Page) -> str:
    cached = getattr(page, "_metadata_hash", None)
    if cached is not None:
        return cached
    return stable_hash(page_metadata(page))


def freeze_metadata(pages) -> None:
    """Hash every page's metadata once; call when pages have stopped changing.

    A page shows up in many lists, and hashing its metadata again for each
    of them was most of the time an unchanged build took.
    """
    pages = list(pages)
    for page in pages:
        page._metadata_hash = None
    for page in pages:
        page._metadata_hash = stable_hash(page_metadata(page))


def page_state(page: Page) -> dict:
    """Everything about one page that its own output depends on."""
    state = {"metadata": metadata_hash(page)}
    state.update(
        content=hash_text(str(page.content)),
        toc=hash_text(str(page.toc_html)),
        template=page.template,
        aliases=list(page.aliases),
        resources=[[res.name, res.url] for res in page.resources],
        prev=page_ref(page.prev) if page.prev is not None else None,
        next=page_ref(page.next) if page.next is not None else None,
        output=page.output_path,
        context=describe(page.extra_context, 0),
    )
    section = page.section
    if section is not None:
        children = [
            [child.name, child.title, child.url, len(child.pages)]
            for child in section.subsections
        ]
        state["section_info"] = [
            section.name,
            section.title,
            section.url,
            children,
            [ancestor.name for ancestor in section.ancestors],
        ]
    return state


def site_pages_key(site) -> str:
    """Changes when the metadata of any regular page does."""
    return stable_hash([metadata_hash(page) for page in site.pages])


def taxonomies_key(site) -> str:
    """Changes when a term appears, disappears or gets another page count."""
    return stable_hash(
        {
            taxonomy.name: [[term.slug, term.name, term.count] for term in taxonomy]
            for taxonomy in site.taxonomies.values()
        }
    )


def site_outline(site) -> dict:
    """The parts of a site that every page may show: sections and menus."""
    return {
        "sections": [
            [section.name, section.title, section.url, section.parent is None]
            for section in site.sections.values()
        ],
        "menus": {
            name: [describe(entry, 0) for entry in menu]
            for name, menu in site.menus.items()
        },
        "home": [site.home.title, site.home.description] if site.home else None,
    }


def template_uses(source: str) -> tuple[bool, bool]:
    """(looks at other pages, looks at taxonomies), judging by the source."""
    return bool(_USES_PAGES.search(source)), bool(_USES_TAXONOMIES.search(source))
