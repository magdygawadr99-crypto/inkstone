from __future__ import annotations

import datetime as dt

import pytest

from inkstone import __version__
from inkstone.build import keys
from inkstone.build.context import FILTER_NAMES, GLOBAL_NAMES, page_context
from inkstone.content import Page
from inkstone.errors import BuildError
from inkstone.tmpl import Markup


@pytest.fixture
def built(blog):
    blog.write("data/team/roles.json", '{"lead": "Magdy"}')
    builder = blog.builder()
    builder.build()
    return builder


def expr(builder, source, **variables):
    """Evaluate a template expression the way a page template would."""
    template = builder.env.from_string("{{ " + source + " }}", "probe.html")
    context = page_context(builder, builder.site.get_page("about.md"))
    context.update(variables)
    return template.render(context)


def test_contract_globals_and_filters_are_registered(built):
    for name in GLOBAL_NAMES:
        assert callable(built.env.globals[name]), name
    for name in FILTER_NAMES:
        assert callable(built.env.filters[name]), name
    assert built.env.globals["inkstone"] == {"version": __version__}
    # and the engine's own are still there
    assert "truncate" in built.env.filters and "tojson" in built.env.filters


def test_page_context_names(built):
    about = built.site.get_page("about.md")
    context = page_context(built, about)
    assert context["site"] is built.site
    assert context["config"] is built.config
    assert context["page"] is about
    assert context["now"] == built.site.build_time
    assert context["now"].tzinfo is not None
    assert context["inkstone"] == {"version": __version__}
    assert "section" not in context and "paginator" not in context

    post = built.site.get_page("posts/2024-01-10-first.md")
    assert page_context(built, post)["section"] is built.site.sections["posts"]

    listing = page_context(built, built.site.get_page("posts"))
    assert listing["section"] is built.site.sections["posts"]
    assert listing["paginator"].page == 1
    assert listing["pages"] is listing["paginator"].items

    term = page_context(built, built.site.get_page("/tags/python/"))
    assert term["taxonomy"].name == "tags"
    assert term["term"].slug == "python"
    assert [page.title for page in term["pages"]] == ["Second", "First"]


def test_extra_context_of_virtual_pages_is_merged(built):
    page = Page.virtual("/x/", template="page.html", posts=[1, 2], page_size=5)
    built.site.add_page(page)
    context = page_context(built, page)
    assert context["posts"] == [1, 2] and context["page_size"] == 5


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("url_for('/about/')", "/about/"),
        ("url_for('about/')", "/about/"),
        ("url_for(page.url)", "/about/"),
        ("url_for(page)", "/about/"),
        ("url_for('/')", "/"),
        ("url_for()", "/"),
        ("url_for('https://other.example/x')", "https://other.example/x"),
        ("url_for('#top')", "#top"),
        ("url_for('mailto:me@example.com')", "mailto:me@example.com"),
        ("url_for(nothing)", "/"),
        ("'/about/' | relative_url", "/about/"),
        ("absolute_url('/about/')", "https://example.com/about/"),
        ("absolute_url(page)", "https://example.com/about/"),
        ("page.url | absolute_url", "https://example.com/about/"),
        ("absolute_url('https://other.example/x')", "https://other.example/x"),
        ("absolute_url()", "https://example.com/"),
        ("asset('css/theme.css')", "/css/theme.css"),
        ("asset('/css/theme.css')", "/css/theme.css"),
        ("asset('https://cdn.example/lib.js')", "https://cdn.example/lib.js"),
        ("asset_integrity('css/theme.css')[:7]", "sha384-"),
        ("get_page('about.md').title", "About"),
        ("get_page('/2024/01/first/').title", "First"),
        ("get_page('nope.md')", ""),
        ("get_page('nope.md') is none", "True"),
        ("get_section('posts').title", "Posts"),
        ("get_section('posts').pages | length", "3"),
        ("get_section('nope')", ""),
        ("get_data('team.roles.lead')", "Magdy"),
        ("get_data('team.nobody.home')", ""),
        ("get_data('team.nobody', 'fallback')", "fallback"),
        ("inkstone.version", __version__),
        ("site.title", "Test Site"),
        ("config.params.footer", "tiny footer"),
        ("config.params.not_set | default('unset')", "unset"),
        ("site.sections.posts.url", "/posts/"),
        ("site.taxonomies.tags.terms.python.count", "2"),
        ("site.menus.main | length", "0"),
        ("site.pages.tagged('python').pluck('title') | join(',')", "Second,First"),
        ("now.year == site.build_time.year", "True"),
    ],
)
def test_globals(built, source, expected):
    assert expr(built, source) == expected


