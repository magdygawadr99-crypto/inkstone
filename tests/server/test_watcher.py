from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from inkstone.server import DEFAULT_IGNORE, ChangeSet, Watcher

from .helpers import wait_for


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "src"
    (root / "posts").mkdir(parents=True)
    (root / "posts" / "hello.md").write_bytes(b"hello")
    (root / "style.css").write_bytes(b"body {}")
    return root


@pytest.fixture
def watching(tree):
    """A running watcher and the list its batches end up in."""
    batches = []
    watcher = Watcher([tree], callback=batches.append, debounce=0.3, poll_interval=0.02)
    watcher.start()
    yield watcher, batches
    watcher.stop()


def test_first_scan_is_only_a_baseline(tree):
    watcher = Watcher([tree])
    assert watcher.scan() == ChangeSet()
    assert not watcher.scan()


def test_scan_reports_added_modified_and_removed(tree):
    watcher = Watcher([tree])
    watcher.scan()
    (tree / "new.md").write_bytes(b"new")
    (tree / "style.css").write_bytes(b"body { margin: 0 }")
    (tree / "posts" / "hello.md").unlink()

    changes = watcher.scan()
    assert changes.added == [tree / "new.md"]
    assert changes.modified == [tree / "style.css"]
    assert changes.removed == [tree / "posts" / "hello.md"]
    assert not watcher.scan()


def test_edit_that_keeps_the_size_is_caught_by_its_mtime(tree):
    watcher = Watcher([tree])
    watcher.scan()
    target = tree / "style.css"
    before = target.stat()
    target.write_bytes(b"main {}")
    # don't count on the clock having moved between the two writes
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
    assert watcher.scan().modified == [target]


def test_new_directories_are_picked_up(tree):
    watcher = Watcher([tree])
    watcher.scan()
    (tree / "drafts" / "2024").mkdir(parents=True)
    (tree / "drafts" / "2024" / "idea.md").write_bytes(b"...")
    assert watcher.scan().added == [tree / "drafts" / "2024" / "idea.md"]


def test_removing_a_directory_reports_its_files(tree):
    watcher = Watcher([tree])
    watcher.scan()
    shutil.rmtree(tree / "posts")
    assert watcher.scan().removed == [tree / "posts" / "hello.md"]


def test_watching_a_single_file(tmp_path):
    config = tmp_path / "site.toml"
    config.write_bytes(b"title = 'a'")
    (tmp_path / "unrelated.txt").write_bytes(b"x")
    watcher = Watcher([config])
    watcher.scan()
    config.write_bytes(b"title = 'a longer title'")
    (tmp_path / "unrelated.txt").write_bytes(b"something else entirely")
    assert watcher.scan() == ChangeSet(modified=[config])


def test_watch_root_that_shows_up_later(tmp_path):
    root = tmp_path / "content"
    watcher = Watcher([root])
    assert not watcher.scan()
    root.mkdir()
    (root / "first.md").write_bytes(b"x")
    assert watcher.scan().added == [root / "first.md"]


def test_overlapping_roots_report_a_file_once(tree):
    watcher = Watcher([tree, tree / "posts", tree / "posts" / "hello.md"])
    watcher.scan()
    (tree / "posts" / "hello.md").write_bytes(b"hello again")
    assert watcher.scan() == ChangeSet(modified=[tree / "posts" / "hello.md"])


def test_relative_watch_paths_are_made_absolute(tree, monkeypatch):
    monkeypatch.chdir(tree.parent)
    watcher = Watcher(["src"])
    watcher.scan()
    (tree / "new.md").write_bytes(b"x")
    assert watcher.scan().added == [tree / "new.md"]


@pytest.mark.parametrize(
    ("pattern", "ignored"),
    [
        ("*.swp", {"a.swp", "posts/b.swp"}),
        ("posts/", {"posts/hello.md", "posts/b.swp", "posts/drafts/wip.md"}),
        ("drafts/", {"posts/drafts/wip.md"}),
        ("drafts", {"posts/drafts/wip.md"}),
        ("/a.swp", {"a.swp"}),
        ("/b.swp", set()),
        ("posts/*.md", {"posts/hello.md"}),
        ("posts/**", {"posts/hello.md", "posts/b.swp", "posts/drafts/wip.md"}),
        ("**/*.md", {"readme.md", "posts/hello.md", "posts/drafts/wip.md"}),
        ("posts/**/wip.md", {"posts/drafts/wip.md"}),
        ("wip.??", {"posts/drafts/wip.md"}),
        ("[ab].swp", {"a.swp", "posts/b.swp"}),
        ("[!a].swp", {"posts/b.swp"}),
        ("read[me.md", set()),
        ("hello.md/", set()),
        ("POSTS/", set()),
        ("  ", set()),
    ],
)
def test_ignore_patterns(tmp_path, pattern, ignored):
    files = {
        "a.swp",
        "readme.md",
        "posts/hello.md",
        "posts/b.swp",
        "posts/drafts/wip.md",
    }
    root = tmp_path / "src"
    root.mkdir()
    watcher = Watcher([root], ignore=[pattern])
    watcher.scan()
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"x")
    seen = {path.relative_to(root).as_posix() for path in watcher.scan().added}
    assert seen == files - ignored


