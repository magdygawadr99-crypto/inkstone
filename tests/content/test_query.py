from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest

from inkstone.content import PageList
from inkstone.tmpl import DictLoader, Environment

UTC = dt.timezone.utc


def item(title, year=None, month=1, section=None, tags=(), weight=0, draft=False):
    date = dt.datetime(year, month, 1, tzinfo=UTC) if year else None
    return SimpleNamespace(
        title=title,
        date=date,
        weight=weight,
        draft=draft,
        section=SimpleNamespace(name=section, parent=None) if section else None,
        taxonomies={"tags": list(tags)},
        params={"featured": weight > 5},
    )


@pytest.fixture
def pages():
    return PageList(
        [
            item("Delta", 2024, 3, "posts", ["python", "Parsing"], weight=4),
            item("alpha", 2023, 7, "posts", ["python"], weight=9),
            item("Charlie", 2024, 1, "notes", ["Site Generators"], weight=1),
            item("Bravo", None, 1, "notes", [], weight=7, draft=True),
            item("Echo", 2022, 12, None, ["python"], weight=2),
        ]
    )


def titles(items):
    return [entry.title for entry in items]


def test_behaves_like_a_list(pages):
    assert isinstance(pages, list)
    assert len(pages) == 5
    assert pages[0].title == "Delta"
    assert pages[-1].title == "Echo"
    assert titles(pages) == ["Delta", "alpha", "Charlie", "Bravo", "Echo"]
    assert pages[1] in pages
    assert bool(pages) and not PageList()
    assert pages == list(pages)
    assert titles(reversed(pages))[0] == "Echo"
    assert pages.index(pages[2]) == 2


def test_slices_stay_page_lists(pages):
    assert isinstance(pages[:2], PageList)
    assert titles(pages[1:3]) == ["alpha", "Charlie"]
    assert titles(pages[::-1])[0] == "Echo"
    assert isinstance(pages + pages[:1], PageList)
    assert len(pages + [item("Extra")]) == 6
    assert isinstance(pages.copy(), PageList)


def test_helpers_do_not_change_the_original(pages):
    before = titles(pages)
    pages.sort_by("title")
    pages.limit(1)
    pages.where("draft")
    pages.reversed()
    assert titles(pages) == before


def test_where_equality_on_dotted_attributes(pages):
    posts = pages.where("section.name", "posts")
    assert isinstance(posts, PageList)
    assert titles(posts) == ["Delta", "alpha"]
    assert titles(pages.where("params.featured", True)) == ["alpha", "Bravo"]
    assert pages.where("section.name", "nope") == []


def test_where_truthiness_and_keywords(pages):
    assert titles(pages.where("draft")) == ["Bravo"]
    assert titles(pages.where("date")) == ["Delta", "alpha", "Charlie", "Echo"]
    assert titles(pages.where(draft=False, weight=1)) == ["Charlie"]
    assert titles(pages.where("section.name", "notes", draft=True)) == ["Bravo"]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("weight", ">", 4), ["alpha", "Bravo"]),
        (("weight", ">=", 4), ["Delta", "alpha", "Bravo"]),
        (("weight", "<", 2), ["Charlie"]),
        (("weight", "<=", 2), ["Charlie", "Echo"]),
        (("weight", "!=", 4), ["alpha", "Charlie", "Bravo", "Echo"]),
        (("weight", "==", 4), ["Delta"]),
        (("weight", "in", [1, 2]), ["Charlie", "Echo"]),
        (("weight", "not in", [1, 2]), ["Delta", "alpha", "Bravo"]),
        (("title", "startswith", "C"), ["Charlie"]),
        (("title", "endswith", "o"), ["Bravo", "Echo"]),
        (("taxonomies.tags", "contains", "python"), ["Delta", "alpha", "Echo"]),
        (("date.year", "gt", 2023), ["Delta", "Charlie"]),
    ],
)
def test_where_operators(pages, args, expected):
    assert titles(pages.where(*args)) == expected


