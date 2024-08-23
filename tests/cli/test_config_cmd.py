from __future__ import annotations

import json

import pytest

from inkstone import tomlw
from inkstone.cli import config_cmd
from inkstone.config import default_config
from inkstone.errors import ConfigError

from .conftest import write

CONFIG = """\
title = "Wet Ink"
base_url = "https://wetink.example/"
plugins = ["shortcodes", "related"]

[author]
name = "Magdy Gawad"

[build]
minify = true

[[menus.main]]
name = "Posts"
url = "/posts/"
weight = 10

[[menus.main]]
name = "About"
url = "/about/"

[plugin.related]
limit = 3
"""


@pytest.fixture
def configured(site):
    write(site / "inkstone.toml", CONFIG)
    return site


def test_prints_the_resolved_config_as_toml(run, configured):
    result = run("config")
    assert result.code == 0
    assert result.err == ""
    data = tomlw.loads(result.out)
    assert data["title"] == "Wet Ink"
    assert data["author"] == {"name": "Magdy Gawad", "email": "", "url": ""}
    # defaults are filled in around what the file says
    assert data["build"]["minify"] is True and data["build"]["incremental"] is True
    assert data["pagination"]["per_page"] == 10
    assert data["plugin"] == {"related": {"limit": 3}}
    assert [entry["name"] for entry in data["menus"]["main"]] == ["Posts", "About"]


def test_json_output(run, configured):
    result = run("config", "--json")
    data = json.loads(result.out)
    assert data["title"] == "Wet Ink"
    assert data["server"]["port"] == 8000
    assert data["plugins"] == ["shortcodes", "related"]
    assert result.out.startswith("{\n  ")


def test_toml_and_json_agree(run, configured):
    as_toml = tomlw.loads(run("config").out)
    as_json = json.loads(run("config", "--json").out)
    assert as_toml == as_json


@pytest.mark.parametrize(
    "key, expected",
    [
        ("title", "Wet Ink"),
        ("base_url", "https://wetink.example/"),
        ("author.name", "Magdy Gawad"),
        ("author.email", ""),
        ("build.minify", "true"),
        ("build.drafts", "false"),
        ("build.jobs", "0"),
        ("server.port", "8000"),
        ("search.fields.title", "3.0"),
        ("plugins", '["shortcodes", "related"]'),
        ("ignore", '["*.swp", "*~", ".DS_Store"]'),
        ("plugin.related.limit", "3"),
        ("menus.main.1.url", "/about/"),
        ("permalinks.posts", "/:year/:month/:slug/"),
    ],
)
def test_single_values_are_printed_bare(run, configured, key, expected):
    result = run("config", key)
    assert (result.code, result.out) == (0, expected + "\n")


def test_a_table_is_printed_as_toml(run, configured):
    result = run("config", "author")
    assert tomlw.loads(result.out) == {"name": "Magdy Gawad", "email": "", "url": ""}
    assert run("config", "build").out.splitlines()[0] == "drafts = false"


def test_a_list_of_tables_is_printed_as_json(run, configured):
    result = run("config", "menus.main")
    assert [entry["url"] for entry in json.loads(result.out)] == ["/posts/", "/about/"]


@pytest.mark.parametrize(
    "key, expected",
    [
        ("title", '"Wet Ink"'),
        ("build.minify", "true"),
        ("server.port", "8000"),
        ("plugins", '[\n  "shortcodes",\n  "related"\n]'),
    ],
)
def test_single_values_as_json(run, configured, key, expected):
    assert run("config", "--json", key).out == expected + "\n"


@pytest.mark.parametrize(
    "key, message",
    [
        ("titel", "no setting called 'titel', did you mean 'title'?"),
        ("build.minfy", "no setting called 'build.minfy', did you mean 'build.minify'"),
        ("nothing.like.it", "no setting called 'nothing.like.it'"),
        ("title.sub", "no setting called 'title.sub'"),
        ("menus.main.7", "no setting called 'menus.main.7'"),
    ],
)
def test_unknown_keys(run, configured, key, message):
    result = run("config", key)
    assert result.code == 1
    assert result.out == ""
    assert result.err.startswith(f"error: {message}")


def test_defaults(run, configured):
    result = run("config", "--defaults")
    assert tomlw.loads(result.out) == default_config()
    assert run("config", "--defaults", "title").out == "My Site\n"
    assert run("config", "--defaults", "build.minify").out == "false\n"
    assert json.loads(run("config", "--defaults", "--json").out) == default_config()


def test_defaults_work_outside_a_site(run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("config", "--defaults", "markdown.highlight_style")
    assert (result.code, result.out) == (0, "dusk\n")
    assert run("config").code == 1


def test_overrides_from_the_environment_show_up(run, configured, monkeypatch):
    monkeypatch.setenv("INKSTONE_BUILD__DRAFTS", "1")
    monkeypatch.setenv("INKSTONE_TITLE", "From env")
    assert run("config", "build.drafts").out == "true\n"
    assert run("config", "title").out == "From env\n"


def test_theme_params_are_part_of_the_resolved_config(run, configured):
    params = json.loads(run("config", "--json", "params").out)
    assert params["search_url"] == "/search/"


def test_dotted_keys():
    tree = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    assert config_cmd.dotted_keys(tree) == ["a", "b", "b.c", "b.d", "b.d.e"]


def test_pick():
    tree = {"a": {"b": [10, {"c": "deep"}]}, "empty": ""}
    assert config_cmd.pick(tree, "a.b.1.c") == "deep"
    assert config_cmd.pick(tree, "a.b.0") == 10
    assert config_cmd.pick(tree, "empty") == ""
    for key in ("a.x", "a.b.5", "a.b.c", "empty.x", ""):
        with pytest.raises(ConfigError):
            config_cmd.pick(tree, key)


@pytest.mark.parametrize(
    "value, text",
    [
        ("plain", "plain"),
        ("", ""),
        (True, "true"),
        (False, "false"),
        (0, "0"),
        (2.5, "2.5"),
        (None, ""),
        ([], "[]"),
        (["a", 1], '["a", 1]'),
        ({"a": 1, "b": {"c": "x"}}, 'a = 1\n\n[b]\nc = "x"'),
        ({}, ""),
    ],
)
def test_as_toml(value, text):
    assert config_cmd.as_toml(value) == text
