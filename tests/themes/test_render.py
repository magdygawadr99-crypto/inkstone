"""Render the theme templates with the real template engine.

There is no builder involved: the context is made of stand-ins shaped like
the content model (Page, Section, Site, Paginator, ...), and the globals and
filters the builder would register are small fakes.
"""

from __future__ import annotations

import datetime as dt
import re
from types import SimpleNamespace

import pytest

from . import layout

tmpl = pytest.importorskip("inkstone.tmpl")
tomllib = pytest.importorskip("tomllib")

Markup = tmpl.Markup
BASE_URL = "https://example.org"
NOW = dt.datetime(2024, 11, 20, 9, 30, tzinfo=dt.timezone.utc)


def day(month, number):
    return dt.datetime(2024, month, number, 12, 0, tzinfo=dt.timezone.utc)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def strip_html(text):
    return re.sub(r"<[^>]+>", "", str(text))


def theme_params(theme):
    params = {}
    for name in reversed(layout.chain(theme)):
        with open(layout.THEMES / name / "theme.toml", "rb") as f:
            params.update(tomllib.load(f).get("params", {}))
    return params


def make_env(theme, prefix="", **options):
    env = tmpl.Environment(
        loader=tmpl.FileSystemLoader(layout.template_dirs(theme)), **options
    )
    env.globals.update(
        url_for=lambda path: prefix + "/" + str(path).lstrip("/"),
        absolute_url=lambda path: BASE_URL + prefix + "/" + str(path).lstrip("/"),
        asset=lambda path: prefix + "/" + path,
        asset_integrity=lambda path: "",
        get_page=lambda path: None,
        get_section=lambda name: None,
        get_data=lambda dotted: None,
        highlight_css=lambda style=None: "",
    )
    env.filters.update(
        markdown=lambda text: Markup(f"<p>{text}</p>"),
        slugify=slugify,
        absolute_url=lambda path: BASE_URL + str(path),
        relative_url=lambda path: prefix + str(path),
        strip_html=strip_html,
        truncate_html=lambda text, length=200: text,
        reading_time=lambda text: 1,
        humanize_bytes=lambda size: f"{size} B",
    )
    return env


def make_page(title, url, **attrs):
    page = SimpleNamespace(
        kind="page",
        title=title,
        slug=slugify(title),
        description="",
        date=None,
        updated=None,
        draft=False,
        weight=0,
        url=url,
        permalink=BASE_URL + url,
        output_path=url.lstrip("/") + "index.html",
        source_path=None,
        section=None,
        tags=[],
        categories=[],
        taxonomies={},
        meta={},
        params={},
        raw="",
        content=Markup(""),
        summary=Markup(""),
        toc=[],
        toc_html="",
        word_count=0,
        reading_time=1,
        template=None,
        layout=None,
        prev=None,
        next=None,
        aliases=[],
        resources=[],
        extra_context={},
    )
    page.__dict__.update(attrs)
    return page


class Taxonomy:
    def __init__(self, name, singular, terms):
        self.name = name
        self.singular = singular
        self.url = f"/{name}/"
        self.terms = {term.slug: term for term in terms}

    def __iter__(self):
        return iter(sorted(self.terms.values(), key=lambda term: term.name))


def make_term(taxonomy, name, pages):
    slug = slugify(name)
    return SimpleNamespace(
        name=name, slug=slug, url=f"/{taxonomy}/{slug}/", pages=pages, count=len(pages)
    )


def make_paginator(items, page=1, pages=1, base="/"):
    def url(number):
        return base if number == 1 else f"{base}page/{number}/"

    return SimpleNamespace(
        items=items,
        page=page,
        pages=pages,
        total=len(items) * pages,
        per_page=len(items),
        has_prev=page > 1,
        has_next=page < pages,
        prev_url=url(page - 1) if page > 1 else None,
        next_url=url(page + 1) if page < pages else None,
        first_url=url(1),
        last_url=url(pages),
        page_urls=[(number, url(number)) for number in range(1, pages + 1)],
    )


