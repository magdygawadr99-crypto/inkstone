from __future__ import annotations

from typing import Iterable, Iterator

from ..utils import log
from ..utils.text import natural_sort_key, slugify
from .query import PageList


def term_slug(name: str) -> str:
    """URL form of a term name; non-Latin names keep their own script."""
    return slugify(name) or slugify(name, allow_unicode=True)


class Term:
    def __init__(self, name: str, slug: str, taxonomy: Taxonomy):
        self.name = name
        self.slug = slug
        self.taxonomy = taxonomy
        self.pages = PageList()

    @property
    def url(self) -> str:
        return f"{self.taxonomy.url}{self.slug}/"

    @property
    def count(self) -> int:
        return len(self.pages)

    def __repr__(self) -> str:
        return f"<Term {self.taxonomy.name}/{self.slug} ({self.count})>"

    def __str__(self) -> str:
        return self.name


class Taxonomy:
    """A way of grouping pages (tags, categories...) and its terms."""

    def __init__(self, name: str, singular: str = ""):
        self.name = name
        self.singular = singular or name
        self.terms: dict[str, Term] = {}

    @property
    def url(self) -> str:
        return f"/{slugify(self.name) or self.name}/"

    def __repr__(self) -> str:
        return f"<Taxonomy {self.name} ({len(self.terms)} terms)>"

    def __iter__(self) -> Iterator[Term]:
        return iter(sorted(self.terms.values(), key=_by_name))

    def __len__(self) -> int:
        return len(self.terms)

    def __bool__(self) -> bool:
        # an empty taxonomy is still a taxonomy; "{% if site.taxonomies.tags %}"
        # asks whether it exists
        return True

    def __contains__(self, name) -> bool:
        return self.get(name) is not None

    def __getitem__(self, name: str) -> Term:
        term = self.get(name)
        if term is None:
            raise KeyError(name)
        return term

    def get(self, name: str, default=None) -> Term | None:
        """Look a term up by slug or by any spelling of its name."""
        if name in self.terms:
            return self.terms[name]
        return self.terms.get(term_slug(str(name)), default)

    def add(self, name: str, page) -> Term | None:
        slug = term_slug(name)
        if not slug:
            log.once(
                "%s: the term %r has no usable characters for a URL, skipped",
                self.name,
                name,
            )
            return None
        term = self.terms.get(slug)
        if term is None:
            term = self.terms[slug] = Term(name, slug, self)
        if page not in term.pages:
            term.pages.append(page)
        return term

    def by_count(self) -> list[Term]:
        """Terms with the most pages first; ties in name order."""
        return sorted(self, key=lambda term: -term.count)

    def terms_of(self, page) -> list[Term]:
        """The Term objects for one page, in the order its front matter lists them."""
        found = []
        for name in page.taxonomies.get(self.name, ()):
            term = self.get(name)
            if term is not None and term not in found:
                found.append(term)
        return found


def _by_name(term: Term):
    return natural_sort_key(term.name)


def _newest_first(page):
    date = page.date
    return (
        0 if date is not None else 1,
        -date.timestamp() if date is not None else 0,
        natural_sort_key(page.title),
    )


def build_taxonomies(
    definitions: dict[str, str], pages: Iterable
) -> dict[str, Taxonomy]:
    """Group ``pages`` by the taxonomies defined in the config (plural -> singular)."""
    taxonomies = {
        plural: Taxonomy(plural, singular) for plural, singular in definitions.items()
    }
    for page in pages:
        for plural, names in page.taxonomies.items():
            taxonomy = taxonomies.get(plural)
            if taxonomy is None:
                continue
            for name in names:
                taxonomy.add(name, page)
    for taxonomy in taxonomies.values():
        for term in taxonomy.terms.values():
            term.pages = PageList(sorted(term.pages, key=_newest_first))
    return taxonomies
