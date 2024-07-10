from __future__ import annotations

import pytest

from inkstone.content import Paginator, paginate
from inkstone.content.pagination import page_url


def test_single_page():
    (only,) = paginate(["a", "b", "c"], 10, "/posts/")
    assert isinstance(only, Paginator)
    assert only.items == ["a", "b", "c"]
    assert (only.page, only.pages, only.total, only.per_page) == (1, 1, 3, 10)
    assert not only.has_prev and not only.has_next
    assert only.prev_url is None and only.next_url is None
    assert only.first_url == only.last_url == "/posts/"
    assert only.page_urls == [(1, "/posts/")]


def test_several_pages():
    pages = paginate(list(range(25)), 10, "/posts/")
    assert [p.page for p in pages] == [1, 2, 3]
    assert [len(p.items) for p in pages] == [10, 10, 5]
    assert all(p.pages == 3 and p.total == 25 for p in pages)
    first, second, third = pages
    assert first.items == list(range(10))
    assert third.items == list(range(20, 25))
    assert (first.has_prev, first.has_next) == (False, True)
    assert (second.has_prev, second.has_next) == (True, True)
    assert (third.has_prev, third.has_next) == (True, False)
    assert first.next_url == "/posts/page/2/"
    assert second.prev_url == "/posts/"
    assert second.next_url == "/posts/page/3/"
    assert third.prev_url == "/posts/page/2/"
    assert third.last_url == "/posts/page/3/"
    assert second.url == "/posts/page/2/"
    assert second.page_urls == [
        (1, "/posts/"),
        (2, "/posts/page/2/"),
        (3, "/posts/page/3/"),
    ]


def test_exact_multiple_has_no_empty_last_page():
    pages = paginate(list(range(20)), 10, "/")
    assert len(pages) == 2
    assert pages[1].url == "/page/2/"


def test_empty_list_still_gives_one_page():
    (only,) = paginate([], 10, "/posts/")
    assert only.items == []
    assert (only.page, only.pages, only.total) == (1, 1, 0)
    assert only.start == 0 and only.end == 0


@pytest.mark.parametrize("per_page", [None, 0, -1])
def test_no_page_size_means_everything_on_one_page(per_page):
    (only,) = paginate(list(range(37)), per_page, "/posts/")
    assert len(only.items) == 37
    assert only.pages == 1


def test_custom_path_segment_and_missing_trailing_slash():
    pages = paginate(list(range(3)), 2, "/tags/python", "seite")
    assert pages[0].url == "/tags/python/"
    assert pages[1].url == "/tags/python/seite/2/"


@pytest.mark.parametrize(
    ("number", "expected"),
    [(1, "/posts/"), (0, "/posts/"), (2, "/posts/page/2/"), (10, "/posts/page/10/")],
)
def test_page_url(number, expected):
    assert page_url("/posts/", number) == expected


def test_paginator_iterates_over_its_items():
    first = paginate(["a", "b", "c"], 2, "/")[0]
    assert list(first) == ["a", "b"]
    assert len(first) == 2


def test_start_and_end_positions():
    pages = paginate(list(range(25)), 10, "/")
    assert [(p.start, p.end) for p in pages] == [(1, 10), (11, 20), (21, 25)]


def test_window_leaves_gaps_in_long_lists():
    page = paginate(list(range(200)), 10, "/p/")[9]
    numbers = [number for number, _url in page.window(around=2)]
    assert numbers == [1, None, 8, 9, 10, 11, 12, None, 20]
    assert dict(page.window())[20] == "/p/page/20/"
    short = paginate(list(range(30)), 10, "/p/")[0]
    assert [number for number, _url in short.window()] == [1, 2, 3]


def test_items_are_a_page_list(files):
    for index in range(5):
        date = f"2024-01-0{index + 1}"
        files.page(f"posts/p{index}.md", title=f"P{index}", date=date)
    site = files.load()
    first = paginate(site.sections["posts"].pages, 2, "/posts/")[0]
    assert first.items.pluck("title") == ["P4", "P3"]


