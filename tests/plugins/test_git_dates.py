from __future__ import annotations

import datetime as dt
import subprocess
from types import SimpleNamespace

import pytest

from inkstone.plugins.builtin import git_dates
from inkstone.plugins.builtin.git_dates import GitDates

from .helpers import day, make_config, make_page, make_site


class FakeGit:
    """Stands in for the git binary: answers from a made-up history.

    ``commits`` is newest first: (ISO date, [paths relative to the repository]).
    """

    def __init__(self, top, commits, tracked=None, merged=None):
        self.top = top
        self.commits = commits
        self.tracked = tracked
        # files whose history only `git log -1 -- file` knows
        self.merged = merged or {}
        self.calls = []

    def __call__(self, command, **kwargs):
        assert command[:3] == ["git", "-c", "core.quotepath=off"]
        assert kwargs["cwd"]
        args = command[3:]
        self.calls.append(args)
        if args[0] == "rev-parse":
            return self.answer(str(self.top).replace("\\", "/") + "\n")
        if args[0] == "ls-files":
            tracked = self.tracked
            if tracked is None:
                tracked = sorted({p for _date, paths in self.commits for p in paths})
            return self.answer("".join(name + "\n" for name in tracked))
        if args[:2] == ["log", "-1"]:
            assert args[2:4] == ["--format=%cI", "--"]
            rel = str(args[4]).replace("\\", "/").split("/content/", 1)[-1]
            return self.answer(self.merged.get("content/" + rel, ""))
        if args[0] == "log":
            out = ""
            for date, paths in self.commits:
                out += "\x00" + date + "\n\n" + "".join(p + "\n" for p in paths)
            return self.answer(out)
        raise AssertionError(f"unexpected git call: {args}")

    @staticmethod
    def answer(stdout, returncode=0):
        return SimpleNamespace(stdout=stdout, returncode=returncode)

    def count(self, *start):
        return sum(1 for call in self.calls if call[: len(start)] == list(start))


SOURCE = "content/posts/%s.md"


def post(config, name, date=None, **attrs):
    path = config.content_path / "posts" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    return make_page(
        name, source_path=f"posts/{name}.md", file_path=path, date=date, **attrs
    )


def load(config, pages, git, monkeypatch):
    monkeypatch.setattr(git_dates.subprocess, "run", git)
    plugin = GitDates(config, {})
    plugin.content_loaded(make_site(config, pages))
    return plugin


def test_updated_comes_from_the_last_commit(config, monkeypatch):
    page = post(config, "edited", day(2024, 5, 3))
    git = FakeGit(
        config.root,
        [
            ("2024-07-01T10:30:00+02:00", ["content/posts/edited.md", "README.md"]),
            ("2024-05-03T09:00:00+02:00", ["content/posts/edited.md"]),
        ],
    )
    load(config, [page], git, monkeypatch)
    assert page.updated == dt.datetime(2024, 7, 1, 8, 30, tzinfo=dt.timezone.utc)
    assert page.updated.tzinfo is not None


def test_one_pass_over_the_log_serves_every_page(config, monkeypatch):
    pages = [post(config, f"p{n}", day(2024, 1, 1)) for n in range(25)]
    commits = [
        (f"2024-03-0{n % 9 + 1}T12:00:00+00:00", [f"content/posts/p{n}.md"])
        for n in range(25)
    ]
    git = FakeGit(config.root, commits)
    load(config, pages, git, monkeypatch)
    assert all(page.updated is not None for page in pages)
    assert len(git.calls) == 3
    assert git.count("log", "-1") == 0


def test_front_matter_updated_is_never_overwritten(config, monkeypatch):
    stamp = day(2024, 6, 6)
    page = post(config, "manual", day(2024, 5, 3), updated=stamp, meta={"updated": "x"})
    git = FakeGit(config.root, [("2024-09-09T00:00:00+00:00", [SOURCE % "manual"])])
    load(config, [page], git, monkeypatch)
    assert page.updated == stamp
    # nothing to look up, so git is not even started
    assert git.calls == []


def test_a_commit_on_the_day_of_writing_is_not_an_update(config, monkeypatch):
    same_day = post(config, "same", day(2024, 5, 3))
    later = post(config, "later", day(2024, 5, 3))
    git = FakeGit(
        config.root,
        [
            ("2024-05-04T00:10:00+00:00", ["content/posts/later.md"]),
            ("2024-05-03T23:50:00+00:00", ["content/posts/same.md"]),
        ],
    )
    load(config, [same_day, later], git, monkeypatch)
    assert same_day.updated is None
    assert later.updated == day(2024, 5, 4).replace(minute=10)


