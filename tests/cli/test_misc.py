"""version, highlight-css and clean."""

from __future__ import annotations

import platform

import pytest

import inkstone
from inkstone.highlight import HtmlFormatter, list_styles

from .conftest import configure, write


def stylesheet(style):
    return HtmlFormatter(style=style).get_css(".highlight").rstrip() + "\n"


class TestVersion:
    def test_prints_the_version(self, run):
        result = run("version")
        assert (result.code, result.out, result.err) == (
            0,
            f"inkstone {inkstone.__version__}\n",
            "",
        )

    def test_verbose_says_where_it_runs(self, run):
        lines = run("version", "-v").out.splitlines()
        assert lines[0] == f"inkstone {inkstone.__version__}"
        assert lines[1].startswith(f"python {platform.python_version()} (")
        assert lines[2].startswith("platform ")
        assert lines[3].startswith("installed in ") and lines[3].endswith("inkstone")

    def test_works_anywhere(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert run("version").code == 0


class TestHighlightCss:
    def test_uses_the_style_of_the_site(self, run, site):
        configure(site, append='\n[markdown]\nhighlight_style = "paper"\n')
        result = run("highlight-css")
        assert result.code == 0
        assert result.out == stylesheet("paper")

    def test_default_style_outside_a_site(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("highlight-css")
        assert result.code == 0
        assert result.out == stylesheet("dusk")

    @pytest.mark.parametrize("style", list_styles())
    def test_every_style(self, run, style):
        result = run("highlight-css", "--style", style)
        assert result.code == 0
        assert result.out.startswith(".highlight {")
        assert result.out == stylesheet(style)

    def test_styles_differ(self, run):
        assert run("highlight-css", "--style", "dusk").out != (
            run("highlight-css", "--style", "paper").out
        )

    def test_selector(self, run):
        result = run("highlight-css", "--style", "mono", "--selector", "pre.code")
        lines = result.out.splitlines()
        assert lines[0].startswith("pre.code {")
        assert all(line.startswith(("pre.code", "@", " ", "}")) for line in lines)
        assert ".highlight" not in result.out

    def test_list(self, run):
        result = run("highlight-css", "--list")
        assert result.out.split() == list_styles()

    def test_unknown_style(self, run):
        result = run("highlight-css", "--style", "neon")
        assert result.code == 1
        assert result.out == ""
        assert result.err.startswith("error: no style called 'neon' (have: ")
        assert "dusk" in result.err

    def test_output_can_be_redirected_into_a_stylesheet(self, run, site):
        css = run("highlight-css", "--style", "dusk").out
        assert css.count("{") == css.count("}") > 10
        assert "\x1b" not in css


class TestClean:
    def test_removes_output_and_cache(self, run, site, builder):
        run("build")
        assert (site / "public").is_dir() and (site / ".inkstone-cache").is_dir()
        result = run("clean")
        assert result.code == 0
        assert result.out == "removed public, .inkstone-cache\n"
        assert not (site / "public").exists()
        assert not (site / ".inkstone-cache").exists()
        # sources stay
        assert (site / "content" / "about.md").is_file()
        assert (site / "inkstone.toml").is_file()

    def test_nothing_to_clean(self, run, site, builder):
        result = run("clean")
        assert (result.code, result.out) == (0, "nothing to clean\n")

    def test_only_what_is_there_is_mentioned(self, run, site, builder):
        write(site / "public" / "index.html", "old")
        assert run("clean").out == "removed public\n"

    def test_custom_directories(self, run, site, builder):
        configure(site, prepend='output_dir = "dist"\ncache_dir = ".cache/ink"\n')
        run("build")
        assert (site / "dist" / "index.html").is_file()
        run("clean")
        assert not (site / "dist").exists()
        assert not (site / ".cache" / "ink").exists()
        assert not (site / "public").exists()

    def test_quiet(self, run, site, builder):
        run("build")
        assert run("-q", "clean").out == ""
        assert not (site / "public").exists()

    def test_from_elsewhere(self, run, site, builder, tmp_path, monkeypatch):
        run("build")
        monkeypatch.chdir(tmp_path)
        result = run("-C", "site", "clean")
        assert result.code == 0
        assert not (site / "public").exists()

    def test_outside_a_site(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert run("clean").code == 1