def make_site(theme):
    """A three-post blog. Returns the pieces the tests want to poke at."""
    posts_section = SimpleNamespace(
        name="posts",
        title="Posts",
        url="/posts/",
        pages=[],
        subsections=[],
        parent=None,
        index=None,
        meta={},
        paginate=None,
    )
    first = make_page(
        "Hello world",
        "/2024/05/hello-world/",
        date=day(5, 3),
        tags=["meta", "python"],
        section=posts_section,
        summary=Markup("<p>The first post.</p>"),
        reading_time=2,
    )
    second = make_page(
        "Parsing <Markdown> & friends",
        "/2024/06/parsing-markdown/",
        date=day(6, 9),
        updated=day(6, 12),
        tags=["python", "parsing"],
        categories=["Notes"],
        section=posts_section,
        description="Five weekends, not two.",
        summary=Markup("<p>It took <em>five</em> weekends.</p>"),
        truncated=True,
        content=Markup('<h2 id="blocks">Blocks</h2><p>Body text.</p>'),
        toc_html=Markup('<ul><li><a href="#blocks">Blocks</a></li></ul>'),
        toc=[SimpleNamespace(level=2, id="blocks", title="Blocks", children=[])],
        reading_time=7,
        word_count=1500,
    )
    third = make_page(
        "A draft",
        "/2024/07/a-draft/",
        date=day(7, 1),
        draft=True,
        section=posts_section,
    )
    pages = [third, second, first]
    posts_section.pages = pages
    second.prev, second.next = first, third
    about = make_page("About", "/about/", content=Markup("<p>Hi.</p>"))

    tags = Taxonomy(
        "tags",
        "tag",
        [
            make_term("tags", "meta", [first]),
            make_term("tags", "python", [second, first]),
            make_term("tags", "parsing", [second]),
        ],
    )
    categories = Taxonomy(
        "categories", "category", [make_term("categories", "Notes", [second])]
    )
    home = make_page("", "/", kind="home", content=Markup("<p>Welcome.</p>"))
    posts_index = make_page("Posts", "/posts/", kind="section", section=posts_section)
    posts_section.index = posts_index

    config = {
        "title": "Test Site",
        "base_url": BASE_URL + "/",
        "description": "A site for tests",
        "language": "en",
        "theme": theme,
        "author": {"name": "Sam Tester", "email": "", "url": ""},
        "markdown": {"highlight": True, "highlight_style": "dusk"},
        "feeds": {"rss": True, "atom": True, "json": False, "sections": ["posts"]},
        "search": {"enabled": True},
        "params": theme_params(theme),
    }
    site = SimpleNamespace(
        config=config,
        pages=pages,
        all_pages=pages + [about, home, posts_index],
        sections={"posts": posts_section},
        home=home,
        taxonomies={"tags": tags, "categories": categories},
        data={},
        menus={
            "main": [
                {"name": "Blog", "url": "/posts/", "weight": 10},
                {"name": "About", "url": "/about/", "weight": 20},
                {"name": "Code", "url": "https://git.example.org/sam", "weight": 30},
            ]
        },
        title=config["title"],
        base_url=config["base_url"],
        language="en",
        author=config["author"],
        params=config["params"],
        build_time=NOW,
    )
    return SimpleNamespace(
        site=site,
        config=config,
        home=home,
        about=about,
        posts=posts_section,
        posts_index=posts_index,
        first=first,
        second=second,
        third=third,
        tags=tags,
    )


def render(theme, template, page, world=None, prefix="", env_options=None, **extra):
    world = world or make_site(theme)
    context = {
        "site": world.site,
        "config": world.config,
        "page": page,
        "now": NOW,
        "inkstone": {"version": "0.0.test"},
    }
    context.update(extra)
    env = make_env(theme, prefix, **(env_options or {}))
    return env.get_template(template).render(context)


