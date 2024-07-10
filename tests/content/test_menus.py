from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstone.content import Menu, MenuEntry
from inkstone.content.menus import Menus, build_menus
from inkstone.errors import ContentError
from inkstone.tmpl import DictLoader, Environment


def names(entries):
    return [entry.name for entry in entries]


def test_menus_from_the_config():
    menus = build_menus(
        {
            "main": [
                {"name": "About", "url": "/about/", "weight": 20},
                {"name": "Blog", "url": "/posts/", "weight": 10},
            ],
            "footer": [{"name": "RSS", "url": "/rss.xml"}],
        }
    )
    assert sorted(menus) == ["footer", "main"]
    main = menus["main"]
    assert isinstance(main, Menu)
    assert main.name == "main"
    assert names(main) == ["Blog", "About"]
    entry = main[0]
    assert isinstance(entry, MenuEntry)
    assert (entry.name, entry.url, entry.weight) == ("Blog", "/posts/", 10)
    assert entry.identifier == "blog"
    assert entry.page is None
    assert menus.footer[0].url == "/rss.xml"


def test_equal_weights_keep_the_order_of_the_config():
    menus = build_menus(
        {"main": [{"name": n, "url": f"/{n}/"} for n in ("c", "a", "b")]}
    )
    assert names(menus["main"]) == ["c", "a", "b"]


def test_missing_menu_is_empty_rather_than_an_error():
    menus = build_menus({})
    assert isinstance(menus, Menus)
    assert menus["main"] == []
    assert menus.main == []
    assert not menus.main
    assert "main" not in menus


def test_extra_keys_are_readable_as_attributes():
    menus = build_menus(
        {"main": [{"name": "Code", "url": "https://git.example/", "icon": "git"}]}
    )
    entry = menus["main"][0]
    assert entry.icon == "git"
    assert entry.params == {"icon": "git"}
    assert entry.external is True
    with pytest.raises(AttributeError):
        entry.nope


def test_children_listed_in_the_config():
    menus = build_menus(
        {
            "main": [
                {
                    "name": "Docs",
                    "url": "/docs/",
                    "children": [
                        {"name": "Guide", "url": "/docs/guide/", "weight": 2},
                        {"name": "Install", "url": "/docs/install/", "weight": 1},
                    ],
                }
            ]
        }
    )
    docs = menus["main"][0]
    assert docs.has_children
    assert names(docs.children) == ["Install", "Guide"]
    assert names(menus["main"].walk()) == ["Docs", "Install", "Guide"]
    assert menus["main"].find("guide").url == "/docs/guide/"
    assert menus["main"].find("nope") is None


def test_children_by_parent_identifier():
    menus = build_menus(
        {
            "main": [
                {"name": "Guide", "url": "/docs/guide/", "parent": "docs"},
                {"name": "Docs", "url": "/docs/", "identifier": "docs"},
                {"name": "Lost", "url": "/lost/", "parent": "no-such-parent"},
            ]
        }
    )
    main = menus["main"]
    assert names(main) == ["Docs", "Lost"]
    assert names(main[0].children) == ["Guide"]


def page(title, url, weight=0, **meta):
    return SimpleNamespace(
        title=title, url=url, weight=weight, meta=meta, source_path=f"{title}.md"
    )


def test_pages_join_menus_through_front_matter():
    pages = [
        page("About", "/about/", menu="main"),
        page("Contact", "/contact/", weight=5, menu=["main", "footer"]),
        page(
            "Imprint",
            "/imprint/",
            menu={"footer": {"name": "Legal", "weight": 1, "icon": "scale"}},
        ),
        page("Plain", "/plain/"),
    ]
    blog = {"name": "Blog", "url": "/posts/", "weight": 3}
    menus = build_menus({"main": [blog]}, pages)
    assert names(menus["main"]) == ["About", "Blog", "Contact"]
    assert names(menus["footer"]) == ["Legal", "Contact"]
    about = menus["main"][0]
    assert about.page is pages[0]
    assert about.url == "/about/"
    legal = menus["footer"][0]
    assert legal.icon == "scale"
    assert legal.weight == 1