def test_urls_below_a_sub_path(blog):
    blog.overrides["base_url"] = "https://example.com/blog/"
    builder = blog.builder()
    builder.build()
    assert expr(builder, "url_for('/about/')") == "/blog/about/"
    assert expr(builder, "url_for('/')") == "/blog/"
    assert expr(builder, "url_for()") == "/blog/"
    assert expr(builder, "'/about/' | relative_url") == "/blog/about/"
    assert expr(builder, "absolute_url('/about/')") == "https://example.com/blog/about/"
    assert expr(builder, "asset('css/theme.css')") == "/blog/css/theme.css"
    assert expr(builder, "page.permalink") == "https://example.com/blog/about/"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("when | date", "2024-09-15"),
        ("when | date('iso')", "2024-09-15"),
        ("when | date('short')", "Sep 15, 2024"),
        ("when | date('long')", "September 15, 2024"),
        ("when | date('full')", "Sunday, September 15, 2024"),
        ("when | date('month')", "September 2024"),
        ("when | date('year')", "2024"),
        ("when | date('time')", "14:30"),
        ("when | date('datetime')", "2024-09-15 14:30"),
        ("when | date('rfc3339')", "2024-09-15T14:30:00+02:00"),
        ("when | date('rfc2822')", "Sun, 15 Sep 2024 14:30:00 +0200"),
        ("when | date('%-d %B %Y')", "15 September 2024"),
        ("when | date('%Y/%m')", "2024/09"),
        ("'2024-01-05' | date('long')", "January 5, 2024"),
        ("nothing | date('long')", ""),
        ("none | date", ""),
        ("'' | date('iso')", ""),
        ("0 | date('year')", "1970"),
        ("'now' | date('year') | length", "4"),
    ],
)
def test_date_filter(built, source, expected):
    when = dt.datetime(2024, 9, 15, 14, 30, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert expr(built, source, when=when) == expected


def test_unknown_date_format_is_a_template_error(built):
    with pytest.raises(Exception, match="unknown date format: 'lng'"):
        expr(built, "now | date('lng')")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("'Site Generators' | slugify", "site-generators"),
        ("'Crème brûlée' | slugify('_')", "creme_brulee"),
        ("nothing | slugify", ""),
        ("'<p>Some <b>bold</b> text</p>' | strip_html", "Some bold text"),
        ("page.content | strip_html", "About me."),
        ("nothing | strip_html", ""),
        ("1536 | humanize_bytes", "1.5 KB"),
        ("nothing | humanize_bytes", ""),
        ("('word ' * 500) | reading_time", "3"),
        ("page.content | reading_time", "1"),
        ("'' | reading_time", "0"),
        ("'*hi*' | markdown", "<p><em>hi</em></p>\n"),
        ("nothing | markdown", ""),
        ("html | truncate_html(9)", "<p>One <em>two</em>…</p>"),
        ("html | truncate_html(9, '...')", "<p>One <em>two</em>...</p>"),
        ("html | truncate_html", "<p>One <em>two</em> three four</p>"),
        ("nothing | truncate_html(5)", ""),
    ],
)
def test_filters(built, source, expected):
    html = Markup("<p>One <em>two</em> three four</p>")
    assert expr(built, source, html=html) == expected


def test_markup_from_filters_is_not_escaped_again(built):
    assert expr(built, "'a < b' | markdown") == "<p>a &lt; b</p>\n"
    assert expr(built, "'<i>x</i>' | truncate_html(50)") == "<i>x</i>"
    # plain strings still are
    assert expr(built, "'<i>x</i>'") == "&lt;i&gt;x&lt;/i&gt;"


def test_highlight_css_global(built):
    inline = expr(built, "highlight_css()")
    assert ".highlight" in inline and "&#39;" not in inline and "&gt;" not in inline
    assert expr(built, "highlight_css('paper')") != ""
    with pytest.raises(BuildError, match="highlight CSS"):
        expr(built, "highlight_css('no-such-style')")