def all_theme_templates():
    return [(t, name) for t in layout.THEME_NAMES for name in layout.all_templates(t)]


@pytest.mark.parametrize("theme,name", all_theme_templates())
def test_template_parses(theme, name):
    template = make_env(theme).get_template(name)
    for dependency in template.all_dependencies():
        make_env(theme).get_template(dependency)


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_loader_sees_every_template(theme):
    assert make_env(theme).list_templates() == layout.all_templates(theme)


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_home_page(theme):
    world = make_site(theme)
    html = render(
        theme,
        "index.html",
        world.home,
        world,
        pages=world.site.pages,
        paginator=make_paginator(world.site.pages, 1, 3),
    )
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="en"' in html
    assert "<title>Test Site · A site for tests</title>" in html
    assert '<a class="skip-link" href="#main">' in html
    assert '<main id="main"' in html
    assert f'<link rel="canonical" href="{BASE_URL}/">' in html
    assert 'type="application/rss+xml"' in html and 'href="/rss.xml"' in html
    assert 'type="application/atom+xml"' in html
    assert "application/feed+json" not in html
    assert '<link rel="next" href="/page/2/">' in html
    assert '<meta name="generator" content="inkstone 0.0.test">' in html
    assert "<p>Welcome.</p>" in html
    assert 'href="/2024/05/hello-world/"' in html
    assert "Hello world" in html
    assert '<time class="' in html and 'datetime="2024-05-03"' in html
    assert html.count("<h1") == 1


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_titles_are_escaped_and_content_is_not(theme):
    world = make_site(theme)
    html = render(theme, "posts/page.html", world.second, world, section=world.posts)
    assert "Parsing &lt;Markdown&gt; &amp; friends" in html
    assert "<Markdown>" not in html
    assert '<h2 id="blocks">Blocks</h2><p>Body text.</p>' in html


def test_default_home_lists_cards_with_summaries_and_tags():
    world = make_site("default")
    html = render(
        "default",
        "index.html",
        world.home,
        world,
        pages=world.site.pages,
        paginator=make_paginator(world.site.pages),
    )
    assert html.count('<article class="post-card') == 3
    assert "<p>It took <em>five</em> weekends.</p>" in html
    assert '<a class="tag p-category" href="/tags/python/" rel="tag">python</a>' in html
    assert "7 min read" in html
    # only the post whose summary was cut gets a "continue reading" link
    assert html.count('class="post-card__more"') == 1
    assert re.search(
        r'post-card__more" href="/2024/06/parsing-markdown/">Continue reading'
        r'<span class="visually-hidden">: Parsing &lt;Markdown&gt; &amp; friends<',
        html,
    )
    assert "post-card--draft" in html and "badge--draft" in html
    assert '<h3 class="post-card__title">' in html
    assert "3 May 2024" in html
    assert "pagination" not in html.split("<main", 1)[1].split("</main>", 1)[0]


def test_default_header_navigation():
    world = make_site("default")
    html = render("default", "page.html", world.about, world)
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert '<nav class="site-nav" id="site-nav" aria-label="Main">' in header
    assert re.search(r'href="/about/"\s+aria-current="page">About</a>', header)
    assert not re.search(r'href="/posts/"[^>]*aria-current', header)
    assert 'href="https://git.example.org/sam" rel="noopener">Code</a>' in header
    assert 'aria-controls="site-nav" aria-expanded="false"' in header
    assert "data-theme-toggle" in header
    assert 'data-search-script="/js/inkstone-search.js"' in header
    assert 'data-search-index="/search-index.json"' in header
    assert 'action="/search/"' in header


def test_default_marks_the_section_in_the_menu_on_posts():
    world = make_site("default")
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert re.search(r'href="/posts/"\s+aria-current="true">Blog</a>', html)


