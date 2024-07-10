from __future__ import annotations

import datetime as dt

import pytest

from inkstone.content import Page, Section, Site, load_site
from inkstone.errors import ContentError
from inkstone.tmpl import Markup

from .conftest import NOW


def urls(pages):
    return [page.url for page in pages]


def test_empty_content_directory_gives_a_site_with_a_home_page(files):
    site = files.load()
    assert isinstance(site, Site)
    assert site.pages == []
    assert site.sections == {}
    assert site.home.kind == "home"
    assert site.home.url == "/"
    assert site.home.title == "My Site"
    assert site.home.source_path is None
    assert site.all_pages == [site.home]
    assert site.build_time == NOW


def test_missing_content_directory_is_a_warning_not_an_error(files, capsys):
    (files.root / "content").rmdir()
    site = files.load()
    assert site.pages == []
    assert any("does not exist" in message for message in site.warnings)
    assert "does not exist" in capsys.readouterr().err


def test_top_level_page(files):
    files.page("about.md", "Hello *there*.\n", title="About me", description="Who")
    site = files.load()
    (page,) = site.pages
    assert isinstance(page, Page)
    assert page.kind == "page"
    assert page.title == "About me"
    assert page.description == "Who"
    assert page.slug == "about"
    assert page.url == "/about/"
    assert page.output_path == "about/index.html"
    assert page.source_path == "about.md"
    assert page.file_path == files.root.resolve() / "content" / "about.md"
    assert page.section is None
    assert page.raw == "Hello *there*.\n"
    assert page.content == Markup("")
    assert page.permalink == "http://localhost:8000/about/"
    assert page.site is site
    assert page.date is None
    assert page.draft is False
    assert page.weight == 0


def test_home_page_from_index_file(files):
    files.page("_index.md", "Welcome.\n", title="Start here", paginate=3)
    site = files.load()
    assert site.home.title == "Start here"
    assert site.home.source_path == "_index.md"
    assert site.home.raw == "Welcome.\n"
    assert site.home.url == "/"
    assert site.home.section is None
    assert site.home.paginate == 3
    assert site.pages == []


def test_home_page_without_a_title_uses_the_site_title(files):
    files.write("_index.md", "Just text.\n")
    assert files.load(title="Wet Ink").home.title == "Wet Ink"


def test_plain_index_md_at_the_root_is_the_home_page_too(files):
    files.page("index.md", title="Front")
    site = files.load()
    assert site.home.title == "Front"
    assert site.pages == []


def test_two_home_pages_are_an_error(files):
    files.page("_index.md", title="One")
    files.page("index.md", title="Two")
    with pytest.raises(ContentError, match="two files want to be the home page"):
        files.load()


def test_directories_are_sections(files):
    files.page("posts/_index.md", "Intro.\n", title="Writing", description="All of it")
    files.page("posts/first.md", title="First", date="2024-01-02")
    files.page("posts/second.md", title="Second", date="2024-02-03")
    site = files.load(permalinks={})
    section = site.sections["posts"]
    assert isinstance(section, Section)
    assert section.name == "posts"
    assert section.title == "Writing"
    assert section.description == "All of it"
    assert section.url == "/posts/"
    assert section.parent is None
    assert section.index.kind == "section"
    assert section.index.url == "/posts/"
    assert section.index.raw == "Intro.\n"
    assert section.index.section is section
    assert section.meta["title"] == "Writing"
    assert urls(section.pages) == ["/posts/second/", "/posts/first/"]
    assert all(page.section is section for page in section.pages)
    assert site.get_section("posts") is section
    assert site.get_section("/posts/") is section
    assert site.get_section("nope") is None


def test_section_without_an_index_file_gets_a_title_from_its_name(files):
    files.page("field-notes/one.md", title="One")
    site = files.load()
    section = site.sections["field-notes"]
    assert section.title == "Field Notes"
    assert section.index.source_path is None
    assert section.index.kind == "section"
    assert section.paginate is None
    assert section.sort_by == "date"


