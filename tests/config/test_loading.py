from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from inkstone.config import (
    CONFIG_NAMES,
    Config,
    default_config,
    find_config_file,
    find_site_root,
    load_config,
)
from inkstone.errors import ConfigError

needs_toml = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="reading TOML needs Python 3.11"
)


def test_defaults_without_a_config_file(site):
    config = load_config(site.root)
    assert config.path is None
    assert config.root == site.root.resolve()
    assert config.title == "My Site"
    assert config.base_url == "http://localhost:8000/"
    assert config.build.pretty_urls is True
    assert config.plugins == ["shortcodes", "toc", "reading_time"]
    assert config.taxonomies == {"tags": "tag", "categories": "category"}
    assert config.permalinks == {"posts": "/:year/:month/:slug/"}


def test_default_config_is_a_fresh_copy_each_time():
    first = default_config()
    first["build"]["drafts"] = True
    first["plugins"].append("related")
    second = default_config()
    assert second["build"]["drafts"] is False
    assert second["plugins"] == ["shortcodes", "toc", "reading_time"]


def test_default_config_has_every_documented_section():
    tree = default_config()
    for key in (
        "author",
        "build",
        "markdown",
        "permalinks",
        "taxonomies",
        "pagination",
        "feeds",
        "search",
        "sitemap",
        "robots",
        "server",
        "menus",
        "params",
        "plugin",
    ):
        assert isinstance(tree[key], dict), key
    assert tree["search"]["fields"] == {"title": 3.0, "tags": 2.0, "body": 1.0}
    assert tree["server"]["port"] == 8000


@needs_toml
def test_toml_file_is_merged_over_the_defaults(site):
    path = site.write(
        """
        title = "Wet Ink"
        base_url = "https://example.com"

        [build]
        minify = true

        [author]
        name = "Magdy"
        """
    )
    config = load_config(site.root)
    assert config.path == path.resolve()
    assert config.title == "Wet Ink"
    assert config.build.minify is True
    # siblings of an overridden key keep their defaults
    assert config.build.incremental is True
    assert config.author.name == "Magdy"
    assert config.author.email == ""


def test_yaml_file(site):
    site.write(
        """
        title: From YAML
        build:
          drafts: true
        plugins: []
        """,
        "inkstone.yaml",
    )
    config = load_config(site.root)
    assert config.title == "From YAML"
    assert config.build.drafts is True
    assert config.plugins == []


def test_json_file(site):
    (site.root / "inkstone.json").write_text(
        json.dumps({"title": "From JSON", "pagination": {"per_page": 3}}),
        encoding="utf-8",
    )
    config = load_config(site.root)
    assert config.title == "From JSON"
    assert config.pagination.per_page == 3
    assert config.pagination.path == "page"


def test_explicit_path_wins_over_the_usual_names(site):
    site.write("title: Usual\n", "inkstone.yaml")
    other = site.write("title: Other\n", "staging.yml")
    config = load_config(site.root, path=other)
    assert config.title == "Other"
    assert config.path == other.resolve()


def test_explicit_path_may_be_relative_to_the_root(site, monkeypatch):
    site.write("title: Relative\n", "conf.yaml")
    monkeypatch.chdir(site.root.parent)
    assert load_config(site.root, path="conf.yaml").title == "Relative"


def test_missing_explicit_path_is_an_error(site):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(site.root, path=site.root / "nope.toml")


def test_missing_site_directory_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(tmp_path / "nowhere")


def test_unsupported_extension_is_an_error(site):
    path = site.write("title = x\n", "inkstone.ini")
    with pytest.raises(ConfigError, match="unsupported config format"):
        load_config(site.root, path=path)


def test_first_config_name_wins_and_the_rest_is_mentioned(site, capsys):
    site.write("title: YAML\n", "inkstone.yaml")
    site.write('{"title": "JSON"}', "inkstone.json")
    config = load_config(site.root)
    assert config.title == "YAML"
    assert "ignoring inkstone.json" in capsys.readouterr().err


def test_find_config_file_and_names(site):
    assert find_config_file(site.root) is None
    path = site.write("{}", "inkstone.json")
    assert find_config_file(site.root) == path
    assert CONFIG_NAMES[0] == "inkstone.toml"


def test_find_site_root_walks_up(site):
    site.write("title: x\n", "inkstone.yaml")
    deep = site.root / "content" / "posts"
    deep.mkdir(parents=True)
    assert find_site_root(deep) == site.root.resolve()
    assert find_site_root(site.root) == site.root.resolve()