def test_default_menu_uses_what_real_menu_entries_offer():
    # the site core's entries know more than name and url: children, and
    # whether a page lives below them
    world = make_site("default")
    docs = SimpleNamespace(
        name="Docs",
        url="/docs/",
        children=[
            SimpleNamespace(name="Guide", url="/docs/guide/", children=[]),
            SimpleNamespace(
                name="Forum", url="https://forum.example.org/", children=[]
            ),
        ],
        is_current=lambda page: page.url.startswith("/docs/"),
    )
    world.site.menus = {"main": [docs, {"name": "About", "url": "/about/"}]}
    page = make_page("Install", "/docs/guide/install/")
    html = render("default", "page.html", page, world)
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert '<li class="site-nav__item site-nav__item--parent">' in header
    assert re.search(r'href="/docs/"\s+aria-current="true">Docs</a>', header)
    assert '<ul class="site-nav__sub">' in header
    assert 'href="/docs/guide/">Guide</a>' in header
    assert 'href="https://forum.example.org/">Forum</a>' in header
    assert not re.search(r'href="/about/"[^>]*aria-current', header)
    assert header.count("<ul") == header.count("</ul>") == 2


def test_default_menu_falls_back_to_sections():
    world = make_site("default")
    world.site.menus = {}
    html = render("default", "page.html", world.about, world)
    assert re.search(r'<a class="site-nav__link" href="/posts/">Posts</a>', html)


def test_default_post_page():
    world = make_site("default")
    world.second.related = [world.first]
    world.second.series = SimpleNamespace(
        name="Building it", pages=[world.first, world.second]
    )
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert "<title>Parsing &lt;Markdown&gt; &amp; friends · Test Site</title>" in html
    assert '<meta name="description" content="Five weekends, not two.">' in html
    assert '<meta property="og:type" content="article">' in html
    assert (
        '<meta property="article:published_time" content="2024-06-09T12:00:00+0000">'
        in html
    )
    assert '<meta property="article:tag" content="parsing">' in html
    assert 'title="Posts · Test Site" href="/posts/rss.xml"' in html
    assert "post-layout--with-toc" in html
    assert "data-toc>" in html and '<a href="#blocks">Blocks</a>' in html
    assert 'datetime="2024-06-09">9 June 2024</time>' in html
    assert 'datetime="2024-06-12">12 June 2024</time>' in html
    assert "7 min read" in html
    assert 'href="/tags/parsing/" rel="tag">parsing</a>' in html
    assert "Filed under" in html and 'href="/categories/notes/">Notes</a>' in html
    assert re.search(
        r'post-nav__link--prev" href="/2024/05/hello-world/" rel="prev"', html
    )
    assert re.search(r'post-nav__link--next" href="/2024/07/a-draft/" rel="next"', html)
    assert '<h2 class="related__title" id="related-title">Related posts</h2>' in html
    assert re.search(r"Part of the series\s+<strong>Building it</strong>", html)
    assert (
        '<span aria-current="page">Parsing &lt;Markdown&gt; &amp; friends</span>'
        in html
    )
    assert '<script src="/js/toc.js" defer></script>' in html
    assert html.index("/js/nav.js") < html.index("/js/toc.js")
    assert "Home</a>" in html and '<a href="/posts/">Posts</a>' in html


def test_post_nav_says_newer_and_older_in_a_section_sorted_by_date():
    world = make_site("default")
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    nav = html.split('<nav class="post-nav"', 1)[1].split("</nav>", 1)[0]
    assert "Previous" in nav and "Next" in nav and "Newer" not in nav

    world.posts.sort_by = "date"
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    nav = html.split('<nav class="post-nav"', 1)[1].split("</nav>", 1)[0]
    assert 'aria-label="Newer and older posts"' in nav
    assert re.search(r"Newer</span>\s*<span[^>]*>Hello world", nav)
    assert re.search(r"Older <svg.*?</svg></span>\s*<span[^>]*>A draft", nav, re.S)
    assert "Previous" not in nav

    world.posts.sort_by = "weight"
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert (
        "Newer" not in html.split('<nav class="post-nav"', 1)[1].split("</nav>", 1)[0]
    )


