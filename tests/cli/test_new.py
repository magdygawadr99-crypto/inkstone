from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from inkstone import frontmatter
from inkstone.config import load_config
from inkstone.scaffold.site import default_config_format

from .conftest import configure


# what `new site` writes depends on whether this Python can read TOML
CONFIG = f"inkstone.{default_config_format()}"


def today(site):
    return dt.datetime.now(load_config(site).tzinfo).date().isoformat()


class TestNewSite:
    def test_creates_a_site_and_says_what_to_do_next(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("new", "site", "myblog")
        assert result.code == 0
        assert result.err == ""
        assert result.out.splitlines() == [
            "Created a site in myblog (9 files). Next:",
            "",
            "  cd myblog",
            "  inkstone serve",
        ]
        assert (tmp_path / "myblog" / CONFIG).is_file()
        assert (tmp_path / "myblog" / "content" / "_index.md").is_file()

    def test_the_quick_start_from_the_readme(self, run, tmp_path, monkeypatch, builder):
        monkeypatch.chdir(tmp_path)
        assert run("new", "site", "myblog").code == 0
        monkeypatch.chdir(tmp_path / "myblog")
        # must not clash with the post the new site comes with
        post = run("new", "post", "Hello world")
        assert post.code == 0
        assert post.out.strip().endswith("-hello-world.md")
        built = run("build")
        assert built.code == 0 and "warning" not in built.out + built.err
        posts = (tmp_path / "myblog" / "public").glob("*/*/*/index.html")
        assert sorted(path.parent.name for path in posts) == [
            "first-post",
            "hello-world",
        ]
        assert run("check", "--strict").code == 0

    def test_title_and_theme(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("new", "site", "b", "--title", "My blog", "--theme", "paper")
        assert result.code == 0
        config = load_config(tmp_path / "b")
        assert (config.title, config.theme) == ("My blog", "paper")
        assert config.author.name == "Ada Example"

    def test_default_title_is_the_config_default(self, run, tmp_path):
        run("new", "site", tmp_path / "b")
        assert load_config(tmp_path / "b").title == "My Site"

    def test_in_the_current_directory(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("new", "site", ".")
        assert result.code == 0
        assert "cd " not in result.out
        assert "inkstone serve" in result.out
        assert (tmp_path / CONFIG).is_file()

    def test_a_site_outside_the_working_directory_is_named_in_full(
        self, run, tmp_path, monkeypatch
    ):
        (tmp_path / "here").mkdir()
        monkeypatch.chdir(tmp_path / "here")
        there = (tmp_path / "there").resolve()
        lines = run("new", "site", "../there").out.splitlines()
        assert lines[0] == f"Created a site in {there} (9 files). Next:"
        assert f"  cd {there}" in lines

    def test_quiet_and_verbose(self, run, tmp_path):
        assert run("-q", "new", "site", tmp_path / "quiet").out == ""
        result = run("new", "site", tmp_path / "loud", "-v")
        assert result.err.count("wrote ") == 9
        assert CONFIG in result.err

    def test_refuses_a_directory_that_is_not_empty(self, run, tmp_path):
        (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
        result = run("new", "site", tmp_path)
        assert result.code == 1
        assert "is not empty (use --force" in result.err
        assert sorted(os.listdir(tmp_path)) == ["keep.txt"]

    def test_force(self, run, tmp_path):
        (tmp_path / "keep.txt").write_text("x", encoding="utf-8")
        result = run("new", "site", tmp_path, "--force")
        assert result.code == 0
        assert (tmp_path / CONFIG).is_file()
        again = run("new", "site", tmp_path, "--force")
        assert again.code == 0
        assert "nothing written" in again.out

    def test_unknown_theme(self, run, tmp_path):
        result = run("new", "site", tmp_path / "x", "--theme", "neon")
        assert result.code == 1
        assert result.err.startswith("error: no theme called 'neon' (available: ")

    def test_does_not_need_to_be_inside_a_site(self, run, site):
        # ...and inside one it still makes a new, separate site
        result = run("new", "site", "nested")
        assert result.code == 0
        assert (site / "nested" / CONFIG).is_file()


class TestNewPost:
    def test_prints_the_path_of_the_new_file(self, run, site):
        result = run("new", "post", "Hello there")
        name = f"{today(site)}-hello-there.md"
        assert result.code == 0
        assert result.err == ""
        assert Path(result.out.strip()) == Path("content") / "posts" / name
        text = (site / "content" / "posts" / name).read_text(encoding="utf-8")
        assert text.splitlines() == [
            "---",
            "title: Hello there",
            f"date: {today(site)}",
            "tags: []",
            "---",
            "",
        ]

    def test_title_does_not_need_quotes(self, run, site):
        result = run("new", "post", "Three", "plain", "words", "--date", "2024-06-01")
        assert result.out.strip().endswith("2024-06-01-three-plain-words.md")
        post = site / "content" / "posts" / "2024-06-01-three-plain-words.md"
        meta, _body = frontmatter.parse(post.read_text(encoding="utf-8"))
        assert meta["title"] == "Three plain words"

    @pytest.mark.parametrize(
        "argv, rel, expected",
        [
            (
                ["Half an idea", "--draft"],
                "posts/2024-06-01-half-an-idea.md",
                {"draft": True, "tags": []},
            ),
            (
                ["Trip report", "--tags", "travel, photos"],
                "posts/2024-06-01-trip-report.md",
                {"tags": ["travel", "photos"]},
            ),
            (
                ["Changes in 1.2", "--section", "notes", "--slug", "changelog-1-2"],
                "notes/2024-06-01-changelog-1-2.md",
                {"title": "Changes in 1.2"},
            ),
            (
                ["Timed", "--date", "2024-06-01 09:15"],
                "posts/2024-06-01-timed.md",
                {"date": dt.datetime(2024, 6, 1, 9, 15)},
            ),
        ],
    )
    def test_options(self, run, site, argv, rel, expected):
        # a later --date replaces this one
        result = run("new", "post", "--date", "2024-06-01", *argv)
        assert result.code == 0
        path = site / "content" / rel
        assert path.is_file()
        meta, _body = frontmatter.parse(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            assert meta[key] == value

    def test_refuses_to_overwrite(self, run, site):
        assert run("new", "post", "Same", "--date", "2024-06-01").code == 0
        post = site / "content" / "posts" / "2024-06-01-same.md"
        post.write_text("precious", encoding="utf-8")
        result = run("new", "post", "Same", "--date", "2024-06-01")
        assert result.code == 1
        assert result.out == ""
        assert result.err == (
            "error: content/posts/2024-06-01-same.md: "
            "already exists, not overwriting it\n"
        )
        assert post.read_text(encoding="utf-8") == "precious"

    def test_bad_date(self, run, site):
        result = run("new", "post", "X", "--date", "someday")
        assert result.code == 1
        assert result.err.startswith("error: --date: ")

    def test_path_is_relative_to_the_working_directory(self, run, site, monkeypatch):
        monkeypatch.chdir(site / "content")
        result = run("new", "post", "Deep", "--date", "2024-06-01")
        assert Path(result.out.strip()) == Path("posts") / "2024-06-01-deep.md"

    def test_with_dash_c_from_outside(self, run, site, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("-C", "site", "new", "post", "Remote", "--date", "2024-06-01")
        assert result.code == 0
        expected = Path("site") / "content" / "posts" / "2024-06-01-remote.md"
        assert Path(result.out.strip()) == expected
        assert expected.is_file()

    def test_outside_a_site(self, run, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("new", "post", "Lost")
        assert result.code == 1
        assert "no inkstone site here" in result.err

    def test_respects_a_custom_content_dir(self, run, site):
        configure(site, prepend='content_dir = "src"\n')
        (site / "content").rename(site / "src")
        result = run("new", "post", "Moved", "--date", "2024-06-01")
        assert result.code == 0
        assert (site / "src" / "posts" / "2024-06-01-moved.md").is_file()


class TestNewPage:
    def test_creates_a_page_with_a_title(self, run, site):
        result = run("new", "page", "projects/widget.md")
        assert result.code == 0
        assert Path(result.out.strip()) == Path("content") / "projects" / "widget.md"
        page = site / "content" / "projects" / "widget.md"
        assert page.read_text(encoding="utf-8") == "---\ntitle: Widget\n---\n\n"

    def test_title_option_and_bundle(self, run, site):
        assert run("new", "page", "trip/", "--title", "The trip").code == 0
        page = site / "content" / "trip" / "index.md"
        assert frontmatter.parse(page.read_text("utf-8"))[0] == {"title": "The trip"}

    def test_refuses_to_overwrite(self, run, site):
        result = run("new", "page", "about.md")
        assert result.code == 1
        assert result.err == (
            "error: content/about.md: already exists, not overwriting it\n"
        )

    def test_refuses_to_leave_the_content_directory(self, run, site):
        result = run("new", "page", "../escape.md")
        assert result.code == 1
        assert "outside the content directory" in result.err
        assert not (site / "escape.md").exists()