def test_find_site_root_gives_none_outside_a_site(tmp_path):
    lonely = tmp_path / "a" / "b"
    lonely.mkdir(parents=True)
    found = find_site_root(lonely)
    # nothing in tmp_path; whatever is found has to be above it
    assert found is None or tmp_path.resolve() not in (found, *found.parents)


@pytest.mark.parametrize(
    ("name", "text", "fragment"),
    [
        ("inkstone.yaml", "title: [unclosed\n", "invalid YAML"),
        ("inkstone.json", '{"title": }', "invalid JSON"),
        ("inkstone.yaml", "- just\n- a list\n", "table of settings"),
    ],
)
def test_broken_files_name_the_file(site, name, text, fragment):
    path = site.write(text, name)
    with pytest.raises(ConfigError) as excinfo:
        load_config(site.root)
    assert fragment in excinfo.value.message
    assert excinfo.value.path == path.resolve()


@needs_toml
def test_broken_toml_names_file_and_line(site):
    path = site.write('title = "ok"\nbase_url = \n')
    with pytest.raises(ConfigError) as excinfo:
        load_config(site.root)
    assert "invalid TOML" in excinfo.value.message
    assert excinfo.value.path == path.resolve()
    assert excinfo.value.line == 2


def test_empty_file_is_all_defaults(site):
    site.write("", "inkstone.yaml")
    assert load_config(site.root).title == "My Site"


def test_access_styles_agree(site):
    site.write("title: Styles\nbuild:\n  minify: true\n", "inkstone.yaml")
    config = load_config(site.root)
    assert config.title == config["title"] == config.get("title") == "Styles"
    assert config.build.minify is True
    assert config["build"]["minify"] is True
    assert config.get("build.minify") is True
    assert config.get("build.nope") is None
    assert config.get("build.nope", 7) == 7
    assert config.get("nothing.at.all", "x") == "x"
    assert "title" in config
    assert "nope" not in config
    assert "build" in list(config)
    assert dict(config.items())["title"] == "Styles"


def test_missing_key_is_an_attribute_error(site):
    config = load_config(site.root)
    with pytest.raises(AttributeError, match="no config key 'nope'"):
        config.nope
    with pytest.raises(KeyError):
        config["nope"]
    assert not hasattr(config, "_private")


def test_set_and_item_assignment(site):
    config = load_config(site.root)
    config.set("build.drafts", True)
    config["title"] = "Changed"
    config.set("params.social", {"github": "x"})
    assert config.build.drafts is True
    assert config.title == "Changed"
    # dicts put in later get attribute access like the rest
    assert config.params.social.github == "x"


def test_to_dict_is_plain_and_detached(site):
    site.write("params:\n  social:\n    github: x\n", "inkstone.yaml")
    config = load_config(site.root)
    tree = config.to_dict()
    assert type(tree) is dict
    assert type(tree["params"]["social"]) is dict
    tree["title"] = "mutated"
    tree["build"]["drafts"] = True
    assert config.title == "My Site"
    assert config.build.drafts is False
    json.dumps(tree)


def test_derived_paths_are_absolute(site):
    site.write("output_dir: dist\ncache_dir: .cache\n", "inkstone.yaml")
    config = load_config(site.root)
    root = site.root.resolve()
    assert config.content_path == root / "content"
    assert config.output_path == root / "dist"
    assert config.static_path == root / "static"
    assert config.data_path == root / "data"
    assert config.templates_path == root / "templates"
    assert config.themes_path == root / "themes"
    assert config.cache_path == root / ".cache"
    assert config.plugins_path == root / "plugins"
    for name in ("content_path", "output_path", "cache_path"):
        assert getattr(config, name).is_absolute()


