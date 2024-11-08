from __future__ import annotations

import sys
from pathlib import Path

import pytest

from inkstone.build import Builder, LinkChecker
from inkstone.build.templates import BUILTIN_THEMES
from inkstone.config import load_config
from inkstone.errors import PluginError
from inkstone.plugins import PluginManager

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "blog"


def example_config(tmp_path):
    """The example site's config, redirected to write below tmp_path.

    Skips when a piece that somebody else owns is not there (yet).
    """
    if sys.version_info < (3, 11):
        pytest.skip("the example site is configured in TOML")
    if not (EXAMPLE / "inkstone.toml").is_file():
        pytest.skip("examples/blog is not there")
    if not (BUILTIN_THEMES / "default" / "templates" / "base.html").is_file():
        pytest.skip("the default theme is not there")
    config = load_config(
        EXAMPLE,
        overrides={
            "output_dir": str(tmp_path / "public"),
            "cache_dir": str(tmp_path / "cache"),
        },
    )
    try:
        PluginManager(config).load()
    except PluginError as exc:
        pytest.skip(f"a plugin the example enables is not available: {exc}")
    return config


def test_example_blog_builds_with_the_default_theme(tmp_path):
    config = example_config(tmp_path)
    sources_before = sorted(path for path in EXAMPLE.rglob("*") if path.is_file())

    builder = Builder(config)
    report = builder.build()

    out = tmp_path / "public"
    assert report.pages_written >= 20
    assert (out / "index.html").is_file()
    assert (out / "404.html").is_file()
    assert (out / "posts" / "index.html").is_file()
    assert (out / "tags" / "index.html").is_file()
    assert (out / "css" / "main.css").is_file()
    assert (out / "css" / "highlight.css").is_file()
    for name in ("rss.xml", "atom.xml", "sitemap.xml", "search-index.json"):
        assert (out / name).is_file(), name

    home = (out / "index.html").read_text(encoding="utf-8")
    assert "<title>" in home and config.title in home
    posts = [page for page in builder.site.pages if page.in_section("posts")]
    assert posts
    for page in posts:
        html = (out / page.output_path).read_text(encoding="utf-8")
        assert page.layout == "posts/page.html"
        assert "</html>" in html
    # the example's own override of the theme
    assert builder.site.get_page("projects").layout == "projects/section.html"

    problems = LinkChecker(out, base_url=config.base_url).run()
    assert [str(problem) for problem in problems] == []

    # nothing was written next to the example's sources
    sources_after = sorted(path for path in EXAMPLE.rglob("*") if path.is_file())
    assert sources_after == sources_before

    again = Builder(config).build()
    assert again.pages_written == 0
    assert again.output_paths == []
