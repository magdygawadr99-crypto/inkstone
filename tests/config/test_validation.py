from __future__ import annotations

import pytest

from inkstone.config import load_config
from inkstone.errors import ConfigError


def load_yaml(site, text):
    site.write(text, "inkstone.yaml")
    return load_config(site.root)


@pytest.mark.parametrize(
    ("text", "key", "expected"),
    [
        ("title: 12\n", "title", "a string"),
        ("build:\n  drafts: 'yes'\n", "build.drafts", "true or false"),
        ("build:\n  jobs: two\n", "build.jobs", "an integer"),
        ("build:\n  jobs: true\n", "build.jobs", "an integer"),
        ("build: fast\n", "build", "a table"),
        ("plugins: toc\n", "plugins", "a list of strings"),
        ("ignore: {a: 1}\n", "ignore", "a list of strings"),
        ("pagination:\n  per_page: '10'\n", "pagination.per_page", "an integer"),
        ("markdown:\n  smart: 1\n", "markdown.smart", "true or false"),
        ("feeds:\n  sections: posts\n", "feeds.sections", "a list of strings"),
        ("server:\n  port: '8000'\n", "server.port", "an integer"),
        ("search:\n  fields: [title]\n", "search.fields", "a table"),
        ("params: 3\n", "params", "a table"),
    ],
)
def test_wrong_type_names_the_key(site, text, key, expected):
    with pytest.raises(ConfigError) as excinfo:
        load_yaml(site, text)
    message = excinfo.value.message
    assert message.startswith(f"{key} must be {expected}")
    assert excinfo.value.path == (site.root / "inkstone.yaml").resolve()


def test_wrong_type_message_shows_the_value_and_its_type(site):
    with pytest.raises(ConfigError, match=r"got 'yes' \(string\)"):
        load_yaml(site, "build:\n  minify: 'yes'\n")


def test_list_items_have_to_be_strings(site):
    with pytest.raises(ConfigError, match=r"plugins\[1\] must be a string, got 3"):
        load_yaml(site, "plugins: [toc, 3]\n")


def test_author_fields_have_to_be_strings_but_extras_are_allowed(site):
    config = load_yaml(site, "author:\n  name: Magdy\n  avatar: /me.png\n")
    assert config.author.avatar == "/me.png"
    with pytest.raises(ConfigError, match="author.name must be a string"):
        load_yaml(site, "author:\n  name: 3\n")


def test_unknown_top_level_key_warns_with_a_suggestion(site, capsys):
    config = load_yaml(site, "titel: Oops\nbase_ulr: /x/\n")
    assert config.title == "My Site"
    assert len(config.warnings) == 2
    assert "unknown setting 'titel', did you mean 'title'?" in config.warnings
    assert "unknown setting 'base_ulr', did you mean 'base_url'?" in config.warnings
    err = capsys.readouterr().err
    assert "did you mean 'title'?" in err
    assert "inkstone.yaml" in err


def test_unknown_key_without_a_near_match_points_at_params(site):
    config = load_yaml(site, "favourite_colour: green\n")
    (warning,) = config.warnings
    assert "unknown setting 'favourite_colour'" in warning
    assert "[params]" in warning


