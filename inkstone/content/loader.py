"""Walking the content directory and turning files into pages and sections."""

from __future__ import annotations

import datetime as dt
import posixpath
import re
from pathlib import Path

from .. import frontmatter
from ..datafiles import load_data_dir
from ..errors import ConfigError, ContentError
from ..utils import log
from ..utils.collections import AttrDict
from ..utils.dates import date_from_filename, parse_date
from ..utils.fs import read_text, walk_files
from ..utils.glob import GlobSet
from ..utils.text import slugify, titlecase
from . import permalinks
from .page import Page, Resource
from .section import SORT_ORDERS, Section
from .site import Site
from .validate import Problem

MARKDOWN_SUFFIXES = (".md", ".markdown")
SECTION_INDEX = "_index"
BUNDLE_INDEX = "index"

# front matter keys with a meaning of their own; everything else is page.params
_INTERPRETED = frozenset(
    {
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
    }
)
_SECTION_KEYS = frozenset({"sort_by", "paginate"})
_ALWAYS_TAXONOMIES = ("tags", "categories")


def is_markdown(name: str) -> bool:
    return name.lower().endswith(MARKDOWN_SUFFIXES)


def _stem(name: str) -> str:
    return posixpath.splitext(posixpath.basename(name))[0]


def title_from_name(name: str) -> str:
    """``hello-world`` -> ``Hello World``, for pages without a title."""
    words = re.sub(r"[-_]+", " ", name).strip()
    return titlecase(words) if words else name


def load_site(
    config,
    *,
    drafts: bool | None = None,
    future: bool | None = None,
    now: dt.datetime | None = None,
    strict: bool = True,
) -> Site:
    """Parse everything under the content and data directories.

    Nothing is rendered: ``page.raw`` holds Markdown, ``page.content`` is
    empty. ``drafts`` and ``future`` default to the config's build settings.
    With ``strict=False`` a file that cannot be read is skipped and noted in
    ``site.problems`` instead of stopping everything, which is what a
    checker wants.
    """
    if drafts is None:
        drafts = bool(config.build.drafts)
    if future is None:
        future = bool(config.build.future)
    return _Loader(config, drafts, future, now, strict).load()


