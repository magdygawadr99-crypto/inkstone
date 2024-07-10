from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstone.content import Page, Resource
from inkstone.tmpl import DictLoader, Environment, Markup


def test_virtual_page_defaults():
    page = Page.virtual("/archive/")
    assert page.kind == "virtual"
    assert page.url == "/archive/"
    assert page.title == ""
    assert page.template is None
    assert page.content == Markup("")
    assert page.source_path is None
    assert page.section is None
    assert page.extra_context == {}
    assert page.output_path == "archive/index.html"
    assert page.slug == "archive"
    assert page.is_generated


def test_virtual_page_takes_context_and_content():
    posts = [object()]
    page = Page.virtual(
        "/archive/",
        title="Archive",
        template="archive.html",
        content="<p>Hi</p>",
        kind="page",
        posts=posts,
        year=2024,
    )
    assert page.title == "Archive"
    assert page.template == "archive.html"
    assert page.kind == "page"
    assert isinstance(page.content, Markup)
    assert page.content == "<p>Hi</p>"
    assert page.extra_context == {"posts": posts, "year": 2024}


def test_virtual_page_url_gets_a_leading_slash():
    assert Page.virtual("feed.xml").url == "/feed.xml"
    assert Page.virtual("feed.xml").output_path == "feed.xml"


def test_virtual_pages_do_not_share_state():
    first, second = Page.virtual("/a/"), Page.virtual("/b/")
    first.extra_context["x"] = 1
    first.aliases.append("/old/")
    first.tags.append("t")
    assert second.extra_context == {} and second.aliases == [] and second.tags == []


def test_plugins_can_attach_attributes():
    page = Page.virtual("/a/")
    page.related = ["other"]
    page.series = SimpleNamespace(name="Building")
    assert page.related == ["other"]
    assert not hasattr(Page, "__slots__")
    env = Environment(loader=DictLoader({"t": "{{ page.series.name }}"}))
    assert env.get_template("t").render(page=page) == "Building"


def test_permalink_joins_the_base_url():
    page = Page.virtual("/about/")
    assert page.permalink == "/about/"
    page.site = SimpleNamespace(base_url="https://example.com/blog/")
    assert page.permalink == "https://example.com/blog/about/"
    page.permalink = "https://elsewhere.example/x/"
    assert page.permalink == "https://elsewhere.example/x/"
    page.permalink = None
    assert page.permalink == "https://example.com/blog/about/"


def test_tags_and_categories_are_views_of_taxonomies():
    page = Page(taxonomies={"tags": ["a"], "series": ["s"]})
    assert page.tags == ["a"]
    assert page.categories == []
    page.tags = ("x", "y")
    page.categories = ["c"]
    assert page.taxonomies == {"tags": ["x", "y"], "series": ["s"], "categories": ["c"]}
    page.tags.append("z")
    assert page.taxonomies["tags"] == ["x", "y", "z"]


def test_word_count_and_reading_time_from_the_source():
    page = Page(raw="one two three four five")
    assert page.word_count == 5
    assert page.reading_time == 1
    long = Page(raw="word " * 900)
    assert long.word_count == 900
    assert long.reading_time == 5


def test_reading_time_is_at_least_one_minute_even_for_nothing():
    assert Page().reading_time == 1
    assert Page().word_count == 0


def test_counts_use_the_rendered_content_once_there_is_one():
    page = Page(raw="one two")
    page.content = Markup("<p>one <em>two</em> three</p>")
    assert page.word_count == 3


def test_plugins_can_set_the_counts():
    page = Page(raw="one two three")
    page.word_count = 120
    page.reading_time = 7
    assert (page.word_count, page.reading_time) == (120, 7)
    page.word_count = None
    assert page.word_count == 3


def test_kind_helpers():
    assert Page(kind="page").is_page
    assert Page(kind="section").is_section and Page(kind="section").is_list
    assert Page(kind="home").is_home and Page(kind="home").is_list
    assert Page(kind="term").is_list
    assert not Page(kind="taxonomy").is_list
    assert not Page(kind="page").is_list


@pytest.mark.parametrize(
    ("source", "filename", "bundle"),
    [
        ("posts/2024-05-03-hello.md", "2024-05-03-hello", False),
        ("posts/trip/index.md", "trip", True),
        ("posts/_index.md", "posts", False),
        ("about.md", "about", False),
        (None, "", False),
    ],
)
def test_filename_and_bundle(source, filename, bundle):
    page = Page(source_path=source)
    assert page.filename == filename
    assert page.is_bundle is bundle


def test_private_attributes_are_hidden_from_templates():
    page = Page(title="T")
    source = "[{{ page._rendered }}][{{ page.title }}]"
    env = Environment(loader=DictLoader({"t": source}))
    assert env.get_template("t").render(page=page) == "[][T]"


def test_repr_shows_kind_and_url():
    assert repr(Page.virtual("/a/")) == "<Page virtual /a/>"


def test_resource():
    resource = Resource(
        "img/photo.JPG", "/trip/img/photo.JPG", "posts/trip/img/photo.JPG"
    )
    assert resource.name == "img/photo.JPG"
    assert resource.output_path == "trip/img/photo.JPG"
    assert resource.ext == ".jpg"
    assert resource.is_image
    assert str(resource) == "/trip/img/photo.JPG"
    assert resource.path is None
    assert not Resource("notes.pdf", "/n.pdf", "n.pdf").is_image
    same = Resource("img/photo.JPG", "/trip/img/photo.JPG", "posts/trip/img/photo.JPG")
    assert resource == same and hash(resource) == hash(same)
    assert resource != Resource("other", "/other", "other")
    assert "photo.JPG" in repr(resource)