def test_the_day_is_judged_in_the_pages_own_time_zone(config, monkeypatch):
    plus_two = dt.timezone(dt.timedelta(hours=2))
    page = post(config, "late", dt.datetime(2024, 5, 3, tzinfo=plus_two))
    # 23:30 UTC on the 3rd is already the 4th at +02:00
    git = FakeGit(config.root, [("2024-05-03T23:30:00+00:00", [SOURCE % "late"])])
    load(config, [page], git, monkeypatch)
    assert page.updated is not None


def test_undated_pages_get_the_commit_date(config, monkeypatch):
    page = post(config, "undated")
    git = FakeGit(config.root, [("2024-02-02T12:00:00+00:00", [SOURCE % "undated"])])
    load(config, [page], git, monkeypatch)
    assert page.updated == day(2024, 2, 2, 12)


def test_dates_are_shown_in_the_sites_time_zone(tmp_path, monkeypatch):
    config = make_config(tmp_path, timezone="+05:00")
    page = post(config, "zoned")
    git = FakeGit(config.root, [("2024-02-02T12:00:00+00:00", [SOURCE % "zoned"])])
    load(config, [page], git, monkeypatch)
    assert page.updated.utcoffset() == dt.timedelta(hours=5)
    assert page.updated.hour == 17


def test_files_git_does_not_know_are_skipped_without_asking(config, monkeypatch):
    new = post(config, "brand-new", day(2024, 5, 3))
    old = post(config, "old", day(2024, 1, 1))
    git = FakeGit(config.root, [("2024-03-03T00:00:00+00:00", [SOURCE % "old"])])
    load(config, [new, old], git, monkeypatch)
    assert new.updated is None and old.updated is not None
    assert git.count("log", "-1") == 0


def test_tracked_files_missing_from_the_log_are_asked_about(config, monkeypatch):
    page = post(config, "merged", day(2024, 1, 1))
    git = FakeGit(
        config.root,
        commits=[],
        tracked=["content/posts/merged.md"],
        merged={"content/posts/merged.md": "2024-04-04T04:00:00+00:00\n"},
    )
    plugin = load(config, [page], git, monkeypatch)
    assert page.updated == day(2024, 4, 4, 4)
    assert git.count("log", "-1") == 1
    # and the answer is remembered
    plugin.last_commit(page.file_path)
    assert git.count("log", "-1") == 1


def test_generated_pages_are_ignored(config, monkeypatch):
    virtual = make_page("Generated", "/generated/")
    git = FakeGit(config.root, [])
    load(config, [virtual], git, monkeypatch)
    assert virtual.updated is None
    assert git.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("git"),
        PermissionError("git"),
        subprocess.TimeoutExpired("git", 20),
    ],
)
def test_silent_without_git(config, monkeypatch, capsys, failure):
    def broken(command, **kwargs):
        raise failure

    page = post(config, "p", day(2024, 1, 1))
    load(config, [page], broken, monkeypatch)
    assert page.updated is None
    assert capsys.readouterr().err == ""


def test_silent_outside_a_repository(config, monkeypatch, capsys):
    def not_a_repo(command, **kwargs):
        return SimpleNamespace(stdout="", returncode=128)

    page = post(config, "p", day(2024, 1, 1))
    plugin = load(config, [page], not_a_repo, monkeypatch)
    assert page.updated is None
    assert plugin.last_commit(page.file_path) is None
    assert capsys.readouterr().err == ""


def test_paths_outside_the_repository_have_no_date(config, monkeypatch, tmp_path):
    # the repository is the site's content directory only
    elsewhere = tmp_path / "notes.md"
    elsewhere.write_text("x", encoding="utf-8")
    git = FakeGit(config.content_path, [])
    plugin = load(config, [post(config, "p", day(2024, 1, 1))], git, monkeypatch)
    assert plugin.last_commit(elsewhere) is None


def test_every_build_reads_the_history_again(config, monkeypatch):
    page = post(config, "p", day(2024, 1, 1))
    git = FakeGit(config.root, [("2024-02-02T00:00:00+00:00", ["content/posts/p.md"])])
    plugin = load(config, [page], git, monkeypatch)
    assert page.updated == day(2024, 2, 2)

    page.updated = None
    git.commits.insert(0, ("2024-03-03T00:00:00+00:00", ["content/posts/p.md"]))
    plugin.content_loaded(make_site(config, [page]))
    assert page.updated == day(2024, 3, 3)


def test_garbage_from_git_is_ignored(config, monkeypatch):
    page = post(config, "p", day(2024, 1, 1))
    git = FakeGit(config.root, [("not a date", ["content/posts/p.md"])])
    load(config, [page], git, monkeypatch)
    assert page.updated is None