@pytest.fixture
def listed(files):
    files.configure("pagination:\n  per_page: 2\n")
    files.page("_index.md", title="Home")
    files.page("posts/_index.md", title="Posts")
    for index in range(1, 6):
        date = f"2024-01-0{index}"
        files.page(f"posts/p{index}.md", title=f"P{index}", date=date, tags=["t"])
    files.page("notes/_index.md", title="Notes", paginate=1)
    files.page("notes/n1.md", title="N1", date="2024-02-01")
    files.page("notes/n2.md", title="N2", date="2024-02-02")
    files.page("about.md", title="About")
    return files.load()


def test_list_pages_are_generated_with_paginators(listed):
    created = listed.generate_list_pages()
    urls = sorted(page.url for page in created)
    assert urls == [
        "/categories/",
        "/notes/page/2/",
        "/page/2/",
        "/page/3/",
        "/posts/page/2/",
        "/posts/page/3/",
        "/tags/",
        "/tags/t/",
        "/tags/t/page/2/",
        "/tags/t/page/3/",
    ]
    assert all(page in listed.all_pages for page in created)
    assert all(page.site is listed for page in created)


def test_first_list_page_is_the_existing_page(listed):
    listed.generate_list_pages()
    index = listed.sections["posts"].index
    paginator = index.extra_context["paginator"]
    assert paginator.page == 1 and paginator.pages == 3 and paginator.total == 5
    assert index.extra_context["pages"] is paginator.items
    assert [page.title for page in paginator.items] == ["P5", "P4"]
    assert index.paginator is paginator


def test_later_list_pages_copy_the_first(listed):
    listed.generate_list_pages()
    second = listed.get_page("/posts/page/2/")
    assert second.kind == "section"
    assert second.title == "Posts"
    assert second.section is listed.sections["posts"]
    assert second.source_path is None
    assert second.first_page is listed.sections["posts"].index
    assert second.output_path == "posts/page/2/index.html"
    assert [page.title for page in second.extra_context["pages"]] == ["P3", "P2"]
    assert second.extra_context["paginator"].prev_url == "/posts/"


def test_section_page_size_override(listed):
    listed.generate_list_pages()
    paginator = listed.sections["notes"].index.extra_context["paginator"]
    assert paginator.per_page == 1 and paginator.pages == 2


def test_home_lists_the_feed_sections(listed):
    listed.generate_list_pages()
    paginator = listed.home.extra_context["paginator"]
    assert paginator.total == 5
    assert [page.title for page in paginator.items] == ["P5", "P4"]
    assert listed.get_page("/page/3/").kind == "home"


def test_home_lists_every_dated_page_when_no_sections_are_named(files):
    files.configure("feeds:\n  sections: []\n")
    files.page("posts/a.md", title="A", date="2024-01-01")
    files.page("notes/b.md", title="B", date="2024-01-02")
    files.page("about.md", title="About")
    site = files.load()
    site.generate_list_pages()
    titles = [page.title for page in site.home.extra_context["pages"]]
    assert titles == ["B", "A"]


def test_taxonomy_and_term_pages(listed):
    listed.generate_list_pages()
    tags = listed.get_page("/tags/")
    assert tags.kind == "taxonomy"
    assert tags.title == "Tags"
    assert tags.extra_context["taxonomy"] is listed.taxonomies["tags"]
    assert "paginator" not in tags.extra_context
    term = listed.get_page("/tags/t/")
    assert term.kind == "term"
    assert term.title == "t"
    assert term.extra_context["term"] is listed.taxonomies["tags"].terms["t"]
    assert term.extra_context["taxonomy"] is listed.taxonomies["tags"]
    assert term.extra_context["paginator"].total == 5
    assert listed.get_page("/tags/t/page/3/").extra_context["paginator"].page == 3


def test_generating_twice_does_not_duplicate_pages(listed):
    first = listed.generate_list_pages()
    count = len(listed.all_pages)
    second = listed.generate_list_pages()
    assert len(listed.all_pages) == count
    assert sorted(p.url for p in first) == sorted(p.url for p in second)
    assert not any(page in listed.all_pages for page in first)


def test_empty_section_still_has_its_list_page(files):
    files.page("posts/_index.md", title="Posts")
    site = files.load()
    assert site.generate_list_pages()[0].kind == "taxonomy"
    paginator = site.sections["posts"].index.extra_context["paginator"]
    assert paginator.items == [] and paginator.pages == 1