def test_series_box_counts_the_parts_when_the_plugin_says_where_we_are():
    world = make_site("default")
    world.second.series = SimpleNamespace(
        name="Building it",
        title="Building it",
        pages=[world.first, world.second, world.third],
        index=2,
        total=3,
    )
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    box = html.split('<aside class="series"', 1)[1].split("</aside>", 1)[0]
    assert re.search(r"Part 2 of 3 in the series\s+<strong>Building it</strong>", box)
    assert box.count("<li") == 3 and box.count("series__item--current") == 1
    assert 'href="/2024/05/hello-world/"' in box

    # the plugin sets page.series to None on pages outside any series
    world.second.series = None
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert 'class="series"' not in html


def test_breadcrumbs_follow_nested_sections():
    world = make_site("default")
    parent = None
    for name, title in [
        ("docs", "Docs"),
        ("docs/guide", "Guide"),
        ("docs/guide/setup", "Setup"),
    ]:
        parent = SimpleNamespace(
            name=name,
            title=title,
            url=f"/{name}/",
            parent=parent,
            pages=[],
            subsections=[],
        )
    page = make_page("Install", "/docs/guide/setup/install/", section=parent)
    html = render("default", "page.html", page, world)
    crumbs = html.split('<nav class="breadcrumbs"', 1)[1].split("</nav>", 1)[0]
    marks = [
        'href="/"',
        'href="/docs/"',
        'href="/docs/guide/"',
        'href="/docs/guide/setup/"',
    ]
    order = [crumbs.index(mark) for mark in marks] + [
        crumbs.index("<span>Install</span>")
    ]
    assert order == sorted(order)
    assert crumbs.count("<li") == 5

    index = make_page("Setup", "/docs/guide/setup/", kind="section", section=parent)
    html = render("default", "section.html", index, world, section=parent, pages=[])
    crumbs = html.split('<nav class="breadcrumbs"', 1)[1].split("</nav>", 1)[0]
    assert crumbs.count("<li") == 4 and 'href="/docs/guide/setup/"' not in crumbs


def test_default_post_page_without_the_optional_parts():
    world = make_site("default")
    html = render("default", "posts/page.html", world.first, world, section=world.posts)
    assert "related__title" not in html
    assert 'class="series"' not in html
    assert "post-layout--with-toc" not in html
    assert "data-toc" not in html
    assert "post-nav" not in html
    assert '<meta name="description" content="The first post.">' in html


def test_front_matter_can_switch_the_toc_off_and_the_theme_setting_too():
    world = make_site("default")
    world.second.params = {"toc": False}
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert "data-toc" not in html

    world = make_site("default")
    world.config["params"]["show_toc"] = False
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert "data-toc" not in html
    world.second.params = {"toc": True}
    html = render(
        "default", "posts/page.html", world.second, world, section=world.posts
    )
    assert "data-toc" in html


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_draft_pages_are_flagged(theme):
    world = make_site(theme)
    html = render(theme, "posts/page.html", world.third, world, section=world.posts)
    assert '<meta name="robots" content="noindex">' in html
    assert "is-draft" in html
    assert "draft" in html.split("<main", 1)[1].lower()


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_section_page_with_pagination(theme):
    world = make_site(theme)
    html = render(
        theme,
        "section.html",
        world.posts_index,
        world,
        section=world.posts,
        pages=world.posts.pages,
        paginator=make_paginator(world.posts.pages, 2, 3, "/posts/"),
    )
    assert "<title>Posts (page 2) · Test Site</title>" in html
    assert '<link rel="prev" href="/posts/">' in html
    assert '<link rel="next" href="/posts/page/3/">' in html
    assert '<nav class="pagination" aria-label="Pagination">' in html
    assert 'href="/posts/page/3/" rel="next"' in html
    assert "Page 2 of 3" in html
    assert "9 entries" in html
    assert html.count("Hello world</a>") == 1


