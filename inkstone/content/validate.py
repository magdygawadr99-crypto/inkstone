"""Checks on a loaded site that need no build: `inkstone check` runs these."""

from __future__ import annotations

import difflib
import posixpath
import re
from dataclasses import dataclass

from .permalinks import DATE_TOKENS, find_collisions, pattern_for, pattern_tokens

PROBLEM_KINDS = (
    "broken-link",
    "missing-anchor",
    "missing-image",
    "external-link",
    "duplicate-url",
    "front-matter",
    "missing-title",
    "bad-date",
    "orphan-alias",
)

# Keys we read ourselves. Something in page.params that is nearly one of these
# is far more likely a typo than a theme option.
KNOWN_KEYS = (
    "title",
    "date",
    "updated",
    "slug",
    "description",
    "summary",
    "draft",
    "weight",
    "template",
    "aliases",
    "url",
    "menu",
    "tags",
    "categories",
    "sort_by",
    "paginate",
)
_DATED_NAME = re.compile(r"\d{4}-\d{1,2}-\d{1,2}(?:[-_]|\Z)")


@dataclass
class Problem:
    kind: str
    source: str
    message: str
    target: str | None = None
    line: int | None = None

    def __str__(self) -> str:
        where = self.source or "site"
        if self.line is not None:
            where += f":{self.line}"
        text = f"{where}: {self.kind}: {self.message}"
        if self.target and self.target not in self.message:
            text += f" ({self.target})"
        return text

    @property
    def sort_key(self) -> tuple:
        return (self.source, self.line or 0, self.kind, self.target or "", self.message)


def validate_site(site) -> list[Problem]:
    """Problems that are visible without building anything.

    Duplicate URLs, front matter that looks mistaken, pages without a title,
    dates that cannot be right, and aliases that will not do anything.
    """
    problems: list[Problem] = list(getattr(site, "problems", ()))
    problems += _duplicate_urls(site)
    known = set(KNOWN_KEYS) | set(site.config.taxonomies)
    for page in site.all_pages:
        if page.source_path is None:
            continue
        problems += _front_matter(page, known)
        problems += _dates(page, site)
        if page.kind == "page" and not _has_title(page):
            problems.append(
                Problem(
                    "missing-title",
                    page.source_path,
                    f"no title in the front matter, using {page.title!r} "
                    "from the file name",
                )
            )
    problems += _aliases(site)
    return sorted(problems, key=lambda problem: problem.sort_key)


def _has_title(page) -> bool:
    title = page.meta.get("title")
    return title is not None and str(title).strip() != ""


def _label(page) -> str:
    return page.source_path or f"generated {page.kind} page"


def _duplicate_urls(site) -> list[Problem]:
    problems = []
    for output_path, pages in sorted(find_collisions(site.all_pages).items()):
        first = pages[0]
        others = ", ".join(_label(page) for page in pages[1:])
        problems.append(
            Problem(
                "duplicate-url",
                _label(first),
                f"writes to the same file as {others}: {output_path}",
                target=first.url,
            )
        )
    # list pages only exist during a build, but their addresses are known now
    reserved: dict[str, str] = {}
    for taxonomy in site.taxonomies.values():
        reserved[taxonomy.url] = f"the list of {taxonomy.name}"
        for term in taxonomy.terms.values():
            reserved[term.url] = f"the {taxonomy.singular} page for {term.name!r}"
    for page in site.all_pages:
        if page.kind == "page" and page.url in reserved:
            problems.append(
                Problem(
                    "duplicate-url",
                    _label(page),
                    f"has the same URL as {reserved[page.url]}",
                    target=page.url,
                )
            )
    return problems


