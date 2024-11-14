"""theme.toml, stylesheets, scripts and the other static files of the themes."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from . import layout

tomllib = pytest.importorskip("tomllib")

REQUIRED_KEYS = ["name", "description", "version"]

CSS_FILES = sorted(
    path
    for theme in layout.THEME_NAMES
    for path in (layout.THEMES / theme).rglob("*.css")
)
JS_FILES = sorted(
    path
    for theme in layout.THEME_NAMES
    for path in (layout.THEMES / theme).rglob("*.js")
)
TEXT_FILES = sorted(
    path
    for theme in layout.THEME_NAMES
    for path in (layout.THEMES / theme).rglob("*")
    if path.suffix in {".html", ".css", ".js", ".toml", ".svg"}
)


def rel(path):
    return path.relative_to(layout.THEMES).as_posix()


def load_theme(theme):
    with open(layout.THEMES / theme / "theme.toml", "rb") as f:
        return tomllib.load(f)


def merged_params(theme):
    params = {}
    for name in reversed(layout.chain(theme)):
        params.update(load_theme(name).get("params", {}))
    return params


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_theme_toml_has_required_keys(theme):
    meta = load_theme(theme)
    for key in REQUIRED_KEYS:
        assert isinstance(meta.get(key), str) and meta[key].strip(), key
    assert meta["name"] == theme
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])
    assert isinstance(meta.get("params", {}), dict)


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_theme_layout_on_disk(theme):
    assert (layout.THEMES / theme / "templates").is_dir()
    assert (layout.THEMES / theme / "static").is_dir()


def test_default_is_a_root_theme_and_paper_inherits_it():
    assert "inherit" not in load_theme("default")
    assert load_theme("paper")["inherit"] == "default"
    assert layout.chain("paper") == ["paper", "default"]


def test_default_declares_the_documented_params():
    params = load_theme("default")["params"]
    for key in (
        "accent",
        "show_reading_time",
        "show_toc",
        "date_format",
        "footer_text",
    ):
        assert key in params, key
    assert isinstance(params["social"], dict)
    assert isinstance(params["show_toc"], bool)
    assert "%" in params["date_format"]


@pytest.mark.parametrize("theme", layout.THEME_NAMES)
def test_params_read_by_templates_have_defaults(theme):
    # a param without a default is undefined on every site that does not set
    # it, and nobody finds out it exists
    params = merged_params(theme)
    for name in layout.all_templates(theme):
        source = layout.source_of(theme, name)
        for key in re.findall(r"config\.params\.([a-z_]+)", source):
            assert key in params, f"{theme}: {name} reads params.{key}"
        for key in re.findall(r"config\.params\.social\.([a-z_]+)", source):
            assert key in params["social"], f"{theme}: {name} reads social.{key}"


def test_paper_only_overrides_known_params_or_adds_its_own():
    paper = load_theme("paper")["params"]
    default = load_theme("default")["params"]
    for key, value in paper.items():
        if key in default:
            assert type(value) is type(default[key]), key


@pytest.mark.parametrize("path", CSS_FILES, ids=rel)
def test_css_braces_are_balanced(path):
    css = layout.strip_css_noise(layout.read(path))
    depth = 0
    for number, line in enumerate(css.splitlines(), 1):
        depth += line.count("{") - line.count("}")
        assert depth >= 0, f"{rel(path)}:{number}: closing brace without a rule"
        assert depth <= 3, f"{rel(path)}:{number}: nested {depth} levels deep"
    assert depth == 0, f"{rel(path)}: {depth} unclosed brace(s)"
    assert css.count("(") == css.count(")")
    assert css.count("[") == css.count("]")


@pytest.mark.parametrize("path", CSS_FILES, ids=rel)
def test_css_makes_no_external_requests(path):
    css = layout.read(path)
    assert "@import" not in css
    assert not re.search(r"url\(\s*[\"']?(?:https?:)?//", css)
    assert "@font-face" not in css


@pytest.mark.parametrize("path", CSS_FILES, ids=rel)
def test_css_custom_properties_are_defined(path):
    css = layout.strip_css_noise(layout.read(path))
    defined = set(re.findall(r"(--[\w-]+)\s*:", css))
    if path.name == "print.css":
        # print.css only re-colours what main.css set up
        main = layout.strip_css_noise(layout.read(path.with_name("main.css")))
        defined |= set(re.findall(r"(--[\w-]+)\s*:", main))
    used = set(re.findall(r"var\(\s*(--[\w-]+)", css))
    assert used <= defined, sorted(used - defined)


def test_main_css_has_both_colour_schemes():
    css = layout.read(layout.THEMES / "default" / "static" / "css" / "main.css")
    assert "@media (prefers-color-scheme: dark)" in css
    assert ':root[data-theme="dark"]' in css
    assert ':root:not([data-theme="light"])' in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ":focus-visible" in css

    # the two copies of the dark palette have to agree
    def palette(selector):
        start = css.index(selector)
        body = css[css.index("{", start) + 1 : css.index("}", start)]
        pairs = re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", body)
        return {name: " ".join(value.split()) for name, value in pairs}

    assert palette(':root:not([data-theme="light"]) {') == palette(
        ':root[data-theme="dark"] {'
    )


def test_classes_set_by_scripts_are_styled():
    # only the default theme: paper ships no scripts of its own
    css = layout.read(layout.THEMES / "default" / "static" / "css" / "main.css")
    scripts = "\n".join(layout.read(path) for path in JS_FILES)
    for name in (
        "code-copy",
        "code-copy--done",
        "code-copy--failed",
        "code-block__lang",
        "footnote-popover",
        "search-result__title",
        "search-result__summary",
        "search-status--error",
    ):
        assert name.split("--")[0] in scripts, f"{name} is not used by any script"
        assert "." + name in css, name
    # these two come from the search client rather than from the theme's js
    assert ".inkstone-search-result" in css and ".is-active" in css


@pytest.mark.parametrize("path", JS_FILES, ids=rel)
def test_scripts_are_plain_iifes(path):
    source = layout.read(path)
    code = re.sub(r"^\s*//.*$", "", source, flags=re.M).strip()
    assert code.startswith("(function () {"), rel(path)
    assert code.endswith("})();"), rel(path)
    assert '"use strict";' in code
    assert not re.search(r"^\s*(import|export)\s", code, re.M)
    assert "require(" not in code
    # ES2017 is the ceiling: no optional chaining, no nullish coalescing
    assert "?." not in code and "??" not in code


@pytest.mark.parametrize("path", JS_FILES, ids=rel)
def test_scripts_parse(path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_default_ships_the_scripts_the_templates_load():
    names = {path.name for path in JS_FILES if "default" in path.parts}
    assert names == {
        "theme.js",
        "nav.js",
        "toc.js",
        "code.js",
        "search-ui.js",
        "footnotes.js",
    }


def test_search_ui_uses_the_documented_client_api():
    source = layout.read(layout.THEMES / "default" / "static" / "js" / "search-ui.js")
    assert "InkstoneSearch.attach(" in source
    assert "data-search-script" in source and "data-search-index" in source
    assert 'event.key !== "/"' in source
    assert 'get("q")' in source


def test_theme_js_does_not_wait_for_the_dom():
    # it has to set data-theme before the first paint
    source = layout.read(layout.THEMES / "default" / "static" / "js" / "theme.js")
    first_apply = source.index("apply(readStored());")
    assert first_apply < source.index("DOMContentLoaded")
    assert "localStorage" in source
    base = layout.source_of("default", "base.html")
    tag = re.search(r"<script[^>]*theme\.js[^>]*>", base).group()
    assert "defer" not in tag and "async" not in tag
    assert base.index("theme.js") < base.index("</head>")


def test_favicon_is_a_small_svg():
    path = layout.THEMES / "default" / "static" / "favicon.svg"
    svg = layout.read(path)
    assert svg.lstrip().startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
    assert path.stat().st_size < 2048


@pytest.mark.parametrize("path", TEXT_FILES, ids=rel)
def test_text_files_are_tidy(path):
    layout.assert_tidy(path, rel(path))