def test_nested_sections(files):
    files.page("docs/_index.md", title="Docs")
    files.page("docs/install.md", title="Install")
    files.page("docs/guide/_index.md", title="Guide")
    files.page("docs/guide/first-steps.md", title="First steps")
    site = files.load()
    docs, guide = site.sections["docs"], site.sections["docs/guide"]
    assert guide.parent is docs
    assert docs.subsections == [guide]
    assert guide.url == "/docs/guide/"
    assert urls(docs.pages) == ["/docs/install/"]
    assert urls(guide.pages) == ["/docs/guide/first-steps/"]
    assert urls(docs.all_pages) == ["/docs/guide/first-steps/", "/docs/install/"]
    assert guide.ancestors == [docs]
    assert guide.depth == 2
    assert site.top_sections == [docs]
    page = guide.pages[0]
    assert page.in_section("docs") and page.in_section("docs/guide")
    assert not page.in_section("posts")


def test_intermediate_directories_become_sections(files):
    files.page("a/b/c/deep.md", title="Deep")
    site = files.load()
    assert sorted(site.sections) == ["a", "a/b", "a/b/c"]
    assert site.sections["a/b"].parent is site.sections["a"]
    assert site.sections["a"].pages == []


def test_all_pages_holds_home_sections_and_pages(files):
    files.page("about.md", title="About")
    files.page("posts/a.md", title="A")
    site = files.load()
    kinds = sorted(page.kind for page in site.all_pages)
    assert kinds == ["home", "page", "page", "section"]
    assert sorted(urls(site.pages)) == sorted(
        page.url for page in site.all_pages if page.kind == "page"
    )


@pytest.mark.parametrize("sort_by", ["date", "weight", "title"])
def test_section_sort_orders(files, sort_by):
    files.page("notes/_index.md", title="Notes", sort_by=sort_by)
    files.page("notes/b.md", title="Banana", date="2024-01-01", weight=3)
    files.page("notes/a.md", title="apple", date="2024-03-01", weight=2)
    files.page("notes/c.md", title="Cherry", date="2024-02-01", weight=1)
    section = files.load().sections["notes"]
    expected = {
        "date": ["apple", "Cherry", "Banana"],
        "weight": ["Cherry", "apple", "Banana"],
        "title": ["apple", "Banana", "Cherry"],
    }[sort_by]
    assert [page.title for page in section.pages] == expected
    assert section.sort_by == sort_by


def test_undated_pages_sort_after_dated_ones(files):
    files.page("notes/undated.md", title="Aardvark")
    files.page("notes/dated.md", title="Zebra", date="2020-01-01")
    section = files.load().sections["notes"]
    assert [page.title for page in section.pages] == ["Zebra", "Aardvark"]


def test_prev_and_next_follow_the_section_order(files):
    for day in (1, 2, 3):
        files.page(f"posts/p{day}.md", title=f"Post {day}", date=f"2024-01-0{day}")
    files.page("about.md", title="About")
    site = files.load()
    newest, middle, oldest = site.sections["posts"].pages
    assert newest.prev is None and newest.next is middle
    assert middle.prev is newest and middle.next is oldest
    assert oldest.prev is middle and oldest.next is None
    about = site.get_page("about.md")
    assert about.prev is None and about.next is None


def test_unknown_sort_order_is_an_error(files):
    files.page("notes/_index.md", sort_by="random")
    files.page("notes/a.md", title="A")
    with pytest.raises(ContentError) as excinfo:
        files.load()
    assert "sort_by must be one of date, weight, title" in excinfo.value.message
    assert excinfo.value.path == "content/notes/_index.md"
    assert excinfo.value.line == 2


@pytest.mark.parametrize(
    ("value", "expected"), [("12", 12), ("false", 0), ("true", None), ("0", 0)]
)
def test_section_paginate_setting(files, value, expected):
    files.write("posts/_index.md", f"---\npaginate: {value}\n---\n")
    files.page("posts/a.md", title="A")
    assert files.load().sections["posts"].paginate == expected


def test_bad_paginate_is_an_error(files):
    files.write("posts/_index.md", "---\npaginate: lots\n---\n")
    with pytest.raises(ContentError, match="paginate must be a number of items"):
        files.load()