def _front_matter(page, known: set[str]) -> list[Problem]:
    problems = []
    for key in page.params:
        if not isinstance(key, str) or key in known:
            continue
        close = difflib.get_close_matches(key, sorted(known), n=1, cutoff=0.8)
        if close:
            problems.append(
                Problem(
                    "front-matter",
                    page.source_path,
                    f"unknown key {key!r}, did you mean {close[0]!r}?",
                    line=_key_line(page, key),
                )
            )
    for plural, names in page.taxonomies.items():
        blank = [name for name in names if not str(name).strip()]
        if blank:
            problems.append(
                Problem(
                    "front-matter",
                    page.source_path,
                    f"{plural} contains an empty entry",
                    line=_key_line(page, plural),
                )
            )
        if len(set(names)) != len(names):
            repeated = sorted({name for name in names if names.count(name) > 1})
            problems.append(
                Problem(
                    "front-matter",
                    page.source_path,
                    f"{plural} lists {', '.join(repeated)} more than once",
                    line=_key_line(page, plural),
                )
            )
    if page.kind != "section" and page.kind != "home":
        for key in ("sort_by", "paginate"):
            if key in page.meta:
                problems.append(
                    Problem(
                        "front-matter",
                        page.source_path,
                        f"{key} only means something in a section's _index.md",
                        line=_key_line(page, key),
                    )
                )
    return problems


def _key_line(page, key: str) -> int | None:
    """Line of a top-level front matter key, found by looking at the file again."""
    path = getattr(page, "file_path", None)
    if path is None:
        return None
    pattern = re.compile(rf"\s*[\"']?{re.escape(key)}[\"']?\s*[:=]")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            for number, line in enumerate(handle, 1):
                if number > 200:
                    break
                if pattern.match(line):
                    return number
    except (OSError, UnicodeDecodeError):
        pass
    return None


def _dates(page, site) -> list[Problem]:
    problems = []
    source = page.source_path
    if page.date is not None and page.updated is not None and page.updated < page.date:
        problems.append(
            Problem(
                "bad-date",
                source,
                f"updated ({page.updated.date().isoformat()}) is earlier than "
                f"date ({page.date.date().isoformat()})",
                line=_key_line(page, "updated"),
            )
        )
    name = posixpath.basename(source)
    if name.lower() in ("index.md", "index.markdown"):
        name = posixpath.basename(posixpath.dirname(source))
    if page.kind == "page" and _DATED_NAME.match(name) and "date" not in page.meta:
        if page.date is None:
            problems.append(
                Problem(
                    "bad-date",
                    source,
                    f"the file name starts like a date, but {name[:10]!r} is not "
                    "a real one",
                )
            )
    if page.kind == "page" and page.date is None and page.section is not None:
        pattern = pattern_for(page.section.name, site.config.permalinks)
        if pattern and DATE_TOKENS.intersection(pattern_tokens(pattern)):
            problems.append(
                Problem(
                    "bad-date",
                    source,
                    f"no date, but the permalink pattern {pattern!r} of section "
                    f"{page.section.name!r} needs one; the page falls back to "
                    f"{page.url}",
                )
            )
    return problems


def _aliases(site) -> list[Problem]:
    problems = []
    urls = {page.url: page for page in site.all_pages}
    claimed: dict[str, object] = {}
    redirects_on = "redirects" in list(site.config.plugins)
    warned_plugin = False
    for page in site.all_pages:
        if not page.aliases:
            continue
        source = _label(page)
        if not redirects_on and not warned_plugin:
            warned_plugin = True
            problems.append(
                Problem(
                    "orphan-alias",
                    source,
                    "aliases are set but the 'redirects' plugin is not enabled, "
                    "so no redirect pages are written",
                )
            )
        for alias in page.aliases:
            if alias == page.url:
                message = "an alias that is the page's own URL does nothing"
            elif alias in urls:
                message = f"the alias is the URL of {_label(urls[alias])}"
            elif alias in claimed and claimed[alias] is not page:
                message = f"the alias is also claimed by {_label(claimed[alias])}"
            else:
                claimed[alias] = page
                continue
            problems.append(
                Problem(
                    "orphan-alias",
                    source,
                    message,
                    target=alias,
                    line=_key_line(page, "aliases"),
                )
            )
    return problems
