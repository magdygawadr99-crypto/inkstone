from __future__ import annotations

from types import SimpleNamespace

import pytest

from inkstone.cli import check as check_command

from .conftest import configure, write


@pytest.fixture(autouse=True)
def needs_builder(builder):
    """`inkstone check` builds the site before it looks at it."""


def page(site, name, body, front_matter=""):
    text = f"---\ntitle: {name.title()}\n{front_matter}---\n\n{body}\n"
    return write(site / "content" / f"{name}.md", text)


def test_a_fresh_site_has_no_problems(run, site):
    result = run("check")
    assert result.code == 0
    assert result.err == ""
    assert result.out.startswith("no problems found (")
    assert "links checked)" in result.out
    assert (site / "public" / "index.html").is_file()


def test_broken_link_fails(run, site):
    page(site, "links", "See [the manual](/manual/) for more.")
    result = run("check")
    assert result.code == 1
    lines = result.out.strip().splitlines()
    assert lines[-1] == "1 error, 0 warnings"
    assert len(lines) == 2
    assert lines[0].startswith("public/links/index.html:")
    assert lines[0].endswith(": broken-link: no such page or file (/manual/)")


def test_missing_image_fails(run, site):
    page(site, "pictures", "![A photo](/img/missing.png)")
    result = run("check")
    assert result.code == 1
    assert "missing-image: image not found (/img/missing.png)" in result.out


def test_each_problem_is_one_line_and_they_add_up(run, site):
    page(site, "many", "[a](/nope-a/) [b](/nope-b/) ![c](/nope-c.png) [d](#nowhere)")
    result = run("check")
    lines = result.out.strip().splitlines()
    assert lines[-1] == "3 errors, 1 warning"
    assert len(lines) == 5
    assert all(line.startswith("public/many/index.html:") for line in lines[:-1])


def test_warnings_alone_pass_unless_strict(run, site):
    page(site, "anchors", "Jump to [the end](#the-end).")
    result = run("check")
    assert result.code == 0
    assert "missing-anchor: nothing with id 'the-end' on this page" in result.out
    assert result.out.strip().endswith("0 errors, 1 warning")

    strict = run("check", "--strict")
    assert strict.code == 1
    assert strict.out == result.out


def test_strict_does_not_fail_a_clean_site(run, site):
    assert run("check", "--strict").code == 0


def test_aliases_without_the_redirects_plugin_are_a_warning(run, site):
    page(site, "moved", "Here now.", "aliases: [/old-home/]\n")
    result = run("check")
    assert result.code == 0
    assert "content/moved.md: orphan-alias:" in result.out
    assert "'redirects' plugin is not enabled" in result.out
    assert run("check", "--strict").code == 1


def test_front_matter_typos_are_reported_with_the_source_file(run, site):
    page(site, "typo", "Text.", "descripton: oops\n")
    result = run("check")
    assert result.code == 1
    assert (
        "content/typo.md:3: front-matter: unknown key 'descripton', "
        "did you mean 'description'?"
    ) in result.out


def test_pages_sharing_a_url(run, site):
    page(site, "one", "First.", "url: /same/\n")
    page(site, "two", "Second.", "url: /same/\n")
    result = run("check")
    assert result.code == 1
    assert "duplicate-url" in result.out
    # the build cannot go ahead with that, and says so too
    assert "the site does not build" in result.err


def test_a_file_that_cannot_be_parsed_does_not_hide_the_others(run, site):
    write(site / "content" / "broken.md", "---\ntitle: [unclosed\n---\n\nx\n")
    page(site, "typo", "Text.", "descripton: oops\n")
    result = run("check")
    assert result.code == 1
    assert "content/broken.md" in result.out
    assert "content/typo.md:3: front-matter" in result.out
    assert "error: the site does not build: content/broken.md" in result.err
    assert "Traceback" not in result.err


def test_source_problems_come_before_link_problems(run, site):
    page(site, "typo", "A [dead link](/dead/).", "descripton: oops\n")
    lines = run("check").out.strip().splitlines()
    assert lines[0].startswith("content/typo.md")
    assert lines[1].startswith("public/typo/index.html")
    assert lines[2] == "2 errors, 0 warnings"


def test_quiet_keeps_the_problems_and_drops_the_summary(run, site):
    page(site, "links", "See [the manual](/manual/).")
    result = run("-q", "check")
    assert result.code == 1
    assert result.out.count("\n") == 1 and "broken-link" in result.out
    clean = site / "content" / "links.md"
    clean.unlink()
    assert run("-q", "check").out == ""


def test_output_directory_name_follows_the_config(run, site):
    configure(site, prepend='output_dir = "dist"\n')
    page(site, "links", "See [the manual](/manual/).")
    assert run("check").out.startswith("dist/links/index.html:")


def test_external_links_are_only_fetched_when_asked(run, site, builder, monkeypatch):
    seen = []

    class Checker:
        checked = 7

        def __init__(self, output_dir, **options):
            seen.append((output_dir, options))

        def run(self):
            return []

    monkeypatch.setattr(builder, "LinkChecker", Checker)
    assert run("check").code == 0
    assert run("check", "--external").out == "no problems found (7 links checked)\n"
    (first_dir, first), (_second_dir, second) = seen
    assert first_dir == (site / "public").resolve()
    assert first["external"] is False and second["external"] is True
    assert first["base_url"] == "http://localhost:8000/"


def test_external_failures_are_warnings(run, site, builder, monkeypatch):
    from inkstone.content import Problem

    class Checker:
        def __init__(self, output_dir, **options):
            pass

        def run(self):
            return [
                Problem(
                    "external-link",
                    "index.html",
                    "HTTP 404",
                    target="https://gone.example/",
                    line=12,
                )
            ]

    monkeypatch.setattr(builder, "LinkChecker", Checker)
    result = run("check", "--external")
    assert result.code == 0
    assert result.out.splitlines() == [
        "public/index.html:12: external-link: HTTP 404 (https://gone.example/)",
        "0 errors, 1 warning",
    ]
    assert run("check", "--external", "--strict").code == 1


@pytest.mark.parametrize(
    "kind, warning",
    [
        ("broken-link", False),
        ("missing-image", False),
        ("duplicate-url", False),
        ("front-matter", False),
        ("bad-date", False),
        ("missing-anchor", True),
        ("external-link", True),
        ("missing-title", True),
        ("orphan-alias", True),
    ],
)
def test_which_kinds_are_warnings(kind, warning):
    assert check_command.is_warning(SimpleNamespace(kind=kind)) is warning


def test_a_severity_on_the_problem_wins():
    downgraded = SimpleNamespace(kind="broken-link", severity="warning")
    upgraded = SimpleNamespace(kind="missing-title", severity="error")
    assert check_command.is_warning(downgraded)
    assert not check_command.is_warning(upgraded)