def test_page_bundle(files):
    files.page(
        "posts/trip/index.md", "![](photo.jpg)\n", title="Trip", date="2024-06-01"
    )
    files.write("posts/trip/photo.jpg", "jpeg bytes")
    files.write("posts/trip/maps/route.svg", "<svg/>")
    site = files.load()
    (page,) = site.pages
    assert page.is_bundle
    assert page.slug == "trip"
    assert page.url == "/2024/06/trip/"
    assert page.section is site.sections["posts"]
    assert sorted(site.sections) == ["posts"]
    names = [resource.name for resource in page.resources]
    assert names == ["maps/route.svg", "photo.jpg"]
    photo = page.get_resource("photo.jpg")
    assert photo.url == "/2024/06/trip/photo.jpg"
    assert photo.source_path == "posts/trip/photo.jpg"
    assert photo.output_path == "2024/06/trip/photo.jpg"
    assert photo.path == files.root.resolve() / "content/posts/trip/photo.jpg"
    assert photo.is_image and photo.ext == ".jpg"
    assert page.get_resource("nope.png") is None


def test_markdown_inside_a_bundle_is_not_a_page(files):
    files.page("posts/trip/index.md", title="Trip", date="2024-06-01")
    files.page("posts/trip/notes.md", title="Notes")
    site = files.load()
    assert [page.title for page in site.pages] == ["Trip"]
    assert site.pages[0].resources == []
    assert any("inside a page bundle" in message for message in site.warnings)


def test_bundle_date_and_slug_come_from_the_directory_name(files):
    files.page("posts/2024-03-09-boat-trip/index.md", title="Boat")
    (page,) = files.load().pages
    assert page.date == dt.datetime(2024, 3, 9, tzinfo=dt.timezone.utc)
    assert page.slug == "boat-trip"
    assert page.url == "/2024/03/boat-trip/"


def test_loose_files_in_sections_are_copied_as_resources(files):
    files.page("docs/setup.md", title="Setup")
    files.write("docs/diagram.png", "png")
    files.write("robots-extra.txt", "x")
    files.write("downloads/tool.zip", "zip")
    site = files.load()
    by_url = {resource.url: resource for resource in site.resources}
    assert sorted(by_url) == [
        "/docs/diagram.png",
        "/downloads/tool.zip",
        "/robots-extra.txt",
    ]
    assert by_url["/docs/diagram.png"].source_path == "docs/diagram.png"
    assert site.sections["docs"].resources == [by_url["/docs/diagram.png"]]
    # a directory with nothing but files is not a section
    assert "downloads" not in site.sections


def test_ignore_patterns_and_hidden_files_are_skipped(files):
    files.configure("ignore: ['*.bak', 'private/', '*~']\n")
    files.page("keep.md", title="Keep")
    files.page("old.md.bak", title="Old")
    files.page("private/secret.md", title="Secret")
    files.page(".hidden.md", title="Hidden")
    files.page("posts/.drafts/x.md", title="X")
    files.write("notes.md~", "junk")
    site = files.load()
    assert [page.title for page in site.pages] == ["Keep"]
    assert site.resources == []
    assert site.sections == {}


def test_markdown_extension_variants(files):
    files.page("one.markdown", title="One")
    files.page("TWO.MD", title="Two")
    assert sorted(page.title for page in files.load().pages) == ["One", "Two"]


def test_drafts_are_left_out_unless_asked_for(files):
    files.page("posts/done.md", title="Done", date="2024-01-01")
    files.page("posts/wip.md", title="WIP", date="2024-01-02", draft=True)
    site = files.load()
    assert [page.title for page in site.pages] == ["Done"]
    assert site.skipped["draft"] == ["posts/wip.md"]
    with_drafts = files.load(drafts=True)
    assert [page.title for page in with_drafts.pages] == ["WIP", "Done"]
    assert with_drafts.pages[0].draft is True
    assert with_drafts.skipped["draft"] == []


def test_drafts_follow_the_config_when_not_given(files):
    files.page("wip.md", title="WIP", draft=True)
    config = files.config(**{"build.drafts": True})
    assert [page.title for page in load_site(config, now=NOW).pages] == ["WIP"]


def test_a_section_of_only_drafts_does_not_exist(files):
    files.page("ideas/one.md", title="One", draft=True)
    assert files.load().sections == {}