def test_where_comparisons_with_missing_values_do_not_match(pages):
    cutoff = dt.datetime(2023, 1, 1, tzinfo=UTC)
    assert titles(pages.where("date", ">", cutoff)) == ["Delta", "alpha", "Charlie"]
    assert pages.where("no.such.attribute", ">", 3) == []


def test_where_with_an_unknown_operator(pages):
    with pytest.raises(ValueError, match="unknown operator '~='"):
        pages.where("weight", "~=", 3)
    with pytest.raises(TypeError):
        pages.where("weight", ">", 3, 4)


def test_exclude_and_filter(pages):
    assert titles(pages.exclude("draft")) == ["Delta", "alpha", "Charlie", "Echo"]
    not_posts = pages.exclude("section.name", "posts")
    assert titles(not_posts) == ["Charlie", "Bravo", "Echo"]
    assert titles(pages.filter(lambda page: len(page.title) == 4)) == ["Echo"]


def test_sort_by(pages):
    by_weight = pages.sort_by("weight")
    assert titles(by_weight) == ["Charlie", "Echo", "Delta", "Bravo", "alpha"]
    assert titles(pages.sort_by("weight", reverse=True))[0] == "alpha"
    assert titles(pages.sort_by("-weight"))[0] == "alpha"
    # case does not matter for text
    by_title = pages.sort_by("title")
    assert titles(by_title) == ["alpha", "Bravo", "Charlie", "Delta", "Echo"]
    assert titles(pages.sort_by(lambda page: len(page.title)))[0] == "Echo"


def test_sort_by_date_puts_undated_last_either_way(pages):
    oldest_first = pages.sort_by("date")
    assert titles(oldest_first) == ["Echo", "alpha", "Charlie", "Delta", "Bravo"]
    newest_first = pages.sort_by("date", reverse=True)
    assert titles(newest_first) == ["Delta", "Charlie", "alpha", "Echo", "Bravo"]


def test_sort_by_handles_mixed_naive_and_aware_dates():
    mixed = PageList(
        [
            SimpleNamespace(title="aware", date=dt.datetime(2024, 1, 2, tzinfo=UTC)),
            SimpleNamespace(title="naive", date=dt.datetime(2024, 1, 1)),
            SimpleNamespace(title="plain", date=dt.date(2024, 1, 3)),
        ]
    )
    assert titles(mixed.sort_by("date")) == ["naive", "aware", "plain"]


def test_natural_ordering_of_numbers_in_text():
    numbered = PageList(SimpleNamespace(title=f"Part {n}") for n in (10, 2, 1))
    assert titles(numbered.sort_by("title")) == ["Part 1", "Part 2", "Part 10"]


def test_limit_offset_first_last(pages):
    assert titles(pages.limit(2)) == ["Delta", "alpha"]
    assert pages.limit(0) == [] and pages.limit(-3) == []
    assert len(pages.limit(99)) == 5
    assert titles(pages.offset(3)) == ["Bravo", "Echo"]
    assert titles(pages.offset(1).limit(2)) == ["alpha", "Charlie"]
    assert pages.first().title == "Delta"
    assert pages.last().title == "Echo"
    assert PageList().first() is None
    assert PageList().last("nothing") == "nothing"


def test_chaining_reads_like_the_readme(pages):
    result = pages.where("section.name", "posts").sort_by("date").limit(5)
    assert titles(result) == ["alpha", "Delta"]


def test_tagged_compares_slugs(pages):
    assert titles(pages.tagged("python")) == ["Delta", "alpha", "Echo"]
    assert titles(pages.tagged("PYTHON")) == ["Delta", "alpha", "Echo"]
    assert titles(pages.tagged("parsing")) == ["Delta"]
    assert titles(pages.tagged("site-generators")) == ["Charlie"]
    assert titles(pages.tagged("Site Generators")) == ["Charlie"]
    assert pages.tagged("nope") == []
    assert pages.tagged("python", taxonomy="categories") == []


