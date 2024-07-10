from __future__ import annotations

import datetime as dt

import pytest

from inkstone.content import Page, permalinks
from inkstone.content.page import output_path_for
from inkstone.errors import ConfigError, ContentError

UTC = dt.timezone.utc


def make_page(**fields):
    defaults = {
        "title": "Hello World",
        "slug": "hello-world",
        "date": dt.datetime(2024, 5, 3, 14, 30, tzinfo=UTC),
        "source_path": "posts/2024-05-03-hello-world.md",
    }
    defaults.update(fields)
    return Page(**defaults)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("/:year/:month/:slug/", "/2024/05/hello-world/"),
        ("/:year/:month/:day/:slug/", "/2024/05/03/hello-world/"),
        ("/n/:slug/", "/n/hello-world/"),
        ("/:section/:title/", "/posts/hello-world/"),
        ("/:section/:filename/", "/posts/2024-05-03-hello-world/"),
        ("/blog/:year-:month-:slug.html", "/blog/2024-05-hello-world.html"),
        ("/:slug", "/hello-world/"),
        ("//archive//:year///:slug/", "/archive/2024/hello-world/"),
        ("/fixed/", "/fixed/"),
    ],
)
def test_pattern_tokens(pattern, expected):
    assert permalinks.expand(pattern, make_page(), "posts") == expected


def test_title_token_slugifies_the_title():
    page = make_page(title="Crème Brûlée & Co.", slug="other")
    assert permalinks.expand("/:title/", page) == "/creme-brulee-and-co/"


def test_title_token_falls_back_to_the_slug_for_untransliterable_titles():
    page = make_page(title="日本語", slug="nihongo")
    assert permalinks.expand("/:title/", page) == "/nihongo/"


def test_dates_are_zero_padded_and_use_the_page_timezone():
    late = dt.datetime(2024, 1, 9, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-8)))
    page = make_page(date=late)
    assert permalinks.expand("/:year/:month/:day/", page) == "/2024/01/09/"


def test_date_token_without_a_date_raises_missing_date():
    page = make_page(date=None)
    with pytest.raises(permalinks.MissingDate) as excinfo:
        permalinks.expand("/:year/:slug/", page, "posts")
    assert isinstance(excinfo.value, ContentError)
    assert excinfo.value.path == "posts/2024-05-03-hello-world.md"
    assert "needs a date" in excinfo.value.message


def test_pattern_without_date_tokens_works_for_undated_pages():
    assert permalinks.expand("/p/:slug/", make_page(date=None)) == "/p/hello-world/"


def test_unknown_token_is_a_config_error():
    with pytest.raises(ConfigError, match="unknown token ':nope'"):
        permalinks.expand("/:nope/", make_page())


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ("posts", "/:year/:slug/"),
        ("docs", "/d/:slug/"),
        ("docs/guide", "/d/:slug/"),
        ("docs/guide/deep", "/deep/:slug/"),
        ("notes", None),
        ("", None),
        (None, None),
    ],
)
def test_pattern_lookup_walks_up_to_parent_sections(section, expected):
    patterns = {
        "posts": "/:year/:slug/",
        "docs": "/d/:slug/",
        "docs/guide/deep": "/deep/:slug/",
    }
    assert permalinks.pattern_for(section, patterns) == expected


def test_page_url_without_a_pattern_mirrors_the_path():
    page = make_page(slug="setup")
    assert permalinks.page_url(page, "docs/guide") == "/docs/guide/setup/"
    assert permalinks.page_url(page, "") == "/setup/"
    assert permalinks.default_url(page, "My Notes") == "/my-notes/setup/"


def test_page_url_with_a_pattern():
    url = permalinks.page_url(
        make_page(), "posts", permalinks={"posts": "/:year/:month/:slug/"}
    )
    assert url == "/2024/05/hello-world/"


@pytest.mark.parametrize(
    ("pretty", "expected"),
    [(True, "/docs/setup/"), (False, "/docs/setup.html")],
)
def test_pretty_and_ugly_urls(pretty, expected):
    page = make_page(slug="setup", source_path="docs/setup.md")
    assert permalinks.page_url(page, "docs", pretty=pretty) == expected


def test_ugly_urls_leave_explicit_file_names_alone():
    page = make_page()
    url = permalinks.page_url(
        page, "posts", permalinks={"posts": "/:slug.htm"}, pretty=False
    )
    assert url == "/hello-world.htm"
    assert permalinks.ugly("/") == "/"
    assert permalinks.ugly("/a/b/") == "/a/b.html"