def test_draft_section_index_hides_the_whole_section(files):
    files.page("secret/_index.md", title="Secret", draft=True)
    files.page("secret/plan.md", title="Plan")
    files.page("secret/deeper/more.md", title="More")
    files.write("secret/file.pdf", "pdf")
    site = files.load()
    assert site.pages == [] and site.sections == {} and site.resources == []
    shown = files.load(drafts=True)
    assert sorted(shown.sections) == ["secret", "secret/deeper"]
    assert len(shown.pages) == 2


def test_future_pages_wait_for_their_date(files):
    files.page("posts/past.md", title="Past", date="2024-06-14")
    files.page("posts/later.md", title="Later", date="2024-06-16")
    site = files.load()
    assert [page.title for page in site.pages] == ["Past"]
    assert site.skipped["future"] == ["posts/later.md"]
    assert [p.title for p in files.load(future=True).pages] == ["Later", "Past"]
    tomorrow = NOW + dt.timedelta(days=2)
    assert [p.title for p in files.load(now=tomorrow).pages] == ["Later", "Past"]


def test_future_follows_the_config_when_not_given(files):
    files.page("posts/later.md", title="Later", date="2999-01-01")
    assert len(files.load(**{"build.future": True}).pages) == 1


def test_naive_now_is_taken_to_be_in_the_site_timezone(files):
    files.page("posts/later.md", title="Later", date="2024-06-15 13:00")
    site = files.load(now=dt.datetime(2024, 6, 15, 12, 30))
    assert site.pages == []
    assert site.build_time.tzinfo is not None


@pytest.mark.parametrize(
    ("name", "date", "slug"),
    [
        ("2024-05-03-hello-world.md", dt.date(2024, 5, 3), "hello-world"),
        ("2024-05-03_hello.md", dt.date(2024, 5, 3), "hello"),
        ("2024-5-3-short.md", dt.date(2024, 5, 3), "short"),
        ("hello-world.md", None, "hello-world"),
        ("2024-13-45-not-a-date.md", None, "2024-13-45-not-a-date"),
        ("2024-05-03.md", dt.date(2024, 5, 3), "2024-05-03"),
        ("My Post_Title.md", None, "my-post-title"),
    ],
)
def test_date_and_slug_from_the_file_name(files, name, date, slug):
    files.write(f"notes/{name}", "Text.\n")
    (page,) = files.load().pages
    assert (page.date.date() if page.date else None) == date
    assert page.slug == slug
    assert page.url == f"/notes/{slug}/"


def test_title_falls_back_to_the_file_name(files):
    files.write("notes/2024-05-03-hello-world.md", "Text.\n")
    assert files.load().pages[0].title == "Hello World"


def test_front_matter_beats_the_file_name(files):
    files.page(
        "notes/2024-05-03-hello.md", title="Hi", date="2023-01-02", slug="Other Name"
    )
    (page,) = files.load().pages
    assert page.date.date() == dt.date(2023, 1, 2)
    assert page.slug == "other-name"


def test_dates_get_the_configured_timezone(files):
    files.configure("timezone: '+02:00'\n")
    files.page("a.md", date="2024-05-03")
    files.page("b.md", date="2024-05-03 14:30")
    files.page("c.md", date="2024-05-03T14:30:00+09:00", updated="May 4, 2024")
    files.write("2024-05-01-named.md", "x\n")
    site = files.load()
    two_hours = dt.timedelta(hours=2)
    a, b, c = (site.get_page(name) for name in ("a.md", "b.md", "c.md"))
    assert a.date.utcoffset() == two_hours and a.date.hour == 0
    assert b.date.utcoffset() == two_hours and b.date.hour == 14
    assert c.date.utcoffset() == dt.timedelta(hours=9)
    assert c.updated.utcoffset() == two_hours
    assert c.updated.date() == dt.date(2024, 5, 4)
    named = site.get_page("2024-05-01-named.md")
    assert named.date.utcoffset() == two_hours


def test_toml_and_json_front_matter(files):
    files.write("j.md", '{"title": "From JSON", "tags": ["a"]}\nBody.\n')
    site = files.load()
    assert site.get_page("j.md").title == "From JSON"
    assert site.get_page("j.md").raw == "Body.\n"