def test_absolute_directories_are_kept(site, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    config = load_config(site.root, overrides={"output_dir": str(elsewhere / "out")})
    assert config.output_path == (elsewhere / "out").resolve()


@pytest.mark.parametrize(
    ("given", "expected", "base_path"),
    [
        ("https://example.com", "https://example.com/", "/"),
        ("https://example.com/", "https://example.com/", "/"),
        ("https://example.com/blog", "https://example.com/blog/", "/blog/"),
        ("https://example.com/a/b/", "https://example.com/a/b/", "/a/b/"),
        ("/docs", "/docs/", "/docs/"),
        ("/", "/", "/"),
        ("", "/", "/"),
    ],
)
def test_base_url_is_normalised(site, given, expected, base_path):
    config = load_config(site.root, overrides={"base_url": given})
    assert config.base_url == expected
    assert config.base_path == base_path


@pytest.mark.parametrize(
    ("name", "offset"),
    [("UTC", 0), ("Z", 0), ("+02:00", 120), ("-0530", -330), ("+1", 60)],
)
def test_timezone_offsets(site, name, offset):
    config = load_config(site.root, overrides={"timezone": name})
    moment = dt.datetime(2024, 5, 3, tzinfo=config.tzinfo)
    assert moment.utcoffset() == dt.timedelta(minutes=offset)


def test_config_object_can_be_built_by_hand(tmp_path):
    config = Config(root=tmp_path)
    assert config.title == "My Site"
    assert config.path is None
    assert config.overrides == {}
    assert config.content_path == tmp_path.resolve() / "content"
    assert repr(config).startswith("<Config ")


def test_reload_reads_the_file_again_and_keeps_overrides(site):
    site.write("title: Before\n", "inkstone.yaml")
    config = load_config(site.root, overrides={"build.drafts": True})
    site.write("title: After\n", "inkstone.yaml")
    again = config.reload()
    assert again is not config
    assert again.title == "After"
    assert again.build.drafts is True
    assert config.title == "Before"


def test_reload_keeps_an_explicit_path(site):
    site.write("title: Usual\n", "inkstone.yaml")
    other = site.write("title: Staging\n", "staging.yaml")
    config = load_config(site.root, path=other)
    assert config.reload().title == "Staging"


def test_lists_replace_the_default_list(site):
    site.write("ignore: ['*.bak']\nplugins: [toc]\n", "inkstone.yaml")
    config = load_config(site.root)
    assert config.ignore == ["*.bak"]
    assert config.plugins == ["toc"]


def test_permalinks_and_taxonomies_replace_instead_of_merging(site):
    site.write(
        """
        permalinks:
          notes: /n/:slug/
        taxonomies:
          tags: tag
        """,
        "inkstone.yaml",
    )
    config = load_config(site.root)
    assert config.permalinks == {"notes": "/n/:slug/"}
    assert config.taxonomies == {"tags": "tag"}


def test_empty_taxonomies_table_means_none(site):
    site.write("taxonomies: {}\n", "inkstone.yaml")
    assert load_config(site.root).taxonomies == {}


def test_search_fields_replace_the_defaults(site):
    site.write("search:\n  fields:\n    title: 5\n", "inkstone.yaml")
    config = load_config(site.root)
    assert config.search.fields == {"title": 5}
    assert config.search.enabled is True


def test_menus_and_plugin_tables_are_kept_as_written(site):
    site.write(
        """
        menus:
          main:
            - {name: Blog, url: /posts/, weight: 10}
            - {name: About, url: /about/}
        plugin:
          related:
            limit: 5
        """,
        "inkstone.yaml",
    )
    config = load_config(site.root)
    assert config.menus.main[0].name == "Blog"
    assert config.menus.main[1].url == "/about/"
    assert config.plugin.related.limit == 5


def test_theme_params_sit_under_the_site_params(site):
    site.theme(
        "mine",
        """
        name = "mine"
        [params]
        accent = "red"
        show_toc = true
        [params.social]
        github = ""
        rss = true
        """,
    )
    site.write(
        """
        theme: mine
        params:
          accent: blue
          social:
            github: me
        """,
        "inkstone.yaml",
    )
    config = load_config(site.root)
    assert config.params.accent == "blue"
    assert config.params.show_toc is True
    assert config.params.social.github == "me"
    assert config.params.social.rss is True
    assert config.to_dict()["params"]["show_toc"] is True


def test_theme_params_stack_through_inheritance(site):
    site.theme("base", 'name = "base"\n[params]\na = 1\nb = 1\nc = 1\n')
    site.theme("child", 'name = "child"\ninherit = "base"\n[params]\nb = 2\nc = 2\n')
    site.write("theme: child\nparams:\n  c: 3\n", "inkstone.yaml")
    config = load_config(site.root)
    assert (config.params.a, config.params.b, config.params.c) == (1, 2, 3)


def test_unknown_theme_does_not_stop_the_config_from_loading(site):
    site.write("theme: nowhere\nparams:\n  x: 1\n", "inkstone.yaml")
    config = load_config(site.root)
    assert config.theme == "nowhere"
    assert config.params.x == 1


def test_broken_theme_file_is_a_config_error(site):
    directory = site.theme("mine", "name = \n")
    site.write("theme: mine\n", "inkstone.yaml")
    with pytest.raises(ConfigError) as excinfo:
        load_config(site.root)
    assert Path(excinfo.value.path) == directory / "theme.toml"