class _Loader:
    def __init__(self, config, drafts: bool, future: bool, now, strict: bool):
        self.config = config
        self.drafts = drafts
        self.future = future
        self.strict = strict
        self.tz = config.tzinfo
        if now is None:
            now = dt.datetime.now(self.tz)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=self.tz)
        self.now = now
        self.root: Path = config.content_path
        self.site = Site(config, build_time=now)
        self.taxonomy_keys = tuple(
            dict.fromkeys((*config.taxonomies, *_ALWAYS_TAXONOMIES))
        )
        self.pretty = bool(config.build.pretty_urls)
        self.content_label = str(config.content_dir).replace("\\", "/").strip("/")

    def label(self, rel: str) -> str:
        """How a source file is named in messages: relative to the site root."""
        return f"{self.content_label}/{rel}" if self.content_label else rel

    def warn(self, message: str) -> None:
        # kept on the site as well, so a build report can list them
        self.site.warnings.append(message)
        log.warning(message)

    def load(self) -> Site:
        site = self.site
        site.data = AttrDict(load_data_dir(self.config.data_path))
        files = self._scan()
        bundles = self._bundle_dirs(files)
        hidden = self._hidden_sections(files)

        home_source = None
        indexes: dict[str, str] = {}
        page_files: list[str] = []
        bundle_files: dict[str, list[str]] = {name: [] for name in bundles}
        loose: list[str] = []
        for rel in files:
            directory, name = posixpath.split(rel)
            if _under(directory, hidden):
                continue
            bundle = _owning_bundle(directory, bundles)
            if bundle is not None:
                if rel != bundles[bundle]:
                    bundle_files[bundle].append(rel)
                continue
            if not is_markdown(name):
                loose.append(rel)
            elif _stem(name) == SECTION_INDEX:
                if directory:
                    self._claim(indexes, directory, rel)
                else:
                    home_source = self._one_home(home_source, rel)
            elif _stem(name) == BUNDLE_INDEX and not directory:
                # content/index.md is accepted as the home page as well
                home_source = self._one_home(home_source, rel)
            else:
                page_files.append(rel)

        site.home = self._home(home_source)
        site.add_page(site.home)
        for directory in sorted(indexes):
            self._section(directory, indexes)
        for rel in page_files:
            self._guarded(self._add_page, rel, posixpath.dirname(rel), indexes, [])
        for bundle, index_file in sorted(bundles.items()):
            nested = _owning_bundle(posixpath.dirname(bundle), bundles) is not None
            if nested or _under(bundle, hidden):
                continue
            self._guarded(
                self._add_page,
                index_file,
                posixpath.dirname(bundle),
                indexes,
                bundle_files[bundle],
            )
        for rel in loose:
            self._add_loose(rel)
        for name in sorted(site.sections):
            site.add_page(site.sections[name].index)
        site.refresh()
        return site

    def _scan(self) -> list[str]:
        if not self.root.is_dir():
            self.warn(f"content directory {self.root} does not exist")
            return []
        try:
            ignore = GlobSet(self.config.ignore)
        except ValueError as exc:
            raise ConfigError(f"ignore: {exc}", path=self.config.path) from None
        return [
            path.relative_to(self.root).as_posix()
            for path in walk_files(self.root, ignore=ignore)
        ]

    @staticmethod
    def _bundle_dirs(files: list[str]) -> dict[str, str]:
        """Directories that are a page bundle -> their index file."""
        found: dict[str, str] = {}
        for rel in files:
            directory, name = posixpath.split(rel)
            if directory and is_markdown(name) and _stem(name) == BUNDLE_INDEX:
                found.setdefault(directory, rel)
        return found

    def _hidden_sections(self, files: list[str]) -> set[str]:
        """Sections whose _index.md is a draft: nothing below them is built."""
        hidden: set[str] = set()
        if self.drafts:
            return hidden
        for rel in files:
            directory, name = posixpath.split(rel)
            if not directory or not is_markdown(name) or _stem(name) != SECTION_INDEX:
                continue
            try:
                meta, _body = self._parse(rel)
            except ContentError:
                # reported properly when the section itself is loaded
                continue
            if meta.get("draft") is True:
                hidden.add(directory)
                self.site.skipped["draft"].append(rel)
        return hidden

    def _claim(self, indexes: dict[str, str], directory: str, rel: str) -> None:
        if directory in indexes:
            raise ContentError(
                f"two index files for one section: {indexes[directory]} and {rel}",
                path=self.label(rel),
            )
        indexes[directory] = rel

    def _one_home(self, current: str | None, rel: str) -> str:
        if current is not None:
            raise ContentError(
                f"two files want to be the home page: {current} and {rel}",
                path=self.label(rel),
            )
        return rel

    def _guarded(self, func, rel: str, *args) -> None:
        """Run a per-file step; in lenient mode a bad file is noted and skipped."""
        try:
            func(rel, *args)
        except ContentError as exc:
            if self.strict:
                raise
            kind = "bad-date" if "date" in exc.message.lower() else "front-matter"
            self.site.problems.append(Problem(kind, rel, exc.message, line=exc.line))

    def _parse(self, rel: str) -> tuple[dict, str]:
        path = self.root / rel
        try:
            text = read_text(path)
        except OSError as exc:
            raise ContentError(
                f"cannot read file: {exc.strerror or exc}", path=self.label(rel)
            ) from None
        except ContentError as exc:
            raise ContentError(
                exc.message, path=self.label(rel), line=exc.line
            ) from None
        return frontmatter.parse(text, path=self.label(rel))

    def _home(self, rel: str | None) -> Page:
        if rel is None:
            page = Page(kind="home", url="/", title=self.config.title)
            page._rendered = True
            return page
        meta, body = self._parse(rel)
        fields = _Fields(meta, self.label(rel), self.root / rel, self.tz)
        page = self._page_from(rel, "home", meta, body, fields)
        page.url = "/"
        page.slug = ""
        if not fields.has("title"):
            page.title = self.config.title
        page.paginate = fields.paginate()
        return page

    def _section(self, name: str, indexes: dict[str, str]) -> Section:
        """Get or create a section, and its parents on the way."""
        existing = self.site.sections.get(name)
        if existing is not None:
            return existing
        parent_name = posixpath.dirname(name)
        parent = self._section(parent_name, indexes) if parent_name else None
        section = Section(name, url=permalinks.section_url(name))
        rel = indexes.get(name)
        if rel is None:
            index = Page(
                kind="section",
                url=section.url,
                title=title_from_name(posixpath.basename(name)),
                slug=posixpath.basename(section.url.rstrip("/")),
            )
            index._rendered = True
        else:
            meta, body = self._parse(rel)
            fields = _Fields(meta, self.label(rel), self.root / rel, self.tz)
            index = self._page_from(rel, "section", meta, body, fields)
            index.url = section.url
            if not fields.has("title"):
                index.title = title_from_name(posixpath.basename(name))
            section.sort_by = fields.choice("sort_by", SORT_ORDERS, "date")
            section.paginate = fields.paginate()
        index.section = section
        section.index = index
        section.parent = parent
        if parent is not None:
            parent.subsections.append(section)
        self.site.sections[name] = section
        return section

    def _add_page(
        self, rel: str, directory: str, indexes: dict[str, str], extra: list[str]
    ) -> None:
        meta, body = self._parse(rel)
        fields = _Fields(meta, self.label(rel), self.root / rel, self.tz)
        page = self._page_from(rel, "page", meta, body, fields)
        if page.draft and not self.drafts:
            self.site.skipped["draft"].append(rel)
            return
        if page.date is not None and page.date > self.now and not self.future:
            self.site.skipped["future"].append(rel)
            return
        if not directory and _stem(rel) == "404":
            # content/404.md supplies the text of the not-found page
            page.kind = "404"
            page.url = "/404.html"
            self.site.add_page(page)
            return
        section = self._section(directory, indexes) if directory else None
        explicit = fields.string("url")
        if explicit:
            page.url = permalinks.normalise(explicit)
        else:
            page.url = self._url_for(page, directory)
        if section is not None:
            section.add(page)
        if page.is_bundle:
            page.resources = self._resources(page, posixpath.dirname(rel), extra)
        self.site.add_page(page)

    def _url_for(self, page: Page, section_name: str) -> str:
        options = {"permalinks": self.config.permalinks, "pretty": self.pretty}
        try:
            return permalinks.page_url(page, section_name, **options)
        except permalinks.MissingDate:
            pattern = permalinks.pattern_for(section_name, self.config.permalinks)
            url = permalinks.default_url(page, section_name)
            if not self.pretty and not page.is_bundle:
                url = permalinks.ugly(url)
            self.warn(
                f"{self.label(page.source_path)}: no date for the permalink "
                f"pattern {pattern}, using {url}"
            )
            return url

    def _page_from(self, rel: str, kind: str, meta: dict, body: str, fields) -> Page:
        name = _stem(rel)
        if name in (SECTION_INDEX, BUNDLE_INDEX):
            name = posixpath.basename(posixpath.dirname(rel))
        name_date, rest = date_from_filename(name)
        base = rest or name

        slug = fields.string("slug")
        if slug:
            slug = slugify(slug) or slugify(slug, allow_unicode=True) or slug
        else:
            slug = slugify(base) or slugify(base, allow_unicode=True) or base

        date = fields.date("date")
        if date is None and name_date is not None:
            date = dt.datetime(
                name_date.year, name_date.month, name_date.day, tzinfo=self.tz
            )

        taxonomies = {}
        for key in self.taxonomy_keys:
            terms = fields.string_list(key)
            if terms or key in meta:
                taxonomies[key] = terms

        skip = _INTERPRETED | set(self.taxonomy_keys)
        if kind != "page":
            skip |= _SECTION_KEYS
        page = Page(
            kind=kind,
            title=fields.string("title") or title_from_name(base),
            slug=slug,
            description=fields.string("description") or "",
            date=date,
            updated=fields.date("updated"),
            draft=fields.boolean("draft", False),
            weight=fields.integer("weight", 0),
            source_path=rel,
            file_path=self.root / rel,
            meta=meta,
            params=AttrDict({k: v for k, v in meta.items() if k not in skip}),
            taxonomies=taxonomies,
            raw=body,
            template=fields.string("template") or None,
            aliases=[_as_url(alias) for alias in fields.string_list("aliases")],
        )
        fields.string("summary")
        return page

    def _resources(
        self, page: Page, directory: str, files: list[str]
    ) -> list[Resource]:
        base = page.url if page.url.endswith("/") else posixpath.dirname(page.url) + "/"
        resources = []
        for rel in sorted(files):
            name = posixpath.relpath(rel, directory)
            if is_markdown(name):
                self.warn(
                    f"{self.label(rel)}: Markdown files inside a page bundle are "
                    "not pages, ignored"
                )
                continue
            url = base + name
            resources.append(Resource(name, url, rel, path=self.root / rel))
        return resources

    def _add_loose(self, rel: str) -> None:
        """A non-Markdown file outside any bundle: copied next to its section."""
        directory, name = posixpath.split(rel)
        url = permalinks.section_url(directory) + name
        resource = Resource(name, url, rel, path=self.root / rel)
        self.site.resources.append(resource)
        section = self.site.sections.get(directory)
        if section is not None:
            section.resources.append(resource)


