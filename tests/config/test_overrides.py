from __future__ import annotations

import pytest

from inkstone.config import load_config
from inkstone.errors import ConfigError


def test_environment_overrides_the_file(site, monkeypatch):
    site.write("title: File\nbase_url: https://file.example/\n", "inkstone.yaml")
    monkeypatch.setenv("INKSTONE_BASE_URL", "https://env.example/")
    config = load_config(site.root)
    assert config.base_url == "https://env.example/"
    assert config.title == "File"


def test_double_underscore_separates_levels(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_BUILD__DRAFTS", "1")
    monkeypatch.setenv("INKSTONE_PAGINATION__PER_PAGE", "25")
    monkeypatch.setenv("INKSTONE_SERVER__HOST", "0.0.0.0")
    config = load_config(site.root)
    assert config.build.drafts is True
    assert config.pagination.per_page == 25
    assert config.server.host == "0.0.0.0"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("No", False),
        ("off", False),
        ("", False),
    ],
)
def test_booleans_from_the_environment(site, monkeypatch, text, expected):
    monkeypatch.setenv("INKSTONE_BUILD__MINIFY", text)
    assert load_config(site.root).build.minify is expected


def test_bad_boolean_from_the_environment_names_the_variable(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_BUILD__DRAFTS", "maybe")
    with pytest.raises(ConfigError) as excinfo:
        load_config(site.root)
    assert "build.drafts must be true or false" in excinfo.value.message
    assert "INKSTONE_BUILD__DRAFTS" in excinfo.value.message


def test_bad_integer_from_the_environment(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_SERVER__PORT", "http")
    with pytest.raises(ConfigError, match="server.port must be an integer"):
        load_config(site.root)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("toc, related", ["toc", "related"]),
        ("toc", ["toc"]),
        ('["toc", "series"]', ["toc", "series"]),
        ("", []),
    ],
)
def test_lists_from_the_environment(site, monkeypatch, text, expected):
    monkeypatch.setenv("INKSTONE_PLUGINS", text)
    assert load_config(site.root).plugins == expected


def test_free_form_params_from_the_environment_get_a_guessed_type(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_PARAMS__SHOW_TOC", "false")
    monkeypatch.setenv("INKSTONE_PARAMS__COLUMNS", "3")
    monkeypatch.setenv("INKSTONE_PARAMS__ACCENT", "#8c3b2a")
    config = load_config(site.root)
    assert config.params.show_toc is False
    assert config.params.columns == 3
    assert config.params.accent == "#8c3b2a"


def test_unrelated_inkstone_variables_are_ignored(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_DEBUG", "1")
    monkeypatch.setenv("INKSTONE_", "x")
    monkeypatch.setenv("INKSTONE_NO_COLOR", "1")
    config = load_config(site.root)
    assert "debug" not in config
    assert config.warnings == []


def test_values_from_the_environment_are_validated_like_the_file(site, monkeypatch):
    monkeypatch.setenv("INKSTONE_PAGINATION__PER_PAGE", "0")
    with pytest.raises(ConfigError, match="pagination.per_page must be at least 1"):
        load_config(site.root)


def test_cli_overrides_beat_environment_and_file(site, monkeypatch):
    site.write("title: File\noutput_dir: from-file\n", "inkstone.yaml")
    monkeypatch.setenv("INKSTONE_OUTPUT_DIR", "from-env")
    monkeypatch.setenv("INKSTONE_TITLE", "Env")
    config = load_config(site.root, overrides={"output_dir": "from-cli"})
    assert config.output_dir == "from-cli"
    assert config.title == "Env"
    assert config.overrides == {"output_dir": "from-cli"}


def test_overrides_use_dotted_keys(site):
    config = load_config(
        site.root,
        overrides={
            "build.drafts": True,
            "base_url": "http://localhost:8000/",
            "server.port": 9001,
            "params.accent": "teal",
            "plugin.related.limit": 3,
        },
    )
    assert config.build.drafts is True
    assert config.server.port == 9001
    assert config.params.accent == "teal"
    assert config.plugin.related.limit == 3


def test_string_overrides_are_converted_to_the_type_of_the_setting(site):
    config = load_config(
        site.root,
        overrides={"build.minify": "true", "server.port": "9002", "plugins": "toc"},
    )
    assert config.build.minify is True
    assert config.server.port == 9002
    assert config.plugins == ["toc"]


def test_override_of_the_wrong_type_is_an_error(site):
    with pytest.raises(ConfigError, match="build.drafts must be true or false"):
        load_config(site.root, overrides={"build.drafts": 3})
    with pytest.raises(ConfigError, match="title must be a string"):
        load_config(site.root, overrides={"title": 3})


def test_override_of_an_unknown_setting_is_an_error(site):
    with pytest.raises(ConfigError, match="unknown setting 'biuld.drafts'.*'build'"):
        load_config(site.root, overrides={"biuld.drafts": True})


def test_override_below_a_scalar_is_an_error(site):
    with pytest.raises(ConfigError, match="'title' is not a table"):
        load_config(site.root, overrides={"title.sub": "x"})


def test_none_means_the_option_was_not_given(site):
    site.write("title: File\nbuild:\n  drafts: true\n", "inkstone.yaml")
    config = load_config(
        site.root, overrides={"build.drafts": None, "title": None, "server.port": 0}
    )
    assert config.build.drafts is True
    assert config.title == "File"
    assert config.overrides == {"server.port": 0}


def test_overrides_are_not_mutated_and_survive_on_the_config(site):
    overrides = {"build.drafts": True}
    config = load_config(site.root, overrides=overrides)
    config.overrides["x"] = 1
    assert overrides == {"build.drafts": True}


def test_param_overrides_also_beat_the_theme_defaults(site, monkeypatch):
    site.theme("mine", 'name = "mine"\n[params]\naccent = "red"\nwide = false\n')
    site.write("theme: mine\n", "inkstone.yaml")
    monkeypatch.setenv("INKSTONE_PARAMS__WIDE", "true")
    config = load_config(site.root, overrides={"params.accent": "green"})
    assert config.params.accent == "green"
    assert config.params.wide is True
