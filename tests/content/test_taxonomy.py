from __future__ import annotations

import pytest

from inkstone.content import Taxonomy, Term
from inkstone.content.taxonomy import build_taxonomies, term_slug


@pytest.fixture
def tagged(files):
    files.page("posts/a.md", title="A", date="2024-01-01", tags=["Python", "parsing"])
    files.page("posts/b.md", title="B", date="2024-02-01", tags=["python"])
    files.page(
        "posts/c.md",
        title="C",
        date="2024-03-01",
        tags=["Site Generators", "python"],
        categories=["Notes"],
    )
    files.page("about.md", title="About")
    return files.load()


def test_taxonomies_from_the_config(tagged):
    assert sorted(tagged.taxonomies) == ["categories", "tags"]
    tags = tagged.taxonomies["tags"]
    assert isinstance(tags, Taxonomy)
    assert tags.name == "tags"
    assert tags.singular == "tag"
    assert tags.url == "/tags/"
    assert tagged.taxonomies["categories"].singular == "category"


def test_terms_are_keyed_by_slug(tagged):
    tags = tagged.taxonomies["tags"]
    assert sorted(tags.terms) == ["parsing", "python", "site-generators"]
    term = tags.terms["site-generators"]
    assert isinstance(term, Term)
    assert term.name == "Site Generators"
    assert term.slug == "site-generators"
    assert term.url == "/tags/site-generators/"
    assert term.count == 1
    assert str(term) == "Site Generators"


def test_spellings_with_the_same_slug_are_one_term(tagged):
    python = tagged.taxonomies["tags"].terms["python"]
    assert python.count == 3
    # the pages keep their own spelling
    assert tagged.get_page("posts/a.md").tags == ["Python", "parsing"]


def test_term_pages_are_newest_first(tagged):
    python = tagged.taxonomies["tags"].terms["python"]
    assert [page.title for page in python.pages] == ["C", "B", "A"]
    assert python.pages.limit(1)[0].title == "C"


def test_iterating_a_taxonomy_gives_terms_sorted_by_name(tagged):
    tags = tagged.taxonomies["tags"]
    assert [term.slug for term in tags] == ["parsing", "python", "site-generators"]
    assert len(tags) == 3
    assert [term.slug for term in tags.by_count()][0] == "python"


def test_term_lookup_by_name_or_slug(tagged):
    tags = tagged.taxonomies["tags"]
    assert tags.get("Site Generators") is tags.terms["site-generators"]
    assert tags.get("site-generators") is tags.terms["site-generators"]
    assert tags["PYTHON"] is tags.terms["python"]
    assert tags.get("nope") is None
    assert "python" in tags and "nope" not in tags
    with pytest.raises(KeyError):
        tags["nope"]


def test_terms_of_a_page(tagged):
    tags = tagged.taxonomies["tags"]
    page = tagged.get_page("posts/c.md")
    assert [term.slug for term in tags.terms_of(page)] == ["site-generators", "python"]
    assert tags.terms_of(tagged.get_page("about.md")) == []


def test_empty_taxonomy_is_still_truthy(files):
    files.page("a.md", title="A")
    site = files.load()
    tags = site.taxonomies["tags"]
    assert len(tags) == 0
    assert bool(tags) is True
    assert list(tags) == []


def test_custom_taxonomies(files):
    files.configure("taxonomies:\n  authors: author\n")
    files.page("a.md", title="A", authors=["Magdy Gawad"], tags=["x"])
    site = files.load()
    assert list(site.taxonomies) == ["authors"]
    authors = site.taxonomies["authors"]
    assert authors.terms["magdy-gawad"].url == "/authors/magdy-gawad/"
    # tags still read fine from the page, there is just no tag taxonomy
    assert site.get_page("a.md").tags == ["x"]


def test_no_taxonomies_at_all(files):
    files.configure("taxonomies: {}\n")
    files.page("a.md", title="A", tags=["x"])
    assert files.load().taxonomies == {}


def test_drafts_do_not_show_up_in_terms(files):
    files.page("a.md", title="A", tags=["x"])
    files.page("b.md", title="B", tags=["x", "only-draft"], draft=True)
    tags = files.load().taxonomies["tags"]
    assert sorted(tags.terms) == ["x"]
    assert tags.terms["x"].count == 1


def test_refresh_rebuilds_terms_after_pages_change(tagged):
    page = tagged.get_page("posts/b.md")
    page.tags = ["rust"]
    tagged.refresh()
    tags = tagged.taxonomies["tags"]
    assert "rust" in tags.terms
    assert tags.terms["python"].count == 2


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Python", "python"),
        ("C++", "c-plus-plus"),
        ("Site Generators", "site-generators"),
        ("日本語", "日本語"),
        ("!!!", ""),
    ],
)
def test_term_slugs(name, slug):
    assert term_slug(name) == slug


def test_terms_without_any_usable_character_are_skipped(capsys):
    taxonomy = Taxonomy("tags", "tag")
    assert taxonomy.add("!!!", object()) is None
    assert taxonomy.terms == {}
    assert "no usable characters" in capsys.readouterr().err


def test_build_taxonomies_only_uses_defined_ones(files):
    files.page("a.md", title="A", tags=["x"], categories=["y"])
    site = files.load()
    built = build_taxonomies({"categories": "category"}, site.pages)
    assert list(built) == ["categories"]
    assert built["categories"].terms["y"].pages == [site.get_page("a.md")]