def test_taxonomy_terms_from_front_matter(files):
    files.configure("taxonomies:\n  tags: tag\n  series: series\n")
    files.page("a.md", tags=["python", "parsing", "python"], series="Building")
    files.page("b.md", categories=["Notes"], authors=["me"])
    site = files.load()
    a, b = site.get_page("a.md"), site.get_page("b.md")
    assert a.tags == ["python", "parsing"]
    assert a.taxonomies == {"tags": ["python", "parsing"], "series": ["Building"]}
    assert a.categories == []
    # categories always work as a shortcut, taxonomy or not
    assert b.categories == ["Notes"]
    # authors is no taxonomy here, so it is just a param
    assert b.params["authors"] == ["me"]
    assert "tags" not in a.params and "series" not in a.params


def test_params_are_the_keys_we_do_not_interpret(files):
    files.write(
        "a.md",
        """
        ---
        title: A
        date: 2024-01-01
        draft: false
        weight: 3
        template: special.html
        aliases: [/old/, older/]
        summary: Short.
        toc: false
        image: /img/a.png
        nested:
          deep: 1
        ---
        Body.
        """,
    )
    (page,) = files.load().pages
    assert dict(page.params) == {
        "toc": False,
        "image": "/img/a.png",
        "nested": {"deep": 1},
    }
    assert page.params.nested.deep == 1
    assert page.meta["title"] == "A"
    assert page.meta["toc"] is False
    assert page.template == "special.html"
    assert page.aliases == ["/old/", "/older/"]
    assert page.weight == 3


@pytest.mark.parametrize(
    ("front_matter", "message", "line"),
    [
        ("draft: 'yes'", "draft must be true or false, got 'yes' (a string)", 3),
        ("weight: heavy", "weight must be a whole number", 3),
        ("slug: [a, b]", "slug must be a string, got ['a', 'b'] (a list)", 3),
        ("tags: {a: 1}", "tags must be a list of strings", 3),
        ("tags: [a, [b]]", "tags must be a list of strings, but it contains", 3),
        ("date: next tuesday", "bad date: unrecognised date format", 3),
        ("date: 2024-02-30", "bad date", 3),
        ("updated: 12", "bad updated", 3),
        ("template: 3.5.1.2\naliases: {a: b}", "aliases must be a list of strings", 4),
        ("description: [x]", "description must be a string", 3),
    ],
)
def test_wrong_front_matter_types_name_file_and_line(
    files, front_matter, message, line
):
    files.write("posts/bad.md", f"---\ntitle: Bad\n{front_matter}\n---\nBody.\n")
    with pytest.raises(ContentError) as excinfo:
        files.load()
    error = excinfo.value
    assert message in error.message
    assert error.path == "content/posts/bad.md"
    assert error.line == line
    assert str(error).startswith(f"content/posts/bad.md:{line}: ")


def test_numbers_are_accepted_as_titles(files):
    files.write("a.md", "---\ntitle: 1984\n---\n")
    assert files.load().pages[0].title == "1984"


def test_single_tag_may_be_written_as_a_string(files):
    files.write("a.md", "---\ntags: python\n---\n")
    assert files.load().pages[0].tags == ["python"]


def test_broken_front_matter_names_the_file(files):
    files.write("posts/broken.md", "---\ntitle: [unclosed\n---\nBody.\n")
    with pytest.raises(ContentError) as excinfo:
        files.load()
    assert "invalid YAML front matter" in excinfo.value.message
    assert excinfo.value.path == "content/posts/broken.md"
    assert excinfo.value.line == 2


def test_file_that_is_not_utf8_names_the_file(files):
    path = files.root / "content" / "latin.md"
    path.write_bytes(b"---\ntitle: Caf\xe9\n---\n")
    with pytest.raises(ContentError) as excinfo:
        files.load()
    assert "not valid UTF-8" in excinfo.value.message
    assert excinfo.value.path == "content/latin.md"


def test_lenient_load_collects_problems_instead_of_raising(files):
    files.page("good.md", title="Good")
    files.write("bad.md", "---\ndraft: maybe\n---\n")
    files.write("worse.md", "---\ndate: someday\n---\n")
    site = files.load(strict=False)
    assert [page.title for page in site.pages] == ["Good"]
    kinds = sorted((problem.kind, problem.source) for problem in site.problems)
    assert kinds == [("bad-date", "worse.md"), ("front-matter", "bad.md")]
    assert site.problems[0].line == 2


