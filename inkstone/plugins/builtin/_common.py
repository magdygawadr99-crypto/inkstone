"""Bits that several of the built-in plugins need."""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlsplit

from ...errors import PluginError

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_MISSING = object()


def lookup(obj, key: str, default=None):
    """Read ``key`` from a Config, a dict or anything with attributes."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    value = getattr(obj, key, _MISSING)
    if value is _MISSING:
        try:
            return obj[key]
        except (KeyError, TypeError, IndexError):
            return default
    return value


def setting(plugin, name: str, default, *, choices=None, minimum=None):
    """A value from the plugin's settings table, checked against its default.

    A wrong type is a mistake in the config file and should say so, with the
    table and key, rather than blow up somewhere inside a hook.
    """
    value = plugin.settings.get(name, _MISSING)
    if value is _MISSING or value is None:
        return default
    where = f"[plugin.{plugin.name}] {name}"
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise PluginError(f"{where} must be true or false, got {value!r}")
    elif isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise PluginError(f"{where} must be a whole number, got {value!r}")
    elif isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PluginError(f"{where} must be a number, got {value!r}")
        value = float(value)
    elif isinstance(default, str):
        if not isinstance(value, str):
            raise PluginError(f"{where} must be a string, got {value!r}")
    elif isinstance(default, (list, tuple)):
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise PluginError(f"{where} must be a list, got {value!r}")
        value = list(value)
    elif isinstance(default, dict):
        if not isinstance(value, dict):
            raise PluginError(f"{where} must be a table, got {value!r}")
    if choices is not None and value not in choices:
        allowed = ", ".join(str(choice) for choice in choices)
        raise PluginError(f"{where} must be one of {allowed}; got {value!r}")
    if minimum is not None and value < minimum:
        raise PluginError(f"{where} cannot be less than {minimum}, got {value!r}")
    return value


def site_prefix(config) -> str:
    """Path part of base_url without the trailing slash: "" or "/blog"."""
    base = lookup(config, "base_path")
    if base is None:
        base_url = lookup(config, "base_url") or ""
        base = urlsplit(base_url).path if "//" in base_url else base_url
    base = str(base).strip("/")
    return "/" + base if base else ""


def url_for(config, url: str) -> str:
    """A site URL as it has to be written into a page.

    Only differs from the URL itself when the site lives below the root of
    its host (base_url = "https://example.com/blog/").
    """
    if not url.startswith("/") or url.startswith("//"):
        return url
    return site_prefix(config) + url


def absolute_url(config, url: str) -> str:
    """base_url joined with a site URL; other URLs pass through."""
    if not url.startswith("/") or url.startswith("//"):
        return url
    base = str(lookup(config, "base_url") or "")
    return base.rstrip("/") + url


def front_matter(page, key: str, default=None):
    """A front matter value, wherever the page keeps it."""
    for holder in (getattr(page, "meta", None), getattr(page, "params", None)):
        if isinstance(holder, dict) and key in holder:
            return holder[key]
    return default


def in_sections(page, names) -> bool:
    """Is the page in one of the named sections, or in one nested below?"""
    name = getattr(getattr(page, "section", None), "name", None)
    if name is None:
        return False
    wanted = [str(item).strip("/") for item in names]
    return any(name == item or name.startswith(item + "/") for item in wanted)


def source_file(page, config=None):
    """Absolute path of a page's source file, or None for generated pages."""
    path = getattr(page, "file_path", None)
    if path is not None:
        return path
    source = getattr(page, "source_path", None)
    content = lookup(config, "content_path")
    if source and content is not None:
        return content / source
    return None


def display_path(page, config=None) -> str | None:
    """How a page's source is named in messages: relative to the site root."""
    path = source_file(page, config)
    root = lookup(config, "root")
    if path is not None and root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return str(path)
    if path is not None:
        return str(path)
    return getattr(page, "source_path", None)


def date_key(page) -> float:
    """Sortable timestamp of a page's date; undated pages sort as the epoch."""
    date = getattr(page, "date", None)
    if date is None:
        return 0.0
    if not isinstance(date, dt.datetime):
        date = dt.datetime(date.year, date.month, date.day)
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    return date.timestamp()


def template_exists(env, name: str) -> bool:
    if env is None:
        return False
    from ...tmpl import TemplateNotFound

    try:
        env.get_template(name)
    except TemplateNotFound:
        return False
    return True
