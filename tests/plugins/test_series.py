from __future__ import annotations

from inkstone.plugins.builtin.series import SeriesPlugin

from .helpers import day, make_page, make_site


def part(title, date, series="Building it", **meta):
    meta = {"series": series, **meta} if series else meta
    page = make_page(title, date=date, meta=meta)
    page.source_path = f"posts/{page.slug}.md"
    return page


def load(config, pages, **settings):
    site = make_site(config, pages)
    plugin = SeriesPlugin(config, settings)
    plugin.content_loaded(site)
    return plugin, site


def test_parts_are_ordered_by_date(config):
    third = part("Third", day(2024, 3, 1))
    first = part("First", day(2024, 1, 1))
    second = part("Second", day(2024, 2, 1))
    load(config, [third, first, second])
    assert [page.title for page in first.series.pages] == ["First", "Second", "Third"]
    assert first.series.parts is first.series.pages
    assert (first.series.index, second.series.index, third.series.index) == (1, 2, 3)
    assert first.series.total == 3


def test_what_templates_read(config):
    first = part("First", day(2024, 1, 1))
    second = part("Second", day(2024, 2, 1))
    load(config, [first, second])
    info = second.series
    assert info.title == info.name == "Building it"
    assert info.slug == "building-it"
    assert info.url == "/series/building-it/"
    assert info.prev is first and info.next is None
    assert first.series.prev is None and first.series.next is second
    assert first.series.first and not first.series.last
    assert second.series.last and not second.series.first


def test_pages_without_a_series_get_none(config):
    lone = part("Lone", day(2024, 1, 1), series=None)
    blank = part("Blank", day(2024, 1, 2), series="   ")
    plugin, _site = load(config, [lone, blank])
    assert lone.series is None and blank.series is None
    assert plugin.all == []


def test_series_names_are_matched_loosely(config):
    a = part("A", day(2024, 1, 1), series="Building Inkstone")
    b = part("B", day(2024, 1, 2), series="building inkstone ")
    plugin, _site = load(config, [a, b])
    assert len(plugin.all) == 1
    assert a.series.total == 2
    # the name as the first page (by URL) spells it
    assert plugin.all[0].name == "Building Inkstone"


def test_several_series_are_kept_apart_and_sorted_by_name(config):
    pages = [
        part("Z one", day(2024, 1, 1), series="Zebra"),
        part("A one", day(2024, 1, 2), series="apple"),
        part("Z two", day(2024, 1, 3), series="Zebra"),
    ]
    plugin, _site = load(config, pages)
    assert [(s.name, s.total) for s in plugin.all] == [("apple", 1), ("Zebra", 2)]
    assert pages[1].series.total == 1


def test_series_order_overrides_the_date(config):
    intro = part("Intro", day(2024, 6, 1), series_order=-1)
    one = part("One", day(2024, 1, 1))
    two = part("Two", day(2024, 2, 1))
    appendix = part("Appendix", day(2023, 1, 1), series_order=9)
    load(config, [one, two, intro, appendix])
    order = [page.title for page in one.series.pages]
    assert order == ["Intro", "One", "Two", "Appendix"]


def test_undated_parts_go_last_and_ties_use_the_title(config):
    b = part("Bravo", day(2024, 1, 1))
    a = part("Alpha", day(2024, 1, 1))
    undated = part("Undated", None)
    load(config, [undated, b, a])
    assert [page.title for page in a.series.pages] == ["Alpha", "Bravo", "Undated"]


def test_series_as_a_table_in_the_front_matter(config):
    page = part("A", day(2024, 1, 1), series={"name": "From a table"})
    load(config, [page])
    assert page.series.name == "From a table"


def test_index_pages(config):
    pages = [
        part("First", day(2024, 1, 1)),
        part("Second <2>", day(2024, 2, 1)),
        part("Solo", day(2024, 3, 1), series="Other things"),
    ]
    plugin, site = load(config, pages)
    generated = {page.url: page for page in plugin.generate_pages(site)}
    assert list(generated) == [
        "/series/",
        "/series/building-it/",
        "/series/other-things/",
    ]

    overview = generated["/series/"]
    assert overview.title == "Series"
    assert overview.template == "page.html"
    assert [s.name for s in overview.extra_context["all_series"]] == [
        "Building it",
        "Other things",
    ]
    html = str(overview.content)
    link = '<a href="/series/building-it/">Building it</a>'
    assert f"{link} <small>2 parts</small>" in html
    assert "<small>1 part</small>" in html

    one = generated["/series/building-it/"]
    assert one.title == "Building it"
    assert one.extra_context["series"] is plugin.all[0]
    listed = [page.title for page in one.extra_context["pages"]]
    assert listed == ["First", "Second <2>"]
    assert str(one.content) == (
        '<ol class="series__list">\n'
        '<li><a href="/first/">First</a></li>\n'
        '<li><a href="/second-2/">Second &lt;2&gt;</a></li>\n'
        "</ol>"
    )


def test_index_settings(config):
    pages = [part("First", day(2024, 1, 1))]
    plugin, site = load(config, pages, url="/multi-part/", title="Longer reads")
    generated = list(plugin.generate_pages(site))
    urls = [page.url for page in generated]
    assert urls == ["/multi-part/", "/multi-part/building-it/"]
    assert generated[0].title == "Longer reads"
    assert pages[0].series.url == "/multi-part/building-it/"

    plugin, site = load(config, pages, index=False)
    assert list(plugin.generate_pages(site)) == []


def test_no_series_no_pages(config):
    plugin, site = load(config, [part("Lone", day(2024, 1, 1), series=None)])
    assert list(plugin.generate_pages(site)) == []


def test_a_second_build_starts_over(config):
    first = part("First", day(2024, 1, 1))
    plugin, site = load(config, [first])
    second = part("Second", day(2024, 2, 1))
    plugin.content_loaded(make_site(config, [first, second]))
    assert len(plugin.all) == 1
    assert first.series.total == 2
    assert first.series.next is second
