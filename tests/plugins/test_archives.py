from __future__ import annotations

import pytest

from inkstone.errors import PluginError
from inkstone.plugins.builtin.archives import Archives
from inkstone.tmpl import DictLoader, Environment

from .helpers import day, make_config, make_page, make_site


class FakeBuilder:
    def __init__(self, templates):
        self.env = Environment(loader=DictLoader(templates))


def posts():
    return [
        make_page("May one", "/2024/05/one/", date=day(2024, 5, 3), section="posts"),
        make_page("May two", "/2024/05/two/", date=day(2024, 5, 20), section="posts"),
        make_page("January", "/2024/01/jan/", date=day(2024, 1, 9), section="posts"),
        make_page("Last year", "/2023/11/x/", date=day(2023, 11, 30), section="notes"),
        make_page("About", "/about/"),
    ]


def generate(config, pages=None, **settings):
    site = make_site(config, posts() if pages is None else pages)
    plugin = Archives(config, settings)
    return {page.url: page for page in plugin.generate_pages(site)}


def test_index_year_and_month_pages(config):
    pages = generate(config)
    assert list(pages) == [
        "/archive/",
        "/archive/2024/",
        "/archive/2024/05/",
        "/archive/2024/01/",
        "/archive/2023/",
        "/archive/2023/11/",
    ]
    assert pages["/archive/"].title == "Archive"
    assert pages["/archive/2024/"].title == "Archive: 2024"
    assert pages["/archive/2024/05/"].title == "Archive: May 2024"
    assert pages["/archive/2024/05/"].output_path == "archive/2024/05/index.html"
    assert all(page.kind == "virtual" for page in pages.values())


def test_context_of_the_index(config):
    context = generate(config)["/archive/"].extra_context
    assert [page.title for page in context["pages"]] == [
        "May two",
        "May one",
        "January",
        "Last year",
    ]
    assert [year.year for year in context["years"]] == [2024, 2023]
    assert context["year"] is None and context["month"] is None
    this_year = context["years"][0]
    assert (this_year.count, this_year.url) == (3, "/archive/2024/")
    assert [(m.month, m.name, m.count) for m in this_year.months] == [
        (5, "May", 2),
        (1, "January", 1),
    ]
    assert this_year.months[0].url == "/archive/2024/05/"


def test_context_of_year_and_month_pages(config):
    pages = generate(config)
    year = pages["/archive/2024/"].extra_context
    assert year["year"].year == 2024 and year["month"] is None
    assert [page.title for page in year["pages"]] == ["May two", "May one", "January"]
    assert len(year["years"]) == 2

    month = pages["/archive/2024/05/"].extra_context
    assert (month["year"].year, month["month"].month) == (2024, 5)
    assert [page.title for page in month["pages"]] == ["May two", "May one"]


def test_undated_pages_are_left_out(config):
    context = generate(config)["/archive/"].extra_context
    assert "About" not in [page.title for page in context["pages"]]


def test_falls_back_to_the_page_template_with_ready_made_content(config):
    pages = generate(config)
    index = pages["/archive/"]
    assert index.template == "page.html"
    html = str(index.content)
    assert '<h2 id="y2024"><a href="/archive/2024/">2024</a></h2>' in html
    assert '<h3 id="m2024-05"><a href="/archive/2024/05/">May</a></h3>' in html
    assert (
        '<li><time datetime="2024-05-20">May 20</time> '
        '<a href="/2024/05/two/">May two</a></li>'
    ) in html
    assert html.index("May two") < html.index("May one") < html.index("Last year")

    year = str(pages["/archive/2024/"].content)
    assert '<h2 id="m2024-01"><a href="/archive/2024/01/">January</a></h2>' in year
    assert "<strong>2024</strong>" in year
    assert '<a href="/archive/2023/">2023</a>' in year

    month = str(pages["/archive/2024/05/"].content)
    assert month.count("<li>") == 2
    assert '<a href="/archive/2024/">2024</a>' in month


def test_titles_are_escaped_in_the_generated_lists(config):
    page = make_page("Tom & <Jerry>", "/t/", date=day(2024, 2, 2))
    html = str(generate(config, [page])["/archive/"].content)
    assert "Tom &amp; &lt;Jerry&gt;" in html


def test_uses_the_theme_template_when_there_is_one(config):
    site = make_site(config, posts())
    plugin = Archives(config, {})
    plugin.setup(FakeBuilder({"archive.html": "x", "page.html": "y"}))
    assert {page.template for page in plugin.generate_pages(site)} == {"archive.html"}

    plugin = Archives(config, {"template": "lists/dated.html"})
    plugin.setup(FakeBuilder({"lists/dated.html": "x"}))
    used = {page.template for page in plugin.generate_pages(site)}
    assert used == {"lists/dated.html"}


def test_url_and_title_settings(config):
    pages = generate(config, url="history", title="Everything")
    assert "/history/" in pages and "/history/2024/05/" in pages
    assert pages["/history/"].title == "Everything"
    assert pages["/history/2023/"].title == "Everything: 2023"
    assert '<a href="/history/2024/">' in str(pages["/history/"].content)


def test_yearly_and_monthly_can_be_switched_off(config):
    only_index = generate(config, yearly=False, monthly=False)
    assert list(only_index) == ["/archive/"]
    html = str(only_index["/archive/"].content)
    assert '<h2 id="y2024">2024</h2>' in html
    assert '<h3 id="m2024-05">May</h3>' in html

    no_months = generate(config, monthly=False)
    assert list(no_months) == ["/archive/", "/archive/2024/", "/archive/2023/"]


def test_sections_setting(config):
    pages = generate(config, sections=["notes"])
    assert list(pages) == ["/archive/", "/archive/2023/", "/archive/2023/11/"]


def test_an_empty_site_still_gets_the_index(config):
    pages = generate(config, [make_page("About", "/about/")])
    assert list(pages) == ["/archive/"]
    assert "Nothing here yet" in str(pages["/archive/"].content)


def test_links_honour_a_base_path(tmp_path):
    config = make_config(tmp_path, base_url="https://example.com/blog/")
    html = str(generate(config)["/archive/"].content)
    assert '<a href="/blog/archive/2024/">' in html
    assert '<a href="/blog/2024/05/two/">' in html


def test_same_day_posts_are_ordered_by_title(config):
    pages = [
        make_page("Bravo", "/b/", date=day(2024, 3, 3)),
        make_page("Alpha", "/a/", date=day(2024, 3, 3)),
    ]
    context = generate(config, pages)["/archive/"].extra_context
    assert [page.title for page in context["pages"]] == ["Alpha", "Bravo"]


@pytest.mark.parametrize("settings", [{"url": 5}, {"yearly": "no"}, {"sections": {}}])
def test_bad_settings(config, settings):
    with pytest.raises(PluginError, match=r"\[plugin.archives\]"):
        Archives(config, settings)