def _under(directory: str, roots: set[str]) -> bool:
    return any(directory == root or directory.startswith(root + "/") for root in roots)


def _owning_bundle(directory: str, bundles: dict[str, str]) -> str | None:
    """The outermost bundle directory that ``directory`` is, or sits inside."""
    owner = None
    current = directory
    while current:
        if current in bundles:
            owner = current
        current = posixpath.dirname(current)
    return owner


def _as_url(alias: str) -> str:
    alias = alias.strip()
    return alias if alias.startswith("/") else "/" + alias


def _describe(value) -> str:
    if isinstance(value, bool):
        kind = "a boolean"
    elif isinstance(value, str):
        kind = "a string"
    elif isinstance(value, (int, float)):
        kind = "a number"
    elif isinstance(value, list):
        kind = "a list"
    elif isinstance(value, dict):
        kind = "a table"
    elif value is None:
        kind = "empty"
    else:
        kind = type(value).__name__
    return f"{value!r} ({kind})"


class _Fields:
    """Typed access to one file's front matter, with errors that say where."""

    def __init__(self, meta: dict, label: str, path: Path, tz):
        self.meta = meta
        self.label = label
        self.path = path
        self.tz = tz

    def has(self, key: str) -> bool:
        value = self.meta.get(key)
        return value is not None and value != ""

    def fail(self, key: str, message: str) -> ContentError:
        return ContentError(message, path=self.label, line=self._line_of(key))

    def _line_of(self, key: str) -> int | None:
        pattern = re.compile(rf"\s*[\"']?{re.escape(key)}[\"']?\s*[:=]")
        try:
            lines = read_text(self.path).split("\n")
        except (OSError, ContentError):
            return None
        for number, line in enumerate(lines[:200], 1):
            if pattern.match(line):
                return number
        return None

    def string(self, key: str) -> str | None:
        value = self.meta.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # title: 1984
            return str(value)
        if isinstance(value, (dt.date, dt.datetime)) and key in ("title", "slug"):
            # title: 2024-05-03 gets parsed as a date by YAML and TOML
            return value.isoformat()
        raise self.fail(key, f"{key} must be a string, got {_describe(value)}")

    def boolean(self, key: str, default: bool) -> bool:
        value = self.meta.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        raise self.fail(key, f"{key} must be true or false, got {_describe(value)}")

    def integer(self, key: str, default: int) -> int:
        value = self.meta.get(key)
        if value is None:
            return default
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise self.fail(key, f"{key} must be a whole number, got {_describe(value)}")

    def string_list(self, key: str) -> list[str]:
        value = self.meta.get(key)
        if value is None:
            return []
        if isinstance(value, str):
            # "tags: python" for the common case of a single one
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            out = []
            for item in value:
                if isinstance(item, bool) or not isinstance(item, (str, int, float)):
                    raise self.fail(
                        key,
                        f"{key} must be a list of strings, but it contains "
                        f"{_describe(item)}",
                    )
                text = str(item).strip()
                if text and text not in out:
                    out.append(text)
            return out
        raise self.fail(key, f"{key} must be a list of strings, got {_describe(value)}")

    def date(self, key: str) -> dt.datetime | None:
        value = self.meta.get(key)
        if value is None or value == "":
            return None
        try:
            return parse_date(value, default_tz=self.tz)
        except ValueError as exc:
            raise self.fail(key, f"bad {key}: {exc}") from None

    def choice(self, key: str, allowed: tuple[str, ...], default: str) -> str:
        value = self.meta.get(key)
        if value is None:
            return default
        if isinstance(value, str) and value.strip().lower() in allowed:
            return value.strip().lower()
        options = ", ".join(allowed)
        raise self.fail(
            key, f"{key} must be one of {options}; got {_describe(value)}"
        )

    def paginate(self) -> int | None:
        """``paginate: 12`` items per page, ``false`` for one long page."""
        value = self.meta.get("paginate")
        if value is None or value is True:
            return None
        if value is False:
            return 0
        if isinstance(value, int) and value >= 0:
            return value
        raise self.fail(
            "paginate",
            f"paginate must be a number of items per page or false, got "
            f"{_describe(value)}",
        )