def test_group_by_year_and_month(pages):
    by_year = pages.group_by_year()
    assert [year for year, _group in by_year] == [2024, 2023, 2022]
    assert titles(by_year[0][1]) == ["Delta", "Charlie"]
    assert all(isinstance(group, PageList) for _year, group in by_year)
    by_month = pages.group_by_month()
    months = [key for key, _group in by_month]
    assert months == [(2024, 3), (2024, 1), (2023, 7), (2022, 12)]
    assert PageList().group_by_year() == []


def test_group_by_attribute(pages):
    groups = pages.group_by("section.name")
    assert [key for key, _group in groups] == ["posts", "notes", None]
    assert titles(dict(groups)["notes"]) == ["Charlie", "Bravo"]
    # unhashable values are grouped by what they look like
    by_tags = pages.group_by("taxonomies.tags")
    assert len(by_tags) == 5 - 1


def test_dated_published_drafts(pages):
    assert titles(pages.dated()) == ["Delta", "alpha", "Charlie", "Echo"]
    assert titles(pages.published()) == ["Delta", "alpha", "Charlie", "Echo"]
    assert titles(pages.drafts()) == ["Bravo"]


def test_pluck_and_unique(pages):
    assert pages.pluck("weight") == [4, 9, 1, 7, 2]
    assert pages.pluck("section.name")[-1] is None
    doubled = pages + pages[:2]
    assert len(doubled.unique()) == 5


def test_in_section_follows_nesting():
    docs = SimpleNamespace(name="docs", parent=None)
    guide = SimpleNamespace(name="docs/guide", parent=docs)
    items = PageList(
        [
            SimpleNamespace(title="install", section=docs),
            SimpleNamespace(title="steps", section=guide),
            SimpleNamespace(title="about", section=None),
        ]
    )
    assert titles(items.in_section("docs")) == ["install", "steps"]
    assert titles(items.in_section("docs", nested=False)) == ["install"]
    assert titles(items.in_section("docs/guide")) == ["steps"]


def test_repr_names_the_type():
    assert repr(PageList([1, 2])) == "PageList([1, 2])"
    assert json.dumps(PageList([1, 2])) == "[1, 2]"


def test_usable_from_templates(pages):
    env = Environment(
        loader=DictLoader(
            {
                "t": (
                    "{% set posts = pages.where('section.name', 'posts') %}"
                    "{% for p in posts.sort_by('date') %}"
                    "{{ p.title }},{% endfor %}"
                    "|{{ pages | length }}"
                    "|{{ pages[:2] | map(attribute='title') | join('+') }}"
                    "|{% for year, group in pages.group_by_year() %}{{ year }}:"
                    "{{ group | length }} {% endfor %}"
                    "|{{ pages.tagged('python').limit(1).first().title }}"
                )
            }
        )
    )
    rendered = env.get_template("t").render(pages=pages)
    assert rendered == "alpha,Delta,|5|Delta+alpha|2024:2 2023:1 2022:1 |Delta"


def test_site_and_section_pages_are_page_lists(files):
    files.page("posts/a.md", title="A", date="2024-01-01", tags=["python"])
    files.page("posts/b.md", title="B", date="2024-02-01")
    files.page("about.md", title="About")
    site = files.load()
    assert isinstance(site.pages, PageList)
    assert isinstance(site.sections["posts"].pages, PageList)
    oldest = site.pages.where("section.name", "posts").sort_by("date").limit(5)
    assert titles(oldest) == ["A", "B"]
    assert titles(site.pages.tagged("python")) == ["A"]
    assert titles(site.pages.in_section("posts")) == ["B", "A"]
    assert [year for year, _pages in site.pages.group_by_year()] == [2024]
