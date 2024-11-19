"""The files a build writes besides pages: feeds, sitemap, robots.txt, search."""

from __future__ import annotations

import dataclasses
import datetime as dt
from urllib.parse import urlsplit

from .. import __version__
from ..content import Page, PageList
from ..content.section import sort_pages
from ..errors import BuildError
from ..utils import log
from ..utils import text as textutil
from ..utils.hashing import hash_text, stable_hash
from ..utils.paths import url_join

HIGHLIGHT_CSS = "css/highlight.css"
SEARCH_SCRIPT = "js/inkstone-search.js"
SEARCH_INDEX = "search-index.json"
SITEMAP = "sitemap.xml"
ROBOTS = "robots.txt"
NOT_FOUND = "404.html"

_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def has_absolute_base(config) -> bool:
    """Feeds and sitemaps need full URLs; a path-only base_url cannot give them."""
    parts = urlsplit(config.base_url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def highlight_css(
    config, style: str | None = None, selector: str = ".highlight"
) -> str:
    """Stylesheet for highlighted code.

    Without an explicit style this is the site's: ``markdown.highlight_style``
    plus, if ``params.highlight_style_dark`` is set, that one for dark mode,
    both for readers whose system asks for it and for those who flipped the
    theme switch.
    """
    from ..highlight import HighlightError, HtmlFormatter

    try:
        if style is not None:
            return HtmlFormatter(style=style).get_css(selector)
        css = HtmlFormatter(style=config.markdown.highlight_style).get_css(selector)
        dark = config.params.get("highlight_style_dark")
        if dark:
            formatter = HtmlFormatter(style=str(dark))
            # not for readers who chose the light theme on a dark system
            system = f':root:not([data-theme="light"]) {selector}'
            media = "(prefers-color-scheme: dark)"
            css += "\n" + formatter.get_css(system, media=media)
            css += "\n" + formatter.get_css(f'[data-theme="dark"] {selector}')
        return css
    except HighlightError as exc:
        raise BuildError(f"highlight CSS: {exc.message}", path=config.path) from None


def generated_assets(config) -> dict[str, str]:
    """Static files we make up ourselves: logical path -> contents.

    They are fed to the asset pipeline as its lowest-priority source, so they
    get minified and fingerprinted like everything else and a file of the
    same name in the site's static/ replaces them.
    """
    files: dict[str, str] = {}
    if config.markdown.highlight:
        files[HIGHLIGHT_CSS] = highlight_css(config)
    if config.search.enabled:
        from ..search import client_script

        files[SEARCH_SCRIPT] = client_script()
    return files


def not_found_page(site) -> Page:
    """The 404 page: content/404.md if the site has one, else an empty shell."""
    for page in site.all_pages:
        if page.kind == "404":
            return page
    page = Page.virtual("/" + NOT_FOUND, title="Page not found", kind="404")
    site.add_page(page)
    return page


def feed_pages(site, section=None) -> PageList:
    """Dated pages that go into a feed, newest first."""
    if section is not None:
        pages = section.all_pages
    else:
        wanted = list(site.config.feeds.sections)
        pages = site.pages
        if wanted:
            pages = pages.filter(lambda page: any(page.in_section(n) for n in wanted))
    return sort_pages(pages.dated(), "date")


def _authors(site, page=None) -> list:
    from ..feeds import Author

    if page is not None:
        name = page.params.get("author")
        if isinstance(name, str) and name.strip():
            return [Author(name.strip())]
        if isinstance(name, dict) and name.get("name"):
            return [Author(str(name["name"]), name.get("email"), name.get("url"))]
        return []
    author = site.author
    if not author.get("name"):
        return []
    email = author.get("email") or None
    return [Author(author["name"], email, author.get("url") or None)]


def feed_entry(site, page):
    from ..feeds import FeedEntry

    config = site.config
    full = bool(config.feeds.full_content)
    image = page.params.get("image")
    return FeedEntry(
        id=page.permalink,
        title=page.title,
        url=page.permalink,
        published=page.date,
        updated=page.updated,
        summary=page.description or textutil.strip_html(str(page.summary)) or None,
        content_html=str(page.content if full else page.summary) or None,
        authors=_authors(site, page),
        tags=list(page.tags),
        image=image if isinstance(image, str) and image else None,
    )


def _feed_meta(site, *, title: str, link: str, feed_url: str, description: str):
    from ..feeds import FeedMeta

    return FeedMeta(
        title=title,
        link=link,
        feed_url=feed_url,
        description=description,
        language=site.language or None,
        authors=_authors(site),
        generator=f"inkstone {__version__}",
    )


def build_feeds(site) -> dict[str, str]:
    """``{output path: text}`` for the site-wide feeds and the section feeds."""
    from .. import feeds

    config = site.config
    settings = config.feeds
    if not (settings.rss or settings.atom or settings.json):
        return {}
    if not has_absolute_base(config):
        log.once(
            "feeds need an absolute base_url (http://...), not %r; none written",
            config.base_url,
        )
        return {}
    limit = int(settings.limit) or None
    base = config.base_url
    files: dict[str, str] = {}

    def render(kind: str, meta, pages) -> str:
        entries = [feed_entry(site, page) for page in pages]
        if not entries:
            # the Atom renderer would stamp an empty feed with the build
            # time, and then the file would change on every build
            meta = dataclasses.replace(meta, updated=_EPOCH)
        try:
            if kind == "rss":
                return feeds.render_rss(meta, entries, limit=limit)
            if kind == "atom":
                return feeds.render_atom(meta, entries, limit=limit)
            return feeds.render_json_feed(meta, entries, limit=limit)
        except feeds.FeedError as exc:
            raise BuildError(f"cannot write the {kind} feed: {exc.message}") from None

    pages = feed_pages(site)
    newest = pages[: limit or len(pages)]
    for kind, name, enabled in (
        ("rss", "rss.xml", settings.rss),
        ("atom", "atom.xml", settings.atom),
        ("json", "feed.json", settings.json),
    ):
        if not enabled:
            continue
        meta = _feed_meta(
            site,
            title=site.title,
            link=base,
            feed_url=url_join(base, name),
            description=config.description,
        )
        files[name] = render(kind, meta, newest)

    # TODO: Atom and JSON per section as well; RSS has been enough so far
    if settings.rss:
        for name in settings.sections:
            section = site.get_section(name)
            if section is None:
                continue
            path = section.url.strip("/") + "/rss.xml"
            meta = _feed_meta(
                site,
                title=f"{section.title} · {site.title}",
                link=url_join(base, section.url),
                feed_url=url_join(base, path),
                description=section.description or config.description,
            )
            members = feed_pages(site, section)
            files[path] = render("rss", meta, members[: limit or len(members)])
    return files


def _in_sitemap(page: Page) -> bool:
    if page.kind in ("404", "virtual"):
        # virtual pages are redirects, archives and the like: let the plugin
        # that made them opt in with page.sitemap = True
        return bool(getattr(page, "sitemap", False))
    if page.params.get("sitemap") is False or page.params.get("noindex"):
        return False
    return page.output_path.endswith((".html", ".htm"))


def build_sitemap(site) -> dict[str, str]:
    from .. import feeds

    config = site.config
    if not config.sitemap.enabled:
        return {}
    if not has_absolute_base(config):
        log.once(
            "the sitemap needs an absolute base_url (http://...), not %r; not written",
            config.base_url,
        )
        return {}
    sitemap = feeds.Sitemap()
    changefreq = config.sitemap.changefreq or None
    try:
        for page in sorted(site.all_pages, key=lambda page: page.url):
            if not _in_sitemap(page):
                continue
            lastmod = page.updated or page.date
            if lastmod is None and page.kind in ("home", "section", "term"):
                # a list changes when its newest member does
                dated = [p.updated or p.date for p in site.list_items(page) if p.date]
                lastmod = max(dated, default=None)
            sitemap.add(page.permalink, lastmod=lastmod, changefreq=changefreq)
        return sitemap.render_files(config.base_url)
    except feeds.FeedError as exc:
        raise BuildError(f"cannot write the sitemap: {exc.message}") from None


def build_robots(site) -> dict[str, str]:
    from .. import feeds

    config = site.config
    if not config.robots.enabled:
        return {}
    sitemaps = []
    if config.sitemap.enabled and has_absolute_base(config):
        sitemaps.append(url_join(config.base_url, SITEMAP))
    rule = feeds.RobotsRule(disallow=list(config.robots.disallow))
    try:
        return {ROBOTS: feeds.render_robots([rule], sitemaps=sitemaps)}
    except feeds.FeedError as exc:
        raise BuildError(f"robots.disallow: {exc.message}", path=config.path) from None


def search_pages(site) -> list[Page]:
    """Pages that go into the search index: the ones written by hand."""
    return [
        page
        for page in sorted(site.pages, key=lambda page: page.url)
        if page.params.get("search") is not False
    ]


def search_key(site, url_for) -> str:
    """Changes whenever the index would; lets an unchanged index be skipped."""
    config = site.config
    rows = [
        [url_for(page.url), page.title, list(page.tags), hash_text(str(page.content))]
        for page in search_pages(site)
    ]
    fields = {name: float(boost) for name, boost in config.search.fields.items()}
    return stable_hash([__version__, fields, config.language, rows])


def build_search_index(site, url_for) -> str:
    """The JSON the browser client loads. ``url_for`` adds the base path."""
    from ..search import IndexBuilder, SearchError

    config = site.config
    fields = {name: float(boost) for name, boost in config.search.fields.items()}
    try:
        builder = IndexBuilder(
            fields,
            language=config.language or "en",
            store=("title", "url", "summary", "date"),
        )
        for page in search_pages(site):
            url = url_for(page.url)
            summary = page.description or textutil.strip_html(str(page.summary))
            document = {
                "title": page.title,
                "tags": list(page.tags),
                "categories": list(page.categories),
                "description": page.description,
                "body": textutil.strip_html(str(page.content)),
            }
            for name in fields:
                # any other field name is looked up in the front matter
                if name not in document:
                    document[name] = page.params.get(name)
            stored = {
                "title": page.title,
                "url": url,
                "summary": textutil.truncate_chars(summary, 200),
                "date": page.date.date().isoformat() if page.date else None,
            }
            builder.add(url, document, stored)
        return builder.build().to_json()
    except SearchError as exc:
        raise BuildError(f"search index: {exc.message}", path=config.path) from None
