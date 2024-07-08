"""Navigation menus, from the config and from ``menu:`` front matter."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping

from ..errors import ContentError
from ..utils.paths import is_external
from ..utils.text import slugify

_ENTRY_KEYS = frozenset({"name", "url", "weight", "identifier", "parent", "children"})


class MenuEntry:
    def __init__(
        self,
        name: str,
        url: str,
        weight: float = 0,
        *,
        identifier: str | None = None,
        parent: str | None = None,
        page=None,
        params: Mapping[str, Any] | None = None,
    ):
        self.name = name
        self.url = url
        self.weight = weight
        self.identifier = identifier or slugify(name) or name
        self.parent = parent
        self.page = page
        self.children: list[MenuEntry] = []
        # whatever else the entry carried (icon, title, rel...)
        self.params = dict(params or {})

    def __repr__(self) -> str:
        return f"<MenuEntry {self.name!r} {self.url}>"

    def __getattr__(self, name: str):
        # so templates can write item.icon for extra keys
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.__dict__.get("params", {})[name]
        except KeyError:
            raise AttributeError(name) from None

    @property
    def external(self) -> bool:
        return is_external(self.url)

    @property
    def has_children(self) -> bool:
        return bool(self.children)

    def is_active(self, page) -> bool:
        """Is this entry the page being rendered? Takes a Page or a URL."""
        return _same_url(self.url, _url_of(page))

    def is_ancestor(self, page) -> bool:
        """Does the page live below this entry (in the menu or in the URL tree)?"""
        url = _url_of(page)
        for child in self.children:
            if child.is_active(url) or child.is_ancestor(url):
                return True
        if self.external or self.url in ("", "/"):
            return False
        here = self.url if self.url.endswith("/") else self.url + "/"
        return url.startswith(here) and not _same_url(self.url, url)

    def is_current(self, page) -> bool:
        """Active or an ancestor: what a nav bar usually wants to highlight."""
        return self.is_active(page) or self.is_ancestor(page)

    def walk(self) -> Iterator[MenuEntry]:
        yield self
        for child in self.children:
            yield from child.walk()


class Menu(list):
    """The top-level entries of one menu, sorted by weight."""

    def __init__(self, name: str = "", entries: Iterable[MenuEntry] = ()):
        super().__init__(entries)
        self.name = name

    def __repr__(self) -> str:
        return f"<Menu {self.name!r} ({len(self)} entries)>"

    def walk(self) -> Iterator[MenuEntry]:
        for entry in self:
            yield from entry.walk()

    def find(self, identifier: str) -> MenuEntry | None:
        for entry in self.walk():
            if entry.identifier == identifier:
                return entry
        return None

    def active(self, page) -> MenuEntry | None:
        """The entry to highlight: an exact match, else the closest ancestor."""
        url = _url_of(page)
        best: MenuEntry | None = None
        for entry in self.walk():
            if entry.is_active(url):
                return entry
            if entry.is_ancestor(url):
                if best is None or len(entry.url) > len(best.url):
                    best = entry
        return best


class Menus(dict):
    """``{name: Menu}``; asking for a menu that is not defined gives an empty one."""

    def __missing__(self, name: str) -> Menu:
        return Menu(name)

    def __getattr__(self, name: str) -> Menu:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def _url_of(page) -> str:
    if isinstance(page, str):
        return page
    return getattr(page, "url", "") or ""


def _same_url(a: str, b: str) -> bool:
    if a == b:
        return True
    return bool(a) and bool(b) and a.rstrip("/") == b.rstrip("/")


def _entry_from_config(raw: Mapping, where: str) -> MenuEntry:
    if not isinstance(raw, Mapping) or "name" not in raw or "url" not in raw:
        raise ContentError(f"{where}: a menu entry needs a name and a url, got {raw!r}")
    entry = MenuEntry(
        str(raw["name"]),
        str(raw["url"]),
        raw.get("weight", 0) or 0,
        identifier=raw.get("identifier"),
        parent=raw.get("parent"),
        params={key: value for key, value in raw.items() if key not in _ENTRY_KEYS},
    )
    for index, child in enumerate(raw.get("children") or ()):
        entry.children.append(_entry_from_config(child, f"{where}.children[{index}]"))
    return entry


def _page_entries(page) -> list[tuple[str, MenuEntry]]:
    """Entries a page asks for with ``menu:`` in its front matter.

    Three spellings: ``menu: main``, ``menu: [main, footer]`` and
    ``menu: {main: {name: Blog, weight: 10, parent: about}}``.
    """
    spec = page.meta.get("menu")
    if spec is None or spec is False:
        return []
    if isinstance(spec, str):
        spec = {spec: {}}
    elif isinstance(spec, (list, tuple)):
        spec = {name: {} for name in spec}
    if not isinstance(spec, Mapping):
        raise ContentError(
            f"menu must be a menu name, a list of names or a table, got {spec!r}",
            path=page.source_path,
        )
    found = []
    for menu_name, options in spec.items():
        if options is None or options is True:
            options = {}
        if not isinstance(menu_name, str) or not isinstance(options, Mapping):
            raise ContentError(
                f"menu.{menu_name}: expected a table of options, got {options!r}",
                path=page.source_path,
            )
        weight = options.get("weight", page.weight)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ContentError(
                f"menu.{menu_name}.weight must be a number, got {weight!r}",
                path=page.source_path,
            )
        entry = MenuEntry(
            str(options.get("name") or page.title),
            page.url,
            weight,
            identifier=options.get("identifier"),
            parent=options.get("parent"),
            page=page,
            params={k: v for k, v in options.items() if k not in _ENTRY_KEYS},
        )
        found.append((menu_name, entry))
    return found


def _nest(name: str, entries: list[MenuEntry]) -> Menu:
    """Hang entries with a ``parent`` under it and sort every level."""
    by_id: dict[str, MenuEntry] = {}
    for entry in entries:
        for item in entry.walk():
            by_id.setdefault(item.identifier, item)
    top: list[MenuEntry] = []
    for entry in entries:
        parent = by_id.get(entry.parent) if entry.parent else None
        if parent is None or parent is entry:
            # an unknown parent is not worth failing a build over
            top.append(entry)
        else:
            parent.children.append(entry)

    def order(items: list[MenuEntry]) -> None:
        # sort() is stable, so equal weights keep the order they were given in
        items.sort(key=lambda item: item.weight)
        for item in items:
            order(item.children)

    order(top)
    return Menu(name, top)


def build_menus(config_menus: Mapping[str, list] | None, pages: Iterable = ()) -> Menus:
    collected: dict[str, list[MenuEntry]] = {}
    for name, raw_entries in (config_menus or {}).items():
        bucket = collected.setdefault(name, [])
        for index, raw in enumerate(raw_entries or ()):
            bucket.append(_entry_from_config(raw, f"menus.{name}[{index}]"))
    for page in pages:
        for name, entry in _page_entries(page):
            collected.setdefault(name, []).append(entry)
    return Menus({name: _nest(name, entries) for name, entries in collected.items()})