def test_page_entries_can_name_a_parent():
    pages = [
        page("Docs", "/docs/", menu={"main": {"identifier": "docs"}}),
        page("Install", "/docs/install/", menu={"main": {"parent": "docs"}}),
    ]
    main = build_menus({}, pages)["main"]
    assert names(main) == ["Docs"]
    assert names(main[0].children) == ["Install"]


@pytest.mark.parametrize("spec", [3, {"main": "nope"}, {"main": {"weight": "heavy"}}])
def test_bad_menu_front_matter_names_the_file(spec):
    with pytest.raises(ContentError) as excinfo:
        build_menus({}, [page("Bad", "/bad/", menu=spec)])
    assert excinfo.value.path == "Bad.md"


def test_malformed_config_entry_is_an_error():
    with pytest.raises(ContentError, match=r"menus.main\[0\]: a menu entry needs"):
        build_menus({"main": [{"name": "No URL"}]})


def test_active_state_helpers():
    menus = build_menus(
        {
            "main": [
                {"name": "Home", "url": "/"},
                {"name": "Blog", "url": "/posts/"},
                {"name": "Docs", "url": "/docs", "children": [
                    {"name": "Guide", "url": "/docs/guide/"},
                ]},
                {"name": "Code", "url": "https://git.example/me"},
            ]
        }
    )
    home, blog, docs, code = menus["main"]
    post = SimpleNamespace(url="/posts/2024/hello/")
    assert blog.is_active("/posts/") and blog.is_active(SimpleNamespace(url="/posts"))
    assert not blog.is_active(post)
    assert blog.is_ancestor(post) and blog.is_current(post)
    assert not blog.is_ancestor("/posts/")
    assert blog.is_current("/posts/")
    # the home entry is not an ancestor of everything
    assert home.is_active("/") and not home.is_ancestor(post)
    assert docs.is_active("/docs/")
    assert docs.is_ancestor("/docs/guide/")
    assert docs.is_ancestor("/docs/guide/first-steps/")
    assert not docs.is_ancestor("/documents/")
    assert not code.is_ancestor(post) and not code.is_active(post)
    assert not blog.is_active(None)


def test_menu_active_picks_the_closest_entry():
    menus = build_menus(
        {
            "main": [
                {"name": "Docs", "url": "/docs/"},
                {"name": "Guide", "url": "/docs/guide/"},
                {"name": "Blog", "url": "/posts/"},
            ]
        }
    )
    main = menus["main"]
    assert main.active("/docs/guide/steps/").name == "Guide"
    assert main.active("/docs/install/").name == "Docs"
    assert main.active("/docs/").name == "Docs"
    assert main.active("/about/") is None


def test_site_menus_combine_config_and_pages(files):
    files.configure(
        """
        menus:
          main:
            - {name: Blog, url: /posts/, weight: 10}
        """
    )
    files.write("about.md", "---\ntitle: About\nmenu:\n  main:\n    weight: 20\n---\n")
    files.write("hidden.md", "---\ntitle: Hidden\nmenu: main\ndraft: true\n---\n")
    files.page("posts/a.md", title="A", date="2024-01-01")
    site = files.load()
    assert names(site.menus["main"]) == ["Blog", "About"]
    assert site.menus["main"][1].page is site.get_page("about.md")
    assert site.menus["footer"] == []
    assert "menu" not in site.get_page("about.md").params


def test_bad_menu_front_matter_in_a_site_names_the_content_file(files):
    files.write("about.md", "---\ntitle: About\nmenu: 3\n---\n")
    with pytest.raises(ContentError, match="menu must be a menu name"):
        files.load()


def test_menus_in_templates():
    menus = build_menus(
        {
            "main": [
                {"name": "Blog", "url": "/posts/"},
                {"name": "About", "url": "/about/"},
            ]
        }
    )
    env = Environment(
        loader=DictLoader(
            {
                "nav": (
                    "{% for item in menus.main %}"
                    "{{ item.name }}{% if item.is_current(page) %}*{% endif %} "
                    "{% endfor %}|{% if menus.footer %}footer{% else %}none{% endif %}"
                )
            }
        )
    )
    page_obj = SimpleNamespace(url="/posts/hello/")
    rendered = env.get_template("nav").render(menus=menus, page=page_obj)
    assert rendered == "Blog* About |none"