def test_backslashes_in_patterns_work_on_windows(tree):
    if os.sep != "\\":
        pytest.skip("backslash is an ordinary character here")
    watcher = Watcher([tree], ignore=["posts\\*.md"])
    watcher.scan()
    (tree / "posts" / "second.md").write_bytes(b"x")
    assert not watcher.scan()


def test_default_ignores_cover_the_usual_clutter(tree):
    watcher = Watcher([tree], ignore=DEFAULT_IGNORE)
    watcher.scan()
    clutter = [
        ".git/HEAD",
        ".git/objects/ab/cdef",
        "__pycache__/build.cpython-312.pyc",
        "posts/.hello.md.swp",
        "posts/hello.md~",
        "posts/.#hello.md",
        "posts/#hello.md#",
        "posts/4913",
        ".DS_Store",
    ]
    for name in [*clutter, "posts/real.md"]:
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_bytes(b"x")
    assert watcher.scan() == ChangeSet(added=[tree / "posts" / "real.md"])


def test_ignored_single_file_root(tmp_path):
    swap = tmp_path / "notes.swp"
    watcher = Watcher([swap], ignore=["*.swp"])
    watcher.scan()
    swap.write_bytes(b"x")
    assert not watcher.scan()


def test_excluded_directory_is_skipped(tree):
    output = tree / "_site"
    watcher = Watcher([tree], exclude=[output])
    watcher.scan()
    output.mkdir()
    (output / "index.html").write_bytes(b"<p>built</p>")
    (tree / "posts" / "new.md").write_bytes(b"x")
    assert watcher.scan() == ChangeSet(added=[tree / "posts" / "new.md"])


def test_symlinked_directories_are_followed_without_looping(tree, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "logo.svg").write_bytes(b"<svg/>")
    try:
        os.symlink(shared, tree / "assets", target_is_directory=True)
        os.symlink(tree, tree / "posts" / "up", target_is_directory=True)
    except OSError:
        pytest.skip("can't create symlinks here")
    watcher = Watcher([tree])
    watcher.scan()
    (shared / "logo.svg").write_bytes(b"<svg></svg>")
    assert tree / "assets" / "logo.svg" in watcher.scan().modified


def test_changeset_normalises_what_it_is_given():
    changes = ChangeSet(added=["b.md", "a.md"], removed={Path("z.md")})
    assert changes.added == [Path("a.md"), Path("b.md")]
    assert changes.modified == []
    assert changes.removed == [Path("z.md")]
    assert changes.paths == [Path("a.md"), Path("b.md"), Path("z.md")]
    assert len(changes) == 3
    assert changes


def test_empty_changeset_is_falsy():
    assert not ChangeSet()
    assert len(ChangeSet()) == 0
    assert ChangeSet().summary() == "no changes"


@pytest.mark.parametrize(
    ("changes", "summary"),
    [
        (ChangeSet(added=["a"]), "1 added"),
        (ChangeSet(added=["a"], modified=["b", "c"]), "1 added, 2 modified"),
        (ChangeSet(modified=["a"], removed=["b"]), "1 modified, 1 removed"),
    ],
)
def test_changeset_summary(changes, summary):
    assert changes.summary() == summary


@pytest.mark.parametrize(
    ("first", "later", "merged"),
    [
        (ChangeSet(added=["a"]), ChangeSet(modified=["a"]), ChangeSet(added=["a"])),
        (ChangeSet(added=["a"]), ChangeSet(removed=["a"]), ChangeSet()),
        (ChangeSet(modified=["a"]), ChangeSet(removed=["a"]), ChangeSet(removed=["a"])),
        (ChangeSet(removed=["a"]), ChangeSet(added=["a"]), ChangeSet(modified=["a"])),
        (
            ChangeSet(modified=["a"]),
            ChangeSet(modified=["a"]),
            ChangeSet(modified=["a"]),
        ),
        (ChangeSet(), ChangeSet(removed=["a"]), ChangeSet(removed=["a"])),
        (ChangeSet(added=["a"]), ChangeSet(), ChangeSet(added=["a"])),
        (
            ChangeSet(added=["a"], removed=["x"]),
            ChangeSet(added=["b"], modified=["c"]),
            ChangeSet(added=["a", "b"], modified=["c"], removed=["x"]),
        ),
    ],
    ids=[
        "added-then-modified",
        "added-then-removed",
        "modified-then-removed",
        "removed-then-added",
        "modified-twice",
        "nothing-then-removed",
        "added-then-nothing",
        "unrelated",
    ],
)
def test_changeset_merge(first, later, merged):
    assert first.merge(later) == merged


