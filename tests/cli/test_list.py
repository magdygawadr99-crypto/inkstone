from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import write


def post(site, name, title, date, extra="", section="posts"):
    text = f"---\ntitle: {title}\ndate: {date}\n{extra}---\n\nSome words here.\n"
    return write(site / "content" / section / f"{name}.md", text)


@pytest.fixture
def content(site):
    post(site, "old", "Zebra crossing", "2023-01-15", "tags: [animals, roads]\n")
    post(site, "new", "Apple pie", "2024-06-01", "tags: [Food]\n")
    post(site, "draft", "Unfinished", "2024-07-01", "draft: true\ntags: [food]\n")
    post(site, "widget", "Widget", "2022-03-03", section="projects")
    post(site, "nested", "Deep one", "2021-01-01", section="projects/old")
    return site


def column(result, name):
    """One column of the table output, found by where its header starts."""
    lines = result.out.splitlines()
    if not lines:
        return []
    header = lines[0]
    start = header.index(name)
    rest = header[start + len(name) :].lstrip()
    end = header.index(rest, start + len(name)) if rest else None
    return [line[start:end].strip() for line in lines[2:]]


def titles(result):
    return column(result, "title")


def records(run, *argv):
    result = run("list", "--format", "json", *argv)
    assert result.code == 0
    return json.loads(result.out)


def test_table_lists_pages_newest_first(run, content):
    result = run("list")
    assert result.code == 0
    lines = result.out.splitlines()
    assert lines[0].split() == ["date", "title", "section", "url"]
    assert set(lines[1].replace(" ", "")) == {"-"}
    assert lines[2].split("  ")[0] == "2024-06-01"
    assert [line.split()[0] for line in lines[2:]] == [
        "2024-06-01",
        "2024-05-03",
        "2023-01-15",
        "2022-03-03",
        "2021-01-01",
        "-",
        "-",
    ]
    assert lines[2].rstrip().endswith("/2024/06/new/")
    assert "Unfinished" not in result.out
    assert result.err == "7 pages\n"


def test_columns_line_up(run, content):
    result = run("list")
    urls = column(result, "url")
    assert all(url.startswith("/") and url.endswith("/") for url in urls)
    assert column(result, "section") == [
        "posts",
        "posts",
        "posts",
        "projects",
        "projects/old",
        "-",
        "-",
    ]
    assert column(result, "date")[-1] == "-"


def test_drafts_flag(run, content):
    result = run("list", "--drafts")
    assert "Unfinished (draft)" in result.out
    assert result.err == "8 pages (1 draft)\n"
    assert result.out.splitlines()[2].startswith("2024-07-01")


def test_section_filter(run, content):
    assert titles(run("list", "--section", "posts")) == [
        "Apple pie",
        "First post",
        "Zebra crossing",
    ]
    # nested sections belong to their parents
    assert titles(run("list", "--section", "projects")) == ["Widget", "Deep one"]
    assert titles(run("list", "--section", "projects/old/")) == ["Deep one"]


def test_unknown_section_warns_and_lists_nothing(run, content):
    result = run("list", "--section", "post")
    assert result.code == 0
    assert result.out == ""
    assert "warning: no section called 'post', did you mean 'posts'?" in result.err
    assert result.err.endswith("0 pages\n")


def test_tag_filter_ignores_case(run, content):
    assert titles(run("list", "--tag", "food")) == ["Apple pie"]
    assert titles(run("list", "--tag", "FOOD", "--drafts")) == [
        "Unfinished (draft)",
        "Apple pie",
    ]
    assert titles(run("list", "--tag", "roads")) == ["Zebra crossing"]
    assert run("list", "--tag", "nothing").out == ""


def test_filters_combine(run, content):
    assert titles(run("list", "--section", "posts", "--tag", "meta")) == ["First post"]
    assert run("list", "--section", "projects", "--tag", "meta").out == ""


def test_sort_by_title(run, content):
    assert titles(run("list", "--sort", "title")) == [
        "About",
        "Apple pie",
        "Deep one",
        "First post",
        "Search",
        "Widget",
        "Zebra crossing",
    ]


def test_json_format(run, content):
    found = records(run)
    assert [record["title"] for record in found][:2] == ["Apple pie", "First post"]
    first = found[0]
    assert first == {
        "title": "Apple pie",
        "url": "/2024/06/new/",
        "date": "2024-06-01T00:00:00+00:00",
        "updated": None,
        "section": "posts",
        "tags": ["Food"],
        "draft": False,
        "source": "posts/new.md",
        "words": 3,
    }
    about = next(record for record in found if record["title"] == "About")
    assert about["date"] is None and about["section"] is None


def test_json_output_is_only_json(run, content):
    result = run("list", "--format", "json", "--tag", "nothing")
    assert json.loads(result.out) == []
    assert result.err == ""


def test_json_with_drafts(run, content):
    drafts = [record for record in records(run, "--drafts") if record["draft"]]
    assert [record["title"] for record in drafts] == ["Unfinished"]


def test_paths_format(run, content):
    result = run("list", "--format", "paths", "--section", "posts")
    assert result.err == ""
    assert [Path(line) for line in result.out.splitlines()] == [
        Path("content/posts/new.md"),
        Path("content/posts/2024-05-03-first-post.md"),
        Path("content/posts/old.md"),
    ]
    assert all((content / line).is_file() for line in result.out.splitlines())


def test_paths_are_relative_to_the_cwd(run, content, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("-C", "site", "list", "--format", "paths", "--tag", "food")
    assert Path(result.out.strip()) == Path("site/content/posts/new.md")
    monkeypatch.chdir(content / "content" / "posts")
    result = run("list", "--format", "paths", "--tag", "food")
    assert result.out == "new.md\n"


def test_long_titles_are_cut_in_the_table_only(run, site):
    title = "A very long title that goes on and on well past any sensible width"
    post(site, "long", title, "2024-06-01")
    line = run("list", "--section", "posts").out.splitlines()[2]
    assert title not in line and "…" in line
    assert records(run, "--section", "posts")[0]["title"] == title


def test_an_empty_site(run, tmp_path, monkeypatch):
    write(tmp_path / "inkstone.json", '{"title": "Empty"}')
    (tmp_path / "content").mkdir()
    monkeypatch.chdir(tmp_path)
    result = run("list")
    assert (result.code, result.out, result.err) == (0, "", "0 pages\n")
    assert json.loads(run("list", "--format", "json").out) == []


def test_quiet_drops_the_count(run, content):
    result = run("-q", "list", "--tag", "food")
    assert result.err == ""
    assert "Apple pie" in result.out


def test_listing_does_not_build_anything(run, content):
    run("list")
    assert not (content / "public").exists()
    assert not (content / ".inkstone-cache").exists()