def test_two_index_files_in_one_directory_make_it_a_bundle(files):
    files.page("posts/x/index.md", title="Bundle")
    files.page("posts/x/_index.md", title="Section")
    site = files.load(permalinks={})
    assert [page.title for page in site.pages] == ["Bundle"]
    assert sorted(site.sections) == ["posts"]


def test_content_404_becomes_the_not_found_page(files):
    files.page("404.md", "Nothing here.\n", title="Lost?")
    site = files.load()
    assert site.pages == []
    (page,) = [page for page in site.all_pages if page.kind == "404"]
    assert page.url == "/404.html"
    assert page.output_path == "404.html"
    assert page.title == "Lost?"


def test_data_directory_is_loaded(files):
    files.write("links.yaml", "- name: a\n  url: /a/\n", base="data")
    files.write("team/roles.json", '{"lead": "Magdy"}', base="data")
    site = files.load()
    assert site.data.links[0].name == "a"
    assert site.data.team.roles.lead == "Magdy"
    assert site.get_data("team.roles.lead") == "Magdy"
    assert site.get_data("team.nobody.home") is None
    assert site.get_data("nope", "fallback") == "fallback"


def test_broken_data_file_is_a_content_error(files):
    files.write("bad.json", "{nope", base="data")
    with pytest.raises(ContentError, match="invalid JSON"):
        files.load()


def test_get_page_by_source_path_and_url(files):
    files.page("about.md", title="About")
    files.page("posts/2024-05-03-hello.md", title="Hello")
    files.page("posts/trip/index.md", title="Trip", date="2024-06-01")
    files.page("posts/_index.md", title="Posts")
    site = files.load()
    about = site.pages.where("title", "About").first()
    hello = site.pages.where("title", "Hello").first()
    trip = site.pages.where("title", "Trip").first()
    assert site.get_page("about.md") is about
    assert site.get_page("about") is about
    assert site.get_page("/about/") is about
    assert site.get_page("/about") is about
    assert site.get_page("content/about.md") is about
    assert site.get_page("posts/2024-05-03-hello.md") is hello
    assert site.get_page("posts\\2024-05-03-hello.md") is hello
    assert site.get_page("/2024/05/hello/") is hello
    assert site.get_page("/2024/05/hello/#part") is hello
    assert site.get_page("posts/trip") is trip
    assert site.get_page("posts/trip/index.md") is trip
    assert site.get_page("posts") is site.sections["posts"].index
    assert site.get_page("/") is site.home
    assert site.get_page("nope.md") is None
    assert site.get_page("") is None


def test_site_exposes_the_config_values(files):
    files.configure(
        "title: Wet Ink\nlanguage: de\nauthor:\n  name: Magdy\nparams:\n  accent: red\n"
    )
    site = files.load(base_url="https://example.com/blog")
    assert site.title == "Wet Ink"
    assert site.language == "de"
    assert site.base_url == "https://example.com/blog/"
    assert site.author.name == "Magdy"
    assert site.params.accent == "red"
    assert site.config.title == "Wet Ink"


def test_site_pages_are_newest_first_with_undated_last(files):
    files.page("posts/old.md", title="Old", date="2023-01-01")
    files.page("posts/new.md", title="New", date="2024-01-01")
    files.page("about.md", title="About")
    files.page("notes/mid.md", title="Mid", date="2023-06-01")
    site = files.load()
    assert [page.title for page in site.pages] == ["New", "Mid", "Old", "About"]
    assert [page.title for page in site.pages_by_date()] == ["New", "Mid", "Old"]
    assert [p.title for p in site.pages_by_date(newest_first=False)] == [
        "Old",
        "Mid",
        "New",
    ]


def test_add_page_registers_virtual_pages(files):
    files.page("about.md", title="About")
    site = files.load()
    extra = Page.virtual("/archive/", title="Archive", template="archive.html", n=3)
    assert site.add_page(extra) is extra
    assert extra.site is site
    assert extra in site.all_pages
    assert extra not in site.pages
    assert site.get_page("/archive/") is extra
    assert extra.permalink == "http://localhost:8000/archive/"
    assert extra.extra_context == {"n": 3}
    site.add_page(extra)
    assert site.all_pages.count(extra) == 1
    site.remove_page(extra)
    assert site.get_page("/archive/") is None