def test_merge_leaves_its_operands_alone():
    first, later = ChangeSet(added=["a"]), ChangeSet(removed=["a"])
    first.merge(later)
    assert first == ChangeSet(added=["a"])
    assert later == ChangeSet(removed=["a"])


def test_tick_holds_changes_until_things_go_quiet(tree):
    watcher = Watcher([tree], debounce=1.0)
    assert watcher.tick(now=0.0) is None
    (tree / "a.md").write_bytes(b"a")
    assert watcher.tick(now=10.0) is None
    (tree / "b.md").write_bytes(b"b")
    assert watcher.tick(now=10.6) is None
    # only 0.6s since b.md appeared, though more than a second since a.md did
    assert watcher.tick(now=11.2) is None
    batch = watcher.tick(now=11.7)
    assert batch == ChangeSet(added=[tree / "a.md", tree / "b.md"])
    assert watcher.tick(now=30.0) is None


def test_tick_without_debounce_reports_right_away(tree):
    watcher = Watcher([tree], debounce=0)
    watcher.tick(now=0.0)
    (tree / "a.md").write_bytes(b"a")
    assert watcher.tick(now=0.0) == ChangeSet(added=[tree / "a.md"])


def test_file_that_comes_and_goes_within_the_window_is_never_reported(tree):
    watcher = Watcher([tree], debounce=1.0)
    watcher.tick(now=0.0)
    (tree / "upload.tmp").write_bytes(b"partial")
    assert watcher.tick(now=1.0) is None
    (tree / "upload.tmp").unlink()
    assert watcher.tick(now=1.2) is None
    assert watcher.tick(now=60.0) is None


def test_constant_churn_is_flushed_eventually(tree):
    watcher = Watcher([tree], debounce=1.0)
    watcher.tick(now=0.0)
    log = tree / "build.log"
    batch = None
    # a write every half second never lets the debounce window close
    for step in range(12):
        log.write_bytes(b"x" * (step + 1))
        batch = watcher.tick(now=100.0 + step * 0.5)
        if batch:
            break
    assert batch == ChangeSet(added=[log])
    assert 1 < step < 11


def test_thread_reports_changes(tree, watching):
    watcher, batches = watching
    assert watcher.running
    (tree / "new.md").write_bytes(b"x")
    assert wait_for(lambda: batches)
    assert batches[0] == ChangeSet(added=[tree / "new.md"])


def test_burst_of_saves_comes_out_as_one_batch(tree, watching):
    watcher, batches = watching
    names = [f"post-{n}.md" for n in range(8)]
    for name in names:
        (tree / name).write_bytes(b"x")
    (tree / "style.css").write_bytes(b"body { margin: 0 }")
    (tree / "posts" / "hello.md").unlink()

    assert wait_for(lambda: batches)
    watcher.stop()
    # everything is in the first batch, so there was nothing left for a second
    assert len(batches) == 1
    assert batches[0].added == [tree / name for name in names]
    assert batches[0].modified == [tree / "style.css"]
    assert batches[0].removed == [tree / "posts" / "hello.md"]


def test_change_made_right_after_start_is_not_missed(tree):
    batches = []
    with Watcher([tree], callback=batches.append, debounce=0.02, poll_interval=0.02):
        (tree / "immediately.md").write_bytes(b"x")
        assert wait_for(lambda: batches)
    assert batches[0].added == [tree / "immediately.md"]


def test_stop_does_not_wait_for_the_poll_interval(tree):
    watcher = Watcher([tree], poll_interval=60)
    watcher.start()
    assert watcher.running
    started = time.monotonic()
    watcher.stop()
    assert time.monotonic() - started < 5
    assert not watcher.running
    watcher.stop()


def test_restarted_watcher_reports_what_happened_in_between(tree):
    batches = []
    watcher = Watcher([tree], callback=batches.append, debounce=0, poll_interval=0.02)
    watcher.start()
    watcher.start()
    watcher.stop()
    (tree / "while-stopped.md").write_bytes(b"x")
    watcher.start()
    try:
        assert wait_for(lambda: batches)
    finally:
        watcher.stop()
    assert batches == [ChangeSet(added=[tree / "while-stopped.md"])]


def test_failing_callback_does_not_end_the_watching(tree, capsys):
    batches = []

    def callback(batch):
        batches.append(batch)
        if len(batches) == 1:
            raise RuntimeError("callback exploded")

    with Watcher([tree], callback=callback, debounce=0.02, poll_interval=0.02):
        (tree / "one.md").write_bytes(b"1")
        assert wait_for(lambda: len(batches) == 1)
        (tree / "two.md").write_bytes(b"2")
        assert wait_for(lambda: len(batches) == 2)
    assert "callback exploded" in capsys.readouterr().err