def test_default_pagination_numbers():
    world = make_site("default")
    html = render(
        "default",
        "section.html",
        world.posts_index,
        world,
        section=world.posts,
        pages=world.posts.pages,
        paginator=make_paginator(world.posts.pages, 2, 3, "/posts/"),
    )
    assert re.search(
        r'pagination__page--current" aria-current="page">.*?2</span>', html
    )
    assert re.search(r'<a class="pagination__page" href="/posts/">.*?1</a>', html)
    assert "pagination__step--disabled" not in html


def test_long_lists_use_the_paginator_window_when_there_is_one():
    world = make_site("default")
    paginator = make_paginator(world.posts.pages, 6, 20, "/posts/")
    context = dict(section=world.posts, pages=world.posts.pages, paginator=paginator)
    html = render("default", "section.html", world.posts_index, world, **context)
    assert html.count('class="pagination__page"') == 19
    assert "pagination__gap" not in html

    # what the real Paginator.window() returns: gaps are (None, None)
    def window(around=2):
        shown = [1, None, 4, 5, 6, 7, 8, None, 20]
        return [(n, paginator.page_urls[n - 1][1] if n else None) for n in shown]

    paginator.window = window
    html = render("default", "section.html", world.posts_index, world, **context)
    assert html.count('class="pagination__page"') == 6
    assert html.count("pagination__gap") == 2
    assert re.search(r'pagination__page--current" aria-current="page">.*?6<', html)
    assert 'href="/posts/page/20/"' in html and 'href="/posts/page/12/"' not in html

    # short lists are shown in full even when a window is on offer
    short = make_paginator(world.posts.pages, 2, 5, "/posts/")
    short.window = window
    context["paginator"] = short
    html = render("default", "section.html", world.posts_index, world, **context)
    assert html.count('class="pagination__page"') == 4


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_taxonomy_and_term_pages(theme):
    world = make_site(theme)
    listing = make_page("Tags", "/tags/", kind="taxonomy")
    html = render(theme, "taxonomy.html", listing, world, taxonomy=world.tags)
    assert "<title>Tags · Test Site</title>" in html
    assert "3 tags" in html
    order = [
        html.index(f'href="/tags/{slug}/"') for slug in ("meta", "parsing", "python")
    ]
    assert order == sorted(order)

    term = world.tags.terms["python"]
    page = make_page("python", "/tags/python/", kind="term")
    html = render(
        theme,
        "term.html",
        page,
        world,
        taxonomy=world.tags,
        term=term,
        pages=term.pages,
        paginator=make_paginator(term.pages),
    )
    assert "<title>Tag: python · Test Site</title>" in html
    assert "2 posts" in html
    assert 'href="/tags/">all tags</a>' in html
    assert 'href="/2024/06/parsing-markdown/"' in html
    assert 'href="/2024/05/hello-world/"' in html


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_not_found_page(theme):
    world = make_site(theme)
    page = make_page("", "/404.html", kind="404")
    html = render(theme, "404.html", page, world)
    assert "<title>Page not found · Test Site</title>" in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'rel="canonical"' not in html
    assert "Page not found</h1>" in html
    assert 'href="/2024/06/parsing-markdown/"' in html


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_search_page(theme):
    world = make_site(theme)
    page = make_page("Search", "/search/")
    html = render(theme, "search.html", page, world)
    assert "data-search-page" in html
    assert 'data-search-index="/search-index.json"' in html
    assert (
        '<form class="search-form" role="search" method="get" action="/search/"' in html
    )
    assert 'id="search-status" role="status"' in html
    assert "<noscript>" in html
    assert '<script src="/js/search-ui.js" defer></script>' in html

    world.config["search"]["enabled"] = False
    html = render(theme, "search.html", page, world)
    assert "Search is turned off" in html
    assert "search-ui.js" not in html
    assert "data-search" not in html


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
@pytest.mark.parametrize(
    "template,kind",
    [("index.html", "home"), ("page.html", "page"), ("posts/page.html", "page")],
)
def test_sub_path_base_url_reaches_every_link(theme, template, kind):
    world = make_site(theme)
    page = world.second if kind == "page" else world.home
    html = render(
        theme,
        template,
        page,
        world,
        prefix="/blog",
        section=world.posts,
        pages=world.site.pages,
        paginator=make_paginator(world.site.pages, 1, 2),
    )
    local = re.findall(r'(?:href|src|action|data-search-\w+)="(/[^"]*)"', html)
    assert len(local) > 8
    assert all(url.startswith("/blog/") for url in local), [
        url for url in local if not url.startswith("/blog/")
    ]


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_bare_site_still_renders(theme):
    # no menus, feeds, search, taxonomies, author or params beyond the theme's
    world = make_site(theme)
    world.site.menus = {}
    world.site.taxonomies = {}
    world.site.sections = {}
    world.site.author = {"name": "", "email": "", "url": ""}
    world.config["feeds"] = {"rss": False, "atom": False, "json": False, "sections": []}
    world.config["search"] = {"enabled": False}
    world.config["markdown"] = {"highlight": False}
    world.config["description"] = ""
    for template, page in [
        ("index.html", world.home),
        ("page.html", world.about),
        ("posts/page.html", world.second),
        ("404.html", make_page("", "/404.html", kind="404")),
    ]:
        html = render(theme, template, page, world, pages=[])
        assert "</html>" in html
        assert "rss.xml" not in html
        assert "highlight.css" not in html
        assert "search" not in html.lower() or template == "404.html"
    assert "Nothing published yet." in render(theme, "index.html", world.home, world)


