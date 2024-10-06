from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from inkstone.cli import build as build_command

from .conftest import configure, write

DRAFT = "---\ntitle: Not yet\ndate: 2024-05-04\ndraft: true\n---\n\nUnfinished.\n"
FUTURE = "---\ntitle: From the future\ndate: 2999-01-01\n---\n\nNot yet written.\n"
POST = "2024/05/first-post/index.html"


@pytest.fixture(autouse=True)
def needs_builder(builder):
    """Everything here runs a real build."""


def read(site, rel, output="public"):
    return (site / output / rel).read_text(encoding="utf-8")


def test_build_writes_the_site_and_reports(run, site):
    result = run("build")
    assert result.code == 0
    assert result.err == ""
    assert result.out.count("\n") == 1
    assert " written" in result.out and " in " in result.out
    for rel in ("index.html", POST, "about/index.html", "posts/index.html", "404.html",
                "rss.xml", "sitemap.xml", "search-index.json", "css/main.css"):
        assert (site / "public" / rel).is_file(), rel
    assert "<title>First post" in read(site, POST)
    assert (site / ".inkstone-cache").is_dir()


def test_scaffolded_site_builds_without_warnings(run, site):
    result = run("build")
    assert "warning" not in result.out and "warning" not in result.err
    post = read(site, POST)
    assert 'class="note note--info" role="note"' in post
    assert "{{<" not in post
    assert "Welcome to <strong>Test Site</strong>." in read(site, "index.html")


def test_second_build_is_incremental(run, site):
    run("build")
    result = run("build")
    assert result.code == 0
    assert result.out.startswith("0 pages written")
    assert "unchanged" in result.out


def test_quiet_prints_nothing(run, site):
    result = run("-q", "build")
    assert (result.code, result.out, result.err) == (0, "", "")


def test_drafts_flag(run, site):
    write(site / "content" / "posts" / "2024-05-04-not-yet.md", DRAFT)
    run("build")
    assert not (site / "public" / "2024" / "05" / "not-yet").exists()
    run("build", "--drafts")
    assert "Unfinished." in read(site, "2024/05/not-yet/index.html")
    # and without the flag the draft goes away again
    run("build")
    assert not (site / "public" / "2024" / "05" / "not-yet").exists()


def test_future_flag(run, site):
    write(site / "content" / "posts" / "future.md", FUTURE)
    run("build")
    assert not (site / "public" / "2999").exists()
    run("build", "--future")
    assert (site / "public" / "2999" / "01" / "future" / "index.html").is_file()


def test_base_url_flag(run, site):
    run("build", "--base-url", "https://example.org/blog/")
    post = read(site, POST)
    canonical = "https://example.org/blog/2024/05/first-post/"
    assert f'<link rel="canonical" href="{canonical}">' in post
    assert 'href="/blog/css/main.css"' in post