def test_bundles_keep_a_directory_url_even_when_ugly():
    page = make_page(slug="trip", source_path="posts/trip/index.md")
    assert permalinks.page_url(page, "posts", pretty=False) == "/posts/trip/"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("posts", "/posts/"),
        ("docs/guide", "/docs/guide/"),
        ("Field Notes", "/field-notes/"),
        ("", "/"),
    ],
)
def test_section_urls(name, expected):
    assert permalinks.section_url(name) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("/", "index.html"),
        ("/about/", "about/index.html"),
        ("/2024/05/hello/", "2024/05/hello/index.html"),
        ("/about.html", "about.html"),
        ("/feed.xml", "feed.xml"),
        ("/404.html", "404.html"),
        ("/old-address", "old-address/index.html"),
        ("/a/b?x=1#frag", "a/b/index.html"),
    ],
)
def test_output_path_for_a_url(url, expected):
    assert output_path_for(url) == expected


def test_output_path_can_be_set_explicitly():
    page = Page.virtual("/feed/")
    assert page.output_path == "feed/index.html"
    page.output_path = "feed\\custom.xml"
    assert page.output_path == "feed/custom.xml"
    page.output_path = None
    assert page.output_path == "feed/index.html"


def test_pages_from_the_loader_get_ugly_urls_when_configured(files):
    files.page("about.md", title="About")
    files.page("posts/2024-05-03-hello.md", title="Hello")
    files.page("posts/trip/index.md", title="Trip", date="2024-06-01")
    files.page("posts/_index.md", title="Posts")
    site = files.load(**{"build.pretty_urls": False})
    by_title = {page.title: page for page in site.pages}
    assert by_title["About"].url == "/about.html"
    assert by_title["About"].output_path == "about.html"
    assert by_title["Hello"].url == "/2024/05/hello.html"
    assert by_title["Trip"].url == "/2024/06/trip/"
    # list pages stay directories
    assert site.sections["posts"].url == "/posts/"


def test_undated_page_in_a_dated_section_falls_back_with_a_warning(files):
    files.page("posts/someday.md", title="Someday")
    site = files.load()
    assert site.pages[0].url == "/posts/someday/"
    (warning,) = site.warnings
    assert "content/posts/someday.md" in warning
    assert "/:year/:month/:slug/" in warning


def test_explicit_url_in_front_matter_wins(files):
    files.page("posts/a.md", title="A", date="2024-01-01", url="/custom/place")
    files.page("b.md", title="B", url="/files/b.html")
    site = files.load()
    assert site.get_page("posts/a.md").url == "/custom/place/"
    assert site.get_page("b.md").url == "/files/b.html"
    assert site.get_page("b.md").output_path == "files/b.html"


def test_nested_sections_inherit_the_parent_pattern(files):
    files.configure("permalinks:\n  notes: /n/:slug/\n")
    files.page("notes/2024/deep.md", title="Deep")
    assert files.load().pages[0].url == "/n/deep/"


def test_collisions_are_found_and_described(files):
    files.page("posts/a.md", title="A", url="/same/")
    files.page("notes/b.md", title="B", url="/same/")
    files.page("fine.md", title="Fine")
    site = files.load()
    collisions = permalinks.find_collisions(site.all_pages)
    assert list(collisions) == ["same/index.html"]
    assert sorted(p.source_path for p in collisions["same/index.html"]) == [
        "notes/b.md",
        "posts/a.md",
    ]
    with pytest.raises(ContentError) as excinfo:
        permalinks.check_collisions(site.all_pages)
    message = excinfo.value.message
    assert message.startswith("duplicate URL: ")
    assert "notes/b.md" in message and "posts/a.md" in message
    assert "same/index.html" in message


def test_collisions_ignore_case_and_count_generated_pages(files):
    files.page("About.md", title="About", url="/About/")
    site = files.load()
    site.add_page(Page.virtual("/about/", title="Generated"))
    collisions = permalinks.find_collisions(site.all_pages)
    assert len(collisions) == 1
    description = permalinks.describe_collision(*next(iter(collisions.items())))
    assert "About.md" in description
    assert "a generated virtual page (/about/)" in description


def test_no_collisions_is_fine(files):
    files.page("a.md", title="A")
    files.page("b.md", title="B")
    site = files.load()
    assert permalinks.find_collisions(site.all_pages) == {}
    permalinks.check_collisions(site.all_pages)