def test_accent_param_becomes_a_custom_property():
    world = make_site("default")
    assert "--accent:" not in render("default", "page.html", world.about, world)
    world.config["params"]["accent"] = "#0b6e4f"
    world.config["params"]["accent_dark"] = "#7bd3b0"
    html = render("default", "page.html", world.about, world)
    assert ":root { --accent: #0b6e4f; }" in html
    assert ':root[data-theme="dark"] { --accent: #7bd3b0; }' in html


def test_custom_css_and_footer_text_params():
    world = make_site("default")
    world.config["params"]["custom_css"] = ["css/custom.css"]
    world.config["params"]["footer_text"] = 'Made by <a href="/about/">me</a>'
    html = render("default", "page.html", world.about, world)
    assert '<link rel="stylesheet" href="/css/custom.css">' in html
    assert html.index("/css/main.css") < html.index("/css/custom.css")
    assert 'Made by <a href="/about/">me</a>' in html
    assert "&copy;" not in html


def test_default_footer_social_links():
    world = make_site("default")
    world.config["params"]["social"] = {
        "github": "https://github.com/sam",
        "mastodon": "",
        "email": "sam@example.org",
        "rss": True,
    }
    html = render("default", "page.html", world.about, world)
    footer = html.split('<footer class="site-footer"', 1)[1]
    assert 'href="https://github.com/sam" rel="me noopener"' in footer
    assert 'href="mailto:sam@example.org"' in footer
    assert "Mastodon" not in footer
    assert "&copy; 2024" in footer and "Sam Tester" in footer
    assert "inkstone</a> 0.0.test" in footer


