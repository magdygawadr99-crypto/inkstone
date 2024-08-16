"""Small factories for the plugin tests: real config, pages and sites, built
by hand instead of loaded from files."""

from __future__ import annotations

import datetime as dt

from inkstone.config import load_config
from inkstone.content import Page, Section, Site
from inkstone.utils.text import slugify


def day(year, month=1, date=1, hour=0):
    return dt.datetime(year, month, date, hour, tzinfo=dt.timezone.utc)


def make_config(root, **overrides):
    """The default configuration for a site at ``root``; dotted keys override."""
    return load_config(root, overrides=overrides or None)


def make_page(title, url=None, *, section=None, tags=(), categories=(), **attrs):
    slug = slugify(title)
    taxonomies = {}
    if tags:
        taxonomies["tags"] = list(tags)
    if categories:
        taxonomies["categories"] = list(categories)
    meta = attrs.pop("meta", {})
    page = Page(
        kind=attrs.pop("kind", "page"),
        url=url or f"/{slug}/",
        title=title,
        slug=slug,
        taxonomies=taxonomies,
        meta=dict(meta),
        # the loader keeps the keys it does not interpret here as well
        params=dict(meta),
        **attrs,
    )
    page.section_name = section
    return page


def make_site(config, pages):
    """A Site holding ``pages``, with their sections and taxonomies in place."""
    site = Site(config)
    for page in pages:
        name = getattr(page, "section_name", None)
        if name:
            if name not in site.sections:
                site.sections[name] = Section(name)
            site.sections[name].add(page)
        site.add_page(page)
    site.refresh()
    return site