def test_macros_can_use_the_site_without_being_passed_it(blog):
    blog.write(
        "templates/macros.html",
        "{% macro home() %}<a href=\"{{ url_for('/') }}\">{{ site.title }}"
        " {{ config.params.footer }}</a>{% endmacro %}\n",
    )
    blog.write(
        "templates/partials/footer.html",
        "{% import 'macros.html' as m %}<footer>{{ m.home() }}</footer>\n",
    )
    blog.build()
    html = blog.read("404.html")
    assert '<footer><a href="/">Test Site tiny footer</a></footer>' in html


def test_asset_outside_a_build_does_not_warn(blog):
    builder = blog.builder()
    assert builder.env.globals["asset"]("css/whatever.css") == "/css/whatever.css"
    assert builder.report.warnings == []


def test_describe_reduces_values_to_plain_data(built):
    site = built.site
    about = site.get_page("about.md")
    post = site.get_page("posts/2024-01-10-first.md")
    assert keys.describe(None) is None
    assert keys.describe(3) == 3
    assert keys.describe(dt.date(2024, 5, 3)) == "2024-05-03"
    posts, tags = site.sections["posts"], site.taxonomies["tags"]
    assert keys.describe(posts) == ["section", "posts", "Posts", "/posts/"]
    assert keys.describe(tags) == ["taxonomy", "tags", "tag", "/tags/"]
    assert keys.describe(site.taxonomies["tags"].terms["python"]) == [
        "term",
        "python",
        "python",
        2,
    ]
    nested = keys.describe({"a": [about, {1, 2}]})
    assert nested["a"][0] == ["page", keys.metadata_hash(about)]
    assert keys.describe(about, refs_only=True)[:3] == ["page", "/about/", "About"]
    assert keys.describe(len) == "<callable len>"
    assert keys.describe(object()) == "<object>"

    class Box:
        def __init__(self):
            self.name = "Building"
            self.pages = [post]
            self._private = "hidden"

    described = keys.describe(Box())
    assert described[0] == "Box"
    assert described[1]["name"] == "Building"
    assert "_private" not in described[1]
    keys.stable_hash(described)


def test_pages_that_point_at_each_other_do_not_recurse(built):
    first = built.site.get_page("posts/2024-01-10-first.md")
    second = built.site.get_page("posts/2024-02-10-second.md")
    first.related = [second]
    second.related = [first]
    keys.freeze_metadata([first, second])
    assert keys.plugin_attrs(first) == {"related": [keys.page_ref(second)]}
    state = keys.page_state(first)
    assert state["metadata"] == keys.metadata_hash(first)
    assert state["prev"] == keys.page_ref(second)
    keys.stable_hash(state)


def test_metadata_ignores_the_body_but_not_the_title(built):
    page = built.site.get_page("posts/2024-02-10-second.md")
    page._metadata_hash = None
    before = keys.metadata_hash(page)
    page.content = Markup(str(page.content) + "<p>More.</p>")
    assert keys.metadata_hash(page) == before
    assert keys.page_state(page)["content"] != keys.hash_text("")
    page.title = "Renamed"
    assert keys.metadata_hash(page) != before


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("{% for p in site.pages %}{% endfor %}", (True, False)),
        ("{{ site . pages | length }}", (True, False)),
        ("{{ site.pages_by_date() }}", (True, False)),
        ("{% set p = get_page('about.md') %}", (True, False)),
        ("{{ get_section('posts').title }}", (True, False)),
        ("{% for p in page.section.pages %}{% endfor %}", (True, False)),
        ("{{ site.sections.posts.pages | length }}", (True, False)),
        ("{% for t in site.taxonomies.tags %}{% endfor %}", (False, True)),
        ("{% for t in taxonomy %}{{ t.name }}{% endfor %}", (False, True)),
        ("{{ taxonomy.terms | length }}", (False, True)),
        ("{{ page.title }} {{ site.title }} {{ pages | length }}", (False, False)),
        ("{{ taxonomy.name }} {{ term.pages | length }}", (False, False)),
        ("{{ site.sections.posts.url }}", (False, False)),
    ],
)
def test_template_uses(source, expected):
    assert keys.template_uses(source) == expected