def test_paper_swaps_the_skeleton_but_keeps_the_pages():
    world = make_site("paper")
    html = render(
        "paper",
        "index.html",
        world.home,
        world,
        pages=world.site.pages,
        paginator=make_paginator(world.site.pages),
    )
    assert '<link rel="stylesheet" href="/css/paper.css">' in html
    assert "css/main.css" not in html
    assert '<link rel="stylesheet" href="/css/print.css" media="print">' in html
    assert '<div class="sheet">' in html
    assert ":root { --column: 34rem; }" in html
    assert "theme.js" not in html and "nav.js" not in html
    assert "data-theme-toggle" not in html
    # the one-line post entry and the ISO date from paper's own params
    assert html.count('<article class="post-card h-entry">') == 3
    assert 'datetime="2024-05-03">2024-05-03</time>' in html
    assert "post-card__summary" not in html
    assert '<a href="/search/">Search</a>' in html
    # index.html itself is the default theme's
    assert 'class="home-intro__title"' in html


def test_paper_post_uses_its_own_meta_line_and_no_toc():
    world = make_site("paper")
    html = render("paper", "posts/page.html", world.second, world, section=world.posts)
    assert '<p class="post-meta">' in html
    assert "(revised" in html
    assert "data-toc" not in html
    assert "breadcrumbs" not in html
    assert '<h2 id="blocks">Blocks</h2>' in html


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_macros(theme):
    module = make_env(theme).get_template("partials/macros.html").module
    sun = str(module.icon("sun"))
    assert sun.startswith("<svg") and sun.endswith("</svg>")
    assert 'class="icon icon--sun"' in sun and 'aria-hidden="true"' in sun
    assert 'width="18"' in sun
    assert 'width="32"' in str(module.icon("rss", 32))
    assert str(module.icon("sun")) != str(module.icon("moon"))
    assert "<circle" in str(module.icon("no-such-icon"))

    stamp = str(module.format_date(day(4, 6), "%-d %b %Y", "when"))
    assert stamp == '<time class="when" datetime="2024-04-06">6 Apr 2024</time>'
    assert str(module.format_date(day(4, 6), "")) == (
        '<time datetime="2024-04-06">6 April 2024</time>'
    )
    assert str(module.count(1, "post")) == "1 post"
    assert str(module.count(4, "post")) == "4 posts"
    assert str(module.count(2, "entry", "entries")) == "2 entries"
    assert "3 min read" in str(module.reading_time(3))
    assert str(module.sr("a < b")) == '<span class="visually-hidden">a &lt; b</span>'


def page_templates():
    return [
        (theme, name)
        for theme, name in all_theme_templates()
        if not name.startswith("partials/") and name != "base.html"
    ]


# The builder may or may not turn the whitespace options on; the templates
# should come out the same either way.
@pytest.mark.parametrize(
    "env_options",
    [{}, {"trim_blocks": True, "lstrip_blocks": True}],
    ids=["default", "trimmed"],
)
@pytest.mark.parametrize("theme,name", page_templates())
def test_output_has_balanced_landmarks(theme, name, env_options):
    world = make_site(theme)
    term = world.tags.terms["python"]
    pages = {
        "index.html": world.home,
        "section.html": world.posts_index,
        "taxonomy.html": make_page("Tags", "/tags/", kind="taxonomy"),
        "term.html": make_page("python", "/tags/python/", kind="term"),
        "404.html": make_page("", "/404.html", kind="404"),
        "search.html": make_page("Search", "/search/"),
    }
    html = render(
        theme,
        name,
        pages.get(name, world.second),
        world,
        section=world.posts,
        pages=world.site.pages,
        paginator=make_paginator(world.site.pages, 2, 3),
        taxonomy=world.tags,
        term=term,
        env_options=env_options,
    )
    assert not re.search(r"\w<(?:a|time)\b", html), "a word runs straight into a tag"
    for tag in ("html", "head", "body", "main", "header", "footer", "nav", "ul", "ol"):
        opened = len(re.findall(rf"<{tag}[\s>]", html))
        closed = html.count(f"</{tag}>")
        assert (
            opened == closed
        ), f"{theme}/{name}: <{tag}> {opened} opened, {closed} closed"
    assert html.count("<main") == 1
    assert html.count("<h1") == 1
    assert "<title>" in html and "Undefined" not in html
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)