def test_output_flag_is_relative_to_the_cwd(run, site, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("-C", "site", "build", "--output", "elsewhere")
    assert result.code == 0
    assert (tmp_path / "elsewhere" / "index.html").is_file()
    assert not (site / "public").exists()
    assert not (site / "elsewhere").exists()


def test_minify_flag(run, site):
    run("build")
    plain = read(site, POST)
    stylesheet = read(site, "css/main.css")
    run("build", "--minify")
    small = read(site, POST)
    assert len(small) < len(plain)
    assert "\n  <" not in small
    # assets too, which the minify plugin would leave alone
    assert len(read(site, "css/main.css")) < len(stylesheet)


def test_fingerprint_flag(run, site):
    run("build", "--fingerprint")
    names = [path.name for path in (site / "public" / "css").glob("main*.css")]
    assert len(names) == 1 and names[0] != "main.css"
    assert f'href="/css/{names[0]}"' in read(site, POST)


def test_no_incremental_flag_reaches_the_builder(run, site, builder, monkeypatch):
    seen = []

    class Spy(builder.Builder):
        def build(self, changed=None):
            report = super().build(changed)
            seen.append((self.incremental, report.pages_rendered))
            return report

    monkeypatch.setattr(builder, "Builder", Spy)
    run("build")
    run("build")
    run("build", "--no-incremental")
    incremental, rendered = zip(*seen)
    assert incremental == (True, True, False)
    # the cache spares the second build the rendering, the flag does not
    assert rendered[1] == 0
    assert rendered[2] == rendered[0] > 0


def test_clean_flag_starts_from_nothing(run, site):
    run("build")
    stray = write(site / "public" / "stray.txt", "left behind")
    cache_marker = write(site / ".inkstone-cache" / "marker", "x")
    result = run("build", "--clean")
    assert result.code == 0
    assert not stray.exists() and not cache_marker.exists()
    assert not result.out.startswith("0 pages")
    assert (site / "public" / "index.html").is_file()


def test_profile_flag(run, site):
    result = run("build", "--profile")
    lines = result.out.splitlines()
    assert lines[1].split() == ["phase", "time", "share"]
    names = [line.split()[0] for line in lines[3:]]
    assert names[-1] == "total"
    assert {"load", "markdown", "templates", "write"} <= set(names)
    assert all("%" in line for line in lines[3:-1])
    # still there with --quiet: it was asked for
    assert "phase" in run("-q", "build", "--profile").out


def test_from_a_subdirectory(run, site, monkeypatch):
    monkeypatch.chdir(site / "content" / "posts")
    assert run("build").code == 0
    assert (site / "public" / "index.html").is_file()


def test_broken_front_matter_fails_with_file_and_line(run, site):
    write(site / "content" / "bad.md", "---\ntitle: [unclosed\n---\n\ntext\n")
    result = run("build")
    assert result.code == 1
    assert result.out == ""
    lines = result.err.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("error: content/bad.md:")


def test_unknown_shortcode_fails_with_file_and_line(run, site):
    write(site / "content" / "bad.md", "---\ntitle: Bad\n---\n\n{{< figrue src=x >}}\n")
    result = run("build")
    assert result.code == 1
    assert result.err == (
        "error: content/bad.md:5: unknown shortcode 'figrue', did you mean 'figure'?\n"
    )
    assert "Traceback" in run("build", "--debug").err


def test_missing_theme_is_a_plain_error(run, site):
    configure(site, replace={'theme = "default"': 'theme = "nope"'})
    result = run("build")
    assert result.code == 1
    assert "theme 'nope' not found" in result.err
    assert "Traceback" not in result.err


def test_config_warnings_are_shown_but_do_not_fail(run, site):
    configure(site, prepend="titel = 'typo'\n")
    result = run("build")
    assert result.code == 0
    assert "warning: inkstone.toml: unknown setting 'titel', did you mean 'title'?" in (
        result.err
    )
    assert "warning" in result.out


def test_environment_variables_reach_the_build(run, site, monkeypatch):
    monkeypatch.setenv("INKSTONE_TITLE", "From the environment")
    run("build")
    assert "From the environment" in read(site, "index.html")


def test_search_index_is_valid_json(run, site):
    run("build")
    assert json.loads(read(site, "search-index.json"))


def flags(**given):
    names = ("drafts", "future", "no_incremental", "minify", "fingerprint")
    values = {name: False for name in names}
    values.update(output=None, base_url=None)
    values.update(given)
    return argparse.Namespace(**values)


def test_flags_left_out_do_not_override_the_config():
    assert set(build_command.overrides(flags()).values()) == {None}


@pytest.mark.parametrize(
    "given, key, value",
    [
        ({"drafts": True}, "build.drafts", True),
        ({"future": True}, "build.future", True),
        ({"no_incremental": True}, "build.incremental", False),
        ({"minify": True}, "build.minify", True),
        ({"fingerprint": True}, "build.fingerprint", True),
        ({"base_url": "https://e.org/"}, "base_url", "https://e.org/"),
    ],
)
def test_each_flag_becomes_one_override(given, key, value):
    found = build_command.overrides(flags(**given))
    assert {k: v for k, v in found.items() if v is not None} == {key: value}


def test_output_override_is_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    found = build_command.overrides(flags(output="out"))
    assert Path(found["output_dir"]) == tmp_path.resolve() / "out"


def test_profile_table():
    table = build_command.profile({"load": 0.25, "render": 0.75})
    assert table.splitlines() == [
        "phase     time  share",
        "------  ------  -----",
        "load    250 ms    25%",
        "render  750 ms    75%",
        "total   1.00 s",
    ]
    assert build_command.profile({}).splitlines()[-1].split() == ["total", "0", "ms"]