def test_unknown_nested_key_warns_with_its_full_name(site):
    config = load_yaml(site, "build:\n  minfy: true\n")
    assert config.warnings == [
        "unknown setting 'build.minfy', did you mean 'build.minify'?"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "params:\n  anything: goes\n  nested: {a: 1}\n",
        "plugin:\n  related:\n    limit: 5\n",
        "permalinks:\n  notes: /n/:slug/\n",
        "taxonomies:\n  series: series\n",
        "author:\n  mastodon: '@me'\n",
        "search:\n  fields:\n    description: 1.5\n",
    ],
)
def test_open_tables_take_any_key_without_warning(site, text):
    assert load_yaml(site, text).warnings == []


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("base_url: ftp://example.com/\n", "base_url must be an http(s) URL"),
        ("base_url: example.com\n", "base_url must be an http(s) URL"),
        ("base_url: https://example.com/?x=1\n", "query or fragment"),
        ("timezone: Mars/Olympus\n", "timezone: unknown time zone"),
        ("content_dir: ''\n", "content_dir cannot be empty"),
        ("theme: ''\n", "theme cannot be empty"),
        ("ignore: ['[z-a]']\n", "ignore: bad pattern"),
        ("build:\n  jobs: -1\n", "build.jobs cannot be negative"),
        ("pagination:\n  per_page: 0\n", "pagination.per_page must be at least 1"),
        ("pagination:\n  path: a/b\n", "pagination.path must be a single URL segment"),
        ("feeds:\n  limit: -5\n", "feeds.limit cannot be negative"),
        ("server:\n  port: 70000\n", "server.port must be between 0 and 65535"),
        ("sitemap:\n  changefreq: often\n", "sitemap.changefreq must be one of"),
        ("permalinks:\n  posts: ':year/:slug/'\n", "permalinks.posts must start with"),
        ("permalinks:\n  posts: 3\n", "permalinks.posts must be a string"),
        ("taxonomies:\n  tags: 3\n", "taxonomies.tags must be the singular name"),
        ("taxonomies:\n  'a/b': x\n", "cannot be used as a URL segment"),
        ("search:\n  fields:\n    title: heavy\n", "title must be a number"),
        ("search:\n  fields:\n    title: -1\n", "title cannot be negative"),
        ("plugin:\n  related: 5\n", "plugin.related must be a table"),
        ("menus:\n  main: nope\n", "menus.main must be a list of entries"),
        ("menus:\n  main:\n    - {name: Blog}\n", "menus.main[0] needs a 'url'"),
        ("menus:\n  main:\n    - {url: /x/}\n", "menus.main[0] needs a 'name'"),
        (
            "menus:\n  main:\n    - {name: A, url: /a/, weight: heavy}\n",
            "menus.main[0].weight must be a number",
        ),
        (
            "menus:\n  main:\n    - {name: A, url: /a/, children: [{name: B}]}\n",
            "menus.main[0].children[0] needs a 'url'",
        ),
    ],
)
def test_invalid_values_are_rejected(site, text, fragment):
    with pytest.raises(ConfigError) as excinfo:
        load_yaml(site, text)
    assert fragment in excinfo.value.message


def test_unknown_permalink_token_suggests_the_right_one(site):
    with pytest.raises(ConfigError, match="token ':yaer', did you mean ':year'"):
        load_yaml(site, "permalinks:\n  posts: /:yaer/:slug/\n")


def test_unknown_permalink_token_without_a_guess_lists_them_all(site):
    with pytest.raises(ConfigError, match=r"\(known: :year :month :day :slug"):
        load_yaml(site, "permalinks:\n  posts: /:zzz/\n")


def test_unknown_highlight_style_suggests_one(site):
    with pytest.raises(ConfigError, match="unknown style 'dusc', did you mean 'dusk'"):
        load_yaml(site, "markdown:\n  highlight_style: dusc\n")


def test_highlight_style_is_not_checked_when_highlighting_is_off(site):
    config = load_yaml(
        site, "markdown:\n  highlight: false\n  highlight_style: whatever\n"
    )
    assert config.markdown.highlight_style == "whatever"


@pytest.mark.parametrize(
    "output_dir", [".", "content", "content/..", "static", "templates", "data"]
)
def test_output_dir_may_not_swallow_the_sources(site, output_dir):
    with pytest.raises(ConfigError, match="output_dir .* cannot be"):
        load_yaml(site, f"output_dir: '{output_dir}'\n")


def test_output_dir_above_the_root_is_refused(site):
    with pytest.raises(ConfigError, match="a clean build would delete the sources"):
        load_yaml(site, "output_dir: '..'\n")


def test_cache_dir_may_not_be_the_root(site):
    with pytest.raises(ConfigError, match="cache_dir .* cannot be the site root"):
        load_yaml(site, "cache_dir: '.'\n")


def test_port_zero_is_allowed_for_an_ephemeral_port(site):
    assert load_yaml(site, "server:\n  port: 0\n").server.port == 0


def test_iana_timezone_names_work_where_the_database_exists(site):
    zoneinfo = pytest.importorskip("zoneinfo")
    try:
        zoneinfo.ZoneInfo("Europe/Berlin")
    except zoneinfo.ZoneInfoNotFoundError:
        pytest.skip("no time zone database on this machine")
    config = load_yaml(site, "timezone: Europe/Berlin\n")
    assert str(config.tzinfo) == "Europe/Berlin"
